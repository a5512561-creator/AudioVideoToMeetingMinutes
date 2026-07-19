# P3 — 可編輯會議記錄 HTML → Outlook 草稿（本地 server）設計

- **日期**：2026-07-19
- **狀態**：設計（brainstorming 產出，待複審）
- **範圍**：AudioVideoToMeetingMinutes 工作流的 P3 子計畫 — 產出後的「編輯 → 匯出到 Outlook」體驗
- **前置**：P1（audit 骨幹）、P2（入口 + 隱私）。本文件僅為設計，尚未實作。

---

## 0. 背景與動機

現有工作流：`/meetingminutes` skill → `process` pipeline → 產生 `minutes.html`（唯讀）＋ `intermediate/synthesized.json` ＋ `audit.json`。痛點:

- LLM 產出的會議記錄每次都要人工再修，但現在的修改要靠 CLI 互動，不夠好用。
- 使用者要的體驗：**在 HTML 內直接編輯**決議／內文／action，編輯完按一個鈕，就**開啟 Outlook 草稿、把整理好的會議記錄放進信件內文**（不寄出），同時把成品留在會議資料夾供 SharePoint 上傳。

「開 Outlook 草稿帶內文」的機制**已存在**：`script/outlook_draft.py` 的 `open_draft(subject, html_body)`（win32com COM，開可編輯視窗、不 Send）。但它需要一個**本地 Python 程序**去呼叫 — 瀏覽器單靠自己叫不動 Outlook COM。因此本設計採用**本地簡易 server**。

（brainstorming 已排除「純前端無 server」：因為 mailto 無法可靠帶富文字內文，且瀏覽器無法呼叫 Outlook COM。使用者原先傾向無 server，本子計畫經討論後改採本地 server。）

---

## 1. 架構

本地 Python **簡易 server**，用**標準庫 `http.server`（不新增依賴）**，只綁定 `127.0.0.1`（不對外）。端到端流程:

```
process 產生 intermediate/synthesized.json + intermediate/audit.json（P1/P2 既有）
   ↓
使用者執行  python -m script.main edit <name>
   ↓
server 載入該 out/<name> 的 synthesized.json + audit.json，於 127.0.0.1:<port> 起服務，開瀏覽器
   ↓
瀏覽器內：contenteditable 編輯議題標題／summary／決議／action；即時 Layer-1 重驗；勾「已審閱」
   ↓
按「匯出並開 Outlook」→ POST 編輯後 DATA（JSON）給 server
   ↓
server 端「權威」重驗 Layer-1（不信任前端）→ 通過 →
     (a) 把編輯後內容存回 intermediate/synthesized.json
     (b) 產 email.html 寫回會議資料夾
     (c) 呼叫 open_draft() 開 Outlook 草稿（帶內文、不寄出）
   ↓
server 回 JSON 狀態 → 瀏覽器顯示成功／哪幾項未過／Outlook 是否成功開啟
```

**設計原則**：pipeline 只「產生」，server 只「編輯＋匯出」，兩者職責分離。server 不重跑任何 LLM。

---

## 2. 元件（各一責任，重用既有碼）

### 2.1 `script/edit_server.py`（新）
標準庫 `http.server` 的 `BaseHTTPRequestHandler`。路由:

- `GET /` → 回編輯頁 HTML（DATA 內嵌成 `window.DATA`）。
- `GET /data` → 回目前 `{synthesized, audit}` JSON（供前端載入 / 需要時重取）。
- `POST /export` → 收編輯後 JSON；server 端重驗 Layer-1；通過則寫檔 + 開 Outlook；回狀態 JSON。

啟動函式 `serve(out_dir, *, open_browser=True) -> None`：找空 port、起 server、（可選）開瀏覽器、阻塞直到使用者關閉（Ctrl-C）或匯出後可選擇自動關。**只綁 127.0.0.1。**

### 2.2 `script/templates/edit.html.j2`（新）
沿用 `minutes.html.j2` 的樣式與結構，改為可編輯:

- 議題標題、每句 summary、每條決議、action 的任務／負責人／期限／優先級 → `contenteditable`。
- `window.DATA` 為**唯一真相**（內嵌自 synthesized.json）；欄位 `blur` 時寫回 DATA，不即時重 render（避免游標亂跳）。匯出時 POST 的是 DATA，不是刮 DOM。
- 每個議題／action 有 ＋／🗑 加刪列鈕。
- 頂部 audit bar：Layer-1 綠/紅燈（JS 即時重驗，鏡像 `audit_mechanical.py` 規則）＋ Layer-2 語意項清單（來自 audit.json，唯讀顯示）＋「已審閱」勾選框。
- 「匯出並開 Outlook」按鈕：僅在 Layer-1 全綠 AND 已勾「已審閱」時 enable。

### 2.3 CLI `edit` 指令（`script/main.py` 新增）
```
python -m script.main edit <name> [--name <name>] [--no-browser] [--port <n>]
```
解析 `out/<name>`，確認 `intermediate/synthesized.json` 存在，呼叫 `edit_server.serve(...)`。

### 2.4 重用既有碼（不重造）
- `script/audit_mechanical.py::evaluate` / `overall_pass` — **server 端權威 Layer-1 閘**。
- `script/email_writer.py::synth_to_finalized` + `render_email_html` — 由編輯後 synth 產 email HTML。
- `script/outlook_draft.py::open_draft` — 開 Outlook 草稿（Outlook 不在時回 False，優雅降級）。
- `script/schemas.py::SynthesizedMinutes` / `AuditResult` — 載入／驗證／寫回。

---

## 3. audit 閘（沿用 P1，server 端權威）

兩處把關:

1. **前端 JS 即時重驗 Layer-1**：每次 `blur` 重跑機械檢查（負責人／期限不得空、決議非空、標題／摘要非空、無殘留 `[待確認]`/TODO 等），紅項高亮該列並 disable 匯出鈕；勾「已審閱」才解鎖。JS 規則**鏡像** `audit_mechanical.py`。
2. **server 端 `/export` 再跑一次 `audit_mechanical.evaluate`**（權威、不信前端 — 前端可被繞過）：沒過就 HTTP 回拒絕 + 哪幾項 `offending`，**不寫檔、不開 Outlook**。

匯出條件 = Layer-1 全綠 **AND** 已勾「已審閱」。Layer-2 語意項只顯示、不阻斷（與 P1 一致）。

---

## 4. 產出（本子計畫範圍）

`POST /export` 通過後:

- **Outlook 草稿**：`open_draft(subject, email_html)` 開可編輯視窗、帶整理好內文、不寄出。
- **`email.html`** 寫回會議資料夾（`out/<name>/`，SharePoint 用；無 JS/無音檔，貼 Outlook 安全）。
- **存回 `intermediate/synthesized.json`**：資料夾反映編輯後最終版（也讓之後可 `--rerender`）。

**不含**（→ P4）：帶 10 秒音檔的 zip、以及真開瀏覽器逐條聽的 E2E 驗證。

---

## 5. 隱私、降級與取代

- **隱私**：server 只處理**已綜整的 minutes**（synthesized.json，已是 LLM 產物），**不碰原始逐字稿／音檔**；只綁 127.0.0.1；編輯／匯出過程**無任何 LLM 呼叫**。故不影響 P2 的 company-mode 隱私保證。
- **降級**：Outlook 不可用（無 pywin32／COM 失敗）→ `open_draft` 回 False → server 仍寫出 `email.html`，回報「Outlook 未開，已輸出 email.html，請手動開啟」。功能不掉。
- **取代**：終端 `finalize` Q&A 流程（`script/finalize.py` + `qna.py`）→ 交付路徑被此可編輯 server 取代（Outlook 邏輯經 `open_draft` 重用）。碼可先留、文件不再提為交付路徑。
- **skill 串接**：`/meetingminutes` 在 `process` 完成後，引導使用者跑 `edit <name>` 開編輯頁（skill 文案微調，非本 spec 重點）。

---

## 6. 測試

- **server handler 單元測**：`/export` 的權威重驗（合法 → 寫檔+開 Outlook；Layer-1 未過 → 拒絕、回 offending、不寫檔）、email 建構正確。用 in-process test client 或直接呼叫 handler 邏輯函式（把 handler 的核心抽成純函式 `handle_export(posted_data, out_dir) -> result` 便於測）。
- **Outlook 降級**：monkeypatch `open_draft` 回 False → 確認仍寫 `email.html`、狀態回報未開。
- **權威閘**：POST 一份 Layer-1 不合格的 DATA（如空負責人）→ 確認 server 拒絕、不寫檔、不開 Outlook。
- **JS ↔ Python 一致性**：Python `audit_mechanical` 為權威來源、已有測；JS 端鏡像規則，在計畫中以固定案例比對兩邊結果（或至少註記同步紀律）。
- **只綁 localhost**：確認 server 綁 127.0.0.1。

---

## 7. 待實作階段釐清的風險 / 開放項

- **port 選擇與衝突**：固定 port vs 自動找空 port；被占用時的行為。
- **server 生命週期**：匯出成功後自動關閉 vs 常駐等使用者 Ctrl-C；多次匯出。
- **編輯頁 vs 既有 `minutes.html`**：本設計新增 `edit.html.j2` 由 server 服務，暫不動 pipeline 仍產出的唯讀 `minutes.html`（快速預覽）。兩模板職責不同；未來若要合併為單一來源另議（避免雙版飄移）。
- **JS Layer-1 與 `audit_mechanical.py` 的同步紀律**：改一邊要改另一邊；理想以共用固定案例測比對。
- **Outlook subject 來源**：沿用 `synth_to_finalized` 的 subject 規則（會議名）。
- **並發**：單使用者本地工具，server 假設單一 client；不處理多分頁同時編輯的衝突。
- **[P3 最終審查發現，待你定奪] action `context` 標記缺口**：`audit_mechanical` 的 `no_placeholder_markers` 會掃 action 的 `context`，但（a）編輯頁沒把 `context` 設為可編輯欄位，（b）`context` 不在匯出的 email 裡（`synth_to_finalized` 只帶 task/owner/due/note，不帶 context/priority）。若 `synthesized.json` 某 action 的 `context` 含 `TODO`/`[待確認]` 等標記 → audit 恆紅、UI 無從修 → 該會議在頁面上永遠匯不出（死結）。兩個修法擇一（是產品判斷）：(i) 把 `context` 從 `no_placeholder_markers` 掃描移除（理由：只 gate「會出現在成品 email 且可編輯」的欄位）— 需同步改 `audit_mechanical.py` + JS 鏡像 + 測試；或 (ii) 在編輯頁把 `context` 設為可編輯欄位。發生機率低（context 常為空），非阻斷，故留為 follow-up。

---

## 決策紀錄（本次 brainstorming 拍板）

| 項目 | 決定 |
|------|------|
| 架構 | 本地簡易 server（標準庫 http.server，綁 127.0.0.1，無新依賴） |
| 匯出目標 | Outlook 草稿帶內文（重用 open_draft）+ email.html 寫回資料夾 + 存回 synthesized.json |
| audit 閘 | 沿用 P1；前端即時重驗 + server 端權威重驗；Layer-1 全綠 AND 已審閱才可匯出 |
| 音檔 zip / E2E | 整個留給 P4 |
| 隱私 | server 只碰已綜整 minutes、綁 localhost、無 LLM → 不影響 company-mode |
| finalize Q&A | 交付路徑被可編輯 server 取代 |
