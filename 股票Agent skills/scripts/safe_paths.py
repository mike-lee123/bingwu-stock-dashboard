"""共用的參數檢查：代號、日期格式，以及輸出路徑不可跑出指定資料夾。

這些腳本會由 AI 研究代理呼叫，參數與 report.json 都可能被網頁內容影響，
所以一律在寫檔前檢查，避免 ../ 之類的路徑穿越。
"""
import re
import sys
from pathlib import Path

TICKER_RE = re.compile(r"\^?[A-Z0-9][A-Z0-9.\-]{0,14}")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def check_ticker(raw):
    t = (raw or "").strip().upper()
    if not TICKER_RE.fullmatch(t) or ".." in t:
        sys.exit(f"代號格式不正確：{raw!r}")
    return t


def check_date(raw):
    d = str(raw or "")
    if not DATE_RE.fullmatch(d):
        sys.exit(f"as_of 日期格式應為 YYYY-MM-DD：{raw!r}")
    return d


def inside(path, base):
    """確認 path 解析後仍在 base 底下，回傳解析後的路徑。"""
    p, b = Path(path).resolve(), Path(base).resolve()
    if p != b and b not in p.parents:
        sys.exit(f"輸出路徑超出允許範圍：{p}")
    return p
