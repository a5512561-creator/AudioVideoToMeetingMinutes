# minutes.html 可點播錄音片段 — 設計文件

- **日期**: 2026-05-20（v2.1）/ 2026-05-20（v2）/ 2026-05-19（v1）
- **版本**: v2.1
- **作者**: paddychen + Claude
- **狀態**: Implemented (v2.1)
- **關聯**: 接續 `2026-05-19-interactive-synthesized-minutes-design.md`

---

## v2.1 變更摘要（2026-05-20，補修）

v2 在本機 `file://` 開 `minutes.html` 能播，但**上 OneDrive / SharePoint 後 ▶ 仍然不能播**。
根本原因：雲端預覽器把 HTML 渲染在自己網域的 iframe 裡，HTML 內 `clip.src = "clip_46.m4a"`
這種相對路徑會被解到 `https://onedrive.live.com/...` 而**不是**使用者那個資料夾。檔案在
資料夾裡、HTML 找不到。這跟 v1 的 Range 失敗是「同個病的兩個症狀」—— v2 只解了一半。

| 變更 | v2 | v2.1 | 原因 |
|---|---|---|---|
| Clip 引用 | 相對檔名 `clip_<s>.<ext>` | **`data:audio/mp4;base64,<...>`** 內嵌 | 雲端 viewer iframe 解不到相對路徑 |
| Pipeline 輸出 | 寫 `clip_*.m4a` 並把檔名傳給 HTML | 寫 `clip_*.m4a` + **讀回 base64 編碼**，把 data URL dict 傳給 HTML | clip 檔仍保留作為「未來改回外部引用」或除錯用 |
| HTML 結構 | 每個 ▶ 帶完整路徑 `data-clip="clip_46.m4a"` | **每個 ▶ 帶起始秒數 `data-clip="46"`，data URL 集中在 JS `CLIPS` 字典裡** | 多個 decision 共用同一錨點時 URL 不會被重複 4 份；HTML 從直觀計算的 ~2.7MB 降到實測 ~1.2MB |
| ffmpeg 編碼參數 | 預設（128k stereo） | **`-ac 1 -b:a 48k`**（mono 48k） | 與 HE-AAC 來源同等級語音品質，clip 檔從 ~160KB 降到 ~60KB，連帶把內嵌 HTML 體積砍半 |
| 單檔可攜性 | **不**（HTML + N 個 .m4a 須一起上傳） | **是**（單一 HTML 走天下） | 雲端分享、email 附件都簡單；clip 檔仍寫到磁碟供需要外部播放器的場景 |
| HTML 大小 | ~50KB | **~1.2MB**（實測，16 個 anchor × 60KB × 1.33 base64 開銷 + 模板） | 對 email/雲端分享仍在合理範圍（Gmail 25MB 上限、SharePoint 任意大小） |

## v2 變更摘要（2026-05-20）

| 變更 | v1 原設計 | v2 採用 | 原因 |
|---|---|---|---|
| 音訊供應 | 單一 `audio.<ext>` 完整檔，瀏覽器靠 `currentTime` seek | **預先用 ffmpeg 切 N 個 `clip_<start>.<ext>` 小檔**（每個 ▶ 一檔）+ 仍保留完整 `audio.<ext>` 供長聽 | SharePoint/Outlook **不可靠地支援 HTTP Range requests**，HTML5 seek 在這些主機上實際**無法播放**。切成各自獨立的小檔可避開 Range/seek 完全失敗的問題 |
| ffmpeg 依賴 | **刻意不引入** | **引入**（用 `ffmpeg -ss <s> -i <src> -map 0:a:0 -t <dur> <dst>` 重新編碼，每片 ~1s，含 HE-AAC retry；17 片 ~20s） | 在 v1 假設下「不引入」是合理的；但 v1 在實機 SharePoint 上 ▶ 完全失效。引入 ffmpeg 是改 architecture 而非 cleanup —— 同 PR 也更新 spec |
| JS 邏輯 | `clip.currentTime=s; setTimeout-style 用 timeupdate 在 s+CLIP_LEN 暫停` | `clip.src=btn.dataset.clip; clip.play()`（無 seek、無 stop 計時器；clip 檔本身就是 dur 秒） | 配合上述：每個 ▶ 載入自己的小檔，瀏覽器不需要 Range、JS 也不需要 stop 計時 |
| 模板 data 屬性 | `data-start="<seconds>"` | `data-clip="clip_<start>.<ext>"` | 同上 |
| `audio_clip_duration_seconds` 用途 | 傳給模板成 JS `CLIP_LEN` 常數 | 傳給 `cut_clips()` 作為 `-t` 秒數 | 同上 |
| Email 版（`minutes_email.html`） | 不變、不支援音訊 | **同 v1（不變）**，但 v2 之後**可選**未來把 clip 用 `<a href>` 嵌入（範圍外） | clip 檔現在是自包含的，email 客戶端用 `<a>` 點開就能聽 —— 仍列為未來工作以避免 scope 擴張 |

`★ 為何 v1 沒抓到這個問題`：v1 brainstorming 用 `file://` 在本機磁碟驗證 ▶ 能播，
但實際發佈情境是把 `minutes.html` + `audio.m4a` 上到 SharePoint，使用者從 Doc.aspx
渲染頁開啟。SharePoint 把 `.m4a` 包成 `Content-Disposition: attachment` 並且不
完整支援 Range；同時相對 URL 也被解到 `/sites/.../Doc.aspx?sourcedoc={GUID}` 而
不是原始 m4a。v1 文件第 159 行（未來工作）僅短註「網路磁碟可能有 CORS 限制」，
低估了 SharePoint 的 Range 行為差異。

---

## 1. 目標與動機

互動版 `minutes.html` 目前在議題下顯示一串 `⏱ 00:05:50, …` 純文字時間戳，
對讀者沒有幫助。改為：**每條決議、每個 Action 後面各一顆 ▶ 按鈕，點了就播
對應錄音片段**（預設時間戳前 5 秒起、共 10 秒，即 t−5 ~ t+5）。

`★ 架構張力（v1 → v2）`：本 session 早期刻意移除所有音訊處理
（media/transcribe/diarize）。本功能**重新引入「原始音訊檔」作為 minutes.html
的依賴**，但**不**加回 ASR/語者模組 —— 因為逐字稿的 `MM:SS` 來自
recorder.google.com，本就是該錄音檔的真實時間偏移。v1 期望 HTML5 `<audio>` 直接
seek 即可；v2 因 SharePoint Range 失效**改為 pipeline 端用 ffmpeg 預切 N 個小檔**
（每個 ▶ 對應一個獨立 clip）。代價：互動版 minutes.html 仍非「單檔自包含」（需
同目錄一組 `clip_*.<ext>`，可選保留完整 `audio.<ext>`），且 pipeline 引入 ffmpeg
依賴。

範圍外：
- 不加回 ASR/語者；不對 clip 重新編碼（仍只用 ffmpeg 的 `-c copy` 串流複製）。
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

### 4.1 `script/audio_assets.py`

- `find_sibling_audio(src: str) -> Path | None`：在 `Path(src).parent` 找
  stem 等於 `Path(src).stem`、副檔名依序為
  `.m4a, .mp3, .wav, .ogg, .aac`（小寫比對）的第一個存在檔；無則 `None`。
- `clip_start(ts: str, pre: int) -> int | None`：`HH:MM:SS` → 秒，
  回 `max(0, 秒 − pre)`；無法解析回 `None`（呼叫端略過該 ▶）。
- `output_audio(out_dir) -> Path | None`：掃 `out_dir/audio.<ext>`，副檔名
  優先順序同上。
- **`mime_for_ext(ext) -> str`（v2.1 新增）**：副檔名 → MIME（`.m4a → audio/mp4`、`.mp3 → audio/mpeg`、…），預設 `audio/mp4`。
- **`file_to_data_url(path) -> str`（v2.1 新增）**：讀檔案 + base64 編碼 → `data:<mime>;base64,...`。給 pipeline 把 ffmpeg 切出的 clip 轉成可直接灌進 HTML `<audio src=...>` 的 URL。
- **`cut_clips(audio_path, starts, duration, out_dir) -> dict[int, str]`（v2 新增、v2.1 調整 codec 參數）**：
  對 `starts` 內每個唯一秒數 `s`，用
  `ffmpeg -y -loglevel error -ss <s> -i <audio_path> -map 0:a:0 -t <duration> -ac 1 -b:a 48k <out_dir>/clip_<s>.<ext>`
  寫出一個 mono 48kbps 小檔（讓 ffmpeg 依輸出容器選擇預設 codec 重新編碼，**不**用 `-c copy`）。
  `-ac 1 -b:a 48k`（v2.1 加）：源頭 HE-AAC 也只有 48 kbps，輸出端對齊可把每片從 ~160KB 砍到 ~60KB；連帶把 v2.1 base64 內嵌 HTML 體積砍半。
  傳回 `{s: "clip_<s>.<ext>"}`（檔名，**非** data URL；pipeline 再呼叫 `file_to_data_url` 編碼）。
  - 開始前先 `glob("clip_*<ext>")` 把舊片清掉，避免 `audio_clip_*_seconds` 變動後留下錯誤長度的舊片
  - **不用 `-c copy`**：串流複製在 keyframe 對不齊時會 silently 產生 0 bytes 檔（rc=0 但無內容），改 re-encode 較可靠
  - **HE-AAC 來源 quirk**：Google Recorder 產出的 m4a 是 HE-AAC（含 SBR），在任意位置 seek 後 encode 偶爾會產生 0-bytes 檔（推測為 SBR state 初始化問題）。每片失敗時**自動重試一次**；仍失敗則 skip 該秒（best-effort policy），不影響其他片。實測 17 個 anchor 重試後可達 17/17。
  - `-map 0:a:0`：強制只處理第一個音訊軌；recorder.google.com 的 m4a 額外帶有 3 個 `mett` metadata 軌會干擾 stream selection
  - ffmpeg 不存在於 PATH（`FileNotFoundError`） → 整批回 `{}`（graceful degradation；caller 視為「無音訊」）

### 4.2 `script/pipeline.py`

- 完整 run（`# Outputs` 之前）：
  1. `audio = find_sibling_audio(src)`；若有 → 複製到
     `out/<name>/audio<audio.suffix.lower()>`（`shutil.copyfile`），
     log `stage.audio_asset copied=...`；無 → log `stage.audio_asset missing` 不報錯
  2. **v2 新增**：呼叫 `clips = _cut_audio_clips(out_dir, synth, settings)`
     - v2 行為：回傳 `{s: "clip_<s>.<ext>"}`（檔名）
     - **v2.1 行為**：內部用 `cut_clips` 切出 clip 檔後**對每個檔再跑 `file_to_data_url`**，回傳 `{s: "data:audio/mp4;base64,..."}`
     - log `stage.audio_clips count=<N>`
  3. `write_minutes_html(..., pre=settings.audio_clip_pre_seconds, clips=clips)`
- `rerender_only`：同樣呼叫 `_cut_audio_clips`（依舊以 `out/<name>/audio.*` 為來源），
  log 附 `mode="rerender"` 區別。

### 4.3 `script/html_writer.py`

- 簽章（v2，v2.1 不變）：
  `write_minutes_html(synth, review, dst, *, meeting_file, meta=None, pre: int = 5, clips: dict[int, str] | None = None)`
  - 移除 v1 的 `duration` 參數（v2 不再由 JS 強制 clamp 結束時間）
  - `clips`：caller（pipeline）給的字典。v2 是「`秒數 → 檔名`」；**v2.1 是「`秒數 → data URL`」**。html_writer 對二者皆能渲染（key 在 dict 即視為有 clip），但下游模板期望 v2.1 形式。
- `has_audio = bool(clips)`（v2 改用「有切到 clip」判斷，不再 scan `audio.*`）
- 組裝 ▶ 資料（**v2.1 改**）：
  - 每個 **topic / action** 算 `s = clip_start(...source_timestamps[0], pre)`，
    `clip_key = str(s)` if `s in clips` else `None`
  - 傳給模板：`has_audio`、topics/actions 各帶 `clip`（**字串化的秒數**或 None）、外加全域 `clips_js`（`json.dumps({str(s): url})`）
  - v2.1 為何把「秒數」當 key 而非檔名：同錨點被多 decision 共用時，URL 不會在多顆 button 上重複，HTML 體積較小且整潔
- 移除模板用的 topic 層級 `source_timestamps` 純文字行（改由 ▶ 取代）。

### 4.4 `script/templates/minutes.html.j2`

- 移除 `<p class="src">⏱ …</p>` 那行。
- `has_audio` 為真時，於 `<body>` 末放
  `<audio id="clip" preload="none"></audio>`（**不**在 `src` 上預設值，由 JS 動態 swap）。
- 決議：`<li>{{ d }}{% if t.clip %} <button class="play" data-clip="{{ t.clip }}">▶</button>{% endif %}</li>`，
  `t.clip` 在 **v2.1 是秒數字串**（如 `"345"`）而非檔名。
- Action 表格尾欄：`{% if a.clip %}<button class="play" data-clip="{{ a.clip }}">▶</button>{% endif %}`。
- JS（**v2.1 改**）：
  ```js
  var CLIPS={{ clips_js|safe }};   // {"345": "data:audio/mp4;base64,...", ...}
  document.querySelectorAll('.play').forEach(function(btn){
    btn.addEventListener('click',function(){
      var url=CLIPS[btn.dataset.clip];
      if(!url) return;
      clip.src=url; clip.play();
    });
  });
  ```
  無 `currentTime`、無 `timeupdate`、無 `CLIP_LEN` 計時器 —— 因為 clip 檔本身已是 dur 秒。
- `has_audio` 為假時：完全不渲染 `<audio>`、不渲染 `CLIPS`、不渲染任何 ▶ —— 與 v1 相同。

---

## 5. 資料流

```
逐字稿 src ──(find_sibling_audio)──> 同名音訊?
                                       │
                                       ├──有──> 複製 out/<name>/audio.<ext>
                                       │       └──(_cut_audio_clips: 收 starts + cut_clips)
                                       │            └──> out/<name>/clip_<s>.<ext> × N
                                       │                 └──> clips: {s: "clip_<s>.<ext>"}
                                       └──無──> clips = {}

SynthesizedMinutes + meta + pre + clips ─> write_minutes_html ─> minutes.html
   (has_audio = bool(clips) → 決議/Action 渲染 ▶ + <audio>)
minutes_email.html / review_report.md / minutes.json：不變
```

---

## 6. 錯誤處理

- 無同名音訊 → 不複製、`clips={}`、`has_audio=False`、無 ▶；log `stage.audio_asset missing` + `stage.audio_clips count=0`，非錯誤。
- 某 topic/action 第一個時間戳缺或無法解析 → 該項不渲染 ▶（其他正常）。
- 某 topic/action 的 `start` 不在 `clips` dict 內（例如該 start 的 ffmpeg 切片失敗）→ 該項不渲染 ▶（其他正常）。
- `clip_start` 對 `t < pre` → `max(0, t−pre)`=0（從頭播）。
- 複製音訊 IO 失敗 → 視為「無音訊」降級（log 警告），不中斷 pipeline。
- **ffmpeg 不存在於 PATH（v2）** → `cut_clips` 回 `{}`、`has_audio=False`、無 ▶，pipeline 照常完成（log `stage.audio_clips count=0`）。
- **單片 ffmpeg 失敗（rc≠0 或 0 bytes）（v2）** → 重試一次；若仍失敗則 skip 該秒，其他片照常切。對應的 topic/action 不渲染 ▶，其他正常。常見於 HE-AAC 來源（Google Recorder m4a），實測偶發但重試後通常可達 100% 命中。
- 瀏覽器靠副檔名判斷 MIME；保留原副檔名即可（`.m4a`/`.mp3` 等主流瀏覽器可播）。

---

## 7. 測試策略

- `tests/test_audio_assets.py`：
  - `find_sibling_audio`：同 stem 不同副檔名命中順序、找不到回 None、不同 stem 不誤抓。
  - `clip_start`：`HH:MM:SS`→秒−pre、`t<pre` 夾 0、壞字串回 None。
  - **`cut_clips`（v2 新增）**：
    - 唯一 starts dedup（list 內有重複秒數時只切一次）
    - `None` starts 被忽略
    - 開始前清掉同副檔名的舊 `clip_*.<ext>`（避免設定變動後留下錯誤長度）
    - ffmpeg 不存在（mock 拋 `FileNotFoundError`）→ 回 `{}`
    - ffmpeg rc≠0 → 回 `{}`
- `tests/test_config.py`：新增兩個 audio clip 設定預設值（5 / 10）測試。
- `tests/test_html_writer.py`（v2 改）：
  - 傳入 `clips={345: "clip_345.m4a", 82: "clip_82.m4a"}` → 決議與 Action 出現
    `<button class="play" data-clip="clip_345.m4a">`、`<audio id="clip"` 無預設 `src`、
    無 `CLIP_LEN`；`data-clip` 名稱由 caller 直接給出。
  - 不傳 `clips`（或傳 `{}`） → 無 `class="play"`、無 `<audio`（回歸現狀）。
  - 部分命中（只給其中一個 start 的 clip）→ 只有對應項渲染 ▶，其他略過。
- `tests/test_pipeline.py`：
  - 偵測到同名音訊（建臨時 sibling）→ `out/<name>/audio.<ext>` 存在；
    `cut_clips` 被呼叫一次、duration 從 settings 帶入。
  - 無音訊 → 不建立、不呼叫 `cut_clips`、pipeline 照常完成。
  - `write_minutes_html` 收到 `pre` + `clips` kwargs（v2：`duration` 已從簽章移除）。
- 驗收：對 `D:\Meeting\20260518_leadersync\`（旁有 `5月18日 下午2-07.m4a`）完整跑，
  把 `out\leadersync_20260518\` 整個資料夾（含 `audio.m4a` + N 個 `clip_*.m4a` + `minutes.html`）
  傳到 SharePoint，從 SharePoint 渲染頁開 `minutes.html`，點決議/Action 的 ▶ 確認能播 t−5~t+5；
  `minutes_email.html` 不變。

---

## 8. 未來工作（範圍外）

- 決議逐條精準錨點（brainstorm 方案 B：用 `source_index`「決議 N」對應）—— 待
  A 的議題層級顆粒度不足時再評估。
- 把 clip 用 `<a href="clip_<s>.m4a">▶</a>` 嵌進 `minutes_email.html`，讓 Outlook
  也能點開單片播放（v2 後 clip 是自包含小檔，技術上已可行；避免本次 scope 擴張暫不做）。
- 把 clip base64 內嵌進 `minutes.html`，做成真正單檔可攜（HTML 約 +6MB；對 email
  系統有上限風險）。
- 完整 `audio.<ext>` 是否仍需複製到 `out/`：clip 已自包含，完整檔僅供「想聽前後文」
  使用；未來可加 settings 旗標讓使用者選擇是否保留以節省空間。
- Review 項目對應時間（需 synthesis 階段建 raw→synth 對照）。
- 從網路磁碟（UNC 路徑）以 `file://` 開啟 minutes.html 時，部分瀏覽器（Chrome）對本機音訊有 CORS 限制；放本機磁碟可正常播放。
- `find_sibling_audio` 的副檔名比對為小寫清單；本專案僅 Windows（不分大小寫），若日後移植 Linux（大小寫敏感）需補大寫處理。
- ffmpeg 出錯時目前是「整批不切」（graceful degradation）。未來可改為「跳過失敗那片、其他繼續」以提高可用性。
