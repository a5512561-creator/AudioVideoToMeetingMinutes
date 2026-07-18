# 會議記錄工作流增強 — 設計文件

- **日期**：2026-07-18
- **狀態**：設計（brainstorming 產出，待複審）
- **範圍**：AudioVideoToMeetingMinutes 端到端工作流增強
- **前置**：本文件僅為設計，尚未實作。實作需經 writing-plans 產出計畫後另行進行。

---

## 0. 背景與目標

現有工具把逐字稿 + 錄音轉成會議記錄。本次增強目標，來自使用者描述的 10 點理想工作流與 3 個痛點:

**理想工作流（10 點）**

1. 逐字稿 + 錄音放進**同一個資料夾**。
2. 啟動 Claude，下指令讀逐字稿+音檔、檢查格式/內容。工作流須**主動詢問**「本次會議轉檔要用公司 LLM（default）還是 Claude 目前使用的 LLM」，並以機制強制 Claude 每次都問。
3. 若選 default 公司 LLM：**保證逐字稿/音檔只有公司 LLM 碰得到，絕不給任何雲端 LLM 碰到**（資安硬要求）。
4. 沿用現有工作流產生會議記錄。
5. **強制觸發**的品質稽核（audit），依 SOTA 專業會議記錄標準判斷輸出品質/正確性/流暢度，附 checklist。
6. 會議記錄先輸出成**可互動 HTML**，使用者可逐筆編輯內容。
7. 確認後按「匯出會議記錄」鈕 → 產出 `email.html`。
8. 另產一份 zip：與 `email.html` 同內容但**加上 10 秒音檔片段**的 HTML + 各 10 秒切片，打包成 `.zip`。
9. 所有輸出放在**與逐字稿+原音檔同一個資料夾**（SharePoint 上傳）。
10. 不需要其他格式輸出。

**痛點**

- `email.html` 無法播放 10 秒音檔。
- LLM 產出的記錄每次都要人工再修 → 直接產「可編輯 HTML」的路徑要強化。
- 來源與輸出目前分兩個資料夾，但使用者實務上同置（SharePoint）。

---

## 1. 架構：兩引擎收斂共用 schema

兩條產生路徑，收斂到同一組 JSON、同一個 renderer。

- **Engine A — Python pipeline → 公司地端 LLM**
  現有 `script/pipeline.py`。stage：逐字稿載入 → （選用）專有名詞校正 → chunk → map/reduce → review → synth → **新增 audit**。全打公司 OpenAI 相容端點。

- **Engine B — Claude 本人 session（Claude Max，無 API key）**
  這個 Claude Code session 自己讀 `transcript.md`，直接寫出 `synthesized.json` / `review.json` / `audit.json`，再呼叫 Python `--rerender` 走同一個 renderer。**不是** Python 呼叫某雲端 API — 是 session 自己當產生器。

兩引擎都吐同一組中間 JSON（`intermediate/{minutes,review,synthesized}.json` + `audit.json`）→ 共用 renderer 產出 HTML。

---

## 2. 入口 + 隱私隔離（三層防線）

點 3 是資安**硬要求**（機密逐字稿絕不碰雲端）。硬要求用機制擋，不靠自律。三層各守一關:

1. **主入口 = superpowers skill `/minutes`（HARD-GATE）**
   skill body 強制先問「公司 LLM（default）還是 Claude 目前使用的 LLM」。取代原先脆弱的 UserPromptSubmit pattern hook。skill 觸發最可靠 → 保證「問」。

2. **CLI 沒帶 LLM 選擇就報錯**
   `main.py` 不帶明確 LLM 選擇參數即拒跑 → 漏走 skill 也逼得出選擇。

3. **PreToolUse hook（開啟）**
   選公司 LLM 模式時，工具層直接擋 Claude 讀逐字稿/音檔檔案 → 機密物理隔離，不靠 Claude 自律。這是「機密真的碰不到雲端」唯一的機制保證。

**格式/內容檢查（點 2）**：用純 Python 本地 validator（無 LLM）。Claude 只看 validator 的 stdout，engine A 全程不開逐字稿檔內容。解掉「點 2 要 Claude 讀來檢查」vs「點 3 不准雲端碰」的矛盾。

---

## 3. 強制 audit 閘（兩層，阻斷匯出）

audit 分兩層，因為使用者會在頁面上改內容、改完機器不會自動重審:

- **Layer 1 — 機械/結構項（JS 即時重驗，真正鎖匯出鈕）**
  編輯 blur 當下就重跑，不需 LLM。必過項例如:
  - 每個 Action 有負責人 + 期限（不得空）
  - 每個決議非空、掛在某議題下
  - 標題/摘要非空
  - 無殘留 `[待確認]` / TODO 標記
  任一項紅 → 匯出鈕 disabled + 標出哪一列。

- **Layer 2 — 語意品質項（LLM 產生時評分，需勾「已審閱」才解鎖）**
  固定一份 SOTA 專業會議記錄 checklist（內建，engine A 由公司 LLM 評、engine B 由 Claude 評），逐項打分 + 理由。例如:
  - 決議與討論可追溯、無臆測
  - 語句通順、無口語贅字
  - 行動項具體可執行（動詞開頭、可驗收）
  - 議題涵蓋完整、無遺漏重大討論
  - 用詞一致（人名/專有名詞）
  此層不阻斷編輯（改完不重審），但頁面**強制**逐項看過、勾總「已審閱」才解鎖匯出。

- **Layer 3 — zip 音檔 E2E 驗證（真啟瀏覽器，逐條聽）**
  zip 產出後，音檔連結不能只信「檔案存在 / 非 0 byte」，必須端到端證明「使用者解壓後點連結真的聽得到聲音」。流程:
  1. **zip 前快速檢查**：每個 `clip_*.m4a` 存在、大小合理（≥ 最小真實切片 bytes）、`email_with_audio.html` 內每個播放連結都對得到一個實體切片檔（無斷連、無孤兒檔）。
  2. **解壓完整驗證**：把 zip 解到暫存資料夾，真的啟動 Chrome（或等效瀏覽器，走 browser automation）載入 `email_with_audio.html`，**逐一**點擊每個音檔連結，確認實際播放（audio 元素 `duration>0`、無 error、`currentTime` 有推進 → 代表真解碼出聲，不是只 `play()` 成功）。**每一條連結都要檢查，不抽樣。**
  3. **驗證通過才收工**：全部連結通過後，**刪掉解壓的暫存資料夾**（只留 zip 本身）。任一條失敗 → 標記該切片、不刪暫存、報告哪幾條掛掉。
  這層是機制驗證（非 LLM），對應現有 `cut_clips()` 的 HE-AAC 偶發缺片已知風險 — E2E 逐條聽才抓得到「檔案在但放不出聲」的壞片。

- **checklist 全文** 寫進 `script/prompts/audit_checklist.md`，兩引擎共用同一份。

- **匯出鈕解鎖條件** = Layer 1 全綠 **AND** Layer 2 已勾「已審閱」**AND** Layer 3 zip E2E 全條通過。

---

## 4. 互動編輯頁 + 匯出鈕（純前端，無 server）

現有 `minutes.html.j2` 唯讀，改造成可編輯 + 可匯出，資料流全在瀏覽器內。

**編輯機制**

- 議題標題、每句 summary、每條決議、Action 的任務/負責人/期限/優先級 → 全部 `contenteditable`。
- 頁面載入時把 `synthesized.json`（+ audit 結果）內嵌成 JS `DATA` 物件（`<script>window.DATA=…</script>`），DOM 只是視圖。
- 編輯 `blur` 時寫回 `DATA`，不即時 render（避免游標亂跳）。**`DATA` 是唯一真相**，匯出時序列化的是它，不是刮 DOM。
- 加/刪列：每個議題、每條 Action 有 ＋/🗑 鈕。

**audit 閘接入（§3）**

- 頂部固定 audit bar：Layer 1 綠/紅燈 + Layer 2 清單（勾「已審閱」）。
- Layer 1 每次 blur 重驗 `DATA`，紅項高亮該列 + disable 匯出鈕。
- 匯出鈕 = Layer 1 全綠 AND 已勾已審閱才 enable。

**匯出鈕（File System Access API）**

按下:
1. `showDirectoryPicker()` → 使用者選會議資料夾（逐字稿+音檔所在，點 8/9 的 SharePoint 目錄）。
2. 用 `DATA` 產 `email.html`（無 JS/無音檔）→ 寫入該目錄。
3. 產帶音檔 zip：JSZip 打包 `email_with_audio.html`（相對路徑引用 clip）+ `clip_*.m4a` → 寫 `minutes_audio.zip` 到同目錄。

全部瀏覽器內完成，零上傳、零 server。

**降級**（File System Access 僅 Chrome/Edge）

偵測不到 `showDirectoryPicker` → 退回 `Blob` + `<a download>` 逐檔下載（含 zip），使用者自己丟進資料夾。功能不掉，少一次「直接寫入」便利。

**取捨（已決）— email renderer 走前端 JS 重寫**

email 版型現為 Python（`email_writer.py` + `minutes_email.html.j2`）。前端匯出要同一份 email HTML → **決定用 JS 在瀏覽器內重寫 renderer**（符合「純前端、無 server」）。代價：email 版型邏輯 Python + JS 兩份，須立**同步紀律**（改一邊必改另一邊；理想做法：抽共用測試比對兩份輸出）。

---

## 5. 輸出 / zip / 資料夾佈局（點 8/9/10）

**單一輸出目錄 = 逐字稿 + 原音檔所在資料夾**（點 9，SharePoint 直傳）。廢除現有 `out/` 分離目錄的對外交付角色。

匯出鈕按下後，該資料夾多出:

```
會議資料夾/
  meeting.md            ← 原逐字稿（已存在）
  meeting.m4a           ← 原音檔（已存在）
  email.html            ← 點7：無 JS/無音檔，貼進 Outlook 用
  minutes_audio.zip     ← 點8：帶 10 秒音檔的版本
```

`minutes_audio.zip` 解開後:

```
  email_with_audio.html ← 同 email.html 內容 + ▶ 播放鈕
  clip_<sec>.m4a …      ← 各 10 秒切片（相對路徑引用）
```

**關鍵設計點**

- `email.html`（點 7）：**不**內嵌 data URL 音檔。點 7 明確要「能貼進 Outlook 的純 email」→ 無音檔、無 JS（沿用現有 email 模板精神）。音檔只活在 zip 版。
- `email_with_audio.html`（zip 內）：**相對路徑**引用 `clip_*.m4a`（非 data URL）。因為 zip 解到本機後相對路徑可用，且避免 base64 撐爆 HTML。這跟現有 `minutes.html` 的 data-URL 內嵌策略**相反** — 理由不同情境：那是為 SharePoint 線上檢視器；zip 是給人下載解壓本機看。
- 切片：沿用現有 `cut_clips()`（ffmpeg），engine A 產生時就切好放工作區，前端 JSZip 直接讀打包。
- **zip 正確性驗證（見 §3 Layer 3）**：zip 前快速檢查（切片存在/大小/連結對得到檔）→ 解壓 → 真啟瀏覽器逐條點聽 E2E → 全過才刪暫存解壓資料夾。缺片或放不出聲要擋下、報告。

**點 10：廢除的輸出/功能**

- 現有 `finalize` 指令（終端 Q&A → Outlook 草稿）→ **從交付流程移除**（碼可先留，文件不再提，避免一次刪太多）。
- Excel / Markdown / 其他格式 → 不產。
- 唯讀 `minutes.html` → 被可編輯版取代。

---

## 6. 待實作階段釐清的風險 / 開放項

- email renderer Python↔JS 雙版同步：需具體機制（共用 fixture 測試比對輸出）。
- PreToolUse hook 的實際攔截範圍（哪些路徑/工具）需在計畫階段定義精確 matcher。
- Engine B 寫 JSON 的 schema 驗證：需與 Python `schemas.py` 對齊，避免 `--rerender` 吃到不合法 JSON。
- HE-AAC 切片偶發失敗（現有已知限制，30 錨點約 1–3 片缺失）→ zip 內容需容忍缺片。
- File System Access API 僅 Chrome/Edge → 降級路徑須測試。
- **zip E2E 驗證的自動化細節**：以哪個 browser automation 驅動（Claude-in-Chrome / Playwright / headless）、如何判定「真出聲」（`duration>0` + `currentTime` 推進 + 無 error，vs 更嚴格的解碼取樣）、逐條驗多少切片的時間成本、失敗切片是否觸發重切（retry `cut_clips`）。計畫階段定義。
- **E2E 驗證與隱私（點 3）交互**：驗證只碰切片音檔（已是輸出物），不碰原始逐字稿；仍須確認公司 LLM 模式下此步不外洩內容。

---

## 決策紀錄（本次 brainstorming 拍板）

| 項目 | 決定 |
|------|------|
| 匯出機制 | 純前端 File System Access API，無 server |
| 引擎 B 本質 | Claude session 自己寫 JSON（Claude Max，無 API key），非 Python 呼叫雲端 API |
| 主入口 | superpowers skill `/minutes`（HARD-GATE 先問 LLM 選擇） |
| 隱私隔離 | 三層：skill + CLI 拒跑 + PreToolUse hook 開啟 |
| audit 閘 | 三層：機械項 JS 即時鎖匯出 + 語意項 LLM 評分/已審閱 + zip 音檔 E2E 逐條真聽 |
| zip 驗證 | zip 前快檢 → 解壓 → 真啟瀏覽器逐條點聽（每連結不抽樣）→ 全過才刪暫存 |
| email renderer | 前端 JS 重寫（Python/JS 雙版 + 同步紀律） |
| 舊 finalize | 從交付流程移除 |
| 輸出格式 | 只有 email.html + minutes_audio.zip，同置會議資料夾 |
