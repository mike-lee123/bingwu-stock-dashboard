import streamlit as st
import requests
import time
import pandas as pd

st.set_page_config(page_title="AI Research Platform - 台股多源量化分析", layout="wide")
API_BASE_URL = "http://127.0.0.1:8000"

st.title("📈 AI Research Platform - 台股多源量化分析")

with st.sidebar:
    st.header("⚙️ 行情報價設定")
    
    # 報價模式切換
    mode_display = {
        "自動雙軌備援 (Shioaji 優先，異常自動轉 Yahoo)": "auto",
        "強制永豐 Shioaji (券商毫秒直連)": "shioaji_only",
        "強制 Yahoo Finance (免金鑰全標的)": "yahoo_only"
    }
    selected_mode_label = st.radio(
        "選擇行情數據源模式：",
        options=list(mode_display.keys()),
        index=0
    )
    data_mode = mode_display[selected_mode_label]
    
    st.divider()
    
    # Shioaji 設定區塊（僅在需要 Shioaji 的模式下顯示）
    shioaji_key = ""
    shioaji_secret = ""
    is_simulation = True
    
    if data_mode in ["auto", "shioaji_only"]:
        st.subheader("永豐證券 (Shioaji) 憑證")
        shioaji_key = st.text_input("Shioaji API Key", type="password")
        shioaji_secret = st.text_input("Shioaji Secret Key", type="password")
        is_simulation = st.checkbox(
            "使用模擬環境 (Simulation)", 
            value=True, 
            help="若持有測試 Token 請勾選；若已開通正式環境帳號請取消勾選。"
        )
        
        if shioaji_key.strip() and shioaji_secret.strip():
            env_txt = "模擬環境" if is_simulation else "正式環境"
            st.success(f"⚡ 憑證就緒：連線至 {env_txt}")
        else:
            if data_mode == "shioaji_only":
                st.error("⚠️ 強制 Shioaji 模式必須填寫 API Key 與 Secret Key")
            else:
                st.info("💡 未填寫 Shioaji 金鑰時，自動備援模式將直接走 Yahoo 數據源。")
    else:
        st.info("🌐 目前為 Yahoo 模式，無需配置券商金鑰即可查閱所有標的。")

ticker_input = st.text_input("輸入台股代號（例如：2330、2603、2454、6285、3008）", value="6285").strip()

if st.button("啟動研究任務", type="primary"):
    if not ticker_input:
        st.warning("請先輸入股票代號！")
    elif data_mode == "shioaji_only" and (not shioaji_key.strip() or not shioaji_secret.strip()):
        st.error("【強制 Shioaji 模式】必須填入 API Key 與 Secret Key！")
    else:
        payload = {
            "ticker": ticker_input,
            "shioaji_api_key": shioaji_key.strip(),
            "shioaji_secret_key": shioaji_secret.strip(),
            "simulation": is_simulation,
            "data_mode": data_mode
        }
        try:
            res = requests.post(f"{API_BASE_URL}/research", json=payload, timeout=5)
            if res.status_code == 202:
                job_id = res.json()["job_id"]
                st.info(f"🚀 任務已派發！任務 ID: `{job_id}`，正在調取行情資料...")
                status_ph = st.empty()
                done = False
                
                for _ in range(30):
                    s_res = requests.get(f"{API_BASE_URL}/research/{job_id}", timeout=5)
                    if s_res.status_code == 200:
                        jdata = s_res.json()
                        status = jdata.get("status")
                        if status == "completed":
                            result = jdata.get("result", {})
                            summary = result.get("summary", "無內容")
                            chart_records = result.get("chart_data", [])
                            
                            status_ph.success("✅ 行情數據加載完成！")
                            st.markdown(summary)
                            
                            if chart_records:
                                df_chart = pd.DataFrame(chart_records)
                                df_chart.set_index("date", inplace=True)
                                df_chart.rename(columns={
                                    "Close": "收盤價", 
                                    "MA5": "5日均線 (MA5)", 
                                    "MA20": "20日均線 (MA20)"
                                }, inplace=True)
                                
                                st.subheader("📉 近 30 日收盤價與均線走勢圖")
                                st.line_chart(df_chart[["收盤價", "5日均線 (MA5)", "20日均線 (MA20)"]])
                                
                                st.subheader("📊 近 30 日成交量柱狀圖 (Volume)")
                                st.bar_chart(df_chart["Volume"])
                                
                            done = True
                            break
                        elif status == "failed":
                            status_ph.error(f"❌ 任務失敗: {jdata.get('error_message')}")
                            done = True
                            break
                    time.sleep(1)
                if not done:
                    status_ph.warning("⚠️ 任務逾時，請檢查連線狀態。")
            else:
                st.error(f"後端派發失敗: {res.text}")
        except Exception as e:
            st.error(f"連線後端異常: {e}")