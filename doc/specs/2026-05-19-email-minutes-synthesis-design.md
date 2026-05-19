# 會議記錄綜整 + Email 範本輸出 — 設計文件

- **日期**: 2026-05-19
- **版本**: v1
- **作者**: paddychen + Claude (brainstorming)
- **狀態**: Draft (待 review)
- **關聯**: 接續 `2026-05-18-transcript-to-minutes-design.md`（逐字稿輸入架構）

---

## 1. 目標與動機

實測 1h55m 會議產出 14 結論 / 21 action / 80 review，**逐句、過細、難讀、不是真正的 action**。
根因：pipeline 只有 **map（逐段抽取）→ reduce（去重合併）**，沒有「綜整」階段；
`minutes_system.j2` 規定每項對應逐字稿真實句（追溯性好但逼出細碎抽取），
`minutes_reduce.j2` 只合併重複、從不收斂成主題式決議或收斂過程性閒聊。

需求：
1. 新增「綜整」階段：把抽取結果收斂成**依議題分組**的可讀內容＋**真可交付**的 Action。
2. 新增一份**精簡 Email HTML**，對齊團隊會議記錄範本，使用者可直接貼進 Outlook 寄出。

範圍外：
- 不改既有 map/reduce 行為、不改 `minutes.html` / `review_report.md`（皆保留）。
- 不做 speaker 識別（參與人員仍由使用者手填）。

---

## 2. 既定決策（brainstorming 結論）

| 項目 | 決定 |
|---|---|
| 綜整做法 | **A**：reduce 之後新增獨立「綜整」LLM 階段，吃 reduced `minutes.json`，現有產出全部保留 |
| §1 會議記錄與決議 | **依議題分組**：主題標題 + 2–4 句討論摘要 + 該議題決議清單 |
| §2 Action Items | **表格**：任務 / 負責人 / 期限 / 優先級；只留有交付物的項目；無法判定填「未明」 |
| 範本表頭 | 能自動帶的帶（日期、會議時長提示），其餘留 `____` 佔位 |
| 追溯性 | 主體不放；**文末附簡要來源清單**（決議 / action → 時間戳） |
| 輸出檔 | 另存 `minutes_email.html`，**不取代**現有檔 |

---

## 3. 範本欄位對應

範本固定欄位 → 來源：

| 範本欄位 | 來源 |
|---|---|
| 📅 會議日期：YYYY/MM/DD | 自動：從輸出資料夾名／來源檔名推（如 `20260518_leadersync` → 2026/05/18）；推不出落 `YYYY/MM/DD` 佔位 |
| 🕒 會議時間：HH:MM - HH:MM | 不猜時鐘時間；顯示提示「（逐字稿長度約 Xh Ym）」+ `____` 佔位 |
| 📍 會議地點 / 會議室 | `____` 佔位 |
| 👥 參與人員 | `____` 佔位（無 speaker 識別） |
| 📝 記錄人 | `____` 佔位 |
| 會議文件 / 會議錄影 / JIRA連結 | `____` 佔位（JIRA 標示 optional） |
| 1. 會議記錄與決議 | `SynthesizedMinutes.topics`（議題分組） |
| 2. Action Items | `SynthesizedMinutes.action_items`（表格） |
| （文末）來源對照 | `SynthesizedMinutes.source_index` |

---

## 4. 架構與元件

採方案 A：reduce 之後新增獨立綜整階段；現有 map/reduce、`minutes.html`、`review_report.md` 不動。

### 4.1 `script/schemas.py` 新增

```python
class SynthTopic(BaseModel):
    title: str                       # 議題標題
    summary: str                     # 2–4 句討論摘要
    decisions: list[str]             # 該議題決議（0..n）
    source_timestamps: list[str]     # 底層抽取項的時間戳集合

class SynthAction(BaseModel):
    task: str
    owner: str                       # 無法判定 = "未明"
    due: str                         # 無法判定 = "未明"
    priority: Literal["high","medium","low"]
    source_timestamps: list[str]

class SourceRef(BaseModel):
    label: str                       # 例 "決議 1" / "Action 2"
    timestamps: list[str]

class MeetingMeta(BaseModel):
    meeting_date: str                # "2026/05/18" 或 "YYYY/MM/DD"
    duration_hint: str               # 例 "逐字稿長度約 1h 55m"

class SynthesizedMinutes(BaseModel):
    meta: MeetingMeta
    topics: list[SynthTopic]
    action_items: list[SynthAction]
    source_index: list[SourceRef]
```

既有 `MeetingMinutes` / `Conclusion` / `Action` / `KeyPoint` 不變。

### 4.2 `script/agents/synthesis_agent.py`（新）

- `SynthesisAgent(LLMAgent)`，沿用 `script/agents/base.py` 既有模式（instructor、retry、usage log）。
- 介面：`synthesize(minutes: MeetingMinutes, meta: MeetingMeta) -> SynthesizedMinutes`。
  `meta` 由 pipeline 計算後傳入，agent 原樣放進輸出模型的 `meta` 欄位（LLM 不負責推日期/時長，僅負責 topics / action_items / source_index）。
- 輸入：reduced `MeetingMinutes` 的 JSON（conclusions + key_points + actions，含 source_timestamp）。
- prompt `script/prompts/synthesis_system.j2` / `synthesis_user.j2` 指令重點：
  1. 依議題把 conclusions/key_points 分組，每組寫標題 + 2–4 句摘要 + 決議清單。
  2. Action 必須是「有明確交付物」者才列；合併子步驟；過程性閒聊／職人語不列。
  3. 無法判定的 owner / due 填「未明」，不得臆造。
  4. **不得新增逐字稿（即輸入抽取項）中未出現的內容**（延續 Fragment-First 精神）。
  5. 每個 topic / action 帶回其底層抽取項的 `source_timestamp` 以供來源清單。
  6. 輸出嚴格符合 `SynthesizedMinutes` schema；全繁體中文。
- meta 由 pipeline 計算後注入（agent 不負責推日期；見 4.4）。

### 4.3 `script/email_writer.py`（新）

- 介面：`write_email_html(synth: SynthesizedMinutes, dst: str, *, meeting_file: str) -> None`。
- 產出**精簡 Email HTML**：語意標籤 + `<table>` + inline 樣式；**無 `<script>`、無折疊、無 flex/grid**；CJK 可讀；刻意做到貼進 Outlook 不跑版。
- 結構：範本表頭（§3 欄位，能帶帶、其餘 `____`）→ §1 議題分組（每 topic：`<h.>` 標題 + 摘要段 + 決議 `<ul>`）→ §2 Action `<table>`（# / 任務 / 負責人 / 期限 / 優先級）→ 文末「來源對照」清單。
- 沿用 jinja2（與 `html_writer.py` 一致），模板 `script/templates/minutes_email.html.j2`。

### 4.4 `script/pipeline.py` 變更

- reduce 產生 `minutes.json` 後，新增 **Stage 5：synthesis**：
  - 計算 `MeetingMeta`：`meeting_date` 由新工具 `script/meeting_meta.py::infer_meeting_date(name, src)` 推（資料夾名/檔名找 `YYYYMMDD` 或 `YYYY-MM-DD`；找不到回 `"YYYY/MM/DD"`）；`duration_hint` 由 transcript 首末 `[HH:MM:SS]` 算。
  - `SynthesisAgent.synthesize(minutes, meta)` → 寫 `intermediate/synthesized.json`。
  - `write_email_html(...)` → `out/<name>/minutes_email.html`。
  - token usage 計入既有彙總；新增 `log_kv` 階段日誌 `stage.synthesis`。
- `rerender_only` 路徑：若 `intermediate/synthesized.json` 存在則重渲染 `minutes_email.html`，否則略過該檔（不強制）。
- 既有輸出與行為不變。

### 4.5 `script/meeting_meta.py`（新，小工具）

- `infer_meeting_date(name: str | None, src: str) -> str`：從 name/src basename 抓 `\d{8}` 或 `\d{4}[-/]\d{2}[-/]\d{2}`；正規化成 `YYYY/MM/DD`；無 → `"YYYY/MM/DD"`。
- `duration_hint(transcript_md_text: str) -> str`：取首末 `[HH:MM:SS]`，算差 → `"逐字稿長度約 Xh Ym"`；無時間戳 → `"逐字稿長度未知"`。

---

## 5. 資料流

```
transcript.md → chunk → map → reduce → minutes.json   (現有，不變)
                                  │
                                  ├─→ minutes.html / review_report.md   (現有，不變)
                                  │
meeting_meta(name,src,transcript) ┘
        │
        ▼
SynthesisAgent.synthesize(minutes) + meta
        │
        ▼
intermediate/synthesized.json → email_writer → out/<name>/minutes_email.html
```

---

## 6. 錯誤處理

- 無 reduced `minutes.json`（理論上不會，reduce 之後才跑）→ 沿用既有 pipeline 例外風格。
- synthesis LLM 回傳不符 schema → 沿用 `instructor` + `LLM_MAX_RETRIES` 重試機制（與既有 agent 一致）。
- 會議日期推不出 → `"YYYY/MM/DD"` 佔位（非錯誤）。
- 逐字稿無時間戳 → `duration_hint = "逐字稿長度未知"`，來源清單時間戳可能為 `00:00:00`（沿用既有行為，非錯誤）。

---

## 7. 測試策略

- `tests/test_meeting_meta.py`：日期推導（8 碼／含分隔／推不出）、duration_hint（正常／無時間戳）。
- `tests/test_synthesis_agent.py`：mock LLM client，驗證輸入為 reduced minutes JSON、輸出 parse 成 `SynthesizedMinutes`、meta 由外部注入。
- `tests/test_email_writer.py`：給定 `SynthesizedMinutes` → 斷言 HTML 含範本各欄位文字、§1 議題標題與決議、§2 表格欄位、文末來源清單；**斷言不含 `<script>`、不含 `class="tab"` 等互動殘留**。
- `tests/test_pipeline.py`：擴充——mock `SynthesisAgent` 與 `write_email_html`，斷言 Stage 5 在 reduce 後被呼叫、`minutes_email.html` 被寫、且既有 `minutes.html`/`review_report.md` 仍被寫（不回歸）。
- `tests/test_schemas.py`：`SynthesizedMinutes` 巢狀模型基本驗證。
- 驗收：對 `out/leadersync_20260518` 重跑（或 `--rerender`），人工檢視 `minutes_email.html` 是否可讀、可直接貼 Outlook、議題分組合理、Action 為真交付項。

---

## 8. 未來工作（範圍外）

- speaker 識別接上後，參與人員可自動帶入（接 `2026-05-18` spec §8 擴充點）。
- 若需 `.docx` 版本，另起 spec（本次只做 Email HTML）。
- 兩段式綜整（方案 C）僅在超長會議品質不足時再評估。
