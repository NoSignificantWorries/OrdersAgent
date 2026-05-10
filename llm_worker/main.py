import json
import logging
import os
from pathlib import Path

import psycopg2
from psycopg2.extras import Json
from dotenv import load_dotenv

from llm.llm import LLM
from logging_config import setup_logging


class Table:
    def __init__(self, data) -> None:
        self.parse(data)

    def parse(self, data_dict):
        for key, val in data_dict.items():
            setattr(self, key, val)


def read_config(path: Path):
    with open(path, "r", encoding="utf-8") as config_file:
        config_data = json.load(config_file)

    llm_config = Table(config_data["llm"])
    return (llm_config,)


def get_db_connection():
    env_path = (Path(__file__).resolve().parent / "../storage/.env").resolve()
    load_dotenv(env_path)

    return psycopg2.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ.get("POSTGRES_PORT", "5432"),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def fetch_new_classify_tasks(conn, limit: int = 100):
    """
    Берём задачи на LLM-классификацию из новой схемы:
      - tasks.status = 'new'
    Собираем текст из темы, raw_email и списка имён файлов.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                t.id AS task_id,
                e.id AS email_id,
                e.email_uid,
                e.email_subject,
                e.raw_email,
                STRING_AGG(
                    d.filename,
                    E'\n' ORDER BY d.id
                ) AS files_text
            FROM tasks t
            JOIN emails e ON e.id = t.email_id
            LEFT JOIN documents d ON d.email_id = e.id
            WHERE t.status = 'new'
            GROUP BY
                t.id,
                e.id,
                e.email_uid,
                e.email_subject,
                e.raw_email
            ORDER BY t.created_at
            LIMIT %s
            """,
            (limit,),
        )
        return cur.fetchall()


def mark_task_processing(conn, task_id: int):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE tasks
            SET status = 'ml_processing'::task_status
            WHERE id = %s
            """,
            (task_id,),
        )


def decide_by_thresholds(prob_1: float):
    """
    Маппинг порогов:
      - prob_1 <= 0.25 → auto_0, класс 0, статус ml_classified
      - prob_1 >= 0.60 → auto_1, класс 1, статус ml_classified
      - иначе → review, класс не ставим, статус ml_low_confidence
    """
    if prob_1 <= 0.25:
        return "auto_0", 0, "ml_classified"
    if prob_1 >= 0.60:
        return "auto_1", 1, "ml_classified"
    return "review", None, "ml_low_confidence"


def update_classification(
    conn,
    task_id: int,
    email_id: int,
    prob_1: float,
    predicted_class: int | None,
    model_decision: str,
    new_task_status: str,
):
    """
    Обновляет:
      - tasks.output_data: prob_1/predicted_class/model_decision
      - tasks.status: ml_classified или ml_low_confidence
      - tasks.completed_at: не ставим, так как это не final-status
      - emails: дублируем prob_1/predicted_class/model_decision
    """
    output_payload = {
        "prob_1": prob_1,
        "predicted_class": predicted_class,
        "model_decision": model_decision,
    }

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE tasks
            SET
                output_data = COALESCE(%s::jsonb, '{}'::jsonb),
                status = %s::task_status
            WHERE id = %s
            """,
            (Json(output_payload), new_task_status, task_id),
        )

        cur.execute(
            """
            UPDATE emails
            SET
                prob_1 = %s,
                predicted_class = %s,
                model_decision = %s
            WHERE id = %s
            """,
            (prob_1, predicted_class, model_decision, email_id),
        )


def mark_task_error(conn, task_id: int, error_message: str):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE tasks
            SET
                status = 'error'::task_status,
                error_message = %s
            WHERE id = %s
            """,
            (error_message[:2000], task_id),
        )


def classify_email_text(
    llm_worker: LLM,
    subject: str | None,
    body: str | None,
    files_text: str | None,
) -> float:
    parts = [subject or "", files_text or "", body or ""]
    text = "\n\n".join(part for part in parts if part).strip()
    return llm_worker.predict_prob_1(text)


def main():
    logger = logging.getLogger(__name__)
    print("1. main started")

    model_path = Path("model_out/final_lora")
    print(f"2. model path = {model_path}")

    logger.info("Loading model from %s", model_path)
    llm_worker = LLM(model_path)
    print("3. model loaded")

    conn = get_db_connection()
    print("4. db connected")

    try:
        rows = fetch_new_classify_tasks(conn, limit=200)

        if not rows:
            logger.info("Нет задач со статусом new для LLM-классификации")
            return

        logger.info("Найдено %d задач для классификации", len(rows))

        for task_id, email_id, email_uid, subject, body, files_text in rows:
            try:
                mark_task_processing(conn, task_id)
                conn.commit()

                prob_1 = classify_email_text(llm_worker, subject, body, files_text)
                model_decision, predicted_class, new_task_status = decide_by_thresholds(
                    prob_1
                )

                update_classification(
                    conn=conn,
                    task_id=task_id,
                    email_id=email_id,
                    prob_1=prob_1,
                    predicted_class=predicted_class,
                    model_decision=model_decision,
                    new_task_status=new_task_status,
                )
                conn.commit()

                logger.info(
                    "task_id=%s email_uid=%s prob_1=%.4f decision=%s "
                    "predicted_class=%s task_status=%s",
                    task_id,
                    email_uid,
                    prob_1,
                    model_decision,
                    predicted_class,
                    new_task_status,
                )

            except Exception as e:
                conn.rollback()
                try:
                    mark_task_error(conn, task_id, str(e))
                    conn.commit()
                except Exception:
                    conn.rollback()

                logger.exception(
                    "Ошибка обработки задачи task_id=%s email_uid=%s: %s",
                    task_id,
                    email_uid,
                    e,
                )

        logger.info("Классификация завершена")

    finally:
        conn.close()


if __name__ == "__main__":
    setup_logging()
    logger = logging.getLogger(__name__)
    main()