import logging
import time
from cgitb import handler
from io import BytesIO
from pathlib import Path
from typing import Dict, List

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
from llm import LLM, decide_by_thresholds
from materials import DELIMETERS, ParseResults, ParserV2
from table import TableParseResults, TableWorker, make_xlsx

POLL_INTERVAL = 30
BUSY_INTERVAL = 5
IDLE_INTERVAL = 120
BATCH_SIZE = 10
MODEL_PATH = Path("model_out/final_lora")
ATTACHMENTS_BUCKET = "orders-attachments"
RESULTS_BUCKET = "results"

logger = logging.getLogger("mail_processor")


def process_new(
    task, email_repo, task_repo, doc_repo, material_repo, cloud, llm_worker
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

    prob_1 = llm_worker.predict_prob_1(text)
    model_decision, predicted_class, new_status = decide_by_thresholds(prob_1)
    logger.info(
        f"Task {task.id}: prob={prob_1:.3f} decision={model_decision} class={predicted_class} status={new_status}"
    )

    email_repo.set_ml_result(email.id, prob_1, predicted_class, model_decision)

    if predicted_class is None:
        task_status = "ml_review"
    else:
        task_status = "ml_classified"
    task_repo.update_status(task.id, task_status)


def process_classified_excel(
    task, email_repo, task_repo, doc_repo, material_repo, cloud, llm_worker
):
    documents = doc_repo.get_by_email_id(task.email_id)
    docnames = [doc.filename for doc in documents]
    logger.info(f"Task {task.id}: Processing documents: {', '.join(docnames)}")
    for doc in documents:
        filename = doc.minio_object_key
        file_data = get_bytes_object(cloud, ATTACHMENTS_BUCKET, filename)
        if file_data is None:
            logger.error(f"Task {task.id}: Can't open file {filename}")
            return

        # opening table
        worker = TableWorker(file_data, Path(filename))
        worker.open_and_clean()
        if worker.tables is None or not bool(worker.tables):
            logger.error(f"Task {task.id}: Unexpected errors with the file {filename}")
            task_repo.update_status(task.id, "error")
            return

        # parsing simple strategy
        res = worker.simple_parser()

        # finding unique materials
        unique_materials = set()
        for table in res:
            if table.empty:
                continue
            unique_materials |= set(table.material)
        unique_materials = list(unique_materials)

        # parsing materials (finding unique parts)
        parser = ParserV2(DELIMETERS)
        unique_materials_dict = {}
        unique_parts = set()
        for material in unique_materials:
            parse_results = parser.parse(material)
            unique_materials_dict[material] = parse_results
            unique_parts |= set(parse_results.parts)
        unique_parts = list(unique_parts)

        # searching materials
        matches = material_repo.batch_find(unique_parts)
        questions = []
        for part, mat_match in matches.items():
            if mat_match is None:
                questions.append({part: False})
                continue
            _, bl = mat_match
            if bl:
                questions.append({part: True})
                continue

        if questions:
            task_repo.update_status(task.id, "materials_review", output_data=questions)
            logger.info(f"Task {task.id}: Needs manual matching for material parts")
            return

        for material, material_obj in unique_materials_dict.items():
            for part in material_obj.parts:
                material_obj.matches.append(matches[part][0])

        wb = make_xlsx(res, unique_materials_dict)

        if wb is None:
            task_repo.update_status(task.id, "error")
            logger.warning(f"Task {task.id}: Empty output file")
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
        if err:
            logger.error(f"Task {task.id}: Can't save file, retrying...")

    task_repo.update_status(task.id, "completed")
    logger.info(f"Task {task.id}: Succesfully parsed files")


def process_manual_matching(
    task, email_repo, task_repo, doc_repo, material_repo, cloud, llm_worker
):
    answers = task.manual_decision
    if answers is None:
        task_repo.update_status(task.id, "error")
        logger.info(f"Task {task.id}: Empty answers")
        return
    answers_flat = [(part, data[0], data[1]) for part, data in answers.items()]
    material_repo.batch_add(answers_flat)

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
        deps["task_repo"].mark_error(task.id, str(err))


def main_loop(
    email_repo, task_repo, doc_repo, material_repo, cloud, llm_worker
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
                            llm_worker=llm_worker,
                        )
                    except Exception as err:
                        task_repo.update_status(task.id, "error")
                        logger.exception(f"Task {task.id}: Error on task: {err}")

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
    llm_worker = LLM(MODEL_PATH)

    try:
        main_loop(
            email_repo=email_repo,
            task_repo=task_repo,
            doc_repo=doc_repo,
            material_repo=material_repo,
            cloud=cloud,
            llm_worker=llm_worker,
        )
    finally:
        DatabaseManager.close()


def development() -> None:
    init_database()
    cloud = MinIOClient.get_client()

    # testfile = Path("../private/tables/1108A.xls")
    filename = "033/1108A.xls"

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

    llm_worker = LLM(model_path)
    print("LLM loaded:", llm_worker)

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
