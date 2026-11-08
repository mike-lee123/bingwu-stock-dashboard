"""在背景啟動 6 人 AI 研究團隊（由儀表板的「新增研究」呼叫，也可手動執行）。

用法：
    python scripts/run_research.py NVDA

狀態寫在 work/<TICKER>/_job.json，Claude Code 的輸出寫在 work/<TICKER>/research.log。
已有 report.json 時自動改為「更新」模式（研究總監會先封存舊版）。
"""
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 研究流程實際用到的工具；其餘操作交給 auto 權限模式判斷，不使用 bypassPermissions
ALLOWED_TOOLS = [
    "Read", "Write", "Edit", "Glob", "Grep", "WebSearch", "WebFetch", "Agent", "Skill",
    "Bash(python *)", "Bash(export *)", "Bash(cd *)", "Bash(ls *)", "Bash(mkdir *)", "Bash(cp *)",
    "Bash(cat *)", "Bash(head *)", "Bash(tail *)",
]


def find_python():
    """找一個裝有 yfinance 與 matplotlib 的 Python（儀表板的 venv 不一定有）。"""
    candidates = [sys.executable, shutil.which("python"), shutil.which("python3")]
    py_launcher = shutil.which("py")
    if py_launcher:
        try:
            out = subprocess.run([py_launcher, "-3", "-c", "import sys; print(sys.executable)"],
                                 capture_output=True, text=True, timeout=30)
            candidates.append(out.stdout.strip())
        except (OSError, subprocess.SubprocessError):
            pass
    for py in filter(None, candidates):
        try:
            if subprocess.run([py, "-c", "import yfinance, matplotlib, pandas"],
                              capture_output=True, timeout=60).returncode == 0:
                return py
        except (OSError, subprocess.SubprocessError):
            continue
    return None


def now():
    return datetime.now().isoformat(timespec="seconds")


def write_job(path, **fields):
    job = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    job.update(fields)
    path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    ticker = sys.argv[1].upper()
    wd = ROOT / "work" / ticker
    wd.mkdir(parents=True, exist_ok=True)
    job = wd / "_job.json"
    log = wd / "research.log"

    claude = shutil.which("claude")
    if not claude:
        write_job(job, status="failed", finished=now(), error="找不到 claude 指令（Claude Code CLI 未安裝）")
        return

    py = find_python()
    if not py:
        write_job(job, status="failed", finished=now(),
                  error="找不到裝有 yfinance、matplotlib、pandas 的 Python，請先 pip install -r requirements.txt")
        return
    # 讓 Claude Code 裡執行的 python 指令也用到同一個環境
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    py_dir = str(Path(py).parent)
    env["PATH"] = os.pathsep.join([py_dir, str(Path(py_dir) / "Scripts"), env.get("PATH", "")])

    update = (wd / "report.json").exists()
    # 指令用英文：Windows 經 claude.cmd 轉傳參數時，中文可能因主控台字碼頁變成亂碼
    prompt = f"/research-director update {ticker}" if update else f"/research-director {ticker} latest earnings"
    write_job(job, ticker=ticker, status="running", mode="更新" if update else "新研究",
              started=now(), finished=None, returncode=None, error=None, reset=None)

    with log.open("w", encoding="utf-8") as out:
        out.write(f"[{now()}] {prompt}\n")
        out.flush()
        # 先抓股價，讓儀表板在研究進行中就有技術面圖可看
        subprocess.run([py, str(ROOT / "scripts" / "fetch_prices.py"), ticker],
                       cwd=ROOT, stdout=out, stderr=subprocess.STDOUT, env=env)
        rc = subprocess.run(
            [claude, "-p", prompt, "--permission-mode", "auto", "--allowedTools", *ALLOWED_TOOLS],
            cwd=ROOT, stdout=out, stderr=subprocess.STDOUT, env=env,
        ).returncode
        out.write(f"\n[{now()}] Claude Code 結束，returncode={rc}\n")

    ok = rc == 0 and (wd / "report.json").exists()
    if ok:
        write_job(job, status="done", finished=now(), returncode=rc, error=None)
        return
    tail = log.read_text(encoding="utf-8", errors="replace")[-2000:]
    limit = re.search(r"hit your (?:session|usage|weekly)? ?limit[^\n]*", tail, re.IGNORECASE)
    if limit:
        reset = re.search(r"resets? ([^\n]+)", limit.group(0))
        write_job(job, status="limited", finished=now(), returncode=rc,
                  reset=reset.group(1).strip() if reset else None,
                  error=f"Claude 用量已達上限（{limit.group(0).strip()}）。額度重置後按「從中斷處繼續」，已完成的部分會沿用。")
    else:
        write_job(job, status="failed", finished=now(), returncode=rc,
                  error="研究未完成定稿，請看執行記錄。按「從中斷處繼續」會沿用已完成的部分。")


if __name__ == "__main__":
    main()
