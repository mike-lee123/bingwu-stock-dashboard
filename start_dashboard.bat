@echo off
chcp 65001 >nul
title 併武主儀表板
rem 切換到本批次檔所在資料夾，避免中文路徑編碼問題
cd /d "%~dp0"
echo 啟動主儀表板，瀏覽器開 http://localhost:8501
echo 在「AI 投資研究團隊艙」填代號即可直接用你的 Claude 訂閱啟動研究。
call ".\.venv\Scripts\activate.bat"
streamlit run app.py --server.address localhost
pause
