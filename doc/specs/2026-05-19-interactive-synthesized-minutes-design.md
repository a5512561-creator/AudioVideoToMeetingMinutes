# 互動版 minutes.html 改吃綜整內容 — 設計文件

- **日期**: 2026-05-19
- **版本**: v1
- **作者**: paddychen + Claude (brainstorming)
- **狀態**: Draft (待 review)
- **關聯**: 接續 `2026-05-19-email-minutes-synthesis-design.md`（綜整 + Email 輸出）

---

## 1. 目標與動機

`minutes.html`（互動：分頁/篩選/搜尋）與 `minutes_email.html`（貼 Email）**內容不同**：
前者來自原始 `MeetingMinutes`（16 結論/25 action，逐項細粒度），後者來自
`SynthesizedMinutes`（9 議題/14 決議/12 action，已收斂）。使用者偏好綜整後的
內容，但給人線上看時 `minutes.html` 的篩選/搜尋較好用。

需求：**`minutes.html` 改為呈現綜整內容，但保留互動 UI**；`minutes_email.html`
維持不變。兩者變成「同內容、不同呈現」。原始細粒度資料仍保留在
`minutes.json` / `review_report.md` 供稽核。

範圍外：
- 不改 `email_writer.py` / `minutes_email.html` 行為。
- 不改 map/reduce/synthesis 抽取與綜整邏輯。
- `review_report.md` 仍以原始 `MeetingMinutes` 產生（不變）。

---

## 2. 既定決策（brainstorming 結論）

| 項目 | 決定 |
|---|---|
| 做法 | **A**：改寫 `html_writer.py` + `minutes.html.j2` 改吃 `SynthesizedMinutes`（單一互動 renderer，移除原始逐項/語者死碼）|
| 原始細粒度 + 來源原句 | 從 HTML 拿掉；仍完整保留在 `minutes.json` / `review_report.md` |
| Review | minutes.html 保留 **Review 分頁**，顯示 reviewer 的 warn/error（來自 `review.json`）|
| 互動功能 | 3 分頁（議題與決議 / Action Items / Review）+ 全文搜尋 + Action 優先級篩選 |
| minutes_email.html | 不變（同一份 synth 的貼上版）|

`★ ID 落差（誠實說明）`：現有 Review 是針對**原始** `MeetingMinutes` 逐項做的
（`target_id` 如 C1/A1 指向原始項）。綜整後這些 ID 對不上新議題/action。Review
分頁照常顯示 warn/error（note + suggestion + 原始 section + 嚴重度），定位為
「詳細審查階段標記的品質警示，供交叉檢查」，**不與綜整議題逐項連動**；分頁頂部
明文說明此點。

---

## 3. 架構與元件

採方案 A。

### 3.1 `script/html_writer.py` 變更

- 簽章改為：
  `write_minutes_html(synth: SynthesizedMinutes, review: ReviewResult, dst: str, *, meeting_file: str, meta: MeetingMeta) -> None`
- 移除（綜整資料無此概念）：`_conclusion_view`、`_keypoint_view`、`_action_view`、
  `_hue`、`_speaker_distribution`、speaker 相關 import（`_remap`/`_remap_text`/
  `speaker_map`）與 `diarization_enabled`/`speakers_detected`/`speaker_map` 參數。
- 新增 view 組裝：
  - `topics`：每筆 `{title, summary, decisions: [...], source_timestamps: [...]}`
  - `actions`：每筆 `{idx, task, owner, due, priority}`（優先級供前端篩選）
  - `review_rows`：沿用現有「warn/error 摘要」邏輯（`{id, section, category,
    severity, icon, note, suggestion}`），只取 `severity in (warn, error)`。
  - `meta`：`{meeting_date, duration_hint}`；`synth.meta` 為 None 時套用與
    `email_writer._empty_meta()` 相同的 fallback（共用一個 helper，見 3.4）。
- jinja2 `Environment(autoescape=True)`（與現況一致）。

### 3.2 `script/templates/minutes.html.j2` 改寫

- 自包含單檔 HTML（沿用現有「無外部資源、可離線開」風格），含極簡內嵌 JS
  （分頁切換、優先級篩選、全文搜尋高亮）——這是互動版，允許 JS（與
  `minutes_email.html` 的「無 JS」限制不同）。
- 表頭：會議檔名、會議日期（`meta.meeting_date`）、逐字稿長度提示
  （`meta.duration_hint`）、計數（議題 N / 決議 N / Action N / warn N / error N）。
- 分頁 1 **議題與決議**：每議題卡片＝標題 + 摘要段 + 決議 `<ul>` +
  小字 source_timestamps。
- 分頁 2 **Action Items**：表格（# / 任務 / 負責人 / 期限 / 優先級），上方
  high/medium/low 篩選鈕（純前端切換顯示）。
- 分頁 3 **Review**：頂部說明句（§2 的 ID 落差說明）；下方 warn/error 清單
  （嚴重度 icon + section + note + suggestion）。
- 全域搜尋框：跨三分頁做關鍵字過濾/高亮（純前端）。

### 3.3 `script/pipeline.py` 變更

- 主流程 Stage 5：`synth` 產生後，原本傳 `MeetingMinutes` 給
  `write_minutes_html` 的呼叫，改為
  `write_minutes_html(synth, review, str(out_dir / "minutes.html"), meeting_file=src, meta=meta)`。
  `write_email_html(...)` 與 `write_review_report_md(...)`（仍吃原始
  `minutes`）不變。
- `rerender_only` 路徑：互動 `minutes.html` 現在需 `synthesized.json`（內含
  `meta`）＋ `review.json`；`review_report.md` 仍需 `minutes.json`。更新前置
  檢查為三者皆需，錯誤訊息列出三個檔；以 `synthesized.json` 重建 synth、
  `review.json` 重建 review、`minutes.json` 重建 minutes（給 review_report）。
  `minutes_email.html` 重建沿用既有 synth 重建分支。

### 3.4 共用 meta fallback

- 將 `email_writer.py::_empty_meta()` 提為共用：移到 `script/meeting_meta.py`
  成 `empty_meta() -> MeetingMeta`（回 `meeting_date="YYYY/MM/DD"`,
  `duration_hint="逐字稿長度未知"`）。`email_writer.py` 與 `html_writer.py`
  皆改 import 之，移除 `email_writer.py` 內的私有 `_empty_meta`。

---

## 4. 資料流

```
SynthesizedMinutes(含 synth.meta) ──┬─→ write_minutes_html(+review)  → minutes.html  (互動)
                                    └─→ write_email_html             → minutes_email.html (貼 Email)
原始 MeetingMinutes ────────────────────→ write_review_report_md     → review_report.md (稽核，不變)
                                          + intermediate/minutes.json (稽核，不變)
ReviewResult ───────────────────────────→ minutes.html 的 Review 分頁 + review_report.md
```

minutes.html 與 minutes_email.html 同內容（皆 synth），不同呈現。

---

## 5. 錯誤處理

- `rerender_only` 缺三必要檔之一 → `RuntimeError`，訊息列出
  `minutes.json` / `review.json` / `synthesized.json`。
- `synth.meta` 為 None（理論上 pipeline 都會注入）→ `empty_meta()` fallback，
  非錯誤。
- 其餘沿用既有 pipeline 例外風格。

---

## 6. 測試策略

- 重寫 `tests/test_html_writer.py`：給定 `SynthesizedMinutes` + `ReviewResult` +
  `MeetingMeta`，斷言：
  - 表頭含會議日期、duration hint、議題/決議/Action/warn/error 計數
  - 三分頁標記存在（議題與決議 / Action Items / Review）
  - 議題標題、摘要、決議文字、source_timestamps 出現
  - Action 表格欄位與三個優先級篩選鈕存在
  - Review 分頁含 ID-落差說明句與 warn/error 的 note/suggestion
  - **不含** speaker / 來源原句 / `SPEAKER_` 殘留
  - HTML 跳脫（傳入 `<b>` → `&lt;b&gt;`）
- `tests/test_meeting_meta.py`：新增 `empty_meta()` 測試。
- `tests/test_email_writer.py`：調整為 import 共用 `empty_meta`（行為不變，
  既有斷言應仍綠）。
- `tests/test_pipeline.py`：更新 —— `write_minutes_html` 改以 synth/meta 呼叫；
  rerender 測試補 `synthesized.json` 為必要、缺檔 raise。
- 驗收：對 `out/leadersync_20260518` 重跑（或 `--rerender`），人工確認
  `minutes.html` 顯示綜整內容、三分頁/篩選/搜尋可用、Review 分頁有警示且有
  落差說明、`minutes_email.html` 不變。

---

## 7. 未來工作（範圍外）

- 若日後要把 Review 與綜整議題逐項對應，需在 synthesis 階段建立
  raw-item → synth-item 對照（本次不做）。
- 議題側邊跳轉/折疊（brainstorming 時的「豐富」選項）暫不做。
