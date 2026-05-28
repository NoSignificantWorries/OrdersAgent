import asyncio

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
    results = await sender.get(
        "/users/change-role", {"email": "test.test@gmail.com", "role": "manager"}
    )
    print(results)

    await sender.close()


if __name__ == "__main__":
    asyncio.run(main())
