"""盤前：用前一日收盤型態、量、前高、法人籌碼打分，產生候選名單。"""
import datetime as dt
import math
from pathlib import Path

from config import PremarketConfig
from twse_history import fetch_institutional, recent_trading_days

WATCHLIST = Path(__file__).parent / "watchlist.txt"


def load_watchlist():
    """watchlist.txt：手動加入族群、消息面標的，一行一個代號，# 後為註解。"""
    if not WATCHLIST.exists():
        return set()
    codes = set()
    for line in WATCHLIST.read_text(encoding="utf-8").splitlines():
        code = line.split("#")[0].strip()
        if code:
            codes.add(code)
    return codes


def _clip01(x):
    return max(0.0, min(1.0, x))


def rank_score(m):
    """盤前綜合分 0–100，讓同樣「條件數」的股票也能分出高下。

    收盤位置 20、前日漲幅 15、量比 20、距前高 15、法人買超 20（買超占均量 12＋連買天數 8）、流動性 10。
    """
    up = m["chg_pct"] > 0
    pts = 20 * m["close_pos"] if up else 0
    pts += 15 * _clip01(m["chg_pct"] / 10)                      # 漲停約 10% 滿分
    pts += 20 * _clip01((m["vol_ratio"] - 1) / 2)               # 量比 3 倍以上滿分
    gap = m["to_high_pct"]                                      # 收盤距前 N 日高點 (%)，>0 為突破
    pts += 15 if gap > 0 else 7.5 * _clip01(1 + gap / 5)        # 距前高 5% 內給部分分
    pts += 12 * _clip01(m["inst_ratio"] / 20)                   # 法人買超達均量 20% 滿分
    pts += 8 * _clip01(m["streak"] / 3)
    pts += 10 * _clip01((math.log10(max(m["avg_value"], 1)) - 8) / 2)  # 1 億 0 分、100 億滿分
    return round(pts, 1)


def score_stock(code, history, inst_days, cfg):
    """history: 由舊到新的 daily dict 清單，最後一筆是前一交易日。回傳 (條件數, 理由, 指標) 或 None。"""
    rows = [d.get(code) for d in history]
    if any(r is None for r in rows[-(cfg.avg_days + 1):]):
        return None
    d0 = rows[-1]
    prev = rows[-(cfg.avg_days + 1):-1]
    avg_value = sum(r["value"] for r in prev) / len(prev)
    if avg_value < cfg.min_avg_value:
        return None

    score, reasons = 0, []
    rng = d0["high"] - d0["low"]
    close_pos = 1.0 if rng == 0 else (d0["close"] - d0["low"]) / rng
    if d0["change"] > 0 and close_pos >= cfg.close_near_high:
        score += 1
        reasons.append("收近最高")

    avg_vol = sum(r["volume"] for r in prev) / len(prev)
    vol_ratio = d0["volume"] / avg_vol if avg_vol else 0
    if vol_ratio >= cfg.volume_surge:
        score += 1
        reasons.append(f"量增{vol_ratio:.1f}倍")

    prior_highs = [r["high"] for r in rows[:-1] if r and r["high"]]
    prior_high = max(prior_highs) if prior_highs else d0["close"]
    if prior_highs and d0["close"] > prior_high:
        score += 1
        reasons.append(f"突破{len(prior_highs)}日高")

    net = [sum(day.get(code, (0, 0))) for day in inst_days]
    streak = 0
    for x in reversed(net):
        if x <= 0:
            break
        streak += 1
    if streak >= 1:
        score += 1
        if streak >= 2:
            score += 1
        reasons.append(f"外資+投信連{streak}買")

    prev_close = d0["close"] - d0["change"]
    metrics = {
        "close_pos": close_pos,
        "chg_pct": d0["change"] / prev_close * 100 if prev_close else 0,
        "vol_ratio": vol_ratio,
        "to_high_pct": (d0["close"] / prior_high - 1) * 100,
        "inst_ratio": (net[-1] / 1000) / avg_vol * 100 if net and avg_vol else 0,  # 法人買超張數 / 5 日均量
        "streak": streak,
        "avg_value": avg_value,
        "avg_vol": avg_vol,
    }
    metrics["rank_score"] = rank_score(metrics)
    return score, reasons, metrics


def build_candidates(today=None, cfg=PremarketConfig(), extra_codes=()):
    """extra_codes：額外強制追蹤的代號（例如儀表板選的族群），與 watchlist.txt 同等對待。"""
    today = today or dt.date.today()
    print("載入歷史收盤資料（第一次較久，之後讀快取）...", flush=True)
    days = recent_trading_days(cfg.lookback_days + 1, today)
    if len(days) < cfg.avg_days + 1:
        raise RuntimeError("歷史資料不足，請確認網路或證交所網站狀態")
    history = [d for _, d in days]
    inst_days = [x for x in (fetch_institutional(date) for date, _ in days[-3:]) if x]

    watch = load_watchlist() | set(extra_codes)
    last = history[-1]
    cands = []
    for code, row in last.items():
        res = score_stock(code, history, inst_days, cfg)
        if res is None:
            continue
        score, reasons, metrics = res
        if score >= cfg.min_score or code in watch:
            if code in watch:
                reasons = reasons + ["自選"]
            cands.append({"code": code, "name": row["name"], "score": score, "reasons": reasons,
                          "prev_close": row["close"], **metrics})
    cands.sort(key=lambda c: (-c["rank_score"], -c["score"], c["code"]))
    cands = cands[:cfg.max_candidates]
    for i, c in enumerate(cands, 1):
        c["rank"] = i
    return cands, days[-1][0]
