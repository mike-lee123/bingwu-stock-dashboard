from app.tools.market_tools import fetch_stock_market_data

def generate_local_report(ticker: str, raw_market_data: str, note_msg: str = "") -> str:
    return f"""### 📊 台股技術與量化策略報告（本地量化模式）
{f"> ⚠️ **系統提示**：{note_msg}" if note_msg else ""}

{raw_market_data}

---
### 📈 技術面均線與量價排列判讀
- **短中期均線格局**：
  - 現價若低於 MA5 與 MA20，短線屬於空方拉回整理格局，MA20 構成反彈主要反壓。
  - 現價若站穩 MA5 且 MA5 > MA20，則屬強勢多頭排列，可沿 5 日線順勢觀察。
  - 均線糾結時表示進入整理沉澱期，應關注帶量突破之方向。

### ⚖️ 關鍵操作策略與風險警示
- **多空防守點**：以 20 日月線（MA20）為短中期多空分水嶺，跌破宜做好資金水位控管。
- **風險提示**：注意大盤系統性波動風險，切忌在出量跌破支撐時逆勢摸底。
"""

def run_stock_research(ticker: str, gemini_api_key: str = None, shioaji_api_key: str = "", shioaji_secret_key: str = "", simulation: bool = True, data_mode: str = "auto") -> dict:
    result = fetch_stock_market_data.run(
        ticker=ticker,
        shioaji_api_key=shioaji_api_key,
        shioaji_secret_key=shioaji_secret_key,
        simulation=simulation,
        data_mode=data_mode
    )

    if not result["success"]:
        return {
            "ticker": ticker,
            "summary": result["text"],
            "chart_data": [],
            "mode": "error"
        }

    raw_text = result["text"]
    chart_data = result["bundle"]["chart_data"]

    report = generate_local_report(ticker, raw_text, f"資料來源模式：{data_mode}")
    return {
        "ticker": ticker,
        "summary": report,
        "chart_data": chart_data,
        "mode": "completed"
    }