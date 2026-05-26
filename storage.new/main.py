from contextlib import asynccontextmanager

from fastapi import FastAPI

from database import init_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_database(echo=False)
    yield


app = FastAPI(title="orders-agent-service-db-api", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health_check():
    return {"status": "ok", "database": "connected"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8800, reload=False)
