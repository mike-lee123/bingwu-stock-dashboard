# 6 人 AI 投資研究團隊

```
研究總監 ─┬─ 總經分析師      ┐
          ├─ 產業分析師      │ 並行研究，交件格式見 shared/analyst-contract.md
          ├─ 基本面分析師    │
          └─ 技術面分析師    ┘
             ↓ 總監初稿
          反方風控官（致命疑點未化解 → 評等最高中性）
             ↓ 總監答辯、定稿
          scripts/render_report.py → reports/<TICKER>_<日期>.pdf
```

## 使用
在 Claude Code 中輸入：`/research-director NVDA 最新一季財報`

## 檔案
| 路徑 | 用途 |
|---|---|
| `.claude/skills/*/SKILL.md` | 6 個角色的 skill |
| `shared/analyst-contract.md` | 交件 JSON 格式與評等上限規則 |
| `scripts/fetch_prices.py` | 下載股價、算指標、畫技術面圖（`--quote` 只看報價） |
| `scripts/render_report.py` | 組成研報 HTML，用 Edge 轉 PDF（`--html-only` 調版面用） |
| `scripts/report.css` | 研報版面樣式 |
| `scripts/make_demo.py` | 產生虛構範例資料，測試版面用 |
| `work/<TICKER>/` | 每次研究的中間產物 |
| `reports/` | 最終 PDF |

## 需求
Python 3.9+、`yfinance`、`pandas`、`matplotlib`；Windows 內建 Edge（轉 PDF）、微軟正黑體。
