import hashlib
import os
import time
import pandas as pd
from datetime import datetime, timedelta
import yfinance as yf

try:
    import shioaji as sj
    SHIOAJI_AVAILABLE = True
except ImportError:
    SHIOAJI_AVAILABLE = False

# 每組 (金鑰, 模擬/正式) 各自一個連線；不同金鑰或模式絕不共用同一個 session
_sj_sessions = {}


def _session_key(ak: str, sk: str, simulation: bool) -> str:
    return hashlib.sha256(f"{ak}\0{sk}\0{bool(simulation)}".encode()).hexdigest()

STOCK_NAME_MAP = {
    "2330": "台積電", "2454": "聯發科", "2317": "鴻海", "2603": "長榮",
    "6285": "啟碁", "3008": "大立光", "2890": "永豐金", "2882": "國泰金",
    "2881": "富邦金", "3019": "亞光", "1560": "中砂", "8069": "元太",
    "2382": "廣達", "3231": "緯創", "2357": "華碩", "2308": "台達電"
}

def get_shioaji_client(api_key: str = "", secret_key: str = "", simulation: bool = True):
    if not SHIOAJI_AVAILABLE:
        return None, "未安裝 shioaji 套件"
    
    ak = api_key.strip() or os.getenv("SHIOAJI_API_KEY", "").strip()
    sk = secret_key.strip() or os.getenv("SHIOAJI_SECRET_KEY", "").strip()
    
    if not ak or not sk:
        return None, "未提供 Shioaji 金鑰"
    
    key = _session_key(ak, sk, simulation)
    if key in _sj_sessions:
        return _sj_sessions[key], "連線就緒"

    try:
        api = sj.Shioaji(simulation=simulation)
        api.login(api_key=ak, secret_key=sk)
        try:
            api.fetch_contracts(contract_type='Stock')
            for _ in range(10):
                if hasattr(api.Contracts, "Stocks") and hasattr(api.Contracts.Stocks, "TSE") and len(api.Contracts.Stocks.TSE) > 0:
                    break
                time.sleep(0.2)
        except Exception:
            pass
        _sj_sessions[key] = api
        return api, "連線成功"
    except Exception as e:
        return None, f"Shioaji 登入失敗: {e}"

def find_stock_contract(api, clean_sym: str):
    if not hasattr(api, "Contracts") or not hasattr(api.Contracts, "Stocks"):
        return None
    stocks = api.Contracts.Stocks
    if hasattr(stocks, "TSE"):
        try:
            if clean_sym in stocks.TSE:
                return stocks.TSE[clean_sym]
        except Exception:
            pass
    if hasattr(stocks, "OTC"):
        try:
            if clean_sym in stocks.OTC:
                return stocks.OTC[clean_sym]
        except Exception:
            pass
    try:
        if clean_sym in stocks:
            return stocks[clean_sym]
    except Exception:
        pass
    return None

def fetch_from_shioaji(ticker: str, api_key: str = "", secret_key: str = "", simulation: bool = True):
    api, msg = get_shioaji_client(api_key, secret_key, simulation)
    if not api:
        return None, msg

    clean_sym = ticker.strip().upper().replace(".TW", "").replace(".TWO", "")
    contract = find_stock_contract(api, clean_sym)
    if not contract:
        return None, f"Shioaji 合約清單無標的 {clean_sym}（模擬伺服器未開放或代碼有誤）"

    end_d = datetime.today().strftime('%Y-%m-%d')
    start_d = (datetime.today() - timedelta(days=90)).strftime('%Y-%m-%d')

    try:
        kbars = api.kbars(contract=contract, start=start_d, end=end_d)
        df = pd.DataFrame({**kbars})
        if df.empty or len(df) < 5:
            return None, "K線筆數不足"

        df["ts"] = pd.to_datetime(df["ts"])
        df.set_index("ts", inplace=True)
        df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
        df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce")
        df.dropna(subset=["Close"], inplace=True)

        df["MA5"] = df["Close"].rolling(5).mean()
        df["MA20"] = df["Close"].rolling(20).mean()
        df["VMA5"] = df["Volume"].rolling(5).mean()
        latest = df.iloc[-1]

        chart_df = df[["Close", "MA5", "MA20", "Volume"]].tail(30).copy()
        chart_records = []
        for dt_idx, row in chart_df.iterrows():
            chart_records.append({
                "date": dt_idx.strftime("%Y-%m-%d"),
                "Close": float(row["Close"]),
                "MA5": float(row["MA5"]) if pd.notnull(row["MA5"]) else float(row["Close"]),
                "MA20": float(row["MA20"]) if pd.notnull(row["MA20"]) else float(row["Close"]),
                "Volume": int(row["Volume"])
            })

        env_tag = "永豐 Shioaji 模擬環境" if simulation else "永豐 Shioaji 正式直連"
        stock_name = getattr(contract, "name", "") or STOCK_NAME_MAP.get(clean_sym, clean_sym)

        close_val = float(latest["Close"])
        ma20_val = float(latest["MA20"]) if pd.notnull(latest["MA20"]) else close_val
        bias20 = round(((close_val - ma20_val) / ma20_val) * 100, 2) if ma20_val > 0 else 0.0

        vma5_val = float(latest["VMA5"]) if pd.notnull(latest["VMA5"]) and latest["VMA5"] > 0 else float(latest["Volume"])
        vol_ratio = round(float(latest["Volume"]) / vma5_val, 2)

        return {
            "source": env_tag,
            "ticker": clean_sym,
            "name": stock_name,
            "close": close_val,
            "ma5": float(latest["MA5"]) if pd.notnull(latest["MA5"]) else close_val,
            "ma20": ma20_val,
            "bias20": bias20,
            "volume": int(latest["Volume"]),
            "vol_ratio": vol_ratio,
            "chart_data": chart_records
        }, "成功"
    except Exception as e:
        return None, f"K線擷取異常: {e}"

def fetch_from_yahoo_bundle(ticker: str):
    clean = ticker.strip().upper().replace(".TW", "").replace(".TWO", "")
    candidates = [f"{clean}.TW", f"{clean}.TWO"]
    df = None
    target_info = {}

    for sym in candidates:
        try:
            s = yf.Ticker(sym)
            h = s.history(period="3mo")
            if not h.empty and len(h) >= 5:
                df = h
                target_info = s.info or {}
                break
        except Exception:
            continue

    if df is None or df.empty:
        return None

    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce")
    df.dropna(subset=["Close"], inplace=True)
    df["MA5"] = df["Close"].rolling(5).mean()
    df["MA20"] = df["Close"].rolling(20).mean()
    df["VMA5"] = df["Volume"].rolling(5).mean()

    latest = df.iloc[-1]
    chart_df = df[["Close", "MA5", "MA20", "Volume"]].tail(30).copy()
    chart_records = []
    for dt_idx, row in chart_df.iterrows():
        chart_records.append({
            "date": dt_idx.strftime("%Y-%m-%d"),
            "Close": float(row["Close"]),
            "MA5": float(row["MA5"]) if pd.notnull(row["MA5"]) else float(row["Close"]),
            "MA20": float(row["MA20"]) if pd.notnull(row["MA20"]) else float(row["Close"]),
            "Volume": int(row["Volume"])
        })

    stock_name = STOCK_NAME_MAP.get(clean) or target_info.get("shortName") or target_info.get("longName") or clean
    close_val = float(latest["Close"])
    ma20_val = float(latest["MA20"]) if pd.notnull(latest["MA20"]) else close_val
    bias20 = round(((close_val - ma20_val) / ma20_val) * 100, 2) if ma20_val > 0 else 0.0

    vma5_val = float(latest["VMA5"]) if pd.notnull(latest["VMA5"]) and latest["VMA5"] > 0 else float(latest["Volume"])
    vol_ratio = round(float(latest["Volume"]) / vma5_val, 2)

    return {
        "source": "Yahoo Finance",
        "ticker": clean,
        "name": stock_name,
        "close": close_val,
        "ma5": float(latest["MA5"]) if pd.notnull(latest["MA5"]) else close_val,
        "ma20": ma20_val,
        "bias20": bias20,
        "volume": int(latest["Volume"]),
        "vol_ratio": vol_ratio,
        "chart_data": chart_records
    }

class MarketDataTool:
    @staticmethod
    def run(ticker: str, shioaji_api_key: str = "", shioaji_secret_key: str = "", simulation: bool = True, data_mode: str = "auto"):
        bundle = None
        sj_msg = ""

        # 模式判斷
        if data_mode == "shioaji_only":
            bundle, sj_msg = fetch_from_shioaji(ticker, shioaji_api_key, shioaji_secret_key, simulation)
            if not bundle:
                return {
                    "success": False,
                    "error": f"【強制 Shioaji 模式】失敗: {sj_msg}",
                    "text": f"⚠️ 【強制 Shioaji 模式】無法取得行情：{sj_msg}"
                }
        elif data_mode == "yahoo_only":
            bundle = fetch_from_yahoo_bundle(ticker)
            if not bundle:
                return {
                    "success": False,
                    "error": f"【強制 Yahoo 模式】查無標的 {ticker}",
                    "text": f"⚠️ 【強制 Yahoo 模式】查無標的 {ticker} 之行情數據。"
                }
        else: # auto
            bundle, sj_msg = fetch_from_shioaji(ticker, shioaji_api_key, shioaji_secret_key, simulation)
            if not bundle:
                bundle = fetch_from_yahoo_bundle(ticker)
            if not bundle:
                return {
                    "success": False,
                    "error": f"Shioaji: {sj_msg}，Yahoo 連線亦查無數據",
                    "text": f"⚠️ 無法取得標的【{ticker}】之行情數據。"
                }

        text_summary = f"""【{bundle['ticker']} {bundle['name']} 基本數據】 (數據來源: {bundle['source']})
最新收盤價: {bundle['close']:.2f} 元
5日均線 (MA5): {bundle['ma5']:.2f} 元 | 20日月線 (MA20): {bundle['ma20']:.2f} 元
20日乖離率 (BIAS20): {bundle['bias20']:+.2f}%
最近交易日成交量: {bundle['volume']:,} 股 (相對於5日均量比: {bundle['vol_ratio']:.2f} 倍)"""

        return {
            "success": True,
            "bundle": bundle,
            "text": text_summary
        }

fetch_stock_market_data = MarketDataTool()