"""CloudSense backend FastAPI entry point."""

from fastapi import FastAPI

app = FastAPI(title="CloudSense")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
