# 分析師交件格式（Analyst Contract）

所有分析師（macro / industry / fundamental / technical）都必須用這份格式交件，
研究總監與反方風控官只認這份格式。交件存成 `work/<TICKER>/<role>.json`。

## JSON 結構

```json
{
  "role": "macro | industry | fundamental | technical",
  "ticker": "NVDA",
  "as_of": "2026-11-02",
  "stance": "bullish | neutral | bearish",
  "confidence": 1,
  "headline": "一句話結論（30 字以內）",
  "theses": [
    {
      "claim": "具體主張，必須含數字",
      "evidence": "支撐這條主張的數據或事實",
      "source": "來源名稱 + URL 或檔案路徑",
      "source_date": "YYYY-MM-DD"
    }
  ],
  "key_metrics": [
    {"name": "指標名稱", "value": "數值含單位", "period": "期間", "source": "來源"}
  ],
  "risks": ["這個面向最大的 2–4 個風險"],
  "change_my_mind": ["出現什麼數據，我就會改變結論"],
  "open_questions": ["查不到或不確定的事，誠實列出"]
}
```

## 規則

1. **沒有來源的數字不准出現。** 查不到就寫進 `open_questions`，不要估。
2. `theses` 3–5 條；每條 `claim` 至少含一個可驗證的數字。
3. `confidence` 1–5：1 = 幾乎是猜測，3 = 證據普通，5 = 多個一手來源互相印證。
4. 一手來源優先：公司 IR、10-K/10-Q、法說會逐字稿、Fed/BLS/BEA 官方數據。
   媒體報導只能當輔助，且要標明是二手。
5. `as_of` 與每條 `source_date` 必須填。超過 6 個月的數據要在 claim 內註明。
6. **不得把使用者的任何個人資料（email、姓名、帳號、API 金鑰）放進對外請求**（URL、標頭、表單）。
   讀 SEC 文件優先用 WebFetch／網路搜尋；若必須用 curl，User-Agent 用
   `AI-Research-Team research-bot`，不附個人 email。
7. 除了 JSON 檔，在對話中只回報 `headline`、`stance`、`confidence` 三項，不要貼全文。

## 反方風控官的交件（`work/<TICKER>/devils-advocate.json`）

```json
{
  "role": "devils-advocate",
  "ticker": "NVDA",
  "as_of": "2026-11-02",
  "challenges": [
    {
      "id": "C1",
      "target": "被攻擊的論點（引用分析師的 role + claim）",
      "attack": "反駁內容，必須含數字或具體事實",
      "evidence": "反駁的依據",
      "source": "來源",
      "severity": "fatal | major | minor",
      "what_would_resolve": "總監要拿出什麼才能化解這條質疑"
    }
  ],
  "consensus_trap": "市場共識可能錯在哪裡（一段話）",
  "bear_case": {"price": "空頭情境價位", "probability": "機率 %", "narrative": "空頭劇本"},
  "kill_criteria": ["論點失效條件：出現就應出場或降評"]
}
```

## 總監答辯（`work/<TICKER>/rebuttal.json`）

```json
{
  "responses": [
    {"id": "C1", "status": "resolved | partially | unresolved", "reply": "答辯內容與依據"}
  ]
}
```

**評等上限規則（硬性）：**
- 任一 `fatal` 不是 `resolved`（`partially` 也算）→ 評等最高「中性」。
- 兩條以上 `major` 不是 `resolved` → 信心度最高 3，且報告須在摘要明示。
- `resolved` 只能用在兩種情況：拿出符合 `what_would_resolve` 的證據，或已接受質疑並修正報告。
  「等下一季財報」不算化解。
