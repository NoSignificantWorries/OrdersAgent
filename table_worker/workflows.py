# worker/workflows.py
from datetime import timedelta
from typing import Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from activities import ExcelProcessingActivities


@workflow.defn
class ExcelProcessingWorkflow:
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

        result = await workflow.execute_activity(
            "process_excel",
            args=[excel_data, filepath],
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
