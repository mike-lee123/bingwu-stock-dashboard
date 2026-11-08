"""證交所盤後資料：每日收盤行情 (MI_INDEX) 與三大法人 (T86)，快取在 data/。"""
import datetime as dt
import json
import time
from pathlib import Path

import requests

DATA_DIR = Path(__file__).parent / "data"
HEADERS = {"User-Agent": "Mozilla/5.0"}
REQUEST_GAP = 3.5  # 證交所連續請求太快會被暫時封鎖


def _num(s):
    s = str(s).replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _is_common_stock(code):
    return len(code) == 4 and code.isdigit() and not code.startswith("0")


def _cached_get(url, cache_file):
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8")), False
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    payload = r.json()
    DATA_DIR.mkdir(exist_ok=True)
    cache_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload, True


def fetch_daily(date):
    """回傳 {代號: {name, volume(張), value, open, high, low, close, change}}；休市回傳 None。"""
    ymd = date.strftime("%Y%m%d")
    url = f"https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={ymd}&type=ALLBUT0999"
    payload, fetched = _cached_get(url, DATA_DIR / f"daily_{ymd}.json")
    if fetched:
        time.sleep(REQUEST_GAP)
    table = next((t for t in payload.get("tables", [])
                  if t.get("fields") and t["fields"][0] == "證券代號" and len(t.get("data", [])) > 500), None)
    if table is None:
        return None
    out = {}
    for row in table["data"]:
        code = row[0].strip()
        if not _is_common_stock(code):
            continue
        o, h, l, c = (_num(x) for x in row[5:9])
        if not c:
            continue
        sign = -1 if "-" in row[9] else 1
        out[code] = {
            "name": row[1].strip(), "volume": (_num(row[2]) or 0) / 1000, "value": _num(row[4]) or 0,
            "open": o, "high": h, "low": l, "close": c, "change": sign * (_num(row[10]) or 0),
        }
    return out


def fetch_institutional(date):
    """回傳 {代號: (外資淨買股數, 投信淨買股數)}；休市回傳 None。"""
    ymd = date.strftime("%Y%m%d")
    url = f"https://www.twse.com.tw/fund/T86?response=json&date={ymd}&selectType=ALLBUT0999"
    payload, fetched = _cached_get(url, DATA_DIR / f"t86_{ymd}.json")
    if fetched:
        time.sleep(REQUEST_GAP)
    if payload.get("stat") != "OK":
        return None
    return {row[0].strip(): (_num(row[4]) or 0, _num(row[10]) or 0) for row in payload["data"]}


def recent_trading_days(n, before):
    """從 before 前一天往回找 n 個有資料的交易日，回傳 [(date, daily)]，由舊到新。"""
    days, d, misses = [], before - dt.timedelta(days=1), 0
    while len(days) < n and misses < 15:
        if d.weekday() < 5:
            daily = fetch_daily(d)
            if daily:
                days.append((d, daily))
                misses = 0
                print(f"  已載入 {d:%Y-%m-%d} 收盤資料（{len(daily)} 檔）", flush=True)
            else:
                misses += 1
        d -= dt.timedelta(days=1)
    return list(reversed(days))
