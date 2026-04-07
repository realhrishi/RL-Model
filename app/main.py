import uuid
import asyncio
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.models import CrisisAction, ResetResult, StepResult
from app.environment import CrisisFlowEnvironment
from app.tasks import TASKS

app = FastAPI(title="CrisisFlow API", version="1.0.0")

class SessionManager:
    def __init__(self):
        self.sessions = {}
        self.lock = asyncio.Lock()
        
    async def create_session(self, task_id: str, seed: int = None) -> tuple[CrisisFlowEnvironment, str]:
        env = CrisisFlowEnvironment(task_id, seed)
        res = env.reset()
        async with self.lock:
            self.sessions[res.session_id] = env
        return env, res.session_id

    async def get_session(self, session_id: str) -> CrisisFlowEnvironment:
        async with self.lock:
            if session_id not in self.sessions:
                raise HTTPException(status_code=404, detail="Session not found or expired")
            return self.sessions[session_id]

manager = SessionManager()

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    status_code = 400
    if isinstance(exc, ValidationError):
        status_code = 422
    return JSONResponse(
        status_code=status_code,
        content={"error": type(exc).__name__, "detail": str(exc)},
    )

@app.get("/health")
def health_check():
    return {"status": "ok", "env": "CrisisFlow", "version": "1.0.0"}

@app.get("/tasks")
def list_tasks():
    return [
        {"id": t["id"], "name": t["name"], "difficulty": t["difficulty"], "description": t["description"]}
        for t in TASKS.values()
    ]

@app.post("/reset", response_model=ResetResult)
async def reset_env(payload: dict):
    task_id = payload.get("task_id")
    seed = payload.get("seed")
    if not task_id or task_id not in TASKS:
        raise HTTPException(status_code=400, detail="Invalid or missing task_id")
    
    env, session_id = await manager.create_session(task_id, seed)
    return ResetResult(observation=env._get_observation(), session_id=session_id)

@app.post("/step", response_model=StepResult)
async def step_env(payload: dict):
    session_id = payload.get("session_id")
    action_data = payload.get("action")
    if not session_id or not action_data:
        raise HTTPException(status_code=422, detail="Missing session_id or action")
        
    try:
        action = CrisisAction(**action_data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
        
    env = await manager.get_session(session_id)
    try:
        result = env.step(action)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    return result

@app.get("/state")
async def get_state(session_id: str):
    env = await manager.get_session(session_id)
    return env.state()
