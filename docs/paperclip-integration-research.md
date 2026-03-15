# Paperclip AI x Whale-Rader 整合研究報告

> 研究日期：2026-03-15

## 1. Paperclip AI 是什麼？

[Paperclip](https://github.com/paperclipai/paperclip) 是一個開源的 AI 代理協調平台（control plane），專為「零人力公司」設計。它不是一個 agent framework，而是一個**管理與協調多個 AI agent 的控制面板**。

### 核心特性

| 功能 | 說明 |
|------|------|
| **組織架構** | 定義 CEO、CTO、工程師等角色，每個角色由一個 AI agent 擔任 |
| **目標管理** | 任務帶有完整目標鏈（goal ancestry），agent 始終理解「為什麼」|
| **預算控制** | 80% 軟警告，100% 自動暫停，Board 可覆蓋 |
| **治理機制** | 審批閘門、配置版本控制、回滾能力 |
| **心跳排程** | Agent 不持續運行，而是在心跳窗口中喚醒執行 |
| **多公司隔離** | 單一部署可運行多家「公司」，資料完全隔離 |

### 技術棧

- **後端**: Node.js + TypeScript
- **前端**: React UI 儀表板
- **資料庫**: 內嵌 PostgreSQL（自動建立）
- **API**: REST API，預設 `http://localhost:3100`
- **授權**: MIT License
- **GitHub**: 23K+ stars，活躍開發中（v0.3.0，2026-03-09）

---

## 2. Whale-Rader 現況

Whale-Rader 是一個 Python 寫的金融鯨魚雷達系統，包含 **5 個引擎 + 1 個互動機器人**：

| 引擎 | 功能 | 檔案 |
|------|------|------|
| Engine 1 | Form 4 內線買入警報 | `whale.py` |
| Engine 2 | Form 144 內線賣出篩選 | `form144.py` |
| Engine 3 | SC 13D/G 機構持股雷達 | `institutional.py` |
| Engine 4 | 8-K 事件 AI 分析 | `ai_analyst.py` |
| Engine 5 | 每日投資組合報告 | `daily_report.py` |
| 秘書機器人 | Telegram 互動 + 排程 | `secretary/` |

**現有 AI 能力**: Gemini 3.1 Pro（分析、篩選、報告）
**排程方式**: GitHub Actions（每 5 分鐘 cron）+ APScheduler

---

## 3. 整合可行性分析

### 3.1 Paperclip 如何連接外部 Agent？

Paperclip 透過 **Adapter** 連接 agent，支援兩種模式：

1. **Run a command** — 執行 shell 命令 / Python 腳本，追蹤執行狀態
2. **HTTP Webhook** — 發送 API 請求喚醒外部 agent（fire-and-forget）

> 最低合約：**只要可被呼叫（be callable）即可**

這代表 whale-rader 的每個 Python 引擎都可以直接作為 Paperclip agent 註冊。

### 3.2 整合架構設想

> **Update (2026-03-15)**: 此扁平架構已被階層式 C-suite 模型取代。
> 新架構定義了 Secretary (C.C.)、CFO (Hayek)、CIO、CHO 四個核心角色。
> 詳見 [組織架構文件](paperclip-org-architecture.md)。

<details>
<summary>初始概念（已取代）</summary>

```
┌─────────────────────────────────────────────┐
│              Paperclip 控制面板               │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐ │
│  │ 預算管理  │ │ 目標追蹤  │ │ 治理 & 審批  │ │
│  └──────────┘ └──────────┘ └──────────────┘ │
│                    │                         │
│           Heartbeat 心跳排程                  │
│      ┌─────┬──────┼──────┬──────┐           │
│      ▼     ▼      ▼      ▼      ▼           │
│   ┌─────┐┌─────┐┌─────┐┌─────┐┌─────┐      │
│   │Whale││F144 ││SC13 ││ 8-K ││Daily│      │
│   │Agent││Agent││Agent││Agent││Rpt  │      │
│   └──┬──┘└──┬──┘└──┬──┘└──┬──┘└──┬──┘      │
└──────┼──────┼──────┼──────┼──────┼──────────┘
       ▼      ▼      ▼      ▼      ▼
  ┌────────────────────────────────────┐
  │     Whale-Rader Python Engines     │
  │  whale.py │ form144.py │ ...       │
  │          Gemini AI + SEC APIs      │
  │          Supabase + Telegram       │
  └────────────────────────────────────┘
```

</details>

### 3.3 具體整合方式

#### 方案 A：Shell Adapter（最簡單）

每個引擎註冊為一個 Paperclip agent，使用 shell adapter：

```json
{
  "name": "whale-form4-agent",
  "adapter": "shell",
  "config": {
    "command": "python whale.py",
    "workdir": "/path/to/whale-rader"
  },
  "role": "SEC Filing Analyst",
  "heartbeat_interval": "5m"
}
```

**優點**: 零改動，現有程式碼直接可用
**缺點**: 單向通訊，Paperclip 只知道成功/失敗

#### 方案 B：HTTP Webhook Adapter（推薦）

為 whale-rader 加一層薄 HTTP 層（Flask/FastAPI），讓 Paperclip 透過 webhook 呼叫：

```python
# webhook_server.py
from fastapi import FastAPI
app = FastAPI()

@app.post("/heartbeat/form4")
async def run_form4(payload: dict):
    """Paperclip heartbeat → 執行 Form 4 掃描"""
    import whale
    result = whale.main()
    return {"status": "ok", "alerts_sent": result}

@app.post("/heartbeat/form144")
async def run_form144(payload: dict):
    import form144
    result = form144.main()
    return {"status": "ok", "alerts_sent": result}
```

**優點**: 雙向通訊，可回傳執行結果、成本、狀態
**缺點**: 需要新增一個輕量 API 層

#### 方案 C：C.C. 秘書作為 Paperclip CEO Agent

把 C.C. 秘書機器人提升為 Paperclip 公司的「CEO」，由它協調其他引擎 agent：

```
C.C. (CEO Agent)
├── Form 4 Analyst (whale.py)
├── Form 144 Screener (form144.py)
├── Institutional Radar (institutional.py)
├── 8-K Analyst (ai_analyst.py)
├── Hayek CFO (daily_report.py)
└── Calendar Secretary (calendar_service.py)
```

**優點**: 最能發揮 Paperclip 的組織架構功能
**缺點**: 需要較大改動，重新設計 agent 通訊

---

## 4. 整合能帶來什麼價值？

### 值得做的（✅）

| 價值 | 說明 |
|------|------|
| **統一儀表板** | 所有引擎的執行狀態、成功率、錯誤一目了然，不用看 GitHub Actions logs |
| **成本追蹤** | Gemini API 呼叫成本、Finnhub API 用量集中監控 |
| **智慧排程** | 取代 GitHub Actions cron，Paperclip 心跳更靈活（可動態調整頻率）|
| **目標對齊** | 引擎不只「跑 cron」，而是有明確目標：「找到高價值內線交易信號」|
| **擴展性** | 未來新增引擎（如選擇權異常、暗池交易）只需註冊新 agent |
| **治理** | 敏感操作（如大額交易建議）可設審批閘門 |

### 可能不值得的（⚠️）

| 疑慮 | 說明 |
|------|------|
| **過度工程** | whale-rader 目前只有 5 個引擎，GitHub Actions cron 已夠用 |
| **增加部署複雜度** | 需要額外跑一個 Node.js + PostgreSQL 服務 |
| **維護成本** | Paperclip 是很新的專案（2026 年初），API 可能不穩定 |
| **團隊規模** | 如果只有 1-2 人在用，Paperclip 的「公司」概念有點殺雞用牛刀 |

---

## 5. 建議

### 短期（低成本嘗試）

1. **先用 Shell Adapter 試水** — 把 `whale.py` 註冊為一個 Paperclip agent，跑幾天看看儀表板體驗
2. **不移除 GitHub Actions** — 保留現有排程作為備份
3. **評估監控價值** — 如果統一儀表板確實比看 GitHub Actions 方便，再深入整合

### 中期（如果短期體驗好）

4. **加 FastAPI webhook 層** — 讓所有引擎支援雙向通訊
5. **成本追蹤整合** — 把 Gemini API 費用回報給 Paperclip
6. **用 Paperclip 目標系統** — 設定「每日至少發現 N 個高價值信號」之類的 KPI

### 長期（全面整合）

7. **C.C. 作為 CEO Agent** — 由 C.C. 根據市場狀況動態調度各引擎
8. **新增更多 agent** — 如技術分析 agent、新聞情緒 agent、選擇權異常 agent
9. **Clipmart** — 等 Paperclip 的 Clipmart 上線後，可以把 whale-rader 打包成可分享的「公司模板」

---

## 6. 結論

**整合可行性：高**。Paperclip 的 adapter 架構天然支援 Python 腳本，whale-rader 的每個引擎都可以直接作為 agent 註冊，**零改動即可開始試用**。

**是否值得：取決於規模**。如果你計劃：
- 擴展更多引擎/資料源 → **值得**，Paperclip 提供了很好的擴展框架
- 維持現有 5 引擎規模 → **暫不急需**，但統一監控仍有價值

**建議**：先用 Shell Adapter 做一個最小可行整合（30 分鐘內完成），體驗後再決定是否深入。

---

## 附錄 A：Paperclip 心跳協議（9 步驟）

Agent 在每次心跳中執行以下流程：

1. **身份驗證** — `GET /api/agents/me`
2. **審批跟進** — 檢查待處理的審批
3. **取得任務** — 取得任務收件匣
4. **選擇工作** — 優先 in_progress > todo，跳過 blocked
5. **原子簽出** — `POST /api/issues/{id}/checkout`（防止重複工作，409 Conflict）
6. **理解上下文** — 讀取 issue 詳情 + 留言
7. **執行工作** — agent 特定邏輯（如跑 `whale.py`）
8. **更新狀態** — `PATCH /api/issues/{id}`
9. **委派子任務** — 視需要建立 subtask 給下屬 agent

## 附錄 B：Paperclip REST API 重要端點

| 端點 | 用途 |
|------|------|
| `GET /api/agents/me` | Agent 身份 |
| `GET /api/companies/{id}/issues?assigneeAgentId={id}&status=...` | 任務收件匣 |
| `POST /api/issues/{id}/checkout` | 原子任務簽出 |
| `PATCH /api/issues/{id}` | 更新任務狀態 |
| `POST /api/companies/{id}/issues` | 建立子任務 / 委派 |
| `GET /api/approvals/{id}` | 審批管理 |
| `GET /api/issues/{id}/comments` | 執行緒式溝通 |
| `GET /api/skills/index` | 技能注入 |
| `GET /api/health` | 健康檢查 |

## 附錄 C：支援的 Adapter 列表

| Adapter | LLM 供應商 | 備註 |
|---------|-----------|------|
| Claude Code | Anthropic | 內建 |
| Codex | OpenAI | 內建 |
| **Gemini CLI** | **Google Gemini** | v0.3.1 新增，支援 API key 偵測 |
| Cursor | 多種 | v0.3.0 新增 |
| OpenCode | 多種 | v0.3.0 新增 |
| Pi | 本地 RPC | v0.3.0 新增 |
| OpenClaw | 多種 | SSE 串流 |
| Hermes (第三方) | Anthropic/OpenAI/Google | NousResearch 維護 |
| **Shell / HTTP** | **任意** | **whale-rader 可用此方式整合** |

## 附錄 D：快速啟動指令

```bash
# 安裝 Paperclip（自動建立 PostgreSQL）
npx paperclipai onboard --yes

# 或手動安裝
git clone https://github.com/paperclipai/paperclip.git
cd paperclip
pnpm install && pnpm dev
# API 啟動於 http://localhost:3100
```

---

## 參考來源

- [paperclipai/paperclip - GitHub](https://github.com/paperclipai/paperclip)
- [Paperclip 官網](https://paperclip.ing/)
- [Paperclip 產品文件](https://github.com/paperclipai/paperclip/blob/master/doc/PRODUCT.md)
- [Paperclip AGENTS.md](https://github.com/paperclipai/paperclip/blob/master/AGENTS.md)
- [Paperclip Core Concepts](https://github.com/paperclipai/paperclip/blob/master/docs/start/core-concepts.md)
- [Heartbeat Protocol Guide](https://github.com/paperclipai/paperclip/blob/master/docs/guides/agent-developer/heartbeat-protocol.md)
- [Developer Documentation](https://github.com/paperclipai/paperclip/blob/master/doc/DEVELOPING.md)
- [eWeek: Meet Paperclip](https://www.eweek.com/news/meet-paperclip-openclaw-ai-company-tool/)
- [Flowtivity: Zero-Human Companies](https://flowtivity.ai/blog/zero-human-company-paperclip-ai-agent-orchestration/)
- [Paperclip Releases](https://github.com/paperclipai/paperclip/releases)
