"""9:30 強勢股即時選股。

用法：
  python main.py              # 8:30 前啟動，自動跑盤前名單 → 試撮追蹤 → 9:00–9:30 確認
  python main.py --premarket  # 只產生盤前候選名單
  python main.py --once       # 不管時間，立刻抓一次行情並評估（測試用）
"""
import argparse
import csv
import datetime as dt
import time
import unicodedata
from pathlib import Path

from config import IntradayConfig
from intraday import OPEN, Tracker, scan_once
from mis import MisClient
from premarket import build_candidates

OUT = Path(__file__).parent / "output"
TRIAL_START, END = dt.time(8, 30), dt.time(9, 30)


def pad(s, width):
    s = str(s)
    w = sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)
    return s + " " * max(width - w, 0)


def pct(x):
    return "   -  " if x is None else f"{x:+6.2%}"


def print_candidates(cands, base_date):
    print(f"\n盤前候選 {len(cands)} 檔（依 {base_date:%Y-%m-%d} 收盤）")
    for c in cands[:30]:
        print(f"  #{c['rank']:<3} {c['code']} {pad(c['name'], 10)} 綜合{c['rank_score']:5.1f}"
              f"  條件{c['score']}  {' '.join(c['reasons'])}")
    if len(cands) > 30:
        print(f"  ...其餘 {len(cands) - 30} 檔見 CSV")


def save_csv(path, rows, fields):
    OUT.mkdir(exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def print_trials(trackers):
    rows = sorted(trackers.values(), key=lambda t: -t.combined_score())
    print(f"\n[{dt.datetime.now():%H:%M:%S}] 試撮排名（盤前綜合分＋試撮加減分，前 20）")
    for i, t in enumerate(rows[:20], 1):
        print(f"  {i:>2}. {t.c['code']} {pad(t.c['name'], 10)} {t.combined_score():5.1f}"
              f"  盤前#{t.c['rank']:<3} {t.trial_status()}")


def print_results(now, results, index_chg):
    print(f"\n[{now:%H:%M:%S}] 加權 {pct(index_chg)}   ✔=符合")
    print("  代號 名稱        結果          漲跌    相對大盤  量比  外盤  守開 回檔  試撮")
    for r in results:
        if r["verdict"] in ("-", "剔除:開高走低"):
            continue
        ch = r["checks"]
        outer = "  -  " if r["outer_ratio"] is None else f"{r['outer_ratio']:4.0%}"
        lock = f" 鎖{r['lock_bid']}張" if r["limit_locked"] else ""
        print(f"  {r['code']} {pad(r['name'], 10)} {pad(r['verdict'], 12)} {pct(r['chg'])} {pct(r['rs'])}"
              f" {r['vol_ratio']:5.1f} {outer}  {'✔' if ch['守開盤'] else '✘'}    {'✔' if ch['回檔守住'] else '·'}"
              f"   {r['trial']}{lock}")
    faded = [r["code"] for r in results if r["verdict"] == "剔除:開高走低"]
    if faded:
        print(f"  開高走低剔除：{' '.join(faded)}")


def wait_until(t):
    while dt.datetime.now().time() < t:
        time.sleep(5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--premarket", action="store_true")
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()

    cfg = IntradayConfig()
    today = dt.date.today()
    cands, base_date = build_candidates(today)
    print_candidates(cands, base_date)
    save_csv(OUT / f"{today:%Y%m%d}_candidates.csv",
             [dict(c, reasons=" ".join(c["reasons"])) for c in cands],
             ["rank", "code", "name", "rank_score", "score", "reasons", "close_pos", "chg_pct", "vol_ratio",
              "to_high_pct", "inst_ratio", "streak", "avg_value", "prev_close", "avg_vol"])
    if args.premarket or not cands:
        return

    mis = MisClient()
    trackers = {c["code"]: Tracker(c, cfg) for c in cands}
    fields = ["rank", "code", "name", "verdict", "last", "chg", "rs", "vol_ratio", "outer_ratio",
              "turnover", "limit_locked", "lock_bid", "trial", "premarket", "reasons", "passed"]

    if args.once:
        now, results, index_chg = scan_once(mis, trackers)
        if results:
            print_results(now, results, index_chg)
        else:
            print_trials(trackers)
        return

    if dt.datetime.now().time() < TRIAL_START:
        print(f"\n等待 {TRIAL_START:%H:%M} 試撮開始...")
        wait_until(TRIAL_START)
    while dt.datetime.now().time() < OPEN:
        for code, q in mis.quotes(list(trackers)).items():
            trackers[code].add_trial(dt.datetime.now(), q)
        print_trials(trackers)
        time.sleep(cfg.poll_seconds)

    results = []
    while dt.datetime.now().time() < END:
        now, results, index_chg = scan_once(mis, trackers)
        print_results(now, results, index_chg)
        save_csv(OUT / f"{today:%Y%m%d}_live.csv", results, fields)
        time.sleep(cfg.poll_seconds)

    final = OUT / f"{today:%Y%m%d}_0930.csv"
    save_csv(final, results, fields)
    print(f"\n9:30 結果已存到 {final}")


if __name__ == "__main__":
    main()
