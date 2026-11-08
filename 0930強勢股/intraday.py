"""盤中：8:30–9:00 追蹤試撮，9:00–9:30 逐次快照確認強勢。"""
import datetime as dt

from config import IntradayConfig

OPEN = dt.time(9, 0)
VERDICT_ORDER = {"強勢+鎖漲停": 0, "強勢": 1, "偏強": 2, "觀察:前5分鐘": 3, "-": 4, "剔除:開高走低": 5}


def scan_once(mis, trackers):
    """抓一次行情：9:00 前記錄試撮，之後更新並評估。回傳 (時間, 評估結果, 加權漲跌幅)。"""
    now = dt.datetime.now()
    quotes = mis.quotes(list(trackers))
    idx = mis.index()
    index_chg = idx["last"] / idx["prev_close"] - 1 if idx and idx["last"] and idx["prev_close"] else None
    results = []
    for code, q in quotes.items():
        tr = trackers[code]
        if now.time() < OPEN:
            tr.add_trial(now, q)
        else:
            tr.update(now, q)
        r = tr.evaluate(now, index_chg)
        if r:
            results.append(r)
    results.sort(key=lambda r: (VERDICT_ORDER.get(r["verdict"], 9), -r["passed"], -r["rank_score"]))
    return now, results, index_chg


def minutes_since_open(t):
    return (t.hour * 60 + t.minute + t.second / 60) - (9 * 60)


def expected_fraction(minutes, curve):
    """依開盤後分鐘數，線性內插出累計量占全日量的比例。"""
    pts = sorted(curve.items())
    if minutes <= pts[0][0]:
        return pts[0][1] * max(minutes, 0.5) / pts[0][0]
    for (m0, f0), (m1, f1) in zip(pts, pts[1:]):
        if minutes <= m1:
            return f0 + (f1 - f0) * (minutes - m0) / (m1 - m0)
    return pts[-1][1]


class Tracker:
    """單一股票的盤中狀態。每次輪詢呼叫 update()。"""

    def __init__(self, cand, cfg=IntradayConfig()):
        self.c, self.cfg = cand, cfg
        self.trials = []            # [(time, 試撮價)]
        self.prices = []            # [(time, 成交價)] 9:00 後
        self.outer = self.inner = 0.0
        self.prev = None
        self.lock_bids = []         # 漲停鎖單委買張數

    # ---------- 盤前試撮 ----------
    def add_trial(self, now, q):
        if q["trial"]:
            self.trials.append((now, q["trial"]))

    def trial_points(self):
        """試撮加減分（-15～+15）：試撮漲幅 -3%～+5% 線性給分，從高點下修再扣 10 分。"""
        if not self.trials:
            return 0.0
        y = self.c["prev_close"]
        last = self.trials[-1][1]
        chg = (last / y - 1) * 100
        pts = -5 + 15 * min(max((chg + 3) / 8, 0), 1) - 5 * (chg < -3)
        if last < max(p for _, p in self.trials) * (1 - self.cfg.trial_fade):
            pts -= 10
        return round(max(-15.0, min(15.0, pts)), 1)

    def combined_score(self):
        """盤前綜合分 + 試撮加減分，用於 9:00 前排序。"""
        return round(self.c.get("rank_score", 0) + self.trial_points(), 1)

    def trial_status(self):
        y = self.c["prev_close"]
        if not self.trials:
            return "無試撮"
        last = self.trials[-1][1]
        peak = max(p for _, p in self.trials)
        chg = last / y - 1
        if last < peak * (1 - self.cfg.trial_fade):
            return f"試撮下修{chg:+.1%}"
        if last <= y:
            return f"試撮平低{chg:+.1%}"
        early = self.trials[len(self.trials) // 2][1]
        return f"試撮走高{chg:+.1%}" if last >= early else f"試撮持平{chg:+.1%}"

    # ---------- 開盤後 ----------
    def update(self, now, q):
        last = q["last"]
        if last is None:
            return
        self.q = q
        self.prices.append((now, last))
        if self.prev is not None:
            dv = q["volume"] - self.prev["volume"]
            if dv > 0:
                # 逐次快照的內外盤近似：成交價打到上一筆委賣算外盤、打到委買算內盤，其餘依漲跌
                p = self.prev
                if p["ask"] and last >= p["ask"]:
                    self.outer += dv
                elif p["bid"] and last <= p["bid"]:
                    self.inner += dv
                elif p["last"] and last > p["last"]:
                    self.outer += dv
                elif p["last"] and last < p["last"]:
                    self.inner += dv
        if q["limit_up"] and last >= q["limit_up"] and q["ask"] is None:
            self.lock_bids.append(q["bid_size"])
        self.prev = q

    def evaluate(self, now, index_chg):
        """回傳 dict：各訊號結果與總結。"""
        if not self.prices:
            return None
        q, cfg, y = self.q, self.cfg, self.c["prev_close"]
        last, o = q["last"], q["open"] or self.prices[0][1]
        low = q["low"] or min(p for _, p in self.prices)
        mins = minutes_since_open(now.time())

        support = min(o, y)
        held = low >= support * (1 - cfg.hold_tolerance) and last >= o * (1 - cfg.hold_tolerance)
        gap_fade = o > y and last < o * (1 - cfg.hold_tolerance)

        chg = last / y - 1
        rs = chg - index_chg if index_chg is not None else None

        est_vol = q["volume"] / expected_fraction(mins, cfg.volume_curve) if mins > 0 else 0
        vol_ratio = est_vol / self.c["avg_vol"] if self.c["avg_vol"] else 0

        traded = self.outer + self.inner
        outer_ratio = self.outer / traded if traded else None
        turnover = q["volume"] * 1000 * last

        # 9:05 之後的回檔低點：守在支撐之上，且現價已站回低點之上
        after = [p for t, p in self.prices if minutes_since_open(t.time()) >= 5]
        pullback_low = min(after) if after else None
        pullback_ok = (pullback_low is not None and mins >= 15
                       and pullback_low >= support * (1 - cfg.hold_tolerance) and last > pullback_low)

        limit_locked = bool(self.lock_bids) and q["ask"] is None and last >= (q["limit_up"] or 1e18)
        lock_growing = limit_locked and len(self.lock_bids) >= 2 and self.lock_bids[-1] >= self.lock_bids[0]

        checks = {
            "守開盤": held,
            "強於大盤": rs is not None and rs > 0,
            "放量": vol_ratio >= cfg.volume_ratio,
            "外盤": outer_ratio is not None and outer_ratio >= cfg.min_outer_ratio,
            "流動性": turnover >= cfg.min_turnover_0930 * min(1.0, max(mins, 1) / 30),
            "回檔守住": pullback_ok,
        }
        core = ("守開盤", "強於大盤", "放量", "流動性")
        if gap_fade:
            verdict = "剔除:開高走低"
        elif mins < 5:
            verdict = "觀察:前5分鐘"
        elif all(checks[k] for k in core) and (checks["回檔守住"] or mins < 15):
            verdict = "強勢" + ("+鎖漲停" if limit_locked else "")
        elif sum(checks.values()) >= 4:
            verdict = "偏強"
        else:
            verdict = "-"
        return {
            "code": self.c["code"], "name": self.c["name"], "verdict": verdict,
            "last": last, "chg": chg, "rs": rs, "vol_ratio": vol_ratio, "outer_ratio": outer_ratio,
            "turnover": turnover, "limit_locked": limit_locked, "lock_growing": lock_growing,
            "lock_bid": self.lock_bids[-1] if self.lock_bids else 0,
            "checks": checks, "passed": sum(checks.values()),
            "premarket": self.c["score"], "reasons": " ".join(self.c["reasons"]),
            "rank": self.c.get("rank"), "rank_score": self.c.get("rank_score", 0),
            "trial": self.trial_status(),
        }
