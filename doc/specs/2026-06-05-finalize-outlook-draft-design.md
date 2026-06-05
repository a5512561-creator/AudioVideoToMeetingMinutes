# 互動式 Finalize → Outlook 草稿 — 設計文件

- **日期**: 2026-06-05
- **版本**: v1
- **作者**: paddychen + Claude (brainstorming)
- **狀態**: Draft (待 review)
- **關聯**: 延伸 `2026-05-18-transcript-to-minutes-design.md` 的輸出階段；新增互動確認與 Outlook 草稿產出

---

## 1. 目標與動機

現狀：`process` 跑完 LLM 後直接輸出 `minutes.html`、`review_report.md`、`minutes_email.html`，其中會議記錄與 action items 全是 LLM 依逐字稿推論的，且會議資訊欄（時間、地點、與會者…）只有空白佔位。

使用者需求：

1. 除了現有 HTML，需要把會議記錄產出成 **Email 草稿**，且**不寄出**，而是新增成 Outlook 可編輯的草稿（使用者要自行修改確保內容）。
2. 不知道、沒有資訊的部份（例如與會者）**不要自行推論**，留白由使用者填。
3. 需要一個 **Q&A 流程**問使用者會議資訊，並**逐一確認** LLM 判斷的每條會議記錄/決議與 action item（action 另確認負責人、到期日）。

格式對齊公司既有「會議記錄 email」範本（樣本：`RE Channelize IP HW architecture discussion.msg`）。

範圍外：

- 不改動 `process` 的 LLM 階段邏輯。
- 不解析 `.msg`（僅作為格式參考，內容已內化進本設計）。
- 不自動寄信、不自動填收件人。

---

## 2. 公司 Email 格式（取自 .msg 樣本）

```
Dear all :

📅 會議日期：2026/06/03
🕒 會議時間：16:00 - 18:00
📍 會議地點 / 會議室：R531
👥 參與人員：Max Mai、張岳華、…、線上同仁
📝 記錄人：林冠名
會議文件： <檔名 + SharePoint 連結>
會議錄影： <檔名 + SharePoint 連結>

1. 會議記錄與決議
   表格：No | 項目 | 摘要         （決議寫進「摘要」散文中，無獨立決議欄）

2. Action Items
   表格：No | 行動項目 | 負責人 | 到期日 | 備註

Best regards,
CN5 DD2 <記錄人>
```

與現有 `minutes_email.html.j2` 的差異：

| 區塊 | 現有模板 | 對齊後 |
|---|---|---|
| 開頭 / 署名 | 無 | `Dear all :` + `Best regards, <記錄人>` |
| 1. 會議記錄 | h3 標題 + 摘要段落 + 決議 bullets | 表格 `No\|項目\|摘要`，決議併入摘要 |
| 2. Action | `#\|任務\|負責人\|期限\|優先級` | `No\|行動項目\|負責人\|到期日\|備註`（**移除優先級欄、新增備註欄**） |

備註欄預設留空（使用者於草稿視窗自行補）；不再顯示 priority。

---

## 3. 高層架構

新增一個**獨立互動指令** `finalize`，與批次 `process` 分離：

```
process  (現狀；慢、跑 LLM)
   → out/<name>/intermediate/synthesized.json (+ minutes.html …)

finalize (新增；互動、不跑 LLM)
   → 讀 out/<name>/intermediate/synthesized.json
   → 終端 Q&A：會議資訊 + 逐項確認(決議 / action)
   → out/<name>/finalized.json
   → 渲染公司格式 email HTML
   → 開啟 Outlook 可編輯草稿（.Display()，不寄出）
```

分離理由：`process` 需數分鐘且耗 token；`finalize` 純互動、可重複跑、不重花 token。

---

## 4. 元件設計

各單元單一職責、介面清楚、可獨立測試。

### 4.1 `schemas.py` 擴充

`MeetingMeta` 新增欄位（全部 `str = ""`，預設空＝不推論）：

```python
class MeetingMeta(BaseModel):
    meeting_date: str
    duration_hint: str
    meeting_time: str = ""     # "16:00 - 18:00"
    location: str = ""         # 會議室
    attendees: str = ""        # 參與人員（自由文字）
    recorder: str = ""         # 記錄人（也用於署名）
    doc_links: str = ""        # 會議文件（自由文字，可含連結）
    video_links: str = ""      # 會議錄影
    jira: str = ""             # JIRA 連結（optional）
```

新增確認後的資料模型：

```python
class FinalTopic(BaseModel):
    item: str          # 項目（= synth topic title）
    summary: str       # 摘要（synth summary，已併入決議文字）

class FinalAction(BaseModel):
    task: str
    owner: str
    due: str
    note: str = ""     # 備註

class FinalizedMinutes(BaseModel):
    meta: MeetingMeta
    subject: str
    topics: list[FinalTopic] = []
    actions: list[FinalAction] = []
```

預設值維持向後相容（既有快取 JSON 可載入）。

### 4.2 `script/qna.py`（純互動邏輯）

介面：`run_qna(synth: SynthesizedMinutes, *, defaults: FinalizedMinutes | None = None, inp=input, out=print) -> FinalizedMinutes`

- `inp`/`out` 可注入，測試以假 stdin 餵入。
- 流程：
  1. **主旨**：預設帶入逐字稿檔名（`name`/`src` basename），Enter 採用、可改。
  2. **會議資訊**：日期（預設帶入 `infer_meeting_date` 結果，可改）、時間、地點/會議室、參與人員、記錄人、會議文件、會議錄影、JIRA(optional)。各欄空白允許 → 留白不推論。
  3. **逐項決議**：對每個 `synth.topics`：顯示「項目 + 摘要(已併入決議)」→ `Enter`保留 / `e`改寫(逐欄問 項目、摘要；Enter 維持原值) / `d`刪除。走完該段提示是否末尾新增（可連續加）。
  4. **逐項 action**：對每個 `synth.action_items`：顯示「任務 / 負責人 / 到期日」→ `e`改寫任務 / `d`刪除；**每項都再確認負責人、到期日**（預設帶 LLM 值，Enter 採用）；可填備註。走完提示末尾新增。
- 決議文字併入摘要規則：`summary = synth.summary`，若 `topic.decisions` 非空則於摘要後接「決議：<以、分隔或分行>」。此併入在進入 Q&A 顯示前完成，使用者看到並可改的就是最終文字。
- 回傳 `FinalizedMinutes`。

若提供 `defaults`（重跑時讀上次 `finalized.json`），每個欄位/項目以上次值為預設。

### 4.3 `script/outlook_draft.py`（唯一 COM 依賴）

介面：`open_draft(subject: str, html_body: str) -> bool`

- 以 `win32com.client.Dispatch("Outlook.Application")` 建 `MailItem`（`CreateItem(0)`），設 `.Subject`、`.HTMLBody`，**不設收件人**，呼叫 `.Display(False)` 開啟可編輯草稿視窗（不寄出）。
- 回傳是否成功。**任何例外（pywin32 未裝 / COM 失敗 / Outlook 不在）皆捕捉**，回傳 `False`，由呼叫端 fallback。

### 4.4 `minutes_email.html.j2` 改版

對齊 §2 公司格式：`Dear all :`、emoji 資訊區（空欄位顯示空白而非 `____`）、兩個表格（決議表 `No|項目|摘要`、action 表 `No|行動項目|負責人|到期日|備註`）、`Best regards, <記錄人>` 署名。維持 inline style、無 JS、可貼進 Outlook。

渲染輸入改為 `FinalizedMinutes`（而非原 `SynthesizedMinutes`）。

### 4.5 `script/email_writer.py` 調整

`write_email_html` 改吃 `FinalizedMinutes`，輸出 HTML 字串並寫檔；`finalize` 指令同時用此 HTML 餵給 `outlook_draft.open_draft`。

> 註：`pipeline.run_pipeline` 內現有的 `write_email_html(synth, …)` 呼叫需配合調整——`process` 階段尚無使用者確認資料，故 `process` 時改用「由 synth 直接轉成的 FinalizedMinutes（meta 欄位留白、未確認）」產生初版 `minutes_email.html`，作為預覽；真正的草稿在 `finalize`。提供 `synth_to_finalized(synth, meta, subject) -> FinalizedMinutes` 轉換函式共用。

### 4.6 `main.py` 新增 `finalize` 指令

```
finalize SRC_OR_NAME [--name] [--reuse]
```

- 定位 `out/<name>/intermediate/synthesized.json`（`name` 預設取 basename，與 `process` 一致）。不存在 → 明確錯誤提示先跑 `process`。`finalize` 的 `SRC_OR_NAME` 可直接給逐字稿路徑（取 basename）或既有的輸出資料夾名。
- `--reuse`：若 `out/<name>/finalized.json` 存在，載入為 Q&A 預設值。
- 流程：載入 synth → `run_qna` → 寫 `finalized.json` → `write_email_html` 寫 `minutes_email.html` → `open_draft`；COM 失敗則提示已輸出 HTML 檔。

### 4.7 相依套件

`requirements`（或 `pyproject`）新增 **`pywin32`**（runtime，Windows）。`extract_msg` 僅為一次性讀樣本，不列入 runtime 相依。

---

## 5. 資料流

```
synthesized.json (SynthesizedMinutes)
  → synth_to_finalized → FinalizedMinutes(初值)
  → run_qna(終端互動) → FinalizedMinutes(確認後)
  → finalized.json
  → minutes_email.html.j2 → HTML
       ├→ 寫 out/<name>/minutes_email.html
       └→ outlook_draft.open_draft(subject, html) → Outlook 可編輯草稿
```

---

## 6. 錯誤處理

- `synthesized.json` 不存在 → `RuntimeError`，訊息提示先 `process`（沿用 pipeline 既有風格）。
- pywin32 未裝 / Outlook COM 失敗 → `open_draft` 回傳 `False`；`finalize` 印出「已輸出 minutes_email.html，請手動開啟」並正常結束（不中斷）。
- Q&A 期間 `Ctrl-C`：不寫 `finalized.json`，原樣退出（避免半套覆寫）。
- 空白輸入一律視為「不填」，不做任何推論。

---

## 7. 測試策略

- `tests/test_qna.py`：以假 `inp`（預先排好的輸入序列）驗證
  - 會議資訊各欄填入 / 留白；
  - 決議保留 / 改寫 / 刪除 / 末尾新增；
  - action 改寫任務、確認負責人+到期日、刪除、新增；
  - `--reuse` 預設值帶入。
- `tests/test_email_template.py`：渲染 `FinalizedMinutes` 快照，確認表格欄位（決議三欄、action 五欄含備註、無優先級）、署名、空欄位不出現 `____`/不推論。
- `tests/test_outlook_draft.py`：以 mock 取代 `win32com`，驗證設定 Subject/HTMLBody 且未設收件人、未呼叫 Send；COM 例外時回傳 False。
- 驗收：對 `out/20260604_Switch_RXDMA_CFT/` 跑一次 `finalize`，完成 Q&A 後 Outlook 跳出已填好的草稿，欄位內容與確認結果一致。

---

## 8. 未來工作（本次範圍外）

- 收件人/CC 自動帶入（目前一律留空由使用者填）。
- 從 `.msg` 自動萃取收件人清單或主題串接「RE:」。
- Q&A 支援多行貼上、SharePoint 連結驗證。
