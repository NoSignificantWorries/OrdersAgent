import json
import logging
import time
from io import BytesIO
from pathlib import Path
from typing import Dict, List

# from  import LLM, decide_by_thresholds
from classify import FeaturesExtractor, RFModel, decide_by_thresholds
from cloud import MinIOClient, get_bytes_object, put_bytes_object
from database import (
    DatabaseManager,
    DocumentRepository,
    EmailRepository,
    MappingRepository,
    TaskRepository,
    init_database,
)
from database.models import TaskStatus
from materials import DELIMETERS, ParseResults, ParserV2
from table import TableParseResults, TableWorker, make_xlsx

POLL_INTERVAL = 30
BUSY_INTERVAL = 5
# IDLE_INTERVAL = 120
IDLE_INTERVAL = 30
BATCH_SIZE = 10
MODEL_PATH = "classify/model.joblib"
# MODEL_PATH = Path("model_out/final_lora")
ATTACHMENTS_BUCKET = "orders-attachments"
RESULTS_BUCKET = "results"

logger = logging.getLogger("mail_processor")


def process_new(
    task, email_repo, task_repo, doc_repo, material_repo, cloud, classify_worker
) -> None:
    email = email_repo.get_by_id(task.email_id)
    if email is None:
        task_repo.mark_error(task.id, "Email not found")
        return

    documents = doc_repo.get_by_email_id(task.email_id)
    file_names = [doc.filename for doc in documents if doc.filename]
    files = "\n".join(file_names).strip() if file_names else None

    parts = [email.email_subject or "", email.raw_email or "", files or ""]
    text = "\n\n".join(part for part in parts if part).strip()

    features = FeaturesExtractor.extract_text_features(text)
    files_features = FeaturesExtractor.extract_files_features(file_names)
    features.update(files_features)

    # prob_1 = llm_worker.predict_prob_1(text)
    pred_labels, pred_indexes, pred_proba = classify_worker.predict([features])
    model_decision, predicted_class, new_status, proba = decide_by_thresholds(
        pred_labels, pred_indexes, pred_proba
    )[0]
    logger.info(
        f"Task {task.id}: prob={proba:.3f} decision={model_decision} class={predicted_class} status={new_status}"
    )

    email_repo.set_ml_result(email.id, proba, predicted_class, model_decision)

    if predicted_class is None:
        task_status = "ml_review"
    else:
        task_status = "ml_classified"
    task_repo.update_status(task.id, task_status)


def process_classified_excel(
    task, email_repo, task_repo, doc_repo, material_repo, cloud, classify_worker
):
    documents = doc_repo.get_by_email_id(task.email_id)
    if not bool(documents):
        task_repo.update_status(task.id, "error")
        logger.info(f"Task {task.id}: No attachments")
        task_repo.mark_error(
            task.id,
            "Нет вложений для анализа",
        )
        return
    docnames = [doc.filename for doc in documents]
    logger.info(f"Task {task.id}: Processing documents: {', '.join(docnames)}")
    unique_materials_dict = {}
    unique_parts = set()
    questions = set()
    at_leat_one_file_saved = False
    file_errors = {}
    for doc in documents:
        filename = doc.minio_object_key
        file_data = get_bytes_object(cloud, ATTACHMENTS_BUCKET, filename)
        if file_data is None:
            logger.error(f"Task {task.id}: Can't open file {filename}")
            file_errors[filename] = "Ошибка доступа к файлу"
            continue

        # opening table
        try:
            worker = TableWorker(file_data, Path(filename))
            worker.open_and_clean()
        except Exception as err:
            logger.exception(
                f"Task {task.id}: File '{filename}' not opened succesfully: {err}"
            )
            file_errors[filename] = (
                "Ошибка при открытии файла (формат не xls/xlsx или файл повреждён)"
            )
            continue
        if worker.tables is None or not bool(worker.tables):
            logger.error(f"Task {task.id}: Unexpected errors with the file {filename}")
            file_errors[filename] = "Ошибка чтения файла (файл повреждён или пустой)"
            # task_repo.update_status(task.id, "error")
            continue

        # parsing simple strategy
        try:
            res = worker.simple_parser()
        except Exception:
            logger.exception(
                f"Task {task.id}: Can't apply simple parser for file '{filename}'"
            )
            file_errors[filename] = "Невозможно применить парсер."
            continue

        # finding unique materials
        unique_materials = set()
        for table in res:
            if table.empty:
                continue
            unique_materials |= set(table.material)
        unique_materials = list(unique_materials)

        # parsing materials (finding unique parts)
        parser = ParserV2(DELIMETERS)
        for material in unique_materials:
            parse_results = parser.parse(material)
            unique_materials_dict[material] = parse_results
            unique_parts |= set(parse_results.parts)
        # unique_parts = list(unique_parts)

        # searching materials
        if task.manual_decision is not None:
            matches = {p: (m, False) for p, (m, bl) in task.manual_decision.items()}
        else:
            matches = material_repo.batch_find(unique_parts)
        local_questions = set()
        for part, mat_match in matches.items():
            if mat_match is None:
                local_questions.add((part, False))
                continue
            _, bl = mat_match
            if bl:
                local_questions.add((part, True))

        if bool(local_questions):
            # task_repo.update_status(task.id, "materials_review", output_data=questions)
            logger.info(
                f"Task {task.id}: Needs manual matching for material parts for file {filename}"
            )
            questions |= local_questions
            continue

        for material, material_obj in unique_materials_dict.items():
            for part in material_obj.parts:
                material_obj.matches.append(matches[part][0])

        try:
            wb = make_xlsx(res, unique_materials_dict)
        except Exception as err:
            logger.exception(
                f"Task {task.id}: Unexpected errors while saving file '{filename}' in workbook: {err}"
            )
            file_errors[filename] = (
                "Внутренняя ошибка при сохранении файла. Пожалуйста, сообщите разработчикам."
            )
            continue

        if wb is None:
            # task_repo.update_status(task.id, "error")
            logger.warning(f"Task {task.id}: Empty output file")
            file_errors[filename] = "Пустой выходной файл."
            continue

        data = BytesIO()
        wb.save(data)
        data.seek(0)

        err = put_bytes_object(
            cloud,
            RESULTS_BUCKET,
            filename,
            data,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        if err:
            logger.error(f"Task {task.id}: Can't save file, retrying...")
            continue
        at_leat_one_file_saved = True

    if questions:
        questions = [{p: bl} for p, bl in questions]
        task_repo.update_status(task.id, "materials_review", output_data=questions)
        logger.info(
            f"Task {task.id}: Needs manual matching for material parts: f{questions}"
        )
        return
    if at_leat_one_file_saved:
        task_repo.update_status(task.id, "completed")
        logger.info(f"Task {task.id}: Succesfully parsed files")
    else:
        task_repo.update_status(task.id, "error")
        logger.info(f"Task {task.id}: No saved files")
        errors = [f"- {fn}: {err}" for fn, err in file_errors.items()]
        task_repo.mark_error(
            task.id,
            "Парсинг всех доступных фалов завершился с ошибкой.\n" + "\n".join(errors),
        )


def process_manual_matching(
    task, email_repo, task_repo, doc_repo, material_repo, cloud, classify_worker
):
    answers = task.manual_decision
    if answers is None:
        task_repo.update_status(task.id, "error")
        logger.info(f"Task {task.id}: Empty answers")
        task_repo.mark_error(
            task.id,
            "Не обнаружено ввода от пользователя.",
        )
        return
    answers_flat = [(part, data[0], data[1]) for part, data in answers.items()]
    try:
        material_repo.batch_add(answers_flat)
    except Exception as err:
        logger.exception(
            f"Task {task.id}: Error while adding materials in the base: {err}"
        )
        return

    task_repo.update_status(task.id, "ml_classified")


HANDLERS = {
    TaskStatus.NEW.value: process_new,
    TaskStatus.ML_CLASSIFIED.value: process_classified_excel,
    TaskStatus.MANUAL_REVIEW_DONE.value: process_manual_matching,
}


def process_single_task(task, **deps) -> None:
    handler = HANDLERS.get(task.status)
    if handler is None:
        logger.warning(f"Task {task.id}: no handler for '{task.status}'")
        return
    try:
        handler(task, **deps)
    except Exception as err:
        logger.exception(f"Task {task.id} failed: {err}")
        deps["task_repo"].mark_error(
            task.id, "Внутренняя ошибка сервера. Пожалуйста, сообщите разработчикам."
        )


def main_loop(
    email_repo, task_repo, doc_repo, material_repo, cloud, classify_worker
) -> None:
    logging.info("Starting main loop")

    while True:
        try:
            while True:
                pending = task_repo.fetch_pending(limit=BATCH_SIZE)
                if not pending:
                    break

                logging.info(f"Processing {len(pending)} tasks")
                for task in pending:
                    try:
                        process_single_task(
                            task,
                            email_repo=email_repo,
                            task_repo=task_repo,
                            doc_repo=doc_repo,
                            material_repo=material_repo,
                            cloud=cloud,
                            classify_worker=classify_worker,
                        )
                    except Exception as err:
                        task_repo.update_status(task.id, "error")
                        logger.exception(f"Task {task.id}: Error on task: {err}")
                        task_repo.mark_error(
                            task.id,
                            "Внутренняя ошибка сервера. Пожалуйста, сообщите разработчикам.",
                        )

            if task_repo.has_manual():
                interval = BUSY_INTERVAL
            else:
                interval = IDLE_INTERVAL

            logging.debug(f"Sleeping {interval}s")
            time.sleep(interval)

        except KeyboardInterrupt:
            logging.info("Keyboard interruption")
            break
        except Exception as err:
            logging.error(f"Main loop error: {err}")
            time.sleep(POLL_INTERVAL)


def main() -> None:
    init_database(pool_size=5)

    email_repo = EmailRepository()
    task_repo = TaskRepository()
    doc_repo = DocumentRepository()
    material_repo = MappingRepository()
    cloud = MinIOClient.get_client()
    # llm_worker = LLM(MODEL_PATH)
    classify_worker = RFModel()
    classify_worker.load(MODEL_PATH)

    try:
        main_loop(
            email_repo=email_repo,
            task_repo=task_repo,
            doc_repo=doc_repo,
            material_repo=material_repo,
            cloud=cloud,
            classify_worker=classify_worker,
        )
    finally:
        DatabaseManager.close()


def development() -> None:
    init_database()
    cloud = MinIOClient.get_client()

    # testfile = Path("../private/tables/1108A.xls")
    # filename = "033/1108A.xls"
    filename = "1/90/1_05.03_Заявка_(Триплекс).xlsx"

    file_data = get_bytes_object(cloud, ATTACHMENTS_BUCKET, filename)
    print(file_data)

    # worker = TableWorker(None, testfile)
    worker = TableWorker(file_data, Path(filename))
    worker.open_and_clean()
    if worker.tables is None or not bool(worker.tables):
        print("Errors with table")

    res = worker.simple_parser()
    print(res)

    unique_materials = set()
    for table in res:
        if table.empty:
            continue
        unique_materials |= set(table.material)
    unique_materials = list(unique_materials)
    print(unique_materials)

    parser = ParserV2(DELIMETERS)
    unique_materials_dict = {}
    unique_parts = set()
    for material in unique_materials:
        parse_results = parser.parse(material)
        unique_materials_dict[material] = parse_results
        unique_parts |= set(parse_results.parts)
    unique_parts = list(unique_parts)

    print(unique_materials_dict)
    print(unique_parts)

    material_repo = MappingRepository()
    matches = material_repo.batch_find(unique_parts)
    print(matches)
    questions = []
    for part, mat_match in matches.items():
        if mat_match is None:
            questions.append({part: False})
            continue
        _, bl = mat_match
        if bl:
            questions.append({part: True})
            continue
    print(questions)

    if questions:
        answers = {"4HPBronze20": ("Bronze20", False), "14": ("14Mr", False)}

        answers_flat = [(part, data[0], data[1]) for part, data in answers.items()]

        material_repo.batch_add(answers_flat)

        matches = material_repo.batch_find(unique_parts)

    print(matches)

    for material, material_obj in unique_materials_dict.items():
        for part in material_obj.parts:
            material_obj.matches.append(matches[part][0])
    print(unique_materials_dict)

    wb = make_xlsx(res, unique_materials_dict)
    print(wb)

    if wb is None:
        print("Empty file")
        return

    data = BytesIO()
    wb.save(data)
    data.seek(0)

    err = put_bytes_object(
        cloud,
        RESULTS_BUCKET,
        filename,
        data,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    print(err)

    DatabaseManager.close()


def dev_llm():
    model_path = Path("model_out/final_lora")

    # llm_worker = LLM(model_path)
    classify_worker = RFModel()
    classify_worker.load(MODEL_PATH)
    print("Model loaded:", classify_worker)

    examples = [
        "Добрый день. Просим сделать расчет.",
        "Нужен счет, прошу выставить.",
        "Заявка в работу, без пересчета.",
    ]

    for text in examples:
        prob_1 = llm_worker.predict_prob_1(text)
        print(f"{text}: {prob_1}")
        model_decision, predicted_class, new_status = decide_by_thresholds(prob_1)
        print(model_decision, predicted_class, new_status)


if __name__ == "__main__":
    # dev_llm()
    # development()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    main()
