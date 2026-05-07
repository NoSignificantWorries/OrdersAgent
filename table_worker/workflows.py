# worker/workflows.py
import asyncio
from datetime import timedelta
from typing import Dict, Optional, Tuple

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from activities import ExcelProcessingActivities


@workflow.defn
class ExcelProcessingWorkflow:
    def __init__(self) -> None:
        self._user_answers: Optional[Dict[str, Tuple[str, bool]]] = None
        self._user_answered = False
        self._query = None

    @workflow.signal
    async def provide_material_answers(self, answers: Dict[str, Tuple[str, bool]]):
        self._user_answers = answers
        self._user_answered = True

    @workflow.query
    async def get_status(self) -> str:
        if self._user_answered:
            return "user_answered"
        return "waiting_for_user"

    @workflow.query
    async def get_questions(self) -> Optional[Dict[str, bool]]:
        return self._query

    @workflow.run
    async def run(self, filepath: str) -> str:
        retry_policy = RetryPolicy(
            maximum_attempts=3,
            maximum_interval=timedelta(seconds=30),
            non_retryable_error_types=["ValueError", "RuntimeError"],
        )

        excel_data = await workflow.execute_activity(
            "download_excel",
            args=["orders-attachments", filepath],
            start_to_close_timeout=timedelta(seconds=50),
            retry_policy=retry_policy,
        )

        # result = await workflow.execute_activity(
        #     "process_excel",
        #     args=[excel_data, filepath],
        #     start_to_close_timeout=timedelta(seconds=50),
        #     retry_policy=retry_policy,
        # )
        query = await workflow.execute_activity(
            "process_excel_materials",
            args=[excel_data, filepath],
            start_to_close_timeout=timedelta(seconds=50),
            retry_policy=retry_policy,
        )

        if query:
            self._query = query
            await workflow.execute_activity(
                "notify_user",
                args=[filepath, query],
                start_to_close_timeout=timedelta(seconds=50),
                retry_policy=retry_policy,
            )
            print("Waiting user")

            try:
                await workflow.wait_condition(
                    lambda: self._user_answered, timeout=timedelta(hours=24)
                )
            except asyncio.TimeoutError:
                workflow.logger.error("User not answered")
                raise ValueError("User response timeout")

            if self._user_answers is None:
                raise ValueError("No user annswers received")

            await workflow.execute_activity(
                "process_excel_match",
                args=[self._user_answers],
                start_to_close_timeout=timedelta(seconds=50),
                retry_policy=retry_policy,
            )

        result = await workflow.execute_activity(
            "process_excel_finally",
            args=[],
            start_to_close_timeout=timedelta(seconds=50),
            retry_policy=retry_policy,
        )

        if result is None:
            workflow.logger.error(f"No data extracted from {filepath}")
            raise ValueError(f"Failed to process {filepath}")

        result_url = await workflow.execute_activity(
            "upload_excel",
            args=[result, "results", filepath],
            start_to_close_timeout=timedelta(seconds=50),
            retry_policy=retry_policy,
        )

        workflow.logger.info(f"Successfully processed {filepath}")

        return result_url
