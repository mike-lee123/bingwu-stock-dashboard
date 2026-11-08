"""研究完成後，把該檔的研究結果推上 GitHub，讓 Streamlit Cloud 版看得到。

用法：
    python scripts/publish_research.py 2330.TW

只提交這一檔的 work/<TICKER>/ 裡的 .json/.md/.csv/.png（每檔 ≤5MB，不含 archive/）與
reports/<TICKER>_*.pdf，不會動到其他未提交的修改。上傳前會掃描金鑰／密碼，發現就停止；
分支上若已有你自己尚未推送的 commit，也不會自動推送。
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
# 只上傳研究流程會產生的檔案類型；其他檔案（log、意外寫入的東西）一律不上傳
ALLOWED_EXT = {".json", ".md", ".csv", ".png"}
MAX_BYTES = 5 * 1024 * 1024
SECRET_PATTERNS = [
    re.compile(p) for p in (
        r"sk-ant-[A-Za-z0-9_\-]{10,}",                  # Anthropic
        r"sk-[A-Za-z0-9]{32,}",                         # OpenAI 類
        r"AIza[0-9A-Za-z_\-]{35}",                      # Google
        r"gh[pousr]_[A-Za-z0-9]{30,}",                  # GitHub token
        r"AKIA[0-9A-Z]{16}",                            # AWS
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        r"(?i)(api[_-]?key|secret[_-]?key|password)\s*[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{16,}",
    )
]


def publishable(path):
    return path.is_file() and path.suffix.lower() in ALLOWED_EXT and path.stat().st_size <= MAX_BYTES


def collect_files(dest, ticker):
    """回傳要上傳的檔案（work/<TICKER>/ 的白名單檔案 + 該檔 PDF）。"""
    files = []
    for p in sorted((dest / "work" / ticker).rglob("*")):
        if not SKIP_DIRS.intersection(p.relative_to(dest / "work" / ticker).parts) and publishable(p):
            files.append(p)
    files += [p for p in sorted((dest / "reports").glob(f"{ticker}_*.pdf")) if p.stat().st_size <= MAX_BYTES * 4]
    return files


def scan_secrets(files):
    hits = []
    for p in files:
        if p.suffix.lower() in {".png", ".pdf"}:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if any(rx.search(text) for rx in SECRET_PATTERNS):
            hits.append(p.name)
    return hits


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

    files = collect_files(dest, ticker)
    if not files:
        raise RuntimeError(f"{ticker} 沒有可上傳的研究檔案。")
    hits = scan_secrets(files)
    if hits:
        raise RuntimeError(f"這些檔案看起來含有金鑰或密碼，已停止上傳：{'、'.join(hits)}。請檢查後再手動上傳。")

    # 只推這一個研究 commit：分支上若已有其他尚未推送的 commit，就不自動推，避免一起被公開
    git(top, "fetch", "--quiet", check=False)
    ahead = git(top, "rev-list", "--count", "@{u}..HEAD", check=False)
    if ahead.returncode != 0:
        raise RuntimeError("目前分支沒有設定遠端追蹤分支（upstream），不自動上傳。")
    if int(ahead.stdout.strip() or 0) > 0:
        raise RuntimeError("分支上已有你自己尚未推送的 commit，為避免一起公開，這次不自動上傳。"
                           "請先自行 git push，再重跑本指令。")

    paths = [p.relative_to(top).as_posix() for p in files]
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
