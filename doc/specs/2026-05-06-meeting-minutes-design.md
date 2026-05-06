# 會議錄影/錄音 → 會議記錄 自動化系統 — 設計文件

- **日期**: 2026-05-06
- **版本**: v3 (加入 Stage 2.95 專有名詞 LLM 修正)
- **作者**: paddychen + Claude (brainstorming)
- **狀態**: Draft (待 review)

---

## 0. 變更紀錄

- **v3 (2026-05-06)**：依同事 ASR pipeline 研究，加入 Stage 2.95「專有名詞 LLM 保守修正」，解決 Whisper 對中文人名/公司名/產品名易拼錯的問題（污染下游所有抽取）。其他建議（FireRedASR2 換引擎、voice enrollment 真名、pyannote Precision-2 付費版）暫不採納，記錄於 §7 / §8 供未來參考。
- **v2 (2026-05-06)**：完成 best-practice 調研，加 diarization 為可選功能、換用 Instructor / Jinja2 / typer / pydantic-settings / stamina / recursive chunking。
- **v1 (2026-05-06)**：初版設計。

---

## 1. 目標與動機

把公司內部會議的影音檔（30 分鐘 ~ 數小時）自動轉成可追蹤、可審核的會議記錄 Excel。

核心約束：
- 只能用公司**地端 LLM**（OpenAI 相容 API：`OPENAI_API_KEY` / `OPENAI_API_BASE` / `OPENAI_MODEL`）
- 不可外傳（會議內容含敏感資訊）
- LLM context 大小**未知且需可調**

核心需求：
1. 影音 → 文字 → 結構化會議記錄 (Excel)
2. 兩個 Agent：MinutesAgent (產記錄)、ReviewerAgent (檢查衝突/不明/不合理)
3. 所有 LLM 推論的項目要明確標記 `[LLM推論]`
4. 為未來擴充 (新 few-shot、新背景知識、新 Agent) 預留乾淨的接口
5. **支援 Speaker Diarization (SPEAKER_1, SPEAKER_2...) — 可選功能，預設關**

---

## 2. 高層架構

### 2.1 Pipeline (5 階段，diarization 為可選)

```
影音檔 (mp4/mov/mp3/wav)
   │
   ▼  Stage 1: media.py
   │  ffmpeg → 16kHz mono WAV
   │
   ▼  Stage 2: transcribe.py
   │  faster-whisper (large-v3, language=zh, vad_filter=True)
   │  → segments (含時間戳)
   │
   ▼  Stage 2.5: diarize.py  (可選，ENABLE_DIARIZATION=true 才跑)
   │  pyannote Community-1 → speaker segments
   │  + wav2vec2 forced alignment (中文模型)
   │  → 每段話標 SPEAKER_1, SPEAKER_2...
   │
   ▼  Stage 2.9: 寫出 transcript.md (含時間戳 + 可選 speaker label)
   │
   ▼  Stage 2.95: TranscriptCorrector  (可選，ENABLE_PROPER_NOUN_CORRECTION=true 才跑)
   │  讀 transcript.md + glossary.md
   │  LLM 保守修正：只修術語表內的人名/產品名拼寫，不改其他內容
   │  → 覆寫 transcript.md，原檔備份為 transcript.raw.md
   │
   ▼  Stage 3: MinutesAgent (map-reduce)
   │  chunker.py → recursive 分塊 (句子優先 + token 三層 fallback)
   │  map: 每塊 LLM → {topics, conclusions, actions} JSON
   │  reduce: 合併、去重、整合 → minutes.json
   │
   ▼  Stage 4: ReviewerAgent
   │  讀 minutes.json，逐條檢查 (衝突/不明/不合理)
   │  → 每條的 review note
   │
   ▼  Output
       minutes.xlsx (2 sheets)
       review_report.md
       intermediate/*.json (除錯)
```

### 2.2 設計準則

- **每階段 I/O 都是檔案**：可單獨 re-run、stage cache（transcript.md 存在就跳 ASR + diarization）
- **資料層 vs 呈現層分離**：LLM 出 raw JSON (含 is_inferred 旗標)，writer 才負責加 `[LLM推論]` 前綴 / 黃底
- **Prompt as Files (Jinja2)**：所有 prompt 在 `script/prompts/`，含 few-shot 注入 template，不寫死在 Python
- **Schema-first**：Pydantic + Instructor，自動 strict mode 偵測 + retry/repair

---

## 3. 目錄結構

```
AudioVideoToMeetingMinutes/
├── .env.example
├── .gitignore                    # .venv, .env, out/, log/, *.pyc, __pycache__, ~/.cache
├── requirements.txt
├── .venv/
├── doc/
│   └── specs/2026-05-06-meeting-minutes-design.md
├── script/
│   ├── main.py                   # CLI 入口 (typer)
│   ├── pipeline.py               # 5 階段 orchestrator
│   ├── media.py                  # ffmpeg subprocess 包裝
│   ├── transcribe.py             # faster-whisper 包裝
│   ├── diarize.py                # WhisperX/pyannote 包裝 (可選)
│   ├── transcript_corrector.py   # Stage 2.95 專有名詞 LLM 修正 (可選)
│   ├── chunker.py                # recursive 分塊 + token 三層 fallback
│   ├── excel_writer.py           # openpyxl 輸出
│   ├── markdown_writer.py        # review_report.md + transcript.md
│   ├── config.py                 # pydantic-settings (.env 驗證)
│   ├── logger.py                 # log/ 寫入
│   ├── agents/
│   │   ├── base.py               # LLMAgent base (Instructor + OpenAI client)
│   │   ├── minutes_agent.py
│   │   ├── reviewer_agent.py
│   │   └── corrector_agent.py    # Stage 2.95 專有名詞修正 agent
│   └── prompts/
│       ├── background.md         # 公司術語、部門名 (兩個 agent 共用)
│       ├── glossary.md           # 專有名詞清單 (corrector 用)
│       ├── corrector_system.j2
│       ├── corrector_user.j2
│       ├── minutes_system.j2
│       ├── minutes_map.j2
│       ├── minutes_reduce.j2
│       ├── reviewer_system.j2
│       ├── reviewer_user.j2
│       └── few_shot/
│           ├── corrector/*.json
│           ├── minutes/*.json
│           └── reviewer/*.json
├── out/
│   └── <basename>/
│       ├── transcript.md         # 經 corrector 修正後 (若啟用)
│       ├── transcript.raw.md     # corrector 啟用時的原始備份
│       ├── minutes.xlsx
│       ├── review_report.md
│       └── intermediate/
│           ├── chunks.json
│           ├── map_outputs.json
│           ├── minutes.json
│           ├── review.json
│           └── correction_diff.json   # corrector 改了哪些字 (debug + audit)
└── log/
    └── run_YYYYMMDD-HHMMSS.log
```

---

## 4. Agent 設計與 Prompt 架構

### 4.1 LLMAgent 基底類別 (`agents/base.py`)

```python
import instructor
from openai import OpenAI
from jinja2 import Environment, FileSystemLoader

class LLMAgent:
    name: str                          # "minutes" / "reviewer"
    system_template: str               # 例 "minutes_system.j2"

    def __init__(self, config):
        client = OpenAI(api_key=..., base_url=...)
        # Mode 由 config.instructor_mode 指定 (預設 JSON 最廣相容)
        # 啟動時可選擇用 probe_instructor_mode() 自動偵測伺服器支援哪個 mode
        self.llm = instructor.from_openai(client, mode=config.instructor_mode)
        self.model = config.openai_model
        self.jinja = Environment(loader=FileSystemLoader("script/prompts/"))
        self.background = open("prompts/background.md").read()
        self.few_shots = load_all(f"prompts/few_shot/{self.name}/")

    def render(self, template: str, **ctx) -> str:
        ctx.setdefault("background", self.background)
        ctx.setdefault("few_shots", self.few_shots)
        return self.jinja.get_template(template).render(**ctx)

    def call(self, system: str, user: str, response_model: BaseModel):
        # Instructor 內建 retry + Pydantic validation
        return self.llm.chat.completions.create(
            model=self.model,
            response_model=response_model,
            max_retries=3,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
```

### 4.2 Decision Rationale — 結構化 LLM 輸出

| 方案 | 優點 | 缺點 |
|---|---|---|
| 純 `response_format=json_object` + Pydantic + 自寫 retry | 廣相容、簡單 | 只保 JSON 合法、不保 schema；地端 LLM 易吐壞 JSON 需自寫 repair |
| OpenAI Structured Outputs (`json_schema` strict) | 100% schema 合規 | 地端 LLM **不一定**支援（取決於 vLLM/SGLang/TGI/llama.cpp 版本） |
| **Instructor library**（採用） | Pydantic-first；自動 Pydantic 驗證 + retry/repair；跨 15+ provider；可任選 mode (TOOLS / JSON_SCHEMA / JSON) | 多一個依賴 |

**選擇理由**：地端 LLM strict mode **無法保證**（小 model 或低量化常吐壞 JSON）。Instructor 不會自動切換 mode（mode 由我們指定），但會在 Pydantic 驗證失敗時**自動把錯誤回貼給 LLM 重試**，這是手寫 repair 最痛的部分。

**Mode 選擇策略**：
1. **預設 `Mode.JSON`**：最廣相容，幾乎所有 OpenAI-相容 server 都支援
2. **`probe_instructor_mode()` 啟動時偵測**：對 `OPENAI_API_BASE` 試打一個 `Mode.JSON_SCHEMA` 探測請求，成功則升級用 strict mode（更高合規率）
3. 結果寫進 `config.instructor_mode` 給 agents 用，後續通通走偵測到的 mode

### 4.3 Decision Rationale — Prompt 管理

| 方案 | 優點 | 缺點 |
|---|---|---|
| 純 `.md` + 手動 string concat | 零依賴、git diff 友善 | few-shot 注入需手寫拼接、無條件/迴圈 |
| **Jinja2 + `.j2` templates**（採用） | 條件/迴圈/include 完備；few-shot `{% for ex in few_shots %}` 一行；git 友善；近標配依賴 | 多一個依賴 (Jinja2) |
| Langfuse / Mirascope / PromptLayer | UI 編輯、版本控制、observability | 工業級 SaaS，個人 CLI 完全 over-engineer |

**選擇理由**：純 string concat 在「自動載入 few-shot」就會痛。Jinja2 學習成本零、檔案仍在 git，直接解決需求。SaaS 平台對單機 CLI 是過度設計。

### 4.4 擴充點 (不改 base class)

| 想做的事 | 怎麼做 |
|---|---|
| 加 reviewer few-shot | 丟 `prompts/few_shot/reviewer/case_xxx.json`，自動載入 |
| 改公司術語 | 編輯 `prompts/background.md` |
| 改 prompt 風格 | 編輯對應 `*_system.j2` / `*_user.j2` |
| 新增 Agent (如 Email 草稿產生器) | 新 `agents/email_draft_agent.py` 繼承 LLMAgent |

### 4.5 Few-shot 檔案格式

`prompts/few_shot/reviewer/example_001_conflict.json`:
```json
{
  "input": "請檢查這份會議結論... [貼會議內容]",
  "output": "{\"reviews\": [{\"target_id\": \"c1\", \"category\": \"conflict\", ...}]}",
  "comment": "示範：reviewer 該如何指出兩條結論衝突 (給人類看的，LLM 不讀)"
}
```

`comment` 不送進 LLM，給未來維護者看。

### 4.6 MinutesAgent — map-reduce

**Map 階段** (對每塊 transcript 跑一次)：

```python
class ChunkExtract(BaseModel):
    topics: list[str]
    conclusions: list[Conclusion]
    actions: list[Action]

class Conclusion(BaseModel):
    text: str
    is_inferred: bool          # True → Excel 顯示時前綴 [LLM推論]
    source_quote: str          # 原句
    source_timestamp: str      # 例 "00:23:15"
    source_speaker: str | None # 例 "SPEAKER_2"，無 diarization 則 None

class Action(BaseModel):
    task: str
    owner: str                 # 找不到填「未明」
    due: str                   # 找不到填「未明」
    priority: Literal["high", "medium", "low"]
    source_quote: str
    source_timestamp: str
    source_speaker: str | None
    rationale: str             # ★「LLM 判斷依據」欄
    is_inferred: bool          # task 本身是否為 LLM 推論
    owner_inferred: bool
    due_inferred: bool
    priority_inferred: bool    # 通常都是 True
```

**Reduce 階段** (一次跑完所有 map 結果):
- input：所有 ChunkExtract 串接
- 任務：去重、合併同主題、跨段串連 → 最終 `MeetingMinutes`
- 若串接結果仍超過 `LLM_CHUNK_CHARS * 2`，自動切換**樹狀 reduce**（兩兩合併）

**Reduce 後的最終 schema**：

```python
class MeetingMinutes(BaseModel):
    conclusions: list[Conclusion]    # ID 由 list index 給：C1, C2, ...
    actions: list[Action]            # ID 由 list index 給：A1, A2, ...
```

ID 規則由 pipeline 層在 reduce 後賦予（不靠 LLM 出 ID，避免重複/跳號）。Reviewer 收到的 input 已含 ID，輸出 `target_id` 直接對應。

### 4.7 Decision Rationale — 長文摘要策略

| 方案 | 優點 | 缺點 |
|---|---|---|
| **Map-reduce + 自動樹狀升級**（採用） | 可平行、scalable；context size 不敏感；debug 容易（每 chunk 獨立可重跑）；地端 LLM 友善 | 跨 chunk 話題斷裂需 overlap 處理；reduce 階段易丟細節 |
| Hierarchical / RAPTOR | narrative flow 保留好；HELMET 顯示與 long-context direct 性能相當但成本低 | 多輪 LLM call → 延遲與成本疊加；debug 需追蹤樹狀關係 |
| Refine (langchain) | 序列化、可累積上下文 | **無法平行**；60K 字會非常慢；前段易被稀釋 |
| RAG over transcript | 適合「問答」 | 結構化抽取需**完整覆蓋**，RAG 召回不全會漏，**不適合主路徑** |
| Long-context direct (128K 灌進去) | 最簡單 | 地端 context 未知；研究顯示 context 越大幻覺率越高；非 GPT-4o 級不可靠 |

**選擇理由**：Map-reduce + 串接超量自動樹狀 reduce = hierarchical 的優雅退化版。RAG/contextual retrieval 留作後續「問答 plugin」，不混進主管線。

### 4.8 TranscriptCorrectorAgent (Stage 2.95)

**動機**：Whisper 對中文人名 / 公司名 / 產品名常拼錯（「小王」→「肖王」、「Sprint」→「司普林特」），這些錯誤會污染下游 MinutesAgent 與 ReviewerAgent 的所有抽取結果。在進入 chunker 前先做一次保守修正成本低、收益高。

**保守原則**：
- **只修**術語表內出現的詞彙（人名、產品名、部門縮寫、技術術語）
- **不改**任何其他文字、句構、標點、時間戳
- 修正動作全部記錄到 `intermediate/correction_diff.json` 供人審查

**Schema**：

```python
class CorrectionDiff(BaseModel):
    original: str          # 原文片段
    corrected: str         # 修正後片段
    matched_term: str      # 對應到 glossary 的哪個詞
    timestamp: str         # 該片段在 transcript 的時間戳

class CorrectionResult(BaseModel):
    corrected_text: str    # 修正後完整文字（含原時間戳格式）
    diffs: list[CorrectionDiff]
```

**運作方式**：
- 按段（每 `LLM_CHUNK_TOKENS` 字元一段，無 overlap，避免 LLM 改到重疊區造成衝突）
- 每段送 LLM：「這是 glossary，請只修正以下文字中對應 glossary 的拼寫錯誤，其他一字不動」
- LLM 回 `CorrectionResult`
- 串接所有段 → 覆寫 `transcript.md`，原檔備份為 `transcript.raw.md`
- 串接所有 diffs → 寫 `correction_diff.json`

**glossary.md 格式**（人類維護）：

```markdown
# 術語表

## 人名
- 小王（不要寫成：肖王、小汪）
- 王小明（不要寫成：王曉明）

## 產品 / 專案代號
- Phoenix（不要寫成：菲尼克斯、鳳凰）
- Roadmap-2026

## 部門 / 縮寫
- RD = 研發部
- PMO = 專案管理辦公室
- Sprint（保持英文，不要音譯成「司普林特」）

## 客戶 / 合作夥伴
- ACME Corp
```

LLM 看到 glossary 後會：(a) 在 transcript 中尋找這些詞的「常見錯誤拼寫」，(b) 改回正確版。

### 4.9 Decision Rationale — 為何放在 chunker 前而非 chunker 後

| 方案 | 優點 | 缺點 |
|---|---|---|
| **Chunker 前修正整份 transcript**（採用） | 下游 (chunker / minutes / reviewer / output) 全部用乾淨 transcript；source_quote 也是乾淨的 | LLM call 數較多（transcript 直接按段切跑） |
| Chunker 後在每塊內修正 | 與 minutes map call 合併到同一輪，省 call 數 | 多項職責塞同一個 prompt 容易互相干擾；source_quote 還會抓到原錯誤 |
| 完全不修，靠 minutes prompt 內加「請忽略拼寫錯誤」 | 零改動 | 不可靠；source_quote 仍是錯的，Excel 看到一堆怪字 |

**選擇理由**：transcript 是 single source of truth，下游所有用到 source_quote 的地方（Excel、Markdown、Reviewer）都會看到原句。在 transcript 層做修正讓「資料來源乾淨」原則維持。

### 4.10 ReviewerAgent

```python
class ReviewNote(BaseModel):
    target_section: Literal["conclusion", "action"]   # 對應 minutes.conclusions / minutes.actions
    target_id: str             # C1, A2, ... (由 pipeline 在 reduce 後賦予)
    category: Literal["conflict", "ambiguity", "unreasonable", "ok"]
    severity: Literal["info", "warn", "error"]
    note: str
    suggestion: str
```

注意：**每一條都要回**（包括 OK 的，category="ok", severity="info"），這樣 Excel 才能對每列填 Review 欄。

excel_writer 把 `target_section` 對應到 Sheet 1 的兩個 section（`conclusion` → 會議結論 section，`action` → Action Items section），用 `target_id` 找列填 Review 欄。

---

## 5. 輸出結構

### 5.1 transcript.md 格式

無 diarization：
```markdown
[00:00:05] 那我們先講第一個議題。
[00:00:12] 上週會議大家有達成共識...
```

有 diarization：
```markdown
[00:00:05] SPEAKER_1: 那我們先講第一個議題。
[00:00:12] SPEAKER_2: 上週會議大家有達成共識...
```

### 5.2 `minutes.xlsx` — 2 sheets

#### Sheet 1：「會議記錄」 (兩個 section 上下排)

```
┌─────────────────────────────────────────────────────────────────────┐
│ ▌會議結論  (section header: 合併儲存格 跨整列、深色底、白字粗體)         │
├─────┬──────────────┬──────────────┬─────────┬────────┬──────────────┤
│ 編號 │ 結論內容      │ 來源原句       │ 時間戳   │ 發言者  │ Review檢查結果 │
├─────┼──────────────┼──────────────┼─────────┼────────┼──────────────┤
│ C1  │ 下季 roadmap…│「我們就照A案走」│ 00:42:18│SPEAKER_1│ ✅ OK         │
│ C2  │ [LLM推論] 預算│「大概五百萬左右」│ 01:15:03│SPEAKER_3│ ⚠️ ambiguity… │
├─────────────────────── (空白行 隔開) ─────────────────────────────────┤
│ ▌Action Items  (section header)                                       │
├─────┬─────┬──────┬─────┬─────┬─────────┬───────┬───────┬─────────┬───┤
│ 編號 │ 任務 │ 負責人│ 期限 │ 優先度│ 來源原句 │ 時間戳 │ 發言者 │ LLM判斷依據│Rev │
├─────┼─────┼──────┼─────┼─────┼─────────┼───────┼───────┼─────────┼───┤
│ A1  │ 完成…│ 小王 │ 5/15│ high │「小王下…│01:02:03│SPEAKER_1│任務直接由…│ ✅ │
└─────┴─────┴──────┴─────┴─────┴─────────┴───────┴───────┴─────────┴───┘
```

實作要點 (openpyxl):
- Section header 用 `merge_cells` 跨整列、深色 fill、白字粗體
- 兩 section 欄數不同：直接讓 Actions section 多用幾欄即可
- `freeze_panes` 設在第一個 section header 下
- Auto-filter：分別對兩個 section 區塊套用
- **發言者欄**：當 ENABLE_DIARIZATION=false 時，整欄留空但保留欄位（schema 一致）

Review 檢查結果格式：`{圖示} {category}：{note}`
- `✅` info
- `⚠️` warn
- `❌` error

#### Sheet 2：「Review 摘要」 (只列 severity ≥ warn)

| 對應位置 | 編號 | 類型 | 嚴重度 | 說明 | 建議修正 |
|---|---|---|---|---|---|
| 結論 | C2 | ambiguity | warn | 「左右」未明確 | 與會者確認 |
| Action | A2 | ambiguity | warn | owner 未經當場確認 | 口頭確認後修正 |

### 5.3 Decision Rationale — Excel 寫入 lib

| 方案 | 優點 | 缺點 |
|---|---|---|
| **openpyxl**（採用） | 唯一同時支援讀+寫+改；styling/merge/freeze/auto-filter 全支援；最大社群 | 寫入速度慢於 xlsxwriter |
| xlsxwriter | 寫入最快；styling 最豐富 | 只能寫不能讀/改 |
| pandas + ExcelWriter | DataFrame 一行輸出 | 本質上呼叫前兩者，僅是包裝 |

**選擇理由**：會議記錄量級（百-千 row）效能差異無感；雙向能力對未來「改既有範本檔」有彈性。

### 5.4 `review_report.md`

```markdown
# Meeting Review Report
**會議檔案**: 2026Q2_planning.mp4
**轉錄時間**: 2026-05-06 14:23
**Diarization**: enabled (3 speakers detected)
**Review 結果**: 2 warn / 0 error / 12 OK

---

## ⚠️ Warning (2)

### 1. 結論 C2 — ambiguity
> [LLM推論] 預算上限 500 萬
> 來源：「大概五百萬左右吧」(01:15:03, SPEAKER_3)

**問題**：「左右」未明確
**建議**：與會者確認是 500 上限或上下浮動

---

## ✅ OK (12)
- C1: 下季度產品 roadmap 以 A 案為主 (SPEAKER_1)
- A1: 完成 API 規格 (小王 / 2026-05-15)
- ...
```

### 5.5 `[LLM推論]` 標記策略

兩層機制：
1. **資料層**：每個欄位帶 `*_inferred: bool` 旗標 (Pydantic schema 強制)
2. **呈現層**：
   - Excel 文字前綴 `[LLM推論]`
   - Excel 儲存格淺黃色底 (openpyxl `PatternFill`)
   - Markdown 同樣前綴

### 5.6 中介產物

| 檔案 | 內容 | 除錯用途 |
|---|---|---|
| `chunks.json` | chunker 切出的每塊 + 時間範圍 | 看分塊邊界是否合理 |
| `map_outputs.json` | 每塊 LLM raw + parsed | 看哪塊抽錯 |
| `minutes.json` | reduce 後的 final | Excel 從這個產生 |
| `review.json` | reviewer raw | 看 reviewer 判斷邏輯 |
| `diarization.json` | speaker segments (有開時) | 看 speaker 切分是否正確 |

---

## 6. ASR / Diarization / Chunking / Config / Logging / Testing

### 6.1 Decision Rationale — ASR 引擎

| 方案 | 中文 | 速度 | License | 採用 |
|---|---|---|---|---|
| **faster-whisper + large-v3**（採用） | CJK 最佳，CER ~4% (AISHELL baseline) | INT8 量化、GPU 加速 | MIT | ✅ |
| openai-whisper 官方 | 同 large-v3 | 慢 4× | MIT | |
| WhisperX | 同 (底層即 faster-whisper) | 較重 | BSD-4 | (在 diarization stage 用) |
| NVIDIA Parakeet v3 | **不支援中文** (僅歐語) | 25-30× Whisper | CC-BY-4.0 | ❌ |
| whisper.cpp | 支援 | INT4/INT8 量化省記憶體 | MIT | (純 CPU 邊緣裝置考量) |

**選擇理由**：Parakeet 雖快但無中文出局；large-v3 仍是 2026 CJK 開源 SOTA；faster-whisper 是其最快實作。

### 6.2 Decision Rationale — Whisper 模型版本

| 模型 | 大小 | 速度 vs v3 | 中文準確率 |
|---|---|---|---|
| **large-v3**（採用） | ~3 GB | 1× | CER ~4%（AISHELL baseline）；CJK 最佳 |
| large-v3-turbo | 809 MB | 2.7-8× | CJK **明顯衰退**（decoder 砍 32→4 層） |
| distil-whisper | ~750 MB | 6× | **僅英語**；中文不可用 |
| Belle-whisper-large-v3-zh | ~3 GB | 同 v3 | 簡中改善 24-65%，繁中需實測 |

**選擇理由**：turbo 對英文影響小但 CJK 因 decoder 簡化衰退顯著；3 GB 一次性下載換正確率值得。INT8 量化（faster-whisper 內建）作為加速首選，比換模型安全。

### 6.3 Decision Rationale — 影片轉音訊

| 方案 | 優點 | 缺點 |
|---|---|---|
| **ffmpeg subprocess**（採用） | 零 Python 依賴；可串流不爆記憶體；Windows 最穩 | 字串組命令需小心 escape |
| ffmpeg-python | wrapper 介面親和 | 維護放緩；多一層 debug 困難 |
| pydub | API 簡單 | **長音檔 OOM**（全載入記憶體） |

**選擇理由**：3 小時會議純命令最穩；命令固定 `ffmpeg -i input -vn -ac 1 -ar 16000 -c:a pcm_s16le out.wav`，無動態組合需求。

### 6.4 Decision Rationale — Speaker Diarization (可選)

| 方案 | 中文 | License | 講者數限制 | 採用 |
|---|---|---|---|---|
| **WhisperX + pyannote Community-1**（採用） | AISHELL-4/AliMeeting SOTA | CC-BY-4.0 (商用 OK) | 無 | ✅ |
| pyannote 3.1 standalone | 中文較弱 | MIT | 無 | |
| NVIDIA Sortformer 4spk-v1 | 主英文 | **CC-BY-NC**（禁商用） | **限 4 人** | ❌ |
| Reverb diarize v2 | 主英文 | research only | 無 | ❌ |
| whisper-diarization (MahmoudAshraf97) | 用 NeMo 中文未優化 | BSD-2 | 支援 | (備選) |

**選擇理由**：Community-1 是 2025 年 pyannote 全新訓練版，AISHELL-4 11.7% / AliMeeting 20.3% DER，中文會議首選；CC-BY-4.0 商用可；無講者數上限。Sortformer 限 4 人 + 禁商用直接出局。

**整合管線**：

```
faster-whisper (segments + 時間戳)
       ↓
wav2vec2 forced alignment (中文模型 jonatasgrosman/wav2vec2-large-xlsr-53-chinese-zh-cn)
       ↓ (word-level timestamps)
pyannote Community-1 (speaker segments)
       ↓ (時間戳對齊)
合併：每個詞 → overlap 最大的 speaker segment
       ↓
連續同 speaker 詞合併為段
       ↓
SPEAKER_1: ..., SPEAKER_2: ...
```

**HF token 流程**：
1. 申請 HF 帳號 → 接受 `pyannote/speaker-diarization-community-1` gated terms（自動核准）
2. `huggingface-cli login` 一次
3. 模型快取在 `~/.cache/huggingface/`，之後**完全離線可跑**
4. 部署時可預打包 cache 到 image，免每台機器重申請

**可選機制**：`.env` 設 `ENABLE_DIARIZATION=false` 則整個 Stage 2.5 跳過，transcript 不含 speaker 標籤、Excel 發言者欄空白；對快速試跑、無 GPU、敏感場景皆方便。

### 6.5 Decision Rationale — Chunking 策略

| 方案 | 優點 | 缺點 |
|---|---|---|
| **Recursive：句子優先 → token 上限切 + token 三層 fallback**（採用） | 不切斷語意；token 計算精確；debug 友善；2026 benchmark 顯示 recursive 勝 semantic（69% vs 54%） | 實作中等複雜度 |
| 純字數 | 零依賴 | 與 token 不對齊（中文 1 字 ≈ 1.5-2 token），可能切句中 |
| 純 token (tiktoken) | 與 context 精確對齊 | 地端模型 tokenizer 不一定能本地拿；tiktoken 對非 OpenAI 只是近似 |
| Semantic chunking (embedding 邊界) | 話題完整性最佳 | 需 embedding model；2026 benchmark 顯示輸給 recursive |

**Token 計算三層 fallback**：
1. 模型自帶 tokenizer（若 OpenAI 相容 server 暴露 `/tokenize` endpoint，如 vLLM 有）
2. tiktoken `o200k_base` 近似（對中文比 cl100k_base 省 20-40% token）
3. 中文字數 × 1.5 作 worst-case 估算

**Overlap**：10%（2026 業界共識上限，再多收益遞減）

### 6.6 `.env.example`

```ini
# === 公司 LLM (OpenAI 相容) ===
OPENAI_API_KEY=sk-xxx
OPENAI_API_BASE=https://internal-llm.company.com/v1
OPENAI_MODEL=gpt-4o-mini-equivalent

# === ASR (faster-whisper) ===
WHISPER_MODEL=large-v3                # tiny|base|small|medium|large-v3
WHISPER_DEVICE=auto                   # auto|cpu|cuda
WHISPER_COMPUTE_TYPE=auto             # auto|int8|int8_float16|float16
WHISPER_LANGUAGE=zh
WHISPER_INITIAL_PROMPT=以下是繁體中文會議記錄，可能包含英文技術名詞如 API、Roadmap、Sprint。
WHISPER_VAD_FILTER=true               # Silero VAD 降低靜音幻覺

# === Diarization (pyannote Community-1, 可選) ===
ENABLE_DIARIZATION=false              # true 開啟，需先申請 HF token
HF_TOKEN=                             # 留空時跳過 diarization
DIARIZATION_MODEL=pyannote/speaker-diarization-community-1
ALIGNMENT_MODEL=jonatasgrosman/wav2vec2-large-xlsr-53-chinese-zh-cn

# === Transcript Correction (Stage 2.95, 可選) ===
ENABLE_PROPER_NOUN_CORRECTION=false   # true 時對 transcript 跑專有名詞 LLM 修正
GLOSSARY_FILE=script/prompts/glossary.md   # 術語表位置（人類維護）

# === Chunking / LLM ===
LLM_CHUNK_TOKENS=4000                 # 上限改用 token 計（三層 fallback 估算）
LLM_CHUNK_OVERLAP_RATIO=0.10          # 10% overlap
LLM_TEMPERATURE=0.2
LLM_MAX_RETRIES=3                     # Instructor 自動 retry 次數
LLM_TIMEOUT_SECS=180
LLM_PARALLEL_MAP=3                    # 同時跑幾塊 map (保護公司 LLM)

# === I/O ===
OUT_DIR=out
LOG_DIR=log
LOG_LEVEL=INFO                        # DEBUG|INFO|WARN|ERROR
KEEP_INTERMEDIATE=true
```

### 6.7 Decision Rationale — Config 管理

| 方案 | 優點 | 缺點 |
|---|---|---|
| **pydantic-settings**（採用） | Pydantic schema 驗證；型別安全；缺值錯誤訊息清楚；底層仍用 dotenv | 需 Pydantic v2（已有） |
| 純 python-dotenv | 簡單載入 | 無驗證、無型別 |
| dynaconf | 多來源（toml/yaml/vault） | 對 CLI 工具過度設計 |

**選擇理由**：需求明確要「.env 驗證 + 錯誤訊息」，正是 pydantic-settings 設計目標；缺 API key 直接告訴使用者哪欄缺。

### 6.8 `requirements.txt`

```
# Core LLM
openai>=1.40.0,<2.0
instructor>=1.5.0,<2.0
pydantic>=2.5.0,<3.0
pydantic-settings>=2.4.0,<3.0

# ASR + Diarization
faster-whisper>=1.0.0,<2.0
whisperx>=3.1.0,<4.0          # 包含 wav2vec2 forced alignment
pyannote.audio>=3.3.0,<4.0    # Community-1 需 3.3+

# Output
openpyxl>=3.1.0,<4.0

# Infra
jinja2>=3.1.0,<4.0
typer>=0.12.0,<1.0
stamina>=24.0.0               # retry (取代 tenacity)
python-dotenv>=1.0.0          # pydantic-settings 內部使用
```

**系統依賴 (README 說明)**：
- `ffmpeg` (在 PATH 上)
- 第一次跑會自動下載：
  - Whisper large-v3 (~3 GB)
  - pyannote Community-1 (~500 MB)
  - wav2vec2 中文 (~1.2 GB)
- 無網路時改用內網 mirror 或預打包 cache

### 6.9 Decision Rationale — Retry library

| 方案 | 優點 | 缺點 |
|---|---|---|
| **stamina**（採用） | tenacity 的 opinionated wrapper（Hynek 作品）；預設安全（jitter + time cap）；少寫樣板；async/類型保留/Prometheus 整合 | 較新（但 24.x 已 Production/Stable） |
| tenacity | 最廣泛使用；高度可組合 | 預設不安全（無 jitter、無時間上限）易誤用 |
| OpenAI SDK 內建 | 零依賴 | 僅 HTTP 層；非 SDK 路徑無法用 |

**選擇理由**：Instructor 已處理 LLM 層 retry；stamina 用於非 LLM 路徑（檔案 I/O、ffmpeg、HF 下載），預設加 jitter/time cap 不易誤用。

### 6.10 Logging

`log/run_YYYYMMDD-HHMMSS.log` 每次執行一檔，結構化 key=value：

```
[2026-05-06 14:23:15] INFO  pipeline.start file=2026Q2_planning.mp4
[2026-05-06 14:23:16] INFO  stage=media duration=1.2s output=audio.wav
[2026-05-06 14:23:16] INFO  stage=transcribe model=large-v3 device=cuda
[2026-05-06 14:31:42] INFO  stage=transcribe duration=486s segments=1247 chars=58932
[2026-05-06 14:31:42] INFO  stage=diarize enabled=true
[2026-05-06 14:34:18] INFO  stage=diarize duration=156s speakers=3
[2026-05-06 14:34:18] INFO  stage=chunk strategy=recursive chunks=11 avg_tokens=3850
[2026-05-06 14:34:18] INFO  stage=minutes_map parallel=3 chunks=11
[2026-05-06 14:34:24] INFO  map chunk=0 duration=6.1s tokens_in=4203 tokens_out=842 mode=json_schema
[2026-05-06 14:34:26] WARN  map chunk=2 instructor_retry=1 reason=validation_error
[2026-05-06 14:34:51] INFO  stage=minutes_map duration=33s tokens_in_total=46233 tokens_out_total=8910
[2026-05-06 14:35:07] INFO  stage=minutes_reduce duration=16s
[2026-05-06 14:35:24] INFO  stage=review duration=17s items=14 warns=2 errors=0
[2026-05-06 14:35:24] INFO  pipeline.done elapsed=729s out=out/2026Q2_planning/
```

### 6.11 錯誤處理 / 重試

| 失敗類型 | 處理 |
|---|---|
| ffmpeg 不存在 | 啟動時 `shutil.which("ffmpeg")` 檢查，缺 → fail fast |
| Whisper 下載失敗 | 印 mirror 設定指引；不重試 |
| HF token 缺/無效（diarization 開時） | fail fast 引導去申請；自動降級為 ENABLE_DIARIZATION=false 並印警告 |
| LLM 429 / 超時 / 連線錯 | Instructor 自動 retry；非 LLM 路徑用 stamina |
| LLM JSON 不合法 | Instructor 自動 repair retry，最多 `LLM_MAX_RETRIES` 次 |
| Reduce 後仍超 size | 自動切換樹狀 reduce |
| 整段 pipeline crash | intermediate/ 保留已完成階段檔案，下次跑同檔自動跳過已存在階段 (`--force` 強制重跑) |

### 6.12 Testing

**Unit (pytest)**:
- `chunker.py`：給定假 transcript，驗 chunks 數、token 上限、overlap、句子完整
- `excel_writer.py`：golden file 比對
- `markdown_writer.py`：snapshot test
- Pydantic schema：壞 JSON 驗 raise
- Instructor mock：用 instructor 的 test mode 驗 retry 行為

**Integration**:
- 30 秒中文範例 wav (`tests/fixtures/`)
- LLM 用 mock：fixture JSON response 取代真實呼叫
- Diarization 跑 + 不跑兩個 path 都驗

**Smoke** (手動):
- `python script/main.py tests/fixtures/short.wav` 用真實 LLM

### 6.13 CLI (typer)

```bash
# 基本
python script/main.py path/to/meeting.mp4

# 指定輸出資料夾名
python script/main.py meeting.mp4 --name 2026Q2_planning

# 開啟 diarization (overrides .env)
python script/main.py meeting.mp4 --diarize

# 強制重跑
python script/main.py meeting.mp4 --force

# 跳過某階段 (例如 transcript 已手動修過)
python script/main.py meeting.mp4 --skip-transcribe

# Verbose
python script/main.py meeting.mp4 -v
```

### 6.14 Decision Rationale — CLI Framework

| 方案 | 優點 | 缺點 |
|---|---|---|
| **typer**（採用） | type hints 自動轉 flag；底層即 click；最少樣板；自動 help/補全 | 多一個依賴 |
| argparse | 內建零依賴 | 樣板多 |
| click | 成熟、生態大 | 比 typer 多樣板 |
| fire | API 最少 | 過於 magic、不適合正式工具 |

**選擇理由**：5+ flag 場景下 typer 樣板最少；type hint 重複利用 (Pydantic config 也用 type hint)。

---

## 7. 範圍外 (Out of Scope)

明確不做（避免 scope creep）：

- **跨會議講者識別**：本期 SPEAKER_1, SPEAKER_2... 是「本場會議內」唯一。要跨會議識別需 voice embedding 比對庫。
- **多語言混說 (code-switching)**：預設中文為主，英文術語靠 `WHISPER_INITIAL_PROMPT` 輔助。
- **Web UI**：本期 CLI only。
- **Email / Slack 推送**：本期不做。
- **歷史會議資料庫 / 跨會議搜尋**：本期單檔處理。
- **RAG 問答**：本期只產記錄，不支援「問會議裡 X 講了什麼」。
- **Voice Enrollment（真名對應）**：v1 只用 SPEAKER_1/2/N 通用標籤。需要真名對應需要錄樣本、跨會議 voice embedding DB、UI 維護介面，是另一個獨立子系統。
- **替換 ASR 引擎為 FireRedASR2-LLM**：FireRed 在中文 benchmark 較強（AISHELL-1 CER ~2.2 vs whisper ~4-5），v1 先用 faster-whisper（已驗證 + 容易裝）。若 v1 transcript 品質不夠，可在 v2 把 ASR 抽 backend interface 並加 FireRed。
- **付費 pyannote Precision-2**：Community-1 已是開源 SOTA 且商用 OK；若 DER 不夠，再考慮升級付費版。

---

## 8. 風險與假設

| 項目 | 假設 / 風險 | 緩解 |
|---|---|---|
| 公司 LLM context size 未知 | 用 `LLM_CHUNK_TOKENS` 可調 | 預設 4000 token；實際跑了再調 |
| 公司 LLM 不支援 strict mode | Instructor 自動 fallback | 偵測無 strict 時自動退 json_object + repair |
| Whisper 模型 ~3GB 下載慢 | 第一次需要外網 | README 說明改用內網 mirror 或預先放 cache |
| pyannote HF token 申請門檻 | 需 HF 帳號 + 同意 gated terms | (1) 預設 ENABLE_DIARIZATION=false，不開不需 token；(2) README 寫清楚申請步驟；(3) 可預打包 cache 到 image |
| GPU 不可用，CPU 跑 large-v3 太慢 | 3 小時會議可能 30+ 分 | `WHISPER_MODEL=medium` 妥協；diarization 對 CPU 更慢，建議 GPU |
| LLM 回 JSON 結構性錯誤頻繁 | Instructor retry 仍可能失敗 | 最終 fail 該塊；intermediate 保留 raw response 給人工修 |
| glossary.md 沒維護 / 過時 | corrector 收益會掉 | (1) glossary 為空時 corrector 自動跳過該段（無詞可修）；(2) README 說明 glossary 是「人維護的活檔案」 |
| corrector 過度修正改錯字 | 保守 prompt 仍可能誤改 | (1) `correction_diff.json` 全部留檔可審；(2) `transcript.raw.md` 保留原檔可比對；(3) 預設關閉 |

---

## 9. 已決定 / 待確認

**已決定**：

| 類別 | 項目 | 決定 |
|---|---|---|
| ASR | 引擎 | faster-whisper |
| ASR | 模型 | large-v3 + INT8 量化 + vad_filter |
| ASR | 影片轉檔 | ffmpeg subprocess |
| ASR | 主語言 | 中文 (英文術語靠 initial_prompt) |
| Diarization | 啟用 | 預設關，可選開（`ENABLE_DIARIZATION`） |
| Diarization | 方案 | WhisperX + pyannote Community-1 |
| Transcript Correction | 啟用 | 預設關，可選開（`ENABLE_PROPER_NOUN_CORRECTION`） |
| Transcript Correction | 位置 | Stage 2.95，chunker 之前；保守原則只修 glossary 詞彙 |
| Transcript Correction | 術語表 | `script/prompts/glossary.md` 人類維護 |
| LLM | 結構化輸出 | Instructor library |
| LLM | 摘要策略 | map-reduce + 自動樹狀升級 |
| LLM | 分塊 | recursive (句子優先 + token 三層 fallback) |
| LLM | Parallel map | 預設 3 並行 |
| Output | Excel lib | openpyxl |
| Output | Excel 結構 | 2 sheets：Sheet1 (結論+Actions) + Sheet2 (Review摘要) |
| Output | Action 欄位 | 任務 / 負責人 / 期限 / 優先度 / 來源原句 / 時間戳 / 發言者 / LLM判斷依據 / Review |
| Output | Reviewer 輸出 | Excel 內 Review 欄 + Sheet2 摘要 + review_report.md |
| Output | [LLM推論] | 資料層 is_inferred 旗標 + 呈現層前綴/黃底 |
| Tooling | Prompt 管理 | Jinja2 + .j2 |
| Tooling | Config | pydantic-settings |
| Tooling | CLI | typer |
| Tooling | Retry | stamina (LLM 用 Instructor 內建) |
| Pipeline | Stage cache | 已有 intermediate 跳過，`--force` 重跑 |

**待確認（spec review 階段可調）**：

- `LLM_CHUNK_TOKENS` 預設 4000（保守）
- `WHISPER_MODEL` 預設 large-v3
- `LLM_PARALLEL_MAP` 預設 3
- `LLM_CHUNK_OVERLAP_RATIO` 預設 0.10

---

## 10. 調研來源 (2026-05 web research)

### ASR / Diarization
- [Whisper large-v3-turbo on HF](https://huggingface.co/openai/whisper-large-v3-turbo)
- [SYSTRAN/faster-whisper GitHub](https://github.com/SYSTRAN/faster-whisper)
- [m-bain/whisperX GitHub](https://github.com/m-bain/whisperX)
- [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1)
- [Community-1 release notes](https://www.pyannote.ai/blog/community-1)
- [Best Speaker Diarization Models Compared 2026 (BrassTranscripts)](https://brasstranscripts.com/blog/speaker-diarization-models-comparison)
- [AssemblyAI Top Speaker Diarization Libraries 2026](https://www.assemblyai.com/blog/top-speaker-diarization-libraries-and-apis)
- [Northflank Best Open Source STT 2026](https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks)

### LLM Long-text + Structured Output
- [JSON Mode vs Function Calling vs Structured Output 2026](https://www.buildmvpfast.com/blog/structured-output-llm-json-mode-function-calling-production-guide-2026)
- [Instructor library](https://python.useinstructor.com/)
- [vLLM Structured Outputs docs](https://docs.vllm.ai/en/latest/features/structured_outputs/)
- [Anthropic Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval)
- [RAPTOR (arXiv 2401.18059)](https://arxiv.org/abs/2401.18059)
- [Best Chunking Strategies for RAG (Firecrawl 2026)](https://www.firecrawl.dev/blog/best-chunking-strategies-rag)
- [LLM Summarization Strategies (Galileo.ai)](https://galileo.ai/blog/llm-summarization-strategies)
- [Working with CJK text in GenAI pipelines](https://tonybaloney.github.io/posts/cjk-chinese-japanese-korean-llm-ai-best-practices.html)

### Python Tooling
- [openpyxl Performance docs](https://openpyxl.readthedocs.io/en/3.1/performance.html)
- [stamina GitHub (hynek)](https://github.com/hynek/stamina)
- [Pydantic Settings docs](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [Typer Alternatives & Comparisons](https://typer.tiangolo.com/alternatives/)
- [Jinja2 prompting guide](https://medium.com/@alecgg27895/jinja2-prompting-a-guide-on-using-jinja2-templates-for-prompt-management-in-genai-applications-e36e5c1243cf)
