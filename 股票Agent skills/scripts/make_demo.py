"""產生 work/DEMO/ 範例資料，用來測試 render_report.py 的版面。數字全為虛構。

用法：
    python scripts/make_demo.py && python scripts/render_report.py DEMO
"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WD = ROOT / "work" / "DEMO"
SRC = "範例來源（虛構）"


def analyst(role, stance, conf, headline):
    return {
        "role": role, "ticker": "DEMO", "as_of": "2026-11-02", "stance": stance, "confidence": conf,
        "headline": headline,
        "theses": [{"claim": f"{headline}——範例主張 {i}，數字 {10 * i}%", "evidence": "範例證據說明",
                    "source": SRC, "source_date": "2026-10-01"} for i in range(1, 4)],
        "key_metrics": [{"name": "範例指標 A", "value": "123.4 億美元", "period": "最新一季", "source": SRC},
                        {"name": "範例指標 B", "value": "45.6%", "period": "最新一季", "source": SRC}],
        "risks": ["範例風險一", "範例風險二"],
        "change_my_mind": ["範例條件：某指標低於 X"],
        "open_questions": ["範例資料缺口"],
    }


def main():
    WD.mkdir(parents=True, exist_ok=True)
    files = {
        "macro": analyst("macro", "neutral", 3, "利率下行有利估值，但政策風險升溫"),
        "industry": analyst("industry", "bullish", 4, "價值鏈瓶頸鬆動，龍頭地位穩固"),
        "fundamental": analyst("fundamental", "bullish", 4, "營收與毛利雙雙超預期"),
        "technical": analyst("technical", "bearish", 3, "跌破 50 日線，短線動能轉弱"),
        "devils-advocate": {
            "role": "devils-advocate", "ticker": "DEMO", "as_of": "2026-11-02",
            "challenges": [
                {"id": "C1", "target": "fundamental：營收超預期", "attack": "範例質疑：應收帳款天數上升 15 天",
                 "evidence": "範例依據", "source": SRC, "severity": "major",
                 "what_would_resolve": "下一季應收天數回落"},
                {"id": "C2", "target": "industry：龍頭地位", "attack": "範例質疑：客製 ASIC 份額擴大",
                 "evidence": "範例依據", "source": SRC, "severity": "fatal",
                 "what_would_resolve": "主要客戶追加訂單證據"},
                {"id": "C3", "target": "technical", "attack": "範例質疑：量能不足", "evidence": "範例依據",
                 "source": SRC, "severity": "minor", "what_would_resolve": "放量突破"},
            ],
            "consensus_trap": "範例：市場已預期連續超預期，門檻極高。",
            "bear_case": {"price": 140, "probability": "20%", "narrative": "範例空頭劇本。"},
            "kill_criteria": ["範例失效條件 A", "範例失效條件 B"],
        },
        "rebuttal": {"responses": [
            {"id": "C1", "status": "partially", "reply": "範例答辯：部分來自季末出貨集中。"},
            {"id": "C2", "status": "resolved", "reply": "範例答辯：客戶公開追加資本支出。"},
            {"id": "C3", "status": "unresolved", "reply": "範例答辯：承認短線量能不足。"},
        ]},
        "report": {
            "demo": True, "ticker": "DEMO", "company": "範例科技公司", "as_of": "2026-11-02",
            "quarter": "FY2027 Q2", "rating": "買進", "confidence": 3, "price_current": 204.64,
            "price_target": 250, "currency": "USD", "one_liner": "範例一句話結論：基本面強勁，短線技術面偏弱，逢回布局。",
            "summary": ["範例摘要一", "範例摘要二", "範例摘要三"],
            "theses": [{"title": "範例論點一", "body": "說明文字。"}, {"title": "範例論點二", "body": "說明文字。"}],
            "valuation": {"method": "Forward P/E + DCF", "body": "範例估值說明。", "scenarios": [
                {"name": "樂觀", "price": 300, "probability": "25%", "assumption": "範例假設"},
                {"name": "基準", "price": 250, "probability": "55%", "assumption": "範例假設"},
                {"name": "悲觀", "price": 150, "probability": "20%", "assumption": "範例假設"}]},
            "conflicts": "範例：基本面看多與技術面看空的裁決說明。",
            "rating_cap_applied": "無（唯一致命疑點 C2 已化解）",
            "catalysts": [{"date": "2026-11 下旬", "event": "範例：下一季財報"}],
            "risk_matrix": [{"risk": "範例風險", "probability": "中", "impact": "高", "mitigant": "範例緩解"}],
            "kill_criteria": ["範例失效條件 A"],
            "sources": [SRC],
        },
    }
    for name, data in files.items():
        (WD / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    nvda = ROOT / "work" / "NVDA"  # 借用真實股價圖測版面
    for f in ("indicators.json", "chart_technical.png"):
        if (nvda / f).exists():
            shutil.copy(nvda / f, WD / f)
    print(WD)


if __name__ == "__main__":
    main()
