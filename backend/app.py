"""CloudSense backend FastAPI entry point."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend import scheduler
from backend.api.routes import router
from backend.config import settings
from backend.deps import services
from backend.store.db import init_db

DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173"]


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if settings.SLACK_BOT_TOKEN and services.notify_review is None:
        from slack_sdk import WebClient

        from backend.review.slack_app import make_notifier

        services.notify_review = make_notifier(WebClient(token=settings.SLACK_BOT_TOKEN))
    task = asyncio.create_task(scheduler.loop(services))
    yield
    task.cancel()


app = FastAPI(title="CloudSense", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=DEV_ORIGINS, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
