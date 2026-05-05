import asyncio
import uuid

from temporalio.client import Client


async def main():
    client = await Client.connect("localhost:7233")
    result = await client.execute_workflow(
        "HelloWorkflow",
        "Temporal",
        id=f"hello-workflow-{uuid.uuid4()}",
        task_queue="test-task-queue"
    )
    print("Workflow results:", result)


if __name__ == "__main__":
    asyncio.run(main())

