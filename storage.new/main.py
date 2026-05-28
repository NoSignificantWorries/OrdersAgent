from contextlib import asynccontextmanager

from fastapi import FastAPI

from api import materials_router, users_router
from database import DatabaseManager, init_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_database(echo=False)
    yield
    await DatabaseManager.close()


app = FastAPI(title="orders-agent-service-db-api", version="1.0.0", lifespan=lifespan)

app.include_router(materials_router)
app.include_router(users_router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "database": "connected"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8800, reload=False)
