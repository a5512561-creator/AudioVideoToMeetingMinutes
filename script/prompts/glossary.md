# 術語表（人類維護）

> **TranscriptCorrector 只會修正下方列出的詞彙**在 transcript 中的常見錯誤拼寫，其他內容一字不動。
> 預設關閉（`ENABLE_PROPER_NOUN_CORRECTION=false`）；要啟用先在下方填好真實人名/產品名，再改 .env。
>
> 格式：`正確寫法（不要寫成：常見錯誤1、常見錯誤2）`
>
> 此檔對「**我們知道該替換成什麼**」的拼寫錯誤有效。對「ASR 整段雜亂無章」的句子無能為力（例如 `讓天寫一個讓它可以自動餐廳那種廣告背部吧`），那要靠 minutes_agent 的推論能力處理。

## 人名（單字人名最容易被 ASR 切錯，補進這裡幫助最大）
- 小王（不要寫成：肖王、小汪、消王）
- 王小明（不要寫成：王曉明、王小銘）
- （請依公司常出現的人名擴充）

### 常見單字人名陷阱（依實際情況填入）
ASR 對「**讓 X 做某事**」、「**請 X 幫忙**」、「**找 X 確認**」這類句型容易把 X 切錯。最常見錯誤模式是**把動詞或副詞誤聽成人名**：
- 「**讓天寫一個工具**」← 通常原意是「讓他寫」或某個單字人名（如「天哥」「天威」）。請依實際同事姓名補正：
  - 例：天威（不要寫成：天）— 若公司有叫天威的同事
- 「**問問同學**」← 「同學」可能是真同事姓「童」+ 「學」字、或「同學」是真用法
- （請依會議中常被誤聽的同事補進來）

## 產品 / 專案代號
- Phoenix（不要寫成：菲尼克斯、鳳凰）
- Roadmap-2026（不要寫成：roadmap二零二六）
- （請依公司產品名擴充。產品名常被 ASR 誤譯，效益最大）

## 部門 / 縮寫
- RD = 研發部
- PMO = 專案管理辦公室
- QA = 品保部
- FAE = 應用工程師（不要寫成：FAB）
- DV = Design Verification（不要寫成：dv、Dv、DD）
- DD = Design / Designer（不要寫成：dd）

## 常被音譯的英文技術詞
- Sprint（不要音譯成：司普林特、思普林）
- Roadmap（不要音譯成：羅德麥）
- spec（不要寫成：思貝克、Spark）
- API（不要寫成：A P I 拆字）
- demo（不要寫成：對謀、得謀）
- CI / CD（不要拆字）
- staging（不要寫成：史德今）
- production / prod（不要寫成：普朗達克、普羅）
- coverage（不要寫成：cover ridge、卡佛瑞吉）
- regression（不要寫成：retro 推測、瑞葛瑞星）
- testbench（不要寫成：test bench、TPK bench、timberland sin）
- golden test case（不要寫成：golden taskc case、golden tax case）

## 公司客戶 / 合作夥伴
- ACME Corp（範例）
- （請依實際客戶名擴充）
