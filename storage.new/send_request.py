import asyncio
from datetime import datetime, timezone

from sender import AsyncDBApiConnector

BASE_URL = "http://0.0.0.0:8800"


async def main():
    sender = AsyncDBApiConnector(BASE_URL)

    # results = await sender.get("/materials/get-all")
    # results = await sender.post("/users/add", {"email": "test.test@gmail.com"})
    # results = await sender.get("/users/get-all")

    # results = await sender.post(
    #     "/materials/add-many",
    #     {"materials": [{"source": "T4", "target": "tt4", "article": "t4"}]},
    # )

    # results = await sender.get("/users/get-many-by-role", {"role": "standart"})

    # results = await sender.get(
    #     "/users/change-role", {"email": "test.test@gmail.com", "role": "manager"}
    # )

    # results = await sender.post(
    #     "/task/add-new-email-task",
    #     {
    #         "subject": "Any email",
    #         "body": "Hello, here is your files",
    #         "date": datetime.now(timezone.utc).isoformat(),
    #         "files": ["01/file1.xls", "01/file2.pdf"],
    #     },
    # )
    # print(results)
    # results = await sender.post(
    #     "/task/add-new-email-task",
    #     {
    #         "subject": "Any another email",
    #         "body": "Tell me coasts of your work",
    #         "date": datetime.now(timezone.utc).isoformat(),
    #         "files": [],
    #     },
    # )

    # results = await sender.post(
    #     "/task/mark-email-task-classified", {"type": "request"}, {"id": 1}
    # )

    results = await sender.post("/task/close-by-email-id", params={"id": 1})
    print(results)

    await sender.close()


if __name__ == "__main__":
    asyncio.run(main())
