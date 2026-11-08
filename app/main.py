import uuid
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.agents.stock_crew import run_stock_research

app = FastAPI(title="AI Research Platform API")
JOBS = {}

class ResearchRequest(BaseModel):
    ticker: str
    gemini_api_key: Optional[str] = None
    shioaji_api_key: Optional[str] = None
    shioaji_secret_key: Optional[str] = None
    simulation: Optional[bool] = True
    data_mode: Optional[str] = "auto"

def background_task(job_id: str, ticker: str, gemini_key: str, sj_key: str, sj_sec: str, sim: bool, dmode: str):
    try:
        res = run_stock_research(
            ticker=ticker,
            gemini_api_key=gemini_key,
            shioaji_api_key=sj_key,
            shioaji_secret_key=sj_sec,
            simulation=sim,
            data_mode=dmode
        )
        JOBS[job_id] = {"status": "completed", "result": res}
    except Exception as e:
        JOBS[job_id] = {"status": "failed", "error_message": str(e)}

@app.post("/research", status_code=202)
def create_research_job(req: ResearchRequest, bg: BackgroundTasks):
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"status": "processing", "ticker": req.ticker}
    bg.add_task(
        background_task,
        job_id,
        req.ticker,
        req.gemini_api_key or "",
        req.shioaji_api_key or "",
        req.shioaji_secret_key or "",
        req.simulation if req.simulation is not None else True,
        req.data_mode or "auto"
    )
    return {"job_id": job_id, "status": "accepted"}

@app.get("/research/{job_id}")
def get_research_status(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    return JOBS[job_id]