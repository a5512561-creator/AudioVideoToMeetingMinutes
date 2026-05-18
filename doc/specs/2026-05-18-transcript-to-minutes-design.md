# 逐字稿 → 會議記錄 架構調整 — 設計文件

- **日期**: 2026-05-18
- **版本**: v1
- **作者**: paddychen + Claude (brainstorming)
- **狀態**: Draft (待 review)
- **關聯**: 取代 `2026-05-06-meeting-minutes-design.md` 的 Stage 1/2/2.5（影音→文字→語者）入口

---

## 1. 目標與動機

目前流程是「影音檔 → 抽音訊 → Whisper 轉文字 → (可選)語者分離 → chunk → minutes → review」。

使用者改為**自行準備逐字稿**，直接由逐字稿產生會議記錄。為了省時間，**暫不做語音端的語者識別 (diarization)**。

核心改動：
1. 主流程入口從「影音檔」改為「逐字稿檔」。
2. 移除所有**純音訊相關**程式碼（抽音訊、ASR、diarization、語者音檔取樣）。
3. **保留語者欄位與輸出排版的彈性**：逐字稿日後可能附帶 speaker 標記，schema / writer / prompt 既有的 speaker 接線不拆除。
4. 逐字稿格式為「`MM:SS` 時間戳一行，接著該段文字」的區塊，無 speaker 標記（speaker 版格式待使用者提供樣本後再做）。

範圍外：
- 隨附的 `.m4a` 錄音檔忽略，不做任何 ASR。
- speaker 標記逐字稿的解析延後（待真實樣本）。

---

## 2. 輸入格式

UTF-8（無 BOM）純文字檔，區塊格式：

```
00:00
這件事情改善多少可以所以聽，所以我才想弄問過你說...
00:10
我覺得剛剛說的你根本沒辦法定半年 ok 非常多少。嗯，...
```

- 時間戳獨立一行，格式 `MM:SS` 或 `H:MM:SS`／`HH:MM:SS`。
- 時間戳下一段（至下一個時間戳之前）為該時間點的文字，可跨多行/含空行。
- 無 speaker 標記。
- 容錯：空行略過；檔案開頭若有文字但無時間戳，視為 `[00:00:00]`。

> 註：`D:\Meeting\20260518_leadersync\5月18日 下午2-07.txt` 目前是無時間戳純文字（舊匯出）。實際輸入採上述含時間戳格式（使用者已確認）。

---

## 3. 高層架構

### 3.1 新流程

```
load+normalize 逐字稿
  → [Stage 2.95 專有名詞修正，可選，預設關]
  → chunk
  → minutes (map / reduce)
  → review
  → 輸出 minutes.html + review_report.md
```

### 3.2 設計關鍵：內部 `[HH:MM:SS] text` 格式為接縫

chunker、MinutesAgent、ReviewerAgent、html_writer、markdown_writer 全部已以
內部「`[HH:MM:SS] text` 每行一句」格式運作。loader 在載入時把 `MM:SS` 區塊
正規化成此格式並寫入 `out_dir/transcript.md`，**下游模組完全不動**。

---

## 4. 元件設計

### 4.1 新增 `script/transcript_loader.py`

**職責**：讀取使用者逐字稿檔 → 正規化 → 寫 `out_dir/transcript.md`。

- 介面：`load_transcript(src: str, dst: str) -> None`
  - `src`：使用者逐字稿檔路徑
  - `dst`：`out_dir/transcript.md`
- 行為：
  1. 以 UTF-8 讀取（`errors="replace"` 防止個別壞字元中斷）。
  2. 逐行掃描，時間戳行（regex `^\s*(\d{1,2}:\d{2}(:\d{2})?)\s*$`）切段。
  3. 每段文字壓成單行（段內換行以空白接合並去除多餘空白）。
  4. 時間戳一律正規化為 `[HH:MM:SS]`（`MM:SS` → 補 `00:` 小時）。
  5. 開頭無時間戳的文字 → `[00:00:00]`。
  6. 輸出每行 `"[HH:MM:SS] <text>"`，UTF-8 寫入 `dst`。
- **擴充點（不實作）**：在時間戳解析處留明確註解標記，未來 speaker 版逐字稿
  在此解析 speaker 並輸出 `"[HH:MM:SS] <speaker>: <text>"`（即 writer 既有
  `TranscribedSegment` 排版格式），下游 prompt 既有 speaker 指示即可運作。

### 4.2 新增 `tests/test_transcript_loader.py`

涵蓋：
- `MM:SS` 與 `H:MM:SS`／`HH:MM:SS` 皆能解析
- 多行/含空行段落壓成單行
- 開頭無時間戳 → `[00:00:00]`
- 輸出格式與 chunker 的 `_TS_RE`（`^\[(\d{2}:\d{2}:\d{2})\]`）相容

### 4.3 修改 `script/pipeline.py`

- 移除 import：`media.extract_audio`、`transcribe`、`diarize`/`assign_speakers`/
  `TranscribedSegment`、`sample_extractor.extract_speaker_samples`。
- 移除 Stage 1（抽音訊）、Stage 2（transcribe）、Stage 2.5（diarize + 語者樣本 +
  `write_template`）。
- 新流程：`force or not transcript.md` → 呼叫 `transcript_loader.load_transcript(src, transcript.md)`；
  否則用快取的 `transcript.md`。
- Stage 2.95 專有名詞修正、chunk、minutes、review、輸出**維持不變**。
- 寫 HTML / review_report 時固定傳 `diarization_enabled=False`、`speakers_detected=0`；
  仍 `speaker_map.load(out_dir/speaker_map.json)`（檔案不存在即空 dict）以保留
  使用者手動提供 speaker 對照表的彈性。
- `--rerender` 路徑維持可用（讀快取 minutes/review 重出輸出），`diarization_enabled`
  改為固定 False。

### 4.4 修改 `script/main.py`

- `src` 參數語意改為「逐字稿檔路徑」（help 文字更新）。
- 移除 `--skip-transcribe`、`--diarize/--no-diarize` 選項。
- 保留 `--name`、`--force`、`--rerender`、`-v/--verbose`。

### 4.5 修改 `script/config.py`

移除純音訊設定與驗證：`whisper_model`、`whisper_device`、`whisper_compute_type`、
`whisper_language`、`whisper_initial_prompt`、`whisper_vad_filter`、`enable_diarization`、
`hf_token`、`diarization_model`、`alignment_model`、`_check_diarization_token` validator。

其餘設定（LLM、chunking、I/O、pricing、`enable_proper_noun_correction`、`glossary_file`）維持。

### 4.6 刪除（純音訊綁定）

- 模組：`script/media.py`、`script/transcribe.py`、`script/diarize.py`、
  `script/sample_extractor.py`
- 測試：`tests/test_transcribe.py`、`tests/test_sample_extractor.py`
- 並移除其他測試/模組對上述的殘留 import

### 4.7 保留（彈性／未來 speaker 支援）

- `schemas.py` 的 `source_speaker`（`str | None = None`）
- `script/speaker_map.py` 與 `tests/test_speaker_map.py`
- `html_writer.py` / `markdown_writer.py` 既有 speaker 排版與 remap
- prompts（含 `minutes_system.j2` 的 speaker 指示）；逐字稿無 speaker 時 LLM 自然輸出 `null`
- Stage 2.95 專有名詞修正（預設關）

### 4.8 修改 `README.md`

更新使用說明：輸入改為逐字稿檔，移除影音/Whisper/diarization 段落，標註
speaker 版逐字稿為未來功能。

---

## 5. 資料流

```
使用者逐字稿(.txt, MM:SS 區塊, UTF-8)
  → transcript_loader → out_dir/transcript.md ([HH:MM:SS] text)
  → (可選) corrector → 覆寫 transcript.md (+ transcript.raw.md, correction_diff.json)
  → chunker → chunks.json
  → MinutesAgent.map → map_outputs.json
  → MinutesAgent.reduce → minutes.json
  → ReviewerAgent.review → review.json
  → html_writer → minutes.html
  → markdown_writer → review_report.md
```

`source_speaker` 全程為 `null`（無 speaker 輸入時），輸出排版自動省略語者。

---

## 6. 錯誤處理

- `src` 不存在 → 明確 `RuntimeError`（沿用 pipeline 既有風格）。
- 逐字稿空檔或全無有效行 → chunker 回傳空 `chunks`，下游照舊（不特別處理，
  與既有空轉錄行為一致）。
- 壞字元以 `errors="replace"` 容錯，不中斷整體流程。

---

## 7. 測試策略

- 新增 `test_transcript_loader.py`（§4.2）。
- 既有測試移除已刪模組相關檔（§4.6）。
- 調整 `test_pipeline.py`：以「提供逐字稿檔」為入口，移除 transcribe/diarize stub。
- 調整 `test_main.py`：移除 `--skip-transcribe`/`--diarize` 相關斷言。
- 調整 `test_config.py`：移除 whisper/diarization 設定相關斷言。
- 驗收：`pytest` 全綠；以 `D:\Meeting\20260518_leadersync\` 的逐字稿（自行補上
  `MM:SS` 時間戳的版本）跑一次 `process`，產出 `minutes.html` + `review_report.md`。

---

## 8. 未來工作（本次範圍外）

- speaker 標記逐字稿解析：待使用者提供真實樣本後，於 §4.1 擴充點實作；
  以設定（如 `TRANSCRIPT_HAS_SPEAKER`）或自動偵測切換。
- 是否清理 prompts / few-shot 中 speaker 措辭，待 speaker 功能定案再評估。
