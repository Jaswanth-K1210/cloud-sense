"""CloudSense FastAPI application."""

import os

import uvicorn
from fastapi import FastAPI

from eval.cloudsense_env.server.routes import router

app = FastAPI(title="CloudSense", version="1.0.0")
app.include_router(router)


def main() -> None:
    """Entry point for `server` console script and `python -m eval.cloudsense_env.server.app`."""
    port = int(os.getenv("PORT", "7860"))
    uvicorn.run("eval.cloudsense_env.server.app:app", host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
