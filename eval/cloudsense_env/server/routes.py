"""CloudSense API routes."""

import threading

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from eval.cloudsense_env.environment import CloudSenseEnv
from eval.cloudsense_env.server.dashboard import DASHBOARD_HTML
from eval.cloudsense_env.tasks import TASKS

router = APIRouter()
env = CloudSenseEnv()
_env_lock = threading.Lock()

DEFAULT_TASK_ID = "startup-cleanup"


class ActionRequest(BaseModel):
    action_type: str
    resource_id: str
    new_config: dict | None = None
    reasoning: str = ""


@router.get("/", response_class=HTMLResponse)
def root():
    return DASHBOARD_HTML


@router.get("/status")
def status():
    return {"status": "ok", "name": "cloudsense", "version": "1.0.0"}


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/version")
def version():
    return {"name": "cloudsense", "version": "1.0.0", "api": "v1"}


@router.post("/reset")
def reset(task_id: str = Query(default=DEFAULT_TASK_ID)):
    with _env_lock:
        try:
            obs = env.reset(task_id)
            return obs.model_dump()
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))


@router.post("/step")
def step(action: ActionRequest):
    with _env_lock:
        try:
            result = env.step(action.model_dump())
            return {
                "observation": result.observation.model_dump(),
                "reward": result.reward,
                "done": result.done,
                "info": result.info,
            }
        except RuntimeError as e:
            raise HTTPException(status_code=400, detail=str(e))


@router.get("/state")
def state():
    with _env_lock:
        try:
            return env.state()
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))


@router.get("/tasks")
def tasks():
    result = []
    for tid, tcls in TASKS.items():
        t = tcls()
        result.append({
            "id": t.task_id,
            "difficulty": t.difficulty,
            "max_steps": t.max_steps,
            "description": t.description,
        })
    return result


@router.post("/close")
def close():
    with _env_lock:
        env.close()
        return {"status": "closed"}
