# Makefile — Windows 任務指令說明

`Makefile` 是這個專案在 **Windows** 上的任務執行器，包裝常用流程（跑 pipeline、重新渲染、測試、清理）。需要 **GNU Make 4.4+**（裝法：`winget install ezwinports.make` 或從 git-bash 取得）。

## 前置

- 已建立虛擬環境 `.venv`（沒有的話先 `make install`）。
- **一律從倉庫根目錄執行**：`D:\GitRepo\AudioVideoToMeetingMinutes-transcription2meeting`。
- 採**變數式參數**（標準 Make 慣例）：`make TARGET VAR=value`。
- 路徑含空白或中文時，加雙引號包起來 `SRC="..."`。

## 指令一覽

| 指令 | 說明 |
|---|---|
| `make` 或 `make help` | 列出所有目標 |
| `make install` | 建立 `.venv` 並安裝執行期套件 |
| `make install-dev` | 安裝執行期 + 測試套件 |
| `make test` | 跑全部 pytest |
| `make test-verbose` | pytest `-v` |
| `make run SRC="<逐字稿檔>" [NAME=foo]` | 跑完整 pipeline（**會呼叫 LLM**）|
| `make rerender NAME=foo` | 只重新渲染輸出（**不呼叫 LLM、免費、秒級**）|
| `make open NAME=foo` | 用瀏覽器開 `out\<NAME>\minutes.html` |
| `make clean` | 刪 `__pycache__` + 各 cache（破壞性）|
| `make clean-out` | 刪整個 `out\`（破壞性，所有會議結果消失）|
| `make clean-logs` | 刪 `log\`（破壞性）|
| `make clean-all` | 上述三個清理全做 |

`NAME` 是輸出資料夾名稱（`out\<NAME>\`）。`run` 省略 `NAME=` 時用逐字稿檔名作為資料夾名。

## 中文路徑：用 `run.ps1`（不要用 `make run`）

GNU `make.exe`（ezwinports MinGW build）在 Big5/cp950 Windows 上**會把非 ASCII 的命令列引數與傳給子行程的環境變數整個重編成 ANSI 而損壞**。Teams 匯出的逐字稿檔名幾乎都是中文（`…會議錄製.vtt`），所以**中文路徑無法走 `make run`**（argv、env 兩條路都試過，都壞）。

中文路徑請改用 `run.ps1`（PowerShell→python 直達，UTF-16 全程不碰 make.exe）：

```powershell
.\run.ps1 "src\20260526_..._驗證狀況了解\I2S FPGA ...會議錄製.vtt" I2S_FPGA_20260526
```

第二個參數（NAME）可省略，預設用檔名。**純 ASCII 路徑** `make run SRC=... NAME=...` 跟 `run.ps1` 兩者皆可。其餘 `make test/clean/rerender/open` 不受影響（NAME 都是你自訂的 ASCII，沒問題）。

## 輸入格式（auto-detect）

`load_transcript` 會看 transcript 第一行非空字串自動分流，無需手動指定：

| 來源 | 第一行 | 內部走的解析器 |
|---|---|---|
| Android Recorder `.txt` | `MM:SS` / `H:MM:SS` 時間戳 | `_normalize_android` |
| Microsoft Teams `.vtt` | `WEBVTT` | `_normalize_vtt`（附帶 `<v Name>` 解出真實人名）|

跑完之後 log 會有一行 `INFO  stage.load_transcript output=... format=android|vtt` 可以驗證它認對了。

## 典型用法

完整重跑（呼叫公司 LLM，約 15+ 次、數分鐘、耗 token）：

```
make run SRC="D:\Meeting\20260518_leadersync\5月18日 下午2-07.txt" NAME=leadersync_20260518
make run SRC="D:\Meeting\20260521_Puffin\xxx.vtt" NAME=puffin_20260521
```

→ 跑 load → chunk → map → reduce → review → synthesis  
→ 產出 `out\<NAME>\` 下：`minutes.html`（互動：3 分頁/搜尋/優先級篩選/▶ 內嵌 base64 音訊）、`minutes_email.html`（貼 Outlook 用）、`review_report.md`、`intermediate\*.json`、若同名 sibling 音訊存在還有 `audio.<ext>` + `clip_*.<ext>` 切片

只重新渲染（重用快取，不花錢，最適合測排版）：

```
make rerender NAME=leadersync_20260518
```

→ 重用 `intermediate\{minutes,review,synthesized}.json`，只重出三個輸出檔。

開結果：

```
make open NAME=leadersync_20260518
```

## 注意事項

- **`run` 不帶 `--force`**：`transcript.md` 會沿用快取（Stage 1 略過），但 map/reduce/review/synthesis 仍整個重跑。要完全忽略所有快取、從頭跑：
  ```
  .venv\Scripts\python.exe -m script.main process "<逐字稿檔>" --name <NAME> --force
  ```
- `rerender` 需要先有過一次完整 `run`（要有 `intermediate\{minutes,review,synthesized}.json`），否則會報錯列出缺哪個檔。
- CLI 是**多命令**（有 `process` 與 `finalize` 子命令）：底層就是 `python -m script.main process <SRC> [--name N] [--force] [--rerender]`。
- 輸入是**已備妥的逐字稿文字檔**（UTF-8）。不吃音訊檔。
- Teams VTT 場景下沒有 sibling audio（影片太大刻意不附），▶ 按鈕自動不顯示。
