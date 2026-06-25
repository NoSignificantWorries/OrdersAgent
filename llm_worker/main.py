import json
import logging
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

# custom modules
from llm.llm import LLM

# configs
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
    load_dotenv("../storage/.env")

    return psycopg2.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ.get("POSTGRES_PORT", "5432"),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def fetch_pending_emails(conn, limit=100):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                email_uid,
                MIN(email_subject) AS email_subject,
                MIN(email_body) AS email_body,
                STRING_AGG(
                    'FILE_' || file_idx::text || ': ' || document_name,
                    E'\n'
                    ORDER BY file_idx
                ) AS files_text
            FROM (
                SELECT
                    email_uid,
                    email_subject,
                    email_body,
                    document_name,
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY email_uid
                        ORDER BY id
                    ) AS file_idx
                FROM process_queue
                WHERE status = 'wait'
            ) t
            GROUP BY email_uid
            ORDER BY MIN(id)
            LIMIT %s
            """,
            (limit,),
        )
        return cur.fetchall()


def decide_by_thresholds(prob_1: float):
    if prob_1 <= 0.37:
        return "auto_0", 0, "classified"
    if prob_1 >= 0.52:
        return "auto_1", 1, "classified"
    return "review", None, "review"


def update_classification(conn, email_uid, prob_1, predicted_class, model_decision, status):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE process_queue
            SET
                prob_1 = %s,
                predicted_class = %s,
                model_decision = %s,
                status = %s
            WHERE email_uid = %s
            """,
            (prob_1, predicted_class, model_decision, status, email_uid),
        )


def classify_email_text(llm_worker, subject: str, body: str, files_text: str | None) -> float:
    parts = [subject or "", files_text or "", body or ""]
    text = "\n\n".join(part for part in parts if part).strip()
    return llm_worker.predict_prob_1(text)

def main():
    logger = logging.getLogger(__name__)
    print("1. main started")

    model_path = Path("model_out/final")
    print(f"2. model path = {model_path}")

    logger.info("Loading model from %s", model_path)
    
    llm_worker = LLM(model_path)
    print("3. model loaded")

    conn = get_db_connection()
    print("4. db connected")

    try:
        rows = fetch_pending_emails(conn, limit=200)

        if not rows:
            logger.info("Нет записей со статусом wait")
            return

        logger.info("Найдено %d писем для классификации", len(rows))

        for email_uid, subject, body, files_text in rows:
            try:
                prob_1 = classify_email_text(llm_worker, subject, body, files_text)
                model_decision, predicted_class, new_status = decide_by_thresholds(prob_1)

                update_classification(
                    conn=conn,
                    email_uid=email_uid,
                    prob_1=prob_1,
                    predicted_class=predicted_class,
                    model_decision=model_decision,
                    status=new_status,
                )

                logger.info(
                    "id=%s prob_1=%.4f decision=%s predicted_class=%s status=%s",
                    email_uid,
                    prob_1,
                    model_decision,
                    predicted_class,
                    new_status,
                )

            except Exception as e:
                logger.exception("Ошибка обработки записи id=%s: %s", email_uid, e)

        conn.commit()
        logger.info("Классификация завершена")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    setup_logging()
    logger = logging.getLogger(__name__)

    main()

