"""AI 投資研究團隊儀表板模組：讀取 work/<TICKER>/ 的研究成果與 reports/ 的 PDF。

獨立執行：streamlit run app.py
嵌入其他 Streamlit 應用：import research_dashboard as rd; rd.render_cabin(api=已登入的 Shioaji 物件)
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work"
REPORTS = ROOT / "reports"

ROLES = [("macro", "總經"), ("industry", "產業"), ("fundamental", "基本面"), ("technical", "技術面")]
STANCE = {"bullish": "看多", "neutral": "中性", "bearish": "看空"}
SEVERITY = {"fatal": "🔴 致命", "major": "🟠 重大", "minor": "⚪ 次要"}
STATUS = {"resolved": "✅ 已化解", "partially": "◐ 部分化解", "unresolved": "❌ 未化解"}
LEVEL = {"高": "🔴 高", "中": "🟠 中", "低": "🟢 低"}
SERIES = ["#2a78d6", "#eb6834", "#6250d6"]  # 分類色：依序固定使用

# ---------- 資料讀取 ----------

def mtime_key(d):
    return tuple(sorted((f.name, f.stat().st_mtime) for f in d.glob("*") if f.is_file()))


@st.cache_data
def load_ticker(ticker, key):
    d = WORK / ticker

    def j(name):
        p = d / f"{name}.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    prices = None
    if (d / "prices.csv").exists():
        prices = pd.read_csv(d / "prices.csv", index_col=0, parse_dates=True)
        prices = prices[prices["Volume"] > 0]
    return {
        "report": j("report"),
        "analysts": {r: j(r) for r, _ in ROLES},
        "da": j("devils-advocate") or {},
        "rebuttal": {x["id"]: x for x in (j("rebuttal") or {}).get("responses", [])},
        "ind": j("indicators") or {},
        "prices": prices,
        "brief": (d / "brief.md").read_text(encoding="utf-8") if (d / "brief.md").exists() else "",
        "draft": (d / "draft.md").read_text(encoding="utf-8") if (d / "draft.md").exists() else "",
        "job": j("_job"),
    }


def list_tickers():
    if not WORK.exists():
        return []
    return sorted(p.name for p in WORK.iterdir()
                  if p.is_dir() and p.name != "DEMO"
                  and ((p / "brief.md").exists() or (p / "_job.json").exists()))


def is_tw(ticker):
    return ticker.endswith((".TW", ".TWO"))


def money(x, cur):
    try:
        return f"{cur} {float(x):,.2f}" if cur == "USD" else f"{cur} {float(x):,.0f}"
    except (TypeError, ValueError):
        return "—"


# ---------- 永豐證券 API（Shioaji） ----------
# 金鑰只存在本次瀏覽工作階段的記憶體中：不寫入檔案、快取或日誌，關閉頁面即消失。
# 本儀表板只讀取報價，不提供下單功能。

def sinopac_panel():
    st.subheader("🔑 永豐證券 API")
    api = st.session_state.get("sj_api")
    if api:
        st.success(f"已連線（{st.session_state['sj_env']}環境）")
        if st.button("登出", icon=":material/logout:"):
            try:
                api.logout()
            except Exception:
                pass
            del st.session_state["sj_api"]
            st.rerun()
        return
    with st.form("sinopac_login", clear_on_submit=True, border=False):
        key = st.text_input("API Key", type="password", placeholder="請輸入永豐 API Key")
        secret = st.text_input("Secret Key", type="password", placeholder="請輸入永豐 Secret Key")
        sim = st.toggle("模擬環境", value=False, help="模擬環境用於測試；正式環境才有即時行情。")
        submitted = st.form_submit_button("連線", icon=":material/link:")
    st.caption("金鑰只保存在這次瀏覽的記憶體中，不會寫入檔案；關閉頁面即清除。本儀表板只讀取報價，不會下單。")
    if not submitted:
        return
    if not key.strip() or not secret.strip():
        st.warning("請填寫 API Key 與 Secret Key。")
        return
    with st.spinner("連線中，下載商品檔約需 10–30 秒…"):
        try:
            import shioaji as sj
            api = sj.Shioaji(simulation=sim)
            api.login(api_key=key.strip(), secret_key=secret.strip(),
                      fetch_contract=True, contracts_timeout=30000)
        except Exception as e:
            st.error(f"連線失敗：{type(e).__name__}：{str(e)[:150]}")
            return
    st.session_state["sj_api"] = api
    st.session_state["sj_env"] = "模擬" if sim else "正式"
    st.rerun()


def sinopac_quote(ticker, api=None):
    api = api or st.session_state.get("sj_api")
    if not api or not is_tw(ticker):
        return None
    try:
        snap = api.snapshots([api.Contracts.Stocks[ticker.split(".")[0]]])[0]
    except Exception as e:
        return {"error": f"{type(e).__name__}：{str(e)[:120]}"}
    return {"close": snap.close, "change_price": snap.change_price, "change_rate": snap.change_rate,
            "volume": snap.total_volume, "time": pd.Timestamp(snap.ts).strftime("%Y-%m-%d %H:%M:%S")}


@st.fragment(run_every="30s")
def live_quote(ticker, target, api=None):
    q = sinopac_quote(ticker, api)
    if q is None:
        return
    if "error" in q:
        st.warning(f"永豐報價讀取失敗：{q['error']}")
        return
    c = st.columns(4)
    c[0].metric("永豐即時成交價", f"TWD {q['close']:,.2f}", f"{q['change_price']:+,.2f}（{q['change_rate']:+.2f}%）",
                delta_color="inverse")
    c[1].metric("成交量（張）", f"{q['volume']:,}")
    if target:
        c[2].metric("相對目標價", f"{(float(target) / q['close'] - 1) * 100:+.1f}%")
    c[3].metric("報價時間", q["time"][11:], q["time"][:10], delta_color="off")
    st.caption("每 30 秒自動更新；資料來源：永豐證券 Shioaji。")


def stage(data):
    job = data.get("job") or {}
    if job.get("status") == "failed":
        return "❌ 研究中斷（看執行記錄）"
    if job.get("status") == "limited":
        return f"⏸ 用量上限（{job.get('reset') or '稍後'}重置）"
    running = job.get("status") == "running"
    if job.get("mode") == "更新" and running:
        return "🔄 更新中"
    if data["report"]:
        return "已定稿"
    if data["da"]:
        s = "答辯中"
    elif data["draft"]:
        s = "風控審查中"
    elif data["brief"]:
        done = sum(1 for v in data["analysts"].values() if v)
        s = f"分析師研究中（{done}/4 已交件）"
    else:
        s = "啟動中"
    return f"⏳ {s}" if running else s


# ---------- 從儀表板新增研究 ----------
# 按鈕會在背景啟動 Claude Code（scripts/run_research.py），會花費 Claude 用量並執行約 15–30 分鐘。
# 只允許從本機（localhost）操作：宿主儀表板若開在區網，其他人不能替你啟動研究。

MAX_RUNNING = 1  # 一次研究會派出 5 個子代理，同時跑多檔很快就會碰到 Claude 用量上限


def normalize_ticker(raw):
    t = raw.strip().upper()
    if re.fullmatch(r"\d{4,6}[A-Z]?", t):  # 只打數字代號時視為台股上市
        t += ".TW"
    return t if re.fullmatch(r"\^?[A-Z0-9][A-Z0-9.\-]{0,14}", t) else None


def can_launch():
    if not shutil.which("claude"):
        return False, ("雲端版（或沒裝 Claude Code 的電腦）無法直接用你的 Claude 訂閱啟動研究。"
                       "在本機雙擊 start_dashboard.bat 開 http://localhost:8501，這裡就會變成「🚀 開始研究」按鈕。")
    host = (st.context.headers.get("Host") or "").split(":")[0]
    if host not in ("localhost", "127.0.0.1"):
        return False, f"為避免他人替你啟動研究，只能從本機開啟（http://localhost:…）時使用；目前為 {host}。"
    return True, ""


def running_jobs():
    jobs = []
    for d in WORK.glob("*/_job.json") if WORK.exists() else []:
        try:
            job = json.loads(d.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if job.get("status") == "running":
            jobs.append(d.parent.name)
    return jobs


def yahoo_has(ticker):
    import yfinance as yf
    try:
        hist = yf.Ticker(ticker).history(period="5d")
    except Exception:
        return False
    return hist is not None and not hist.empty


def launch_research(ticker):
    if not yahoo_has(ticker):
        return False, f"Yahoo Finance 查不到 {ticker}。台股上櫃請加 .TWO（例如 3105.TWO）。"
    if ticker in running_jobs():
        return False, f"{ticker} 已經在研究中。"
    if len(running_jobs()) >= MAX_RUNNING:
        busy = "、".join(running_jobs())
        return False, f"已有研究進行中（{busy}），一次只跑 {MAX_RUNNING} 檔，請等它完成再新增。"
    wd = WORK / ticker
    wd.mkdir(parents=True, exist_ok=True)
    (wd / "_job.json").write_text(json.dumps({"ticker": ticker, "status": "running", "mode": "排程中"},
                                             ensure_ascii=False), encoding="utf-8")
    flags = 0
    if sys.platform == "win32":
        # 不用 DETACHED_PROCESS：沒有主控台時，子程序會收到 Ctrl+C 事件而中斷
        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([sys.executable, str(ROOT / "scripts" / "run_research.py"), ticker], cwd=ROOT,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=flags, close_fds=True)
    return True, f"已在背景啟動 {ticker} 的研究，約 15–30 分鐘完成，總覽會自動更新進度。"


# ---------- 雲端啟動（GitHub Actions） ----------
# Streamlit Secrets 設定 GITHUB_TOKEN（只對本 repo 有 Actions 讀寫權限的 fine-grained token）即啟用。
WORKFLOW_FILE = "research.yml"
DEFAULT_REPO = "mike-lee123/bingwu-stock-dashboard"


def _secret(name, default=""):
    try:
        return st.secrets.get(name, default)
    except Exception:  # 沒有 secrets.toml 時 st.secrets 會丟例外
        return default


def cloud_config():
    """兩種啟用方式：
    1. 側邊欄填 GitHub Token（只存在這次瀏覽工作階段）：持有 token 就是授權，不需另設密碼。
    2. Streamlit Secrets 設 GITHUB_TOKEN：必須同時設 LAUNCH_PASSWORD，否則不開放，避免看得到頁面的人花你的錢。
    """
    repo = _secret("GITHUB_REPO", DEFAULT_REPO)
    limit = int(_secret("CLOUD_DAILY_LIMIT", 3))
    session_token = (st.session_state.get("rs_gh_token") or "").strip()
    if session_token:
        if not token_status(session_token, repo):
            return None
        return {"token": session_token, "password": None, "repo": repo, "limit": limit}
    token, password = _secret("GITHUB_TOKEN"), _secret("LAUNCH_PASSWORD")
    if not token or not password:
        return None
    return {"token": token, "password": password, "repo": repo, "limit": limit}


def password_ok(entered, cfg):
    if cfg["password"] is None:  # 側邊欄 token 模式
        return True
    import hmac
    return hmac.compare_digest((entered or "").encode(), cfg["password"].encode())


def set_repo_secret(token, repo, name, value):
    """用 repo 的公鑰加密後寫入 GitHub Actions Secret（GitHub 規定的 sealed box 加密）。"""
    import base64
    from nacl import encoding, public
    code, key = gh_api("GET", f"/repos/{repo}/actions/secrets/public-key", token)
    if code != 200:
        return False, f"讀不到 repo 公鑰（HTTP {code}）。token 需要 Secrets 讀寫權限。"
    box = public.SealedBox(public.PublicKey(key["key"].encode(), encoding.Base64Encoder()))
    sealed = base64.b64encode(box.encrypt(value.encode())).decode()
    code, _ = gh_api("PUT", f"/repos/{repo}/actions/secrets/{name}", token,
                     {"encrypted_value": sealed, "key_id": key["key_id"]})
    if code in (201, 204):
        return True, f"✅ 已加密存到 GitHub Secrets（{name}）。"
    return False, f"寫入失敗（HTTP {code}）。token 需要 Secrets 讀寫權限。"


@st.cache_data(ttl=60, show_spinner=False)
def repo_secret_exists(token, repo, name):
    code, _ = gh_api("GET", f"/repos/{repo}/actions/secrets/{name}", token)
    return {200: True, 404: False}.get(code)


@st.cache_data(ttl=300, show_spinner=False)
def token_status(token, repo):
    code, _ = gh_api("GET", f"/repos/{repo}", token)
    return code == 200


def cloud_sidebar():
    """左側欄：雲端研究設定。GitHub Token 只存在本次工作階段；Anthropic 金鑰加密後存到 GitHub。"""
    sb = st.sidebar
    sb.markdown("---")
    sb.markdown("#### ☁️ 雲端研究設定")
    sb.text_input("GitHub Token", type="password", key="rs_gh_token",
                  help="fine-grained token，只授權本 repo：Actions 與 Secrets 設為 Read and write。"
                       "只存在這次瀏覽，關掉頁面就要重填。")
    token = (st.session_state.get("rs_gh_token") or "").strip()
    repo = _secret("GITHUB_REPO", DEFAULT_REPO)
    if not token:
        sb.caption("填入 GitHub Token 後，研究艙的欄位就能直接在雲端啟動研究。")
        return
    if not token_status(token, repo):
        sb.error("GitHub Token 無效，或沒有這個 repo 的權限。")
        return
    has_key = repo_secret_exists(token, repo, "ANTHROPIC_API_KEY")
    if has_key:
        sb.success("🟢 GitHub 已連線；Anthropic 金鑰已設定")
    elif has_key is False:
        sb.warning("🟠 GitHub 已連線；還沒設定 Anthropic 金鑰")
    else:
        sb.info("GitHub 已連線（token 沒有 Secrets 讀取權限，無法確認 Anthropic 金鑰）")
    with sb.form("rs_anthropic_form", clear_on_submit=True, border=False):
        key = st.text_input("Anthropic API Key", type="password", key="rs_anthropic_key",
                            help="只需設定一次：加密後存到 GitHub Secrets，不會留在儀表板。")
        save = st.form_submit_button("🔐 儲存到 GitHub" if not has_key else "🔁 更新 Anthropic 金鑰")
    if save:
        key = (key or "").strip()
        if not key.startswith("sk-ant-"):
            sb.warning("看起來不是 Anthropic API 金鑰（應以 sk-ant- 開頭）。")
        else:
            ok, msg = set_repo_secret(token, repo, "ANTHROPIC_API_KEY", key)
            (sb.success if ok else sb.error)(msg)
            repo_secret_exists.clear()


def gh_api(method, path, token, body=None):
    import urllib.error
    import urllib.request
    req = urllib.request.Request(
        f"https://api.github.com{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "ai-research-dashboard"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code, {}
    except OSError:
        return 0, {}


def cloud_busy(token, repo):
    """回傳進行中／排隊中的雲端研究數；查詢失敗回傳 None。"""
    n = 0
    for status in ("in_progress", "queued"):
        code, data = gh_api("GET", f"/repos/{repo}/actions/workflows/{WORKFLOW_FILE}/runs?status={status}",
                            token)
        if code != 200:
            return None
        n += data.get("total_count", 0)
    return n


def cloud_runs_today(token, repo):
    """今天（UTC）已送出的雲端研究數；查詢失敗回傳 None。"""
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    code, data = gh_api("GET", f"/repos/{repo}/actions/workflows/{WORKFLOW_FILE}/runs"
                               f"?event=workflow_dispatch&created=%3E%3D{today}&per_page=1", token)
    return data.get("total_count", 0) if code == 200 else None


def cloud_launch(ticker, cfg):
    token, repo = cfg["token"], cfg["repo"]
    if not yahoo_has(ticker):
        return False, f"Yahoo Finance 查不到 {ticker}。台股上櫃請加 .TWO（例如 3105.TWO）。"
    busy = cloud_busy(token, repo)
    used = cloud_runs_today(token, repo)
    if busy is None or used is None:
        return False, "連不上 GitHub，或 GITHUB_TOKEN 沒有 Actions 權限。"
    if busy >= MAX_RUNNING:
        return False, "雲端已有研究在進行，為控制費用一次只跑一份，請等它完成再送出。"
    if used >= cfg["limit"]:
        return False, f"今天已送出 {used} 份雲端研究，已達每日上限 {cfg['limit']} 份（UTC 換日後重置）。"
    code, _ = gh_api("POST", f"/repos/{repo}/actions/workflows/{WORKFLOW_FILE}/dispatches", token,
                     {"ref": "main", "inputs": {"ticker": ticker}})
    if code != 204:
        return False, f"GitHub 拒絕啟動（HTTP {code}）。請確認 workflow 已推上 main、token 有 Actions 寫入權限。"
    return True, (f"☁️ 已在雲端啟動 {ticker} 的研究，約 20–40 分鐘完成。完成後會自動上傳，"
                  f"Streamlit 重新部署後按「重新載入研究資料」即可看到。"
                  f"進度：https://github.com/{repo}/actions/workflows/{WORKFLOW_FILE}")


def command_builder_panel(why):
    """無法用本機 Claude Code 啟動時：有雲端設定就送到 GitHub Actions，否則產生可複製的指令。"""
    cfg = cloud_config()
    if not cfg:
        st.caption(f"ℹ️ {why} 也可以在左側欄「☁️ 雲端研究設定」填入 GitHub Token，直接在雲端啟動研究。")
    with st.form("rs_cmd_builder", border=False):
        c1, c2 = st.columns([3, 1])
        raw = c1.text_input("股票代號", placeholder="例如 AMD、2317（台股上市可只打數字）、3105.TWO",
                            key="rs_cmd_ticker")
        entered = (c1.text_input("啟動密碼", type="password", key="rs_cloud_pw")
                   if cfg and cfg["password"] else "")
        c2.markdown("<br>", unsafe_allow_html=True)
        submitted = c2.form_submit_button("☁️ 在雲端啟動研究" if cfg else "📋 產生研究指令",
                                          type="primary")
    if cfg:
        st.caption("在 GitHub 的雲端機器上跑 6 人研究團隊，使用 Anthropic API 金鑰（依用量計費，每份約數美元）。"
                   f"一次只跑一份，每日上限 {cfg['limit']} 份。")
    if not submitted:
        return
    ticker = normalize_ticker(raw or "")
    if not ticker:
        st.warning("代號格式不正確。台股上市可只打數字（例如 2317），上櫃請加 .TWO（例如 3105.TWO）。")
        return
    if (WORK / ticker / "report.json").exists():
        st.caption(f"🔁 {ticker} 已有研究，這次會以「更新」模式執行，舊版先封存。")
    if cfg and not password_ok(entered, cfg):
        st.warning("啟動密碼不正確，未送出雲端研究。")
        return
    if cfg:
        with st.spinner(f"確認 {ticker} 並送出到雲端…"):
            ok, msg = cloud_launch(ticker, cfg)
        (st.success if ok else st.warning)(msg)
        if ok:
            return
    st.markdown("**複製下面這行**（右上角有複製鈕），貼到在 `股票Agent skills` 資料夾開啟的 Claude Code：")
    st.code(f"/research-director {ticker}", language=None)
    st.caption("約 15–30 分鐘、使用你的 Claude 用量；完成後會自動上傳到 GitHub。")


def new_research_panel(tickers):
    if "rs_flash" in st.session_state:
        st.success(st.session_state.pop("rs_flash"))
    with st.expander("➕ 新增研究", expanded=not tickers):
        ok, why = can_launch()
        if not ok:
            command_builder_panel(why)
            return
        with st.form("rs_new_research", clear_on_submit=True, border=False):
            c1, c2 = st.columns([3, 1])
            raw = c1.text_input("股票代號", placeholder="例如 AMD、2317（台股上市可只打數字）、3105.TWO",
                                key="rs_new_ticker")
            c2.markdown("<br>", unsafe_allow_html=True)
            submitted = c2.form_submit_button("🚀 開始研究", type="primary")
        st.caption("會在背景啟動 6 人 AI 研究團隊（Claude Code），約 15–30 分鐘、使用你的 Claude 用量。"
                   "已研究過的代號會自動改為「更新」模式，舊版會先封存。")
        if submitted:
            ticker = normalize_ticker(raw)
            if not ticker:
                st.warning("代號格式不正確。")
                return
            with st.spinner(f"確認 {ticker} 的報價資料…"):
                ok, msg = launch_research(ticker)
            if ok:
                st.session_state["rs_flash"] = msg
                load_ticker.clear()
                st.rerun()
            st.warning(msg)


# ---------- 圖表 ----------

def price_chart(df, ind, ticker, template=None):
    up, down = ("#d03b3b", "#0ca30c") if is_tw(ticker) else ("#0ca30c", "#d03b3b")
    d = df.tail(250)
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                        row_heights=[0.55, 0.15, 0.15, 0.15],
                        subplot_titles=("", "成交量", "RSI(14)", "MACD"))
    fig.add_trace(go.Candlestick(x=d.index, open=d["Open"], high=d["High"], low=d["Low"], close=d["Close"],
                                 increasing_line_color=up, decreasing_line_color=down, name="K 線",
                                 showlegend=False), row=1, col=1)
    for col, color in zip(("SMA20", "SMA50", "SMA200"), SERIES):
        fig.add_trace(go.Scatter(x=d.index, y=d[col], name=col, line=dict(color=color, width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=d.index, y=d["BB_upper"], line=dict(width=0), showlegend=False,
                             hoverinfo="skip"), row=1, col=1)
    fig.add_trace(go.Scatter(x=d.index, y=d["BB_lower"], line=dict(width=0), fill="tonexty",
                             fillcolor="rgba(128,128,128,0.12)", name="布林通道", hoverinfo="skip"), row=1, col=1)
    for lv in ind.get("support", []):
        fig.add_hline(y=lv, line=dict(color="#17a2b8", dash="dash", width=1), row=1, col=1,
                      annotation_text=f"支撐 {lv:,.2f}", annotation_position="right")
    for lv in ind.get("resistance", []):
        fig.add_hline(y=lv, line=dict(color="#e67e22", dash="dash", width=1), row=1, col=1,
                      annotation_text=f"壓力 {lv:,.2f}", annotation_position="right")

    colors = [up if c >= o else down for c, o in zip(d["Close"], d["Open"])]
    fig.add_trace(go.Bar(x=d.index, y=d["Volume"], marker_color=colors, showlegend=False, name="成交量"),
                  row=2, col=1)
    fig.add_trace(go.Scatter(x=d.index, y=d["RSI14"], line=dict(color=SERIES[0], width=2),
                             showlegend=False, name="RSI"), row=3, col=1)
    fig.add_hline(y=70, line=dict(color="#e67e22", dash="dot", width=1), row=3, col=1)
    fig.add_hline(y=30, line=dict(color="#17a2b8", dash="dot", width=1), row=3, col=1)
    hist_colors = [up if v >= 0 else down for v in d["MACD_hist"]]
    fig.add_trace(go.Bar(x=d.index, y=d["MACD_hist"], marker_color=hist_colors, showlegend=False,
                         name="柱狀體"), row=4, col=1)
    fig.add_trace(go.Scatter(x=d.index, y=d["MACD"], line=dict(color=SERIES[0], width=2), name="MACD"),
                  row=4, col=1)
    fig.add_trace(go.Scatter(x=d.index, y=d["MACD_signal"], line=dict(color=SERIES[1], width=2),
                             name="Signal"), row=4, col=1)
    fig.update_layout(height=760, hovermode="x unified", xaxis_rangeslider_visible=False,
                      legend=dict(orientation="h", y=1.02, x=0, traceorder="normal"), margin=dict(t=30, r=90, l=10, b=10))
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    fig.update_yaxes(range=[0, 100], row=3, col=1)
    if template:
        fig.update_layout(template=template)
    return fig


def scenario_chart(report, template=None):
    scen = (report.get("valuation") or {}).get("scenarios") or []
    cur = report.get("currency", "")
    fig = go.Figure(go.Bar(
        y=[s["name"] for s in scen], x=[float(s["price"]) for s in scen], orientation="h",
        marker=dict(color=SERIES[0], cornerradius=4),
        text=[f"{money(s['price'], cur)}（{s.get('probability', '')}）" for s in scen], textposition="outside",
        customdata=[s.get("assumption", "") for s in scen],
        hovertemplate="%{y}：%{x:,.2f}<br>%{customdata}<extra></extra>"))
    for value, label, dash in ((report.get("price_current"), "現價", "dash"),
                               (report.get("price_target"), "目標價", "solid")):
        if value:
            fig.add_vline(x=float(value), line=dict(color="#52514e", dash=dash, width=2),
                          annotation_text=f"{label} {float(value):,.0f}", annotation_position="top")
    top = max([float(s["price"]) for s in scen] + [float(report.get("price_current") or 0)])
    fig.update_layout(height=280, margin=dict(t=40, b=10, l=10, r=10), xaxis_range=[0, top * 1.3],
                      yaxis=dict(autorange="reversed"))
    if template:
        fig.update_layout(template=template)
    return fig


# ---------- 頁面區塊 ----------

def no_math(text):
    """NT$、US$ 這類金額裡的 $ 會被 st.markdown 當成 LaTeX 數學式，要先跳脫。"""
    return text.replace("$", r"\$")


def header(ticker, data, api=None):
    r = data["report"] or {}
    ind = data["ind"]
    cur = r.get("currency", "TWD" if is_tw(ticker) else "USD")
    st.header(f"{r.get('company', ticker)}")
    parts = [ticker, f"{r['quarter']} 財報研究" if r.get("quarter") else "",
             f"研究日期 {r['as_of']}" if r.get("as_of") else "", f"狀態：{stage(data)}"]
    st.caption("｜".join(x for x in parts if x))
    if not r:
        job = data.get("job") or {}
        if job.get("status") in ("failed", "limited"):
            (st.warning if job["status"] == "limited" else st.error)(job.get("error") or "研究中斷。")
            resume_button(ticker, "page")
        elif job.get("status") == "running":
            st.info("研究進行中，完成的部分會陸續出現在下方。")
        else:
            st.info("研究尚未定稿，以下顯示已完成的部分。")
        return
    pc, pt = r.get("price_current"), r.get("price_target")
    upside = (float(pt) / float(pc) - 1) * 100 if pc and pt else None
    c = st.columns(5)
    c[0].metric("評等", r.get("rating", "—"))
    c[1].metric("12 個月目標價", money(pt, cur))
    c[2].metric("現價", money(pc, cur), f"{ind.get('change_1d_pct', 0):+.2f}%（{ind.get('last_date', '')}）",
                delta_color="inverse" if is_tw(ticker) else "normal")
    c[3].metric("潛在漲跌幅", f"{upside:+.1f}%" if upside is not None else "—")
    c[4].metric("信心度", f"{r.get('confidence', '—')} / 5")
    live_quote(ticker, pt, api)
    st.markdown(no_math(f"> **{r.get('one_liner', '')}**"))


def tab_overview(data):
    r = data["report"]
    left, right = st.columns([3, 2])
    with left:
        if r:
            st.subheader("重點摘要")
            for s in r.get("summary", []):
                st.markdown(no_math(f"- {s}"))
            st.subheader("投資論點")
            for i, t in enumerate(r.get("theses", []), 1):
                with st.expander(f"{i}. {t['title']}", expanded=i == 1):
                    st.write(t["body"])
        elif data["draft"]:
            st.subheader("總監初稿")
            st.markdown(no_math(data["draft"]))
        else:
            st.subheader("研究簡報")
            st.markdown(no_math(data["brief"]))
    with right:
        st.subheader("研究團隊觀點")
        rows = []
        for role, label in ROLES:
            a = data["analysts"][role]
            rows.append({"角色": label, "結論": STANCE.get(a["stance"], a["stance"]) if a else "研究中",
                         "信心": f"{a['confidence']}/5" if a else "—", "一句話": a["headline"] if a else ""})
        ch = data["da"].get("challenges", [])
        if ch:
            cnt = {k: sum(1 for c in ch if c["severity"] == k) for k in SEVERITY}
            rows.append({"角色": "反方風控官", "結論": "審查", "信心": "—",
                         "一句話": f"致命 {cnt['fatal']}・重大 {cnt['major']}・次要 {cnt['minor']}"})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        if r:
            st.markdown("**評等上限規則**")
            if r.get("rating_cap_applied", "無").startswith("觸發"):
                st.warning(r["rating_cap_applied"])
            else:
                st.success(r.get("rating_cap_applied", "無"))
            st.markdown("**分析師分歧與總監裁決**")
            st.write(r.get("conflicts", ""))


def tab_analysts(data, ticker):
    tabs = st.tabs([label for _, label in ROLES])
    for tab, (role, label) in zip(tabs, ROLES):
        with tab:
            a = data["analysts"][role]
            if not a:
                st.info(f"{label}分析師尚未交件。")
                continue
            st.markdown(no_math(f"#### {STANCE.get(a['stance'])}｜信心 {a['confidence']}/5"))
            st.markdown(no_math(f"**{a['headline']}**"))
            for i, t in enumerate(a.get("theses", []), 1):
                with st.expander(f"{i}. {t['claim'][:80]}{'…' if len(t['claim']) > 80 else ''}"):
                    st.markdown(no_math(f"**主張**：{t['claim']}"))
                    st.markdown(no_math(f"**證據**：{t['evidence']}"))
                    st.caption(f"來源：{t['source']}（{t['source_date']}）")
            if a.get("key_metrics"):
                st.markdown("##### 關鍵指標")
                st.dataframe(pd.DataFrame(a["key_metrics"]).rename(
                    columns={"name": "指標", "value": "數值", "period": "期間", "source": "來源"}),
                    hide_index=True, width="stretch")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("##### 主要風險")
                for x in a.get("risks", []):
                    st.markdown(no_math(f"- {x}"))
            with c2:
                st.markdown("##### 改變看法的條件")
                for x in a.get("change_my_mind", []):
                    st.markdown(no_math(f"- {x}"))
            if a.get("open_questions"):
                with st.expander(f"資料缺口（{len(a['open_questions'])}）"):
                    for x in a["open_questions"]:
                        st.markdown(no_math(f"- {x}"))


def tab_debate(data):
    da = data["da"]
    if not da:
        st.info("反方風控官尚未交件。")
        return
    st.markdown("##### 共識陷阱")
    st.info(da.get("consensus_trap", ""))
    ch = da.get("challenges", [])
    reb = data["rebuttal"]
    picked = st.pills("篩選嚴重度", list(SEVERITY), default=list(SEVERITY),
                      format_func=lambda k: SEVERITY[k], selection_mode="multi",
                      key=f"rs_pills_{id(data)}")
    for c in ch:
        if c["severity"] not in (picked or []):
            continue
        r = reb.get(c["id"], {})
        with st.container(border=True):
            st.markdown(f"**{c['id']}**　{SEVERITY.get(c['severity'])}　"
                        f"{STATUS.get(r.get('status'), '⏳ 待答辯')}　·　攻擊對象：{c['target'][:90]}")
            left, right = st.columns(2)
            with left:
                st.markdown("**風控官質疑**")
                st.write(c["attack"])
                with st.expander("依據與來源"):
                    st.write(c["evidence"])
                    st.caption(c["source"])
            with right:
                st.markdown("**總監答辯**")
                st.write(r.get("reply", "（尚未答辯）"))
                st.caption(f"化解條件：{c['what_would_resolve']}")
    bear = da.get("bear_case") or {}
    if bear:
        st.markdown("##### 空頭劇本")
        st.error(f"**{bear.get('price')}｜機率 {bear.get('probability')}**\n\n{bear.get('narrative', '')}")


def tab_valuation(data, template=None):
    r = data["report"]
    fund = data["analysts"].get("fundamental") or {}
    if r and r.get("valuation"):
        v = r["valuation"]
        st.markdown(no_math(f"**方法**：{v.get('method', '')}"))
        st.plotly_chart(scenario_chart(r, template))
        st.dataframe(pd.DataFrame(v.get("scenarios", [])).rename(
            columns={"name": "情境", "price": "目標價", "probability": "機率", "assumption": "關鍵假設"}),
            hide_index=True, width="stretch")
        st.write(v.get("body", ""))
    elif fund.get("valuation"):
        st.caption("尚未定稿，以下為基本面分析師的估值。")
        v = fund["valuation"]
        st.metric("基本面目標價", f"{v.get('target_price', '—'):,}")
        st.dataframe(pd.DataFrame(v.get("scenarios", [])), hide_index=True, width="stretch")
    else:
        st.info("尚無估值資料。")
        return
    sens = (fund.get("valuation") or {}).get("sensitivity")
    # 兩種格式：{"one_notch_adverse": [...]}（只看不利方向）或直接一個 list（上下雙向）
    if isinstance(sens, dict) and sens.get("one_notch_adverse"):
        rows, title = sens["one_notch_adverse"], "敏感度：各假設往不利方向調一檔（基本面分析師）"
    elif isinstance(sens, list) and sens:
        rows, title = sens, "敏感度：各假設上下調整（基本面分析師）"
    else:
        rows = None
    if rows:
        st.markdown(f"##### {title}")
        st.dataframe(pd.DataFrame(rows).rename(
            columns={"variable": "假設", "price": "價格", "change": "變化"}), hide_index=True,
            width="stretch")


def tab_technical(data, ticker, template=None):
    ind, df = data["ind"], data["prices"]
    if df is None:
        st.info("尚無股價資料。")
        return
    c = st.columns(6)
    c[0].metric("RSI(14)", ind.get("rsi14"))
    c[1].metric("MACD 柱狀體", ind.get("macd_hist"))
    c[2].metric("ATR(14) 占股價", f"{ind.get('atr14_pct')}%", help=f"ATR(14) = {ind.get('atr14')}")
    c[3].metric("距 52 週高點", f"{ind.get('from_52w_high_pct')}%")
    c[4].metric("近 1 月", f"{ind.get('change_1m_pct')}%")
    c[5].metric("近 1 年", f"{ind.get('change_1y_pct')}%")
    st.plotly_chart(price_chart(df, ind, ticker, template))
    st.caption(f"{ind.get('source', '')}｜資料日期 {ind.get('last_date', '')}"
               + ("｜台股慣例：紅漲綠跌" if is_tw(ticker) else "｜美股慣例：綠漲紅跌"))


def tab_risk(data):
    r = data["report"]
    if not r:
        st.info("研究尚未定稿。")
        return
    st.markdown("##### 風險矩陣")
    rm = pd.DataFrame(r.get("risk_matrix", []))
    if not rm.empty:
        rm["probability"] = rm["probability"].map(LEVEL).fillna(rm["probability"])
        rm["impact"] = rm["impact"].map(LEVEL).fillna(rm["impact"])
        st.dataframe(rm.rename(columns={"risk": "風險", "probability": "機率", "impact": "衝擊",
                                        "mitigant": "緩解因素"}), hide_index=True, width="stretch")
    left, right = st.columns(2)
    with left:
        st.markdown("##### 論點失效條件（降評／出場）")
        kills = list(dict.fromkeys(r.get("kill_criteria", []) + data["da"].get("kill_criteria", [])))
        for k in kills:
            st.markdown(no_math(f"- {k}"))
        if r.get("upgrade_criteria"):
            st.markdown("##### 升評條件")
            for k in r["upgrade_criteria"]:
                st.markdown(no_math(f"- {k}"))
    with right:
        st.markdown("##### 催化劑時間表")
        st.dataframe(pd.DataFrame(r.get("catalysts", [])).rename(columns={"date": "時間", "event": "事件"}),
                     hide_index=True, width="stretch")
    with st.expander("資料來源"):
        for s in r.get("sources", []):
            st.markdown(no_math(f"- {s}"))


def page_compare(tickers, api=None):
    st.header("研究總覽")
    new_research_panel(tickers)
    # 有研究在背景執行時，每 30 秒自動更新總覽表
    st.fragment(run_every="30s" if running_jobs() else None)(overview_table)(api)


def overview_table(api=None):
    tickers = list_tickers()
    if not tickers:
        st.info("還沒有任何研究。")
        return
    rows = []
    for t in tickers:
        d = load_ticker(t, mtime_key(WORK / t))
        r = d["report"] or {}
        ch = d["da"].get("challenges", [])
        pc, pt = r.get("price_current"), r.get("price_target")
        row = {"代號": t, "公司": r.get("company", ""), "狀態": stage(d), "評等": r.get("rating", "—"),
               "信心": r.get("confidence"), "現價": pc, "目標價": pt,
               "漲跌空間 %": round((float(pt) / float(pc) - 1) * 100, 1) if pc and pt else None,
               "致命疑點": sum(1 for c in ch if c["severity"] == "fatal"),
               "重大疑點": sum(1 for c in ch if c["severity"] == "major")}
        for role, label in ROLES:
            a = d["analysts"][role]
            row[label] = STANCE.get(a["stance"]) if a else "—"
        q = sinopac_quote(t, api)
        if q and "error" not in q:
            row["永豐即時價"] = q["close"]
            row["即時漲跌空間 %"] = round((float(pt) / q["close"] - 1) * 100, 1) if pt else None
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption("每份研究由 6 人 AI 研究團隊產出：研究總監、總經、產業、基本面、技術面分析師與反方風控官。"
               "致命疑點未化解時，評等最高只能中性。")
    for t in tickers:
        job = load_ticker(t, mtime_key(WORK / t)).get("job") or {}
        log = WORK / t / "research.log"
        if job.get("status") in ("running", "failed", "limited") and log.exists():
            label = {"running": "執行中", "failed": "中斷", "limited": "用量上限"}[job["status"]]
            with st.expander(f"{t} 執行記錄（{label}，開始於 {job.get('started') or '—'}）",
                             expanded=job["status"] != "running"):
                if job.get("error"):
                    (st.warning if job["status"] == "limited" else st.error)(job["error"])
                if job["status"] != "running":
                    resume_button(t, "overview")
                tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
                st.code(chr(10).join(tail) or "（尚無輸出）", language=None)


def resume_button(ticker, where):
    """研究中斷或碰到用量上限時，從中斷處重新啟動（研究總監會沿用已完成的檔案）。"""
    ok, why = can_launch()
    if not ok:
        st.caption(f"無法從這裡啟動研究：{why}")
        return
    if st.button("🔁 從中斷處繼續", key=f"rs_retry_{where}_{ticker}", type="primary"):
        ok, msg = launch_research(ticker)
        if ok:
            st.session_state["rs_flash"] = msg
            load_ticker.clear()
            st.rerun(scope="app")
        st.warning(msg)


def page_ticker(ticker, api=None, template=None):
    data = load_ticker(ticker, mtime_key(WORK / ticker))
    header(ticker, data, api)
    pdfs = sorted(REPORTS.glob(f"{ticker}_*.pdf")) if REPORTS.exists() else []
    if pdfs:
        st.download_button("下載 PDF 研報", pdfs[-1].read_bytes(), file_name=pdfs[-1].name,
                           mime="application/pdf", icon=":material/download:",
                           key=f"rs_pdf_{ticker}")
    t = st.tabs(["總覽", "四大面向", "多空交鋒", "估值", "技術面", "風險與催化劑"])
    with t[0]:
        tab_overview(data)
    with t[1]:
        tab_analysts(data, ticker)
    with t[2]:
        tab_debate(data)
    with t[3]:
        tab_valuation(data, template)
    with t[4]:
        tab_technical(data, ticker, template)
    with t[5]:
        tab_risk(data)
    st.caption("本儀表板內容由 AI 研究團隊依公開資訊產生，僅供研究與教育用途，不構成任何投資建議。")


# 宿主應用用 CSS 把背景改成深色、但 Streamlit 主題仍是淺色時，文字會變成深灰配深底。
# 只在本艙渲染時注入，切到其他艙就不存在，不影響宿主的其他頁面。
DARK_HOST_CSS = """
<style>
[data-testid="stMain"] [data-testid="stMetricLabel"] p,
[data-testid="stMain"] [data-testid="stWidgetLabel"] p,
[data-testid="stMain"] [data-testid="stCaptionContainer"] { color: #cbd5e1 !important; }
[data-testid="stMetricValue"] { color: #f1f5f9 !important; }
.stTabs [data-baseweb="tab"] p { color: #cbd5e1; }
.stTabs [aria-selected="true"] p { color: #ff6b6b; }
.stButton button p, .stDownloadButton button p { color: #0b0f19 !important; }
</style>
"""


def render_cabin(api=None, template="plotly_dark"):
    """嵌入其他 Streamlit 應用時的入口：在主畫面選擇標的；側邊欄只加「雲端研究設定」。"""
    if template == "plotly_dark":
        st.markdown(DARK_HOST_CSS, unsafe_allow_html=True)
    cloud_sidebar()
    tickers = list_tickers()
    if not tickers:
        st.warning("還沒有研究資料，先在下面填入代號開始第一份研究。")
        new_research_panel(tickers)
        return
    c1, c2 = st.columns([3, 1])
    with c1:
        view = st.selectbox("檢視", ["研究總覽"] + tickers, key="rs_view")
    with c2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("重新載入研究資料", icon=":material/refresh:", key="rs_reload"):
            load_ticker.clear()
    if view == "研究總覽":
        page_compare(tickers, api)
    else:
        page_ticker(view, api, template)
