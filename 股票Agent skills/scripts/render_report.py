"""把 work/<TICKER>/ 下的所有 JSON 組成機構級研報，輸出 PDF。

用法：
    python scripts/render_report.py NVDA
    python scripts/render_report.py NVDA --html-only   # 只產生 HTML，方便調版面

讀取：report.json（必要）、macro/industry/fundamental/technical.json、
      devils-advocate.json、rebuttal.json、indicators.json、chart_technical.png
輸出：reports/<TICKER>_<YYYYMMDD>.pdf（與同名 .html）
"""
import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
from html import escape
from pathlib import Path

from safe_paths import check_date, check_ticker, inside

ROOT = Path(__file__).resolve().parent.parent

ROLES = [("macro", "總經"), ("industry", "產業"), ("fundamental", "基本面"), ("technical", "技術面")]
STANCE = {"bullish": ("看多", "pos"), "neutral": ("中性", "neu"), "bearish": ("看空", "neg")}
RATING_CLASS = {"買進": "pos", "中性": "neu", "賣出": "neg"}
SEVERITY = {"fatal": ("致命", "neg"), "major": ("重大", "warn"), "minor": ("次要", "neu")}
STATUS = {"resolved": ("已化解", "pos"), "partially": ("部分化解", "warn"), "unresolved": ("未化解", "neg")}
LEVEL = {"高": "neg", "中": "warn", "低": "pos"}

EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
]


def load(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def e(x):
    return escape("" if x is None else str(x))


def img_tag(path, alt):
    if not path.exists():
        return ""
    data = base64.b64encode(path.read_bytes()).decode()
    return f'<img src="data:image/png;base64,{data}" alt="{e(alt)}">'


def tag(text, cls):
    return f'<span class="tag {cls}">{e(text)}</span>'


def fmt_price(x, cur):
    try:
        return f"{cur} {float(x):,.0f}" if cur == "TWD" else f"{cur} {float(x):,.2f}"
    except (TypeError, ValueError):
        return e(x)


def fmt_num(x, cur):
    """不帶幣別的價格：台股取整數，美股兩位小數。"""
    try:
        return f"{float(x):,.0f}" if cur == "TWD" else f"{float(x):,.2f}"
    except (TypeError, ValueError):
        return e(x if x is not None else "—")


def scenario_chart(report, out, tw=False):
    scen = (report.get("valuation") or {}).get("scenarios") or []
    if not scen:
        return
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = ["Microsoft JhengHei", "sans-serif"]

    names = [s["name"] for s in scen]
    prices = [float(s["price"]) for s in scen]
    up, down = ("#d73027", "#1a9850") if tw else ("#1a9850", "#d73027")
    colors = [up, "#2c5282", down][:len(scen)]
    fig, ax = plt.subplots(figsize=(6.4, 2.6))
    bars = ax.barh(names[::-1], prices[::-1], color=colors[::-1], height=0.55)
    cur = float(report.get("price_current") or 0)
    if cur:
        ax.axvline(cur, color="#333", linestyle="--", linewidth=1)
        ax.text(cur, len(names) - 0.45, f" 現價 {cur:,.0f}", fontsize=8, va="bottom")
    for b, s in zip(bars, scen[::-1]):
        ax.text(b.get_width(), b.get_y() + b.get_height() / 2,
                f" {float(s['price']):,.0f}（{s.get('probability', '')}）", va="center", fontsize=9)
    ax.set_xlim(0, max(prices + [cur]) * 1.25)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.tick_params(labelsize=9)
    fig.tight_layout()
    fig.savefig(out, dpi=170)
    plt.close(fig)


def section_analyst(data, label):
    if not data:
        return f'<div class="analyst"><h3>{label}分析師</h3><p class="muted">（未交件）</p></div>'
    st, cls = STANCE.get(data.get("stance"), (data.get("stance"), "neu"))
    rows = "".join(
        f"<li><b>{e(t.get('claim'))}</b><br>{e(t.get('evidence'))}"
        f"<span class='src'>來源：{e(t.get('source'))}（{e(t.get('source_date'))}）</span></li>"
        for t in data.get("theses", []))
    metrics = "".join(
        f"<tr><td>{e(m.get('name'))}</td><td class='num'>{e(m.get('value'))}</td>"
        f"<td>{e(m.get('period'))}</td><td class='src'>{e(m.get('source'))}</td></tr>"
        for m in data.get("key_metrics", []))
    metrics_html = (f"<table class='grid'><tr><th>指標</th><th>數值</th><th>期間</th><th>來源</th></tr>"
                    f"{metrics}</table>") if metrics else ""
    risks = "".join(f"<li>{e(r)}</li>" for r in data.get("risks", []))
    change = "".join(f"<li>{e(r)}</li>" for r in data.get("change_my_mind", []))
    gaps = "".join(f"<li>{e(r)}</li>" for r in data.get("open_questions", []))
    return f"""
<div class="analyst">
  <h3>{label}分析師 {tag(st, cls)} <span class="conf">信心度 {e(data.get('confidence'))}/5</span></h3>
  <p class="headline">{e(data.get('headline'))}</p>
  <ol class="theses">{rows}</ol>
  {metrics_html}
  <div class="two">
    <div><h4>主要風險</h4><ul>{risks}</ul></div>
    <div><h4>改變看法的條件</h4><ul>{change}</ul></div>
  </div>
  {f'<h4>資料缺口</h4><ul class="muted">{gaps}</ul>' if gaps else ''}
</div>"""


def build_html(ticker, wd):
    report = load(wd / "report.json")
    if not report:
        sys.exit(f"找不到 {wd / 'report.json'}，研究總監要先完成第 5 步")
    analysts = {r: load(wd / f"{r}.json") for r, _ in ROLES}
    da = load(wd / "devils-advocate.json") or {}
    reb = {x["id"]: x for x in (load(wd / "rebuttal.json") or {}).get("responses", [])}
    ind = load(wd / "indicators.json") or {}

    scenario_chart(report, wd / "chart_scenarios.png", tw=ticker.endswith((".TW", ".TWO")))

    cur = report.get("currency", "USD")
    pc, pt = report.get("price_current"), report.get("price_target")
    try:
        upside = f"{(float(pt) / float(pc) - 1) * 100:+.1f}%"
    except (TypeError, ValueError, ZeroDivisionError):
        upside = "—"
    rating = report.get("rating", "")
    rcls = RATING_CLASS.get(rating, "neu")

    challenges = da.get("challenges", [])
    counts = {k: sum(1 for c in challenges if c.get("severity") == k) for k in SEVERITY}
    unresolved = {k: sum(1 for c in challenges if c.get("severity") == k
                         and reb.get(c.get("id"), {}).get("status") != "resolved") for k in SEVERITY}

    team_rows = "".join(
        f"<tr><td>{label}</td><td>{tag(*STANCE.get((analysts[r] or {}).get('stance'), ('未交件', 'neu')))}</td>"
        f"<td class='num'>{e((analysts[r] or {}).get('confidence', '—'))}/5</td>"
        f"<td>{e((analysts[r] or {}).get('headline', ''))}</td></tr>"
        for r, label in ROLES)
    team_rows += (f"<tr><td>反方風控官</td><td>{tag('審查', 'warn')}</td><td class='num'>—</td>"
                  f"<td>致命 {counts['fatal']}（未化解 {unresolved['fatal']}）・"
                  f"重大 {counts['major']}（未化解 {unresolved['major']}）・次要 {counts['minor']}</td></tr>")

    key_data = [
        ("收盤價", fmt_price(ind.get("close"), cur), ind.get("last_date")),
        ("52 週高／低", f"{fmt_num(ind.get('high_52w'), cur)} / {fmt_num(ind.get('low_52w'), cur)}", ""),
        ("距 52 週高點", f"{ind.get('from_52w_high_pct', '—')}%", ""),
        ("近 1 月／3 月／1 年", f"{ind.get('change_1m_pct', '—')}% / {ind.get('change_3m_pct', '—')}% / "
                            f"{ind.get('change_1y_pct', '—')}%", ""),
        ("RSI(14)", ind.get("rsi14", "—"), ""),
        ("ATR(14)", f"{ind.get('atr14', '—')}（{ind.get('atr14_pct', '—')}%）", ""),
    ] if ind else []
    key_rows = "".join(f"<tr><td>{e(a)}</td><td class='num'>{e(b)}</td></tr>" for a, b, _ in key_data)

    summary = "".join(f"<li>{e(s)}</li>" for s in report.get("summary", []))
    theses = "".join(f"<div class='thesis'><h4>{i}. {e(t.get('title'))}</h4><p>{e(t.get('body'))}</p></div>"
                     for i, t in enumerate(report.get("theses", []), 1))

    val = report.get("valuation") or {}
    scen_rows = "".join(
        f"<tr><td>{e(s.get('name'))}</td><td class='num'>{fmt_price(s.get('price'), cur)}</td>"
        f"<td class='num'>{e(s.get('probability'))}</td><td>{e(s.get('assumption'))}</td></tr>"
        for s in val.get("scenarios", []))

    debate_rows = ""
    for c in challenges:
        sv, scls = SEVERITY.get(c.get("severity"), (c.get("severity"), "neu"))
        r = reb.get(c.get("id"), {})
        stt, tcls = STATUS.get(r.get("status"), ("未答辯", "neg"))
        debate_rows += f"""
<div class="challenge">
  <div class="ch-head"><b>{e(c.get('id'))}</b> {tag(sv, scls)} {tag(stt, tcls)}
    <span class="target">攻擊對象：{e(c.get('target'))}</span></div>
  <div class="ch-body">
    <div><h5>風控官質疑</h5><p>{e(c.get('attack'))}</p>
      <p class="src">依據：{e(c.get('evidence'))}｜來源：{e(c.get('source'))}</p></div>
    <div><h5>總監答辯</h5><p>{e(r.get('reply', '（未答辯）'))}</p>
      <p class="src">化解條件：{e(c.get('what_would_resolve'))}</p></div>
  </div>
</div>"""

    bear = da.get("bear_case") or {}
    risk_rows = "".join(
        f"<tr><td>{e(x.get('risk'))}</td><td>{tag(x.get('probability', ''), LEVEL.get(x.get('probability'), 'neu'))}</td>"
        f"<td>{tag(x.get('impact', ''), LEVEL.get(x.get('impact'), 'neu'))}</td><td>{e(x.get('mitigant'))}</td></tr>"
        for x in report.get("risk_matrix", []))
    catalysts = "".join(f"<tr><td class='nowrap'>{e(x.get('date'))}</td><td>{e(x.get('event'))}</td></tr>"
                        for x in report.get("catalysts", []))
    # 總監定稿時已把風控官的失效條件整合進 report.json；兩份合併會出現換句話說的重複
    kills = report.get("kill_criteria") or da.get("kill_criteria", [])
    kill_html = "".join(f"<li>{e(k)}</li>" for k in kills)
    upgrades = report.get("upgrade_criteria", [])
    upgrade_html = ("<h2>升評條件</h2><ul class='kill'>" + "".join(f"<li>{e(u)}</li>" for u in upgrades)
                    + "</ul>") if upgrades else ""
    sources = "".join(f"<li>{e(s)}</li>" for s in report.get("sources", []))
    analyst_html = "".join(section_analyst(analysts[r], label) for r, label in ROLES)
    demo = report.get("demo")

    css = (Path(__file__).parent / "report.css").read_text(encoding="utf-8")
    body_class = "tw" if ticker.endswith((".TW", ".TWO")) else ""
    return f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<title>{e(ticker)} 研究報告 {e(report.get('as_of'))}</title>
<style>{css}</style></head>
<body class="{body_class}">
{'<div class="watermark">範例資料・非真實研究</div>' if demo else ''}

<section class="page cover">
  <div class="masthead"><span>AI 投資研究團隊｜股票研究</span><span>{e(report.get('as_of'))}</span></div>
  <div class="cover-title">
    <div>
      <h1>{e(report.get('company'))}</h1>
      <div class="ticker">{e(ticker)}｜{e(report.get('quarter'))} 財報研究</div>
      <p class="oneliner">{e(report.get('one_liner'))}</p>
    </div>
    <div class="rating-box {rcls}">
      <div class="rating">{e(rating)}</div>
      <table>
        <tr><td>目標價（12 個月）</td><td class="num">{fmt_price(pt, cur)}</td></tr>
        <tr><td>現價</td><td class="num">{fmt_price(pc, cur)}</td></tr>
        <tr><td>潛在漲跌幅</td><td class="num"><b>{upside}</b></td></tr>
        <tr><td>信心度</td><td class="num">{e(report.get('confidence'))} / 5</td></tr>
      </table>
    </div>
  </div>
  <div class="two wide-left">
    <div><h2>重點摘要</h2><ul class="summary">{summary}</ul></div>
    <div><h2>市場數據</h2><table class="grid compact">{key_rows}</table>
      <p class="src">{e(ind.get('source', ''))}</p></div>
  </div>
  <h2>研究團隊觀點</h2>
  <table class="grid team"><tr><th>角色</th><th>結論</th><th>信心</th><th>一句話</th></tr>{team_rows}</table>
</section>

<section class="page">
  <h2>投資論點</h2>{theses}
  <h2>估值</h2>
  <p><b>方法：</b>{e(val.get('method'))}</p><p>{e(val.get('body'))}</p>
  <div class="figure">{img_tag(wd / 'chart_scenarios.png', '情境估值')}</div>
  <table class="grid"><tr><th class="n">情境</th><th class="n">目標價</th><th class="n">機率</th><th>關鍵假設</th></tr>{scen_rows}</table>
  <h2>分析師分歧與總監裁決</h2><p>{e(report.get('conflicts'))}</p>
  <div class="cap-note"><b>評等上限規則：</b>{e(report.get('rating_cap_applied', '無'))}</div>

  <h2>四大面向分析</h2>
  {analyst_html}
  <h3>技術面圖表</h3>
  <div class="figure">{img_tag(wd / 'chart_technical.png', '技術面')}</div>
  <p class="src">支撐：{e(ind.get('support'))}　壓力：{e(ind.get('resistance'))}　資料日期：{e(ind.get('last_date'))}</p>
</section>

<section class="page">
  <h2>多空交鋒：反方風控官審查</h2>
  <div class="callout"><h4>共識陷阱</h4><p>{e(da.get('consensus_trap'))}</p></div>
  {debate_rows}
  <div class="callout neg"><h4>空頭劇本：{fmt_price(bear.get('price'), cur)}（機率 {e(bear.get('probability'))}）</h4>
    <p>{e(bear.get('narrative'))}</p></div>
</section>

<section class="page">
  <h2>風險矩陣</h2>
  <table class="grid"><tr><th>風險</th><th>機率</th><th>衝擊</th><th>緩解因素</th></tr>{risk_rows}</table>
  <h2>催化劑時間表</h2>
  <table class="grid"><tr><th>時間</th><th>事件</th></tr>{catalysts}</table>
  <h2>論點失效條件（Kill Criteria）</h2>
  <ul class="kill">{kill_html}</ul>
  {upgrade_html}
  <h2>資料來源</h2><ol class="sources">{sources}</ol>
  <div class="disclaimer">本報告由 AI 研究團隊依公開資訊產生，僅供研究與教育用途，不構成任何投資建議或買賣邀約。
  數據可能有誤或過時，投資人應自行查證並承擔投資風險。過去績效不代表未來表現。</div>
</section>
</body></html>"""


def to_pdf(html_path, pdf_path):
    tmp_path = pdf_path.with_name(pdf_path.stem + ".new.pdf")
    browser = next((p for p in EDGE_PATHS if Path(p).exists()), None) or shutil.which("msedge")
    if not browser:
        sys.exit("找不到 Edge 或 Chrome，無法轉 PDF；HTML 已產生：" + str(html_path))
    cmd = [browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
           "--run-all-compositor-stages-before-draw", "--virtual-time-budget=5000",
           f"--print-to-pdf={tmp_path}", html_path.resolve().as_uri()]
    tmp_path.unlink(missing_ok=True)
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    if not tmp_path.exists():
        sys.exit("PDF 轉檔失敗")
    # 舊 PDF 開在閱讀器裡時會被鎖住，Edge 寫不進去卻不報錯；所以先寫暫存檔再取代
    try:
        os.replace(tmp_path, pdf_path)
    except PermissionError:
        sys.exit(f"{pdf_path.name} 正被其他程式開啟，無法覆寫。請關閉後重跑；新版暫存在 {tmp_path}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("--html-only", action="store_true")
    args = ap.parse_args()
    ticker = check_ticker(args.ticker)
    wd = inside(ROOT / "work" / ticker, ROOT / "work")

    html = build_html(ticker, wd)
    report = load(wd / "report.json")
    out_dir = ROOT / "reports"
    out_dir.mkdir(exist_ok=True)
    # as_of 來自 AI 寫的 report.json，必須是日期格式，避免檔名被拿來做路徑穿越
    stem = f"{ticker}_{check_date(report.get('as_of')).replace('-', '')}"
    html_path = inside(out_dir / f"{stem}.html", out_dir)
    html_path.write_text(html, encoding="utf-8")
    if args.html_only:
        print(html_path)
        return
    pdf_path = inside(out_dir / f"{stem}.pdf", out_dir)
    to_pdf(html_path, pdf_path)
    print(pdf_path)


if __name__ == "__main__":
    main()
