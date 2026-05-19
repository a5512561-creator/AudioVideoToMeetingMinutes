# minutes.html 可點播錄音片段 — 設計文件

- **日期**: 2026-05-19
- **版本**: v1
- **作者**: paddychen + Claude (brainstorming)
- **狀態**: Draft (待 review)
- **關聯**: 接續 `2026-05-19-interactive-synthesized-minutes-design.md`

---

## 1. 目標與動機

互動版 `minutes.html` 目前在議題下顯示一串 `⏱ 00:05:50, …` 純文字時間戳，
對讀者沒有幫助。改為：**每條決議、每個 Action 後面各一顆 ▶ 按鈕，點了就播
對應錄音片段**（預設時間戳前 5 秒起、共 10 秒，即 t−5 ~ t+5）。

`★ 架構張力（已與使用者確認）`：本 session 早期刻意移除所有音訊處理
（media/transcribe/diarize）。本功能**重新引入「原始音訊檔」作為 minutes.html
的依賴**，但**不**加回 ASR/語者模組 —— 因為逐字稿的 `MM:SS` 來自
recorder.google.com，本就是該錄音檔的真實時間偏移，HTML5 `<audio>` 直接 seek
即可。代價：互動版 minutes.html 不再是「單檔自包含」（需同目錄一份音訊檔）。

範圍外：
- 不加回 ASR/語者；不轉檔/壓縮（不引入 ffmpeg）。
- `minutes_email.html`（貼 Outlook、無 JS）**完全不變**，不支援音訊。
- Review 分頁無時間戳（`ReviewNote` 無時間欄位）→ 無 ▶，維持現狀。

---

## 2. 既定決策（brainstorming 結論）

| 項目 | 決定 |
|---|---|
| 音訊來源 | 慣例式：逐字稿**同目錄、同 stem** 的音訊檔（依序找 `.m4a/.mp3/.wav/.ogg/.aac`）|
| 音訊供應 | 完整 run 時**複製**到 `out/<name>/audio<原副檔名>`，minutes.html 相對引用 |
| 顆粒度 | 每條決議 / 每個 Action 各一顆 ▶，用該項**第一個**時間戳 |
| 決議 ▶ 錨點 | **方案 A**：用「所屬議題的第一個時間戳」（穩定，不靠 LLM 編號對齊）|
| Action ▶ 錨點 | 該 Action 的 `source_timestamps[0]`（逐條精準）|
| 播放視窗 | `[t − AUDIO_CLIP_PRE_SECONDS, t − pre + AUDIO_CLIP_DURATION_SECONDS]`，可由 `.env` 設定 |
| 找不到音訊 | 優雅降級：無 ▶、無 `<audio>`，行為等同現狀；log 一行 |
| Email 版 | 不變 |

---

## 3. 設定（`.env` / `config.py`）

於 `script/config.py` `Settings` 新增（新區塊 `# === Audio clip (minutes.html ▶) ===`）：

| 欄位 | env alias | 預設 | 說明 |
|---|---|---|---|
| `audio_clip_pre_seconds` | `AUDIO_CLIP_PRE_SECONDS` | `5` | 時間戳往前幾秒開始播 |
| `audio_clip_duration_seconds` | `AUDIO_CLIP_DURATION_SECONDS` | `10` | 片段總長度（秒）|

型別 `int`，沿用既有 pydantic-settings 模式。預設值即原本「前後 5 秒」
（pre=5、duration=10 → 視窗 `[t−5, t+5]`）。其餘設定不動。

---

## 4. 架構與元件

### 4.1 `script/audio_assets.py`（新，小工具）

- `find_sibling_audio(src: str) -> Path | None`：在 `Path(src).parent` 找
  stem 等於 `Path(src).stem`、副檔名依序為
  `.m4a, .mp3, .wav, .ogg, .aac`（小寫比對）的第一個存在檔；無則 `None`。
- `clip_start(ts: str, pre: int) -> int`：`HH:MM:SS` → 秒，回 `max(0, 秒 − pre)`；
  無法解析回 `None`（呼叫端略過該 ▶）。

### 4.2 `script/pipeline.py`

- 完整 run（`# Outputs` 之前，靠近 Stage 5 既有 `synth`/`meta` 處）：
  `audio = find_sibling_audio(src)`；若有 → 複製到
  `out/<name>/audio<audio.suffix.lower()>`（覆寫；`shutil.copyfile`），
  log `stage.audio_asset copied=...`；無 → log `stage.audio_asset missing` 不報錯。
- `write_minutes_html(...)` 呼叫新增傳入
  `pre=settings.audio_clip_pre_seconds`、
  `duration=settings.audio_clip_duration_seconds`（見 4.3 簽章）。
- `rerender_only`：不重新探索/複製音訊（沿用既存 `out/<name>/audio.*`）；
  `write_minutes_html` 同樣帶入 pre/duration 設定。

### 4.3 `script/html_writer.py`

- 簽章新增兩個 keyword-only 參數，含預設（向後相容）：
  `write_minutes_html(synth, review, dst, *, meeting_file, meta=None, pre: int = 5, duration: int = 10)`
- 偵測音訊：掃描 `Path(dst).parent` 是否有 `audio.*`（取第一個符合
  `audio.<ext>` 者）。有 → `audio_src = 該檔名`（相對），`has_audio = True`。
- 組裝 ▶ 資料：
  - 每個 **topic** 算 `topic_start = clip_start(topic.source_timestamps[0], pre)`
    （無時間戳/解析失敗 → `None`）。該議題下**每條決議**共用此 `topic_start`。
  - 每個 **action** 算 `action_start = clip_start(action.source_timestamps[0], pre)`。
  - 傳給模板：`has_audio`、`audio_src`、`clip_len = duration`，以及 topics/actions
    的 view 內各自帶 `start`（int 或 None）。
- 移除模板用的 topic 層級 `source_timestamps` 純文字行（改由 ▶ 取代）。

### 4.4 `script/templates/minutes.html.j2`

- 移除 `<p class="src">⏱ …</p>` 那行。
- `has_audio` 為真時，於 `<body>` 末放單一隱藏
  `<audio id="clip" src="{{ audio_src }}" preload="none"></audio>`。
- 決議：`<li>{{ d }}{% if has_audio and t.start is not none %} <button class="play" data-start="{{ t.start }}">▶</button>{% endif %}</li>`。
- Action 表格：尾欄加一格，`{% if has_audio and a.start is not none %}<button class="play" data-start="{{ a.start }}">▶</button>{% endif %}`。
- JS（既有 IIFE 內加一段）：`clip_len` 由 jinja 注入成 JS 常數；點 `.play` →
  `var a=document.getElementById('clip'); a.currentTime=+btn.dataset.start;
  a.play();` 並設一次性 `timeupdate`：`if(a.currentTime >= start + CLIP_LEN){ a.pause(); }`。
  同時只播一段（再點別顆會重設 currentTime）。
- `has_audio` 為假時：完全不渲染 `<audio>`、不渲染任何 ▶ —— 與現狀一致。

---

## 5. 資料流

```
逐字稿 src ──(find_sibling_audio)──> 同名音訊? ──有──> 複製 out/<name>/audio.<ext>
SynthesizedMinutes + meta + pre/duration ─> write_minutes_html ─> minutes.html
   (掃描 out/<name>/audio.* → has_audio → 決議/Action 渲染 ▶ + <audio>)
minutes_email.html / review_report.md / minutes.json：不變
```

---

## 6. 錯誤處理

- 無同名音訊 → 不複製、`has_audio=False`、無 ▶；log `stage.audio_asset missing`，非錯誤。
- 某 topic/action 第一個時間戳缺或無法解析 → 該項不渲染 ▶（其他正常）。
- `clip_start` 對 `t < pre` → `max(0, t−pre)`=0（從頭播）。
- 複製音訊 IO 失敗 → 視為「無音訊」降級（log 警告），不中斷 pipeline。
- 瀏覽器靠副檔名判斷 MIME；保留原副檔名即可（`.m4a`/`.mp3` 等主流瀏覽器可播）。

---

## 7. 測試策略

- `tests/test_audio_assets.py`：
  - `find_sibling_audio`：同 stem 不同副檔名命中順序、找不到回 None、不同 stem 不誤抓。
  - `clip_start`：`HH:MM:SS`→秒−pre、`t<pre` 夾 0、壞字串回 None。
- `tests/test_config.py`：新增兩個 audio clip 設定預設值（5 / 10）測試。
- `tests/test_html_writer.py`：
  - 在 tmp 輸出目錄放一個 `audio.m4a` 假檔 → 決議與 Action 出現
    `<button class="play" data-start=...>`、含單一 `<audio id="clip" src="audio.m4a"`、
    JS 內 `CLIP_LEN` 反映 duration、`data-start` 已套 −pre 並夾 0。
  - 不放 `audio.*` → 無 `class="play"`、無 `<audio id="clip"`（回歸現狀）。
  - 既有 7+1 測試仍綠（時間戳純文字行移除後相關斷言調整）。
- `tests/test_pipeline.py`：
  - 偵測到同名音訊（mock `find_sibling_audio` 或建臨時 sibling）→ `out/<name>/audio.<ext>` 存在。
  - 無音訊 → 不建立、不報錯、pipeline 照常完成。
  - `write_minutes_html` 收到 `pre`/`duration` kwargs（來自 settings）。
- 驗收：對 `D:\Meeting\20260518_leadersync\`（旁有 `5月18日 下午2-07.m4a`）完整跑，
  開 `out\leadersync_20260518\minutes.html`，點決議/Action 的 ▶ 確認能播 t−5~t+5；
  `minutes_email.html` 不變。

---

## 8. 未來工作（範圍外）

- 決議逐條精準錨點（brainstorm 方案 B：用 `source_index`「決議 N」對應）—— 待
  A 的議題層級顆粒度不足時再評估。
- 音訊壓縮以縮小複製體積（需 ffmpeg；本次刻意不引入）。
- Review 項目對應時間（需 synthesis 階段建 raw→synth 對照）。
- 從網路磁碟（UNC 路徑）以 `file://` 開啟 minutes.html 時，部分瀏覽器（Chrome）對本機音訊有 CORS 限制；放本機磁碟可正常播放。
- `find_sibling_audio` 的副檔名比對為小寫清單；本專案僅 Windows（不分大小寫），若日後移植 Linux（大小寫敏感）需補大寫處理。
