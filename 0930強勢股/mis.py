"""證交所基本市況報導 (mis.twse.com.tw) 即時行情。資料約有 5 秒延遲。"""
import time

import requests

BASE = "https://mis.twse.com.tw/stock"
BATCH = 50


def _f(x):
    try:
        v = float(x)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _levels(s):
    """'101.5_101_100.5_' -> [101.5, 101.0, 100.5]"""
    return [float(x) for x in str(s or "").split("_") if _f(x)]


class MisClient:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "Mozilla/5.0"
        self.s.get(f"{BASE}/index.jsp", timeout=15)

    def _query(self, keys):
        r = self.s.get(f"{BASE}/api/getStockInfo.jsp",
                       params={"ex_ch": "|".join(keys), "json": 1, "delay": 0,
                               "_": int(time.time() * 1000)}, timeout=15)
        r.raise_for_status()
        return r.json().get("msgArray", [])

    def quotes(self, codes):
        out = {}
        keys = [f"tse_{c}.tw" for c in codes]
        for i in range(0, len(keys), BATCH):
            for m in self._query(keys[i:i + BATCH]):
                out[m["c"]] = parse(m)
            time.sleep(1.2)
        return out

    def index(self):
        m = self._query(["tse_t00.tw"])
        return parse(m[0]) if m else None


def parse(m):
    asks, bids = _levels(m.get("a")), _levels(m.get("b"))
    bid_sizes = [int(_f(x) or 0) for x in str(m.get("g") or "").split("_") if x.strip()]
    return {
        "time": m.get("t") or m.get("%"),
        "last": _f(m.get("z")),
        # 盤前試撮：pz 為試算參考成交價；沒有時退回 z
        "trial": _f(m.get("pz")) or _f(m.get("z")),
        "open": _f(m.get("o")),
        "high": _f(m.get("h")),
        "low": _f(m.get("l")),
        "prev_close": _f(m.get("y")),
        "volume": _f(m.get("v")) or 0.0,     # 累計成交張數
        "limit_up": _f(m.get("u")),
        "ask": asks[0] if asks else None,
        "bid": bids[0] if bids else None,
        "bid_size": bid_sizes[0] if bid_sizes else 0,
    }
