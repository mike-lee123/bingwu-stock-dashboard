"""研究完成後，把該檔的研究結果推上 GitHub，讓 Streamlit Cloud 版看得到。

用法：
    python scripts/publish_research.py 2330.TW

只提交這一檔的 work/<TICKER>/ 與 reports/<TICKER>_*.pdf，不會動到其他未提交的修改。
- 若本資料夾在 git repo 裡（ai_research_platform/股票Agent skills），直接提交。
- 若是桌面那份（不是 git repo），先把結果複製到 repo 裡的「股票Agent skills」再提交。
  repo 位置可用環境變數 BW_PUBLISH_REPO 指定（指向含 .git 的 ai_research_platform 資料夾）。
- 設定 BW_AUTO_PUBLISH=0 可暫停自動上傳。

注意：GitHub repo 是公開的，上傳後研究內容任何人都看得到。
"""
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIRNAME = "股票Agent skills"
DEFAULT_REPO = Path.home() / "Desktop" / "股市AI研究" / "ai_research_platform"
SKIP_DIRS = {"archive", "__pycache__"}


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失敗：{(r.stderr or r.stdout).strip()}")
    return r


def repo_root(path):
    r = git(path, "rev-parse", "--show-toplevel", check=False)
    return Path(r.stdout.strip()) if r.returncode == 0 else None


def find_target():
    """回傳 (repo 根目錄, repo 裡的「股票Agent skills」資料夾)。"""
    top = repo_root(ROOT)
    if top:
        return top, ROOT
    repo = Path(os.environ.get("BW_PUBLISH_REPO") or DEFAULT_REPO)
    top = repo_root(repo) if repo.exists() else None
    if not top or not (top / SKILLS_DIRNAME).is_dir():
        raise RuntimeError(f"找不到要上傳的 git repo（{repo}）。請設定 BW_PUBLISH_REPO。")
    return top, top / SKILLS_DIRNAME


def copy_results(ticker, dest):
    """桌面那份 → repo：複製 work/<TICKER>/（不含封存）與該檔的 PDF。"""
    src_work = ROOT / "work" / ticker
    if not src_work.is_dir():
        raise RuntimeError(f"找不到研究資料夾 {src_work}")
    shutil.copytree(src_work, dest / "work" / ticker, dirs_exist_ok=True,
                    ignore=lambda d, names: [n for n in names if n in SKIP_DIRS])
    (dest / "reports").mkdir(exist_ok=True)
    for pdf in (ROOT / "reports").glob(f"{ticker}_*.pdf"):
        shutil.copy2(pdf, dest / "reports" / pdf.name)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    ticker = sys.argv[1].strip().upper()
    if not re.fullmatch(r"\^?[A-Z0-9][A-Z0-9.\-]{0,14}", ticker):
        sys.exit(f"代號格式不正確：{ticker}")
    if os.environ.get("BW_AUTO_PUBLISH", "1") == "0":
        print("BW_AUTO_PUBLISH=0，略過上傳。")
        return

    top, dest = find_target()
    if dest != ROOT:
        copy_results(ticker, dest)
        print(f"已把 {ticker} 的研究複製到 {dest}")

    rel = dest.relative_to(top).as_posix()
    paths = [f"{rel}/work/{ticker}"] + [
        f"{rel}/reports/{p.name}" for p in (dest / "reports").glob(f"{ticker}_*.pdf")]
    git(top, "add", "--", *paths)
    if not git(top, "diff", "--cached", "--quiet", "--", *paths, check=False).returncode:
        print(f"{ticker} 沒有新的研究變更，不需上傳。")
        return
    git(top, "commit", "-m", f"research: {ticker} {date.today():%Y-%m-%d}", "--", *paths)
    if git(top, "push", check=False).returncode != 0:
        # 遠端有別的更新時，先接上再推一次
        git(top, "pull", "--rebase", "--autostash")
        git(top, "push")
    print(f"✅ 已上傳 {ticker} 的研究到 GitHub，Streamlit Cloud 重新部署後就看得到。")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        sys.exit(f"⚠️ 上傳失敗：{e}")
