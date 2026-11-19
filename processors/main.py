import time
from dataclasses import dataclass

from minio import Minio

import classify
from cloud import MinIOClient
from database import (
    DatabaseManager,
    DocumentRepository,
    EmailRepository,
    MappingRepository,
    TaskRepository,
    init_database,
)

POLL_INTERVAL = 30
BUSY_INTERVAL = 5
# IDLE_INTERVAL = 120
IDLE_INTERVAL = 30
BATCH_SIZE = 10
MODEL_PATH = "classify/model.joblib"
ATTACHMENTS_BUCKET = "orders-attachments"
RESULTS_BUCKET = "results"


@dataclass
class Source:
    email_repo: EmailRepository
    task_repo: TaskRepository
    doc_repo: DocumentRepository
    material_repo: MappingRepository
    cloud: Minio
    classicator: classify.ClassifyEmail


def process_single_task(task, source: Source) -> None:
    ...


def main_loop(source: Source) -> None:
    while True:
        try:
            while True:
                pending = source.task_repo.fetch_pending(limit=BATCH_SIZE)
                if not pending:
                    break

                for task in pending:
                    try:
                        process_single_task(task, source)
                    except Exception:
                        source.task_repo.update_status(task.id, "error")
                        source.task_repo.mark_error(task.id, "Внутренняя ошибка сервера. Пожалуйста, сообщите разработчикам.")

            if source.task_repo.has_manual():
                interval = BUSY_INTERVAL
            else:
                interval = IDLE_INTERVAL

            time.sleep(interval)

        except KeyboardInterrupt:
            break
        except Exception:
            time.sleep(POLL_INTERVAL)


def main() -> None:
    init_database(pool_size=5)

    source = Source(
        EmailRepository(),
        TaskRepository(),
        DocumentRepository(),
        MappingRepository(),
        MinIOClient.get_client(),
        classify.ClassifyEmail(MODEL_PATH)
    )

    try:
        main_loop(source)
    finally:
        DatabaseManager.close()


if __name__ == "__main__":
    main()
