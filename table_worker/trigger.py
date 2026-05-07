import asyncio

from temporalio.client import Client


async def trigger_processing():
    # Подключаемся к Temporal
    client = await Client.connect("localhost:7233", namespace="default")

    # Запускаем воркфлоу
    result = await client.execute_workflow(
        "ExcelProcessingWorkflow",  # имя воркфлоу
        args=["033/1108A.xls"],  # путь к файлу в MinIO
        id="033-1",  # уникальный ID
        task_queue="processing-files-queue",
    )

    print(f"✅ Workflow completed with result: {result}")


if __name__ == "__main__":
    asyncio.run(trigger_processing())
