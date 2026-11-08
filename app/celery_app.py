import os
from celery import Celery
from dotenv import load_dotenv
from app.db import update_job_result
from app.agents.stock_crew import run_stock_research

load_dotenv()
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery = Celery("stock_tasks", broker=REDIS_URL, backend=REDIS_URL)

@celery.task(name="tasks.execute_research_job")
def execute_research_job(job_id: str, ticker: str, api_key: str):
    try:
        update_job_result(job_id, status="in_progress")
        result = run_stock_research(ticker, api_key)
        update_job_result(job_id, status="completed", result=result)
    except Exception as e:
        update_job_result(job_id, status="failed", error=str(e))
