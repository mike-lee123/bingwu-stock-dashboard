@echo off
chcp 65001 >nul
title AI Research Platform Launcher
rem 切換到本批次檔所在資料夾，避免中文路徑編碼問題
cd /d "%~dp0"

echo [1/3] 啟動 Celery Worker...
start "Celery Worker" cmd /k ".\.venv\Scripts\activate && celery -A app.celery_app.celery worker --loglevel=info -P gevent"

timeout /t 2 >nul

echo [2/3] 啟動 FastAPI 伺服器...
start "FastAPI Server" cmd /k ".\.venv\Scripts\activate && uvicorn app.main:app --reload --port 8000"

timeout /t 2 >nul

echo [3/3] 啟動 Streamlit 儀表板...
start "Streamlit Dashboard" cmd /k ".\.venv\Scripts\activate && streamlit run dashboard/app.py"

echo.
echo 全部服務已啟動，儀表板網址 http://localhost:8501
