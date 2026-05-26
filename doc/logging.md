# 日誌（Logging）功能說明

pipeline 每跑一次會同時把結構化日誌輸出到 **主控台** 與 **檔案**，方便即時觀察與事後追查。

## 檔案位置與命名

- 目錄：`log/`（由 `.env` 的 `LOG_DIR` 設定，預設 `log`）。
- 每跑一次產生一個檔，命名格式：

  ```
  run_<YYYYMMDD-HHMMSS>_<會議名>.log
  例：run_20260526-144430_I2S_FPGA_20260526.log
  ```

- `<會議名>` 是輸出資料夾名（`--name` / `make run NAME=` / `run.ps1` 第二參數；省略時取逐字稿檔名）。經過檔名安全化：Windows 不合法字元 `<>:"/\|?*` 與空白會換成 `_`，中文保留（NTFS 合法），長度上限 60 字。
- 沒有會議名時退回 `run_<YYYYMMDD-HHMMSS>.log`。

## 輸出管道

| 管道 | 用途 |
|---|---|
| 主控台（StreamHandler）| 跑的當下即時看 |
| 檔案（FileHandler, UTF-8）| 事後追查、貼給別人看 |

層級由 `.env` 的 `LOG_LEVEL` 控制（預設 `INFO`）；加 `-v` / `--verbose` 提升到 `DEBUG`。

## 行格式

```
[YYYY-MM-DD HH:MM:SS] LEVEL  event key1=value1 key2=value2 ...
```

結構化的 `event k=v` 形式，方便 grep。例：

```
[2026-05-26 14:38:01] INFO  stage.minutes conclusions=4 actions=9 calls=3 tokens_in=32764 tokens_out=12587
```

## 主要事件一覽

| event | 意義 / 重要欄位 |
|---|---|
| `pipeline.start` | 開跑。`file=` 來源、`name=` 輸出資料夾、`rerender_only=` |
| `stage.load_transcript` | 載入逐字稿。**`format=android\|vtt`** ← 驗證 auto-detect 認對格式 |
| `stage.transcript.cached` | 沿用既有 `transcript.md`（沒重新載入）|
| `stage.chunk` | 切塊完成。`chunks=` 數量 |
| `instructor.mode` | Instructor 模式（`TOOLS` / `JSON`）|
| `progress` | **進度心跳**（見下）。`stage= calls= pct= elapsed=` |
| `stage.minutes` | 抽取階段完成。`conclusions= actions= calls= tokens_in/out=` |
| `stage.review` | 審查階段完成。`items= warns= errors=` |
| `stage.synthesis` | 綜整階段完成。`topics= actions=` |
| `stage.audio_asset` | 同名音訊處理。`copied=` 或 `status=missing` |
| `stage.audio_clips` | 切音訊片段數。`count=`（Teams 無音訊時為 0）|
| `pipeline.tokens` | 全程 token 統計 + `cost=`（沒設牌價則 0）|
| `pipeline.done` | 完成。`out=` 輸出路徑 |

## 進度心跳（Progress Heartbeat）

LLM 階段（minutes / review / synthesis）可能因模型慢而長時間沒輸出，看起來像當機。心跳會**固定間隔**吐一行讓你知道還活著：

```
progress stage=minutes:reduce calls=2/~5 pct=40% elapsed=1m40s
```

| 欄位 | 意義 |
|---|---|
| `stage` | 目前階段：`minutes:map` → `minutes:reduce` → `review` → `synthesis` |
| `calls` | 已完成 LLM 呼叫數 / 預估總數（map + reduce + review + synthesis）|
| `pct` | 約略完成度 = 已完成呼叫 / 預估總數，上限封頂 99%（真正完成看 `pipeline.done`）|
| `elapsed` | 自 pipeline 開始的經過時間 |

設定：`.env` 的 `PROGRESS_INTERVAL_SECS`（預設 `60` 秒，設 `0` 關閉）。

**重要特性**：`pct` 在「單一通很慢的 LLM call」期間會停著不動（拿不到 call 內的 token 進度），但 `elapsed` 持續跳 —— 所以「卡住沒回應」與「還在跑只是慢」一眼可分。地端 `medium` 模型偶爾單通要好幾分鐘，這時心跳就特別有用。

## 常用查詢

```powershell
# 列出某場會議的所有 log
Get-ChildItem log\run_*_I2S_FPGA_20260526.log

# 只看階段里程碑
Select-String "stage\.|pipeline\." log\run_*_I2S_FPGA_20260526.log

# 看 token 用量 / 成本
Select-String "pipeline.tokens" log\*.log
```
