from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.sql.functions import coalesce

from .base import DatabaseManager
from .models import Document, Email, Mapping, Task, TaskStatus, User

# ══════════════════════════════════════════════════════
# UserRepository
# ══════════════════════════════════════════════════════


class UserRepository:
    def get_by_id(self, user_id: int) -> User | None:
        with DatabaseManager.session_scope() as session:
            return session.get(User, user_id)

    def get_by_login(self, login: str) -> User | None:
        with DatabaseManager.session_scope() as session:
            query = select(User).where(User.login == login)
            return session.execute(query).scalar_one_or_none()

    def get_by_email(self, email: str) -> User | None:
        with DatabaseManager.session_scope() as session:
            query = select(User).where(User.email == email)
            return session.execute(query).scalar_one_or_none()

    def get_all_managers(self) -> list[User]:
        with DatabaseManager.session_scope() as session:
            query = select(User).where(User.role == "manager")
            return list(session.execute(query).scalars().all())

    def create(
        self, login: str, email: str, pass_hash: str, role: str = "manager"
    ) -> User:
        with DatabaseManager.session_scope() as session:
            user = User(login=login, email=email, pass_hash=pass_hash, role=role)
            session.add(user)
            session.flush()
            return user


# ══════════════════════════════════════════════════════
# MappingRepository
# ══════════════════════════════════════════════════════


class MappingRepository:
    def find(self, source: str) -> tuple[str, str, bool] | None:
        with DatabaseManager.session_scope() as session:
            mapping = session.get(Mapping, source)
            if mapping:
                return mapping.target, mapping.article, mapping.black_list
            return None

    def batch_find(self, sources: list[str]) -> dict[str, tuple[str, bool] | None]:
        if not sources:
            return {}
        with DatabaseManager.session_scope() as session:
            query = select(Mapping).where(Mapping.source.in_(sources))
            mappings = session.execute(query).scalars().all()
            result = {m.source: (m.target, m.article, m.black_list) for m in mappings}
            for s in sources:
                if s not in result:
                    result[s] = None
            return result

    def add(
        self,
        source: str,
        target: str | None,
        article: str | None,
        black_list: bool = False,
    ) -> None:
        with DatabaseManager.session_scope() as session:
            mapping = Mapping(
                source=source, target=target, article=article, black_list=black_list
            )
            session.add(mapping)

    def batch_add(
        self, items: list[tuple[str, str | None, str | None, bool]]
    ) -> None:
        with DatabaseManager.session_scope() as session:
            stmt = pg_insert(Mapping).values(
                [
                    {"source": s, "target": t, "article": a, "black_list": bl}
                    for s, t, a, bl in items
                ]
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["source"],
                set_=dict(
                    target=coalesce(stmt.excluded.target, Mapping.target),
                    article=coalesce(stmt.excluded.article, Mapping.article),
                    black_list=stmt.excluded.black_list,
                ),
            )
            session.execute(stmt)
            session.commit()

    # def batch_add(
    #     self, items: List[Tuple[str, Optional[str], Optional[str], bool]]
    # ) -> None:
    #     with DatabaseManager.session_scope() as session:
    #         stmt = pg_insert(Mapping).values(
    #             [
    #                 {"source": s, "target": t, "article": a, "black_list": bl}
    #                 for s, t, a, bl in items
    #             ]
    #         )
    #         stmt = stmt.on_conflict_do_update(
    #             index_elements=["source"],
    #             set_=dict(
    #                 target=stmt.excluded.target, black_list=stmt.excluded.black_list
    #             ),
    #         )
    #         session.execute(stmt)
    #         session.commit()

    # def batch_add(self, items: List[Tuple[str, str, bool]]) -> None:
    #     with DatabaseManager.session_scope() as session:
    #         for source, target, black_list in items:
    #             session.add(
    #                 Mapping(source=source, target=target, black_list=black_list)
    #             )

    def update(
        self,
        source: str,
        target: str | None = None,
        article: str | None = None,
        black_list: bool | None = None,
    ) -> bool:
        with DatabaseManager.session_scope() as session:
            mapping = session.get(Mapping, source)
            if not mapping:
                return False
            if target is not None:
                mapping.target = target
            if article is not None:
                mapping.article = article
            if black_list is not None:
                mapping.black_list = black_list
            return True

    def delete(self, source: str) -> bool:
        with DatabaseManager.session_scope() as session:
            mapping = session.get(Mapping, source)
            if mapping:
                session.delete(mapping)
                return True
            return False


# ══════════════════════════════════════════════════════
# EmailRepository
# ══════════════════════════════════════════════════════


class EmailRepository:
    def create(
        self,
        mailbox: str,
        email_uid: int,
        email_from: str | None = None,
        email_subject: str | None = None,
        raw_email: str | None = None,
        email_date: datetime | None = None,
    ) -> Email | None:
        with DatabaseManager.session_scope() as session:
            existing = session.execute(
                select(Email).where(
                    and_(Email.mailbox == mailbox, Email.email_uid == email_uid)
                )
            ).scalar_one_or_none()

            if existing:
                return None  # уже существует

            email = Email(
                mailbox=mailbox,
                email_uid=email_uid,
                email_from=email_from,
                email_subject=email_subject,
                raw_email=raw_email,
                email_date=email_date,
            )
            session.add(email)
            session.flush()
            return email

    def get_by_id(self, email_id: int) -> Email | None:
        with DatabaseManager.session_scope() as session:
            return session.get(Email, email_id)

    def get_by_mailbox_and_uid(self, mailbox: str, email_uid: int) -> Email | None:
        with DatabaseManager.session_scope() as session:
            query = select(Email).where(
                and_(Email.mailbox == mailbox, Email.email_uid == email_uid)
            )
            return session.execute(query).scalar_one_or_none()

    def get_emails_by_mailbox(
        self, mailbox: str, limit: int = 50, offset: int = 0
    ) -> list[Email]:
        with DatabaseManager.session_scope() as session:
            query = (
                select(Email)
                .where(Email.mailbox == mailbox)
                .order_by(Email.email_date.desc())
                .offset(offset)
                .limit(limit)
            )
            return list(session.execute(query).scalars().all())

    def get_all_emails(self, limit: int = 50, offset: int = 0) -> list[Email]:
        with DatabaseManager.session_scope() as session:
            query = (
                select(Email)
                .order_by(Email.email_date.desc())
                .offset(offset)
                .limit(limit)
            )
            return list(session.execute(query).scalars().all())

    def set_ml_result(
        self, email_id: int, prob_1: float, predicted_class: int, model_decision: str
    ) -> None:
        with DatabaseManager.session_scope() as session:
            email = session.get(Email, email_id)
            if email:
                email.prob_1 = prob_1
                email.predicted_class = predicted_class
                email.model_decision = model_decision


# ══════════════════════════════════════════════════════
# DocumentRepository
# ══════════════════════════════════════════════════════


class DocumentRepository:
    def create(
        self,
        email_id: int,
        filename: str = None,
        minio_object_key: str = None,
        content_type: str = None,
        size_bytes: int = None,
    ) -> Document:
        with DatabaseManager.session_scope() as session:
            doc = Document(
                email_id=email_id,
                filename=filename,
                minio_object_key=minio_object_key,
                content_type=content_type,
                size_bytes=size_bytes,
            )
            session.add(doc)
            session.flush()
            return doc

    def get_by_email_id(self, email_id: int) -> list[Document]:
        with DatabaseManager.session_scope() as session:
            query = (
                select(Document)
                .where(Document.email_id == email_id)
                .order_by(Document.created_at)
            )
            return list(session.execute(query).scalars().all())

    def get_by_id(self, doc_id: int) -> Document | None:
        with DatabaseManager.session_scope() as session:
            return session.get(Document, doc_id)


# ══════════════════════════════════════════════════════
# TaskRepository
# ══════════════════════════════════════════════════════


class TaskRepository:
    # --- Создание ---
    def create(
        self, email_id: int, document_id: int = None, status: str = TaskStatus.NEW.value
    ) -> Task:
        with DatabaseManager.session_scope() as session:
            task = Task(
                email_id=email_id,
                document_id=document_id,
                status=status,
            )
            session.add(task)
            session.flush()
            return task

    def get_by_id(self, task_id: int) -> Task | None:
        with DatabaseManager.session_scope() as session:
            return session.get(Task, task_id)

    # --- Получение задач для планировщика ---
    def fetch_pending(self, limit: int = 10) -> list[Task]:
        with DatabaseManager.session_scope() as session:
            query = (
                select(Task)
                .where(
                    Task.status.in_(
                        [
                            TaskStatus.NEW.value,
                            TaskStatus.ML_CLASSIFIED.value,
                            TaskStatus.DOWNLOADED.value,
                            TaskStatus.FILES_SAVED.value,
                            TaskStatus.MANUAL_REVIEW_DONE.value,
                        ]
                    )
                )
                .order_by(Task.created_at)
                .limit(limit)
            )
            return list(session.execute(query).scalars().all())

    # --- Получение задач для WebUI ---
    def fetch_manual(self, limit: int = 50) -> list[Task]:
        with DatabaseManager.session_scope() as session:
            query = (
                select(Task)
                .where(
                    Task.status.in_(
                        [
                            TaskStatus.ML_REVIEW.value,
                            TaskStatus.MATERIALS_REVIEW.value,
                        ]
                    )
                )
                .order_by(Task.created_at)
                .limit(limit)
            )
            return list(session.execute(query).scalars().all())

    def fetch_by_user(self, user_id: int, limit: int = 50) -> list[Task]:
        with DatabaseManager.session_scope() as session:
            query = (
                select(Task)
                .where(Task.assigned_to == user_id)
                .order_by(Task.created_at.desc())
                .limit(limit)
            )
            return list(session.execute(query).scalars().all())

    def has_manual(self) -> bool:
        with DatabaseManager.session_scope() as session:
            query = (
                select(Task.id)
                .where(
                    Task.status.in_(
                        [
                            TaskStatus.ML_REVIEW.value,
                            TaskStatus.MATERIALS_REVIEW.value,
                        ]
                    )
                )
                .limit(1)
            )
            return session.execute(query).scalar_one_or_none() is not None

    # --- Обновление статуса ---
    def update_status(self, task_id: int, status: str, **kwargs) -> None:
        with DatabaseManager.session_scope() as session:
            task = session.get(Task, task_id)
            if task:
                task.status = status
                for key, value in kwargs.items():
                    if hasattr(task, key):
                        setattr(task, key, value)
                task.updated_at = datetime.now(UTC)

    # --- Хелперы для конкретных переходов ---
    def set_ml_result(
        self, task_id: int, output_data: dict, confidence: float = None
    ) -> None:
        conf = (
            confidence if confidence is not None else output_data.get("confidence", 0.0)
        )

        if conf < 0.7:
            new_status = TaskStatus.ML_REVIEW.value
        else:
            new_status = TaskStatus.ML_CLASSIFIED.value

        self.update_status(
            task_id,
            new_status,
            output_data=output_data,
        )

    def set_excel_result(
        self, task_id: int, parsed_data: dict, ambiguous: list | None = None
    ) -> None:
        if ambiguous:
            new_status = TaskStatus.MATERIALS_REVIEW.value
            output = {"parsed": parsed_data, "ambiguous": ambiguous}
        else:
            new_status = TaskStatus.COMPLETED.value
            output = {"parsed": parsed_data}
            self.update_status(
                task_id,
                new_status,
                output_data=output,
                completed_at=datetime.now(UTC),
            )
            return  # не делаем update_status дважды

        self.update_status(task_id, new_status, output_data=output)

    def submit_manual_decision(
        self, task_id: int, decision: dict, user_id: int
    ) -> None:
        self.update_status(
            task_id,
            TaskStatus.MANUAL_REVIEW_DONE.value,
            manual_decision=decision,
            assigned_to=user_id,
        )

    def mark_error(self, task_id: int, error_message: str) -> None:
        with DatabaseManager.session_scope() as session:
            task = session.get(Task, task_id)
            if task:
                task.status = TaskStatus.ERROR.value
                task.error_message = error_message[:1000]
                task.retry_count = (task.retry_count or 0) + 1
                task.updated_at = datetime.now(UTC)

    # --- Для WebUI: взять задачу в работу ---

    def assign(self, task_id: int, user_id: int) -> bool:
        with DatabaseManager.session_scope() as session:
            task = session.get(Task, task_id)
            if task and task.assigned_to is None:
                task.assigned_to = user_id
                task.updated_at = datetime.now(UTC)
                return True
            return False

    def release(self, task_id: int) -> None:
        with DatabaseManager.session_scope() as session:
            task = session.get(Task, task_id)
            if task:
                task.assigned_to = None
                task.updated_at = datetime.now(UTC)
