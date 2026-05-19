# make.cmd — Windows 任務指令說明

`make.cmd` 是這個專案在 **Windows** 上的任務執行器，包裝常用流程（跑 pipeline、重新渲染、測試、清理）。

不需要 GNU make 或 bash —— 純 Windows CMD 批次檔。（先前的 `Makefile` 已移除：它需要 GNU make + POSIX shell，在一般 Windows PowerShell 會因 `cmd.exe` 不懂 `[ -z ... ]` 而失敗。`make.cmd` 就是為了繞開這個問題。）

## 前置

- 已建立虛擬環境 `.venv`（沒有的話先 `.\make.cmd install`）。
- **一律從倉庫根目錄執行**：`D:\GitRepo\AudioVideoToMeetingMinutes-transcription2meeting`。
- PowerShell 要用 `.\make.cmd`（前面的 `.\` 不能省）；cmd.exe 可直接 `make.cmd`。
- 採**位置參數**（非 `KEY=VALUE`）。含空白或中文的路徑要用雙引號包起來。

## 指令一覽

| 指令 | 說明 |
|---|---|
| `.\make.cmd help` | 列出所有目標 |
| `.\make.cmd install` | 建立 `.venv` 並安裝執行期套件 |
| `.\make.cmd install-dev` | 安裝執行期 + 測試套件 |
| `.\make.cmd test` | 跑全部 pytest |
| `.\make.cmd test-verbose` | pytest `-v` |
| `.\make.cmd run "<逐字稿檔>" [NAME]` | 跑完整 pipeline（**會呼叫 LLM**）|
| `.\make.cmd rerender <NAME>` | 只重新渲染輸出（**不呼叫 LLM、免費、秒級**）|
| `.\make.cmd open <NAME>` | 用瀏覽器開 `out\<NAME>\minutes.html` |
| `.\make.cmd clean` | 刪 `__pycache__` + 各 cache（破壞性）|
| `.\make.cmd clean-out` | 刪整個 `out\`（破壞性，所有會議結果消失）|
| `.\make.cmd clean-logs` | 刪 `log\`（破壞性）|
| `.\make.cmd clean-all` | 上述三個清理全做 |

`NAME` 是輸出資料夾名稱（`out\<NAME>\`）。`run` 省略 NAME 時用逐字稿檔名作為資料夾名。

## 典型用法

完整重跑（真的呼叫公司 LLM，約 15+ 次、數分鐘、耗 token）：
```
.\make.cmd run "D:\Meeting\20260518_leadersync\5月18日 下午2-07.txt" leadersync_20260518
```
→ 等同 `python -m script.main "<逐字稿檔>" --name leadersync_20260518`
→ 重跑 load → chunk → map → reduce → review → synthesis
→ 產出 `out\leadersync_20260518\` 下：`minutes.html`（互動：3 分頁/搜尋/優先級篩選）、`minutes_email.html`（貼 Outlook 用）、`review_report.md`、`intermediate\*.json`

只重新渲染（重用快取，不花錢，最適合測排版）：
```
.\make.cmd rerender leadersync_20260518
```
→ 重用 `intermediate\{minutes,review,synthesized}.json`，只重出三個輸出檔。

開結果：
```
.\make.cmd open leadersync_20260518
```

## 注意事項

- **`run` 不帶 `--force`**：`transcript.md` 會沿用快取（Stage 1 略過），但 map/reduce/review/synthesis 仍整個重跑。要完全忽略所有快取、從頭跑，`make.cmd` 沒開這選項，請改用直接指令：
  ```
  .venv\Scripts\python.exe -m script.main "D:\Meeting\20260518_leadersync\5月18日 下午2-07.txt" --name leadersync_20260518 --force
  ```
- `rerender` 需要先有過一次完整 `run`（要有 `intermediate\{minutes,review,synthesized}.json`），否則會報錯列出缺哪個檔。
- CLI 是單命令（**沒有** `process` 子命令）：底層就是 `python -m script.main <SRC> [--name N] [--force] [--rerender]`。
- 輸入是**已備妥的逐字稿文字檔**（UTF-8，`MM:SS` 或 `H:MM:SS` 時間戳一行、文字一行的區塊；無 speaker 標記）。不吃音訊檔。
