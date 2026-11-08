"""AI 投資研究團隊儀表板（獨立版）。畫面與資料邏輯在 research_dashboard.py。

執行：streamlit run app.py
"""
import streamlit as st

st.set_page_config(page_title="AI 投資研究團隊", page_icon="📊", layout="wide")

import research_dashboard as rd  # noqa: E402  set_page_config 必須最先呼叫

tickers = rd.list_tickers()
with st.sidebar:
    st.header("📊 AI 投資研究團隊")
    if not tickers:
        st.warning("work/ 底下還沒有研究資料。")
        st.stop()
    view = st.radio("檢視", ["研究總覽"] + tickers)
    st.divider()
    st.caption("在 Claude Code 輸入 `/research-director <代號>` 產生新研究，重新整理本頁即可看到。")
    if st.button("重新載入資料", icon=":material/refresh:"):
        st.cache_data.clear()
    st.divider()
    rd.sinopac_panel()

if view == "研究總覽":
    rd.page_compare(tickers)
else:
    rd.page_ticker(view)
