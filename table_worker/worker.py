import asyncio
from pathlib import Path

from temporalio.client import Client
from temporalio.worker import Worker

from activities import ExcelProcessingActivities
from clients import initialize_infrastructure, shutdown_infrastructure
from workflows import ExcelProcessingWorkflow


async def main():
    await initialize_infrastructure()

    try:
        client = await Client.connect("localhost:7233", namespace="default")
        print(client)

        activities = ExcelProcessingActivities(Path("config.json"))

        worker = Worker(
            client,
            task_queue="processing-files-queue",
            workflows=[ExcelProcessingWorkflow],
            activities=[
                activities.download_excel,
                activities.process_excel,
                activities.upload_excel,
            ],
        )

        await worker.run()
    finally:
        await shutdown_infrastructure()


if __name__ == "__main__":
    asyncio.run(main())
