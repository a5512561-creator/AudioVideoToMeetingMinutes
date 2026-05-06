# 公司背景知識

> **這個檔案會塞進每次 LLM 呼叫的 system prompt。寫太長會浪費 token、寫太短 LLM 會對你公司不熟悉。建議 200-500 字。**
>
> 標 `（請填）` 的地方是你公司專屬的資訊；其他通用內容可保留。

## 組織

- 公司名稱：（請填，例如「瑞昱半導體」、「ACME 公司」）
- 主要產品線：（請填，例如「Wi-Fi 晶片」、「網路 IC」、「audio codec」）
- 常見部門縮寫：（請填）
  - 範例：RD = 研發部、QA = 品保部、PMO = 專案管理辦公室、PM = 產品經理、FAE = 應用工程師
- 常見產品 / 專案代號：（請填）
  - 範例：產品代號通常是英數混合，如 ALC1220、RTL8125

## 會議類型

- 週會 / 月會 / 季會
- Sprint planning / Sprint review / Retrospective
- 產品 review / Design review / Code review
- 客戶 demo 後檢討
- on-site / off-site workshop

## 常見技術術語（通用）

- API / SDK / spec / RFC
- Roadmap / milestone / blocker / gating issue
- Sprint / Kanban / backlog / ticket
- PR / MR / branch / merge / rebase / cherry-pick
- CI / CD / pipeline / staging / prod / canary
- bug / regression / patch / hotfix
- spec freeze / feature freeze / release candidate / GA

## 推論時的偏好

- 期限若以「下週X」、「下個月」表達，標為相對日期，不要強行換算成絕對日期
- 沒有明確 owner 的任務，priority 一律給 medium，不要猜 high
- 同一場會議若多人重複提到同件事但細節有差異，以最後一次發言為準
