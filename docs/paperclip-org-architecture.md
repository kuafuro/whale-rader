# Whale-Rader × Paperclip AI 組織架構

> 版本：v1.0 | 日期：2026-03-15
> 基於 [整合研究報告](paperclip-integration-research.md) 設計

---

## 1. 組織圖

```
                          ┌──────────────┐
                          │    USER      │
                          │   (Board)    │
                          └──────┬───────┘
                                 │ direct report
                        ┌────────┴────────┐
                        │   C.C. 秘書      │
                        │  (Secretary)     │
                        │  全域閱讀權       │
                        │  Telegram 介面   │
                        └────────┬────────┘
                                 │ reads all agents
              ┌──────────────────┼──────────────────┐
              │                  │                  │
       ┌──────┴──────┐   ┌──────┴──────┐   ┌──────┴──────┐
       │  CFO Hayek  │   │     CIO     │   │     CHO     │
       │    財務長    │   │    資訊長    │   │    人資長    │
       └──────┬──────┘   └─────────────┘   └─────────────┘
              │
       ┌──────┴──────┐
       │ SEC Monitor │
       │  (子 Agent)  │
       ├─────────────┤
       │ whale.py    │
       │ form144.py  │
       │institutional│
       │ ai_analyst  │
       └─────────────┘
```

**層級說明**：
- **Board (User)** — 最高決策者，透過 Telegram 與 C.C. 互動
- **Secretary (C.C.)** — 直接向 Board 匯報，擁有全域閱讀權，是唯一的用戶介面
- **C-Suite (CFO / CIO / CHO)** — 三個平行高管，各司其職，C.C. 可讀取其所有數據
- **SEC Monitor** — CFO 的子 Agent，負責 SEC 申報即時監控

---

## 2. 角色總覽

| 角色 | 代號 | 現有元件 | Adapter 類型 | 心跳頻率 |
|------|------|----------|-------------|---------|
| Secretary | C.C. | `secretary/` (15 tools) | 長駐程序 (Railway polling) | 僅狀態回報 |
| CFO | Hayek | `daily_report.py` + `portfolio_store.py` | HTTP Webhook | 每日 2 次 |
| SEC Monitor | — | `whale.py`, `form144.py`, `institutional.py`, `ai_analyst.py` | Shell Adapter | 每 5 分鐘 |
| CIO | 待命名 | 新建 `cio_agent.py` | Shell Adapter | 每 6 小時 |
| CHO | 待命名 | 新建 `cho_agent.py` | Shell Adapter | 每日 1 次 |

---

## 3. 角色詳細定義

### 3.1 Secretary — C.C.（秘書）

> 直接向 Board 匯報 | 全域閱讀權 | 唯一用戶介面

**身份**：《Code Geass》不死魔女，冷靜淡漠略帶諷刺，繁體中文回覆

**運行方式**：Telegram long polling，長駐於 Railway/Docker，非心跳觸發

**現有 15 個工具**：

| 工具 | 功能 |
|------|------|
| `get_schedule` | 查詢 Google Calendar 日程 |
| `add_event` | 新增行事曆事件 |
| `update_event` | 修改事件 |
| `delete_event` | 刪除事件 |
| `add_task` | 新增待辦 |
| `list_tasks` | 列出待辦 |
| `complete_task` | 完成待辦 |
| `check_team_status` | 查 GitHub Actions 狀態 + 今日警報數 |
| `get_latest_alerts` | 從 Supabase 取最新警報記錄 |
| `get_current_datetime` | 取得 HKT 時間 |
| `get_my_settings` | 查看用戶設定 |
| `set_display_name` | 設定顯示名稱 |
| `list_portfolio` | 查看 eToro 持倉 |
| `upsert_holding` | 新增/更新持倉 |
| `remove_holding` | 移除持倉 |

**現有數據存取**：
- Google Calendar API（per-user OAuth token）
- Supabase：`whale_alerts`、`portfolio_holdings`、`secretary_tasks`、`member_settings`
- GitHub API：查 "5-Minute Whale Alert" + "Daily Portfolio Report" 兩個 workflow
- Telegram Bot API

**自動簡報**（HKT 08:00 + 21:00）：
- 日期與星期
- 今日行事曆
- 待辦事項
- 團隊狀態（GitHub Actions + 今日警報統計）

**新架構中的擴展**：
- 新增 Paperclip API 查詢：`GET /api/companies/{id}/issues`（無 assignee 過濾 = 全域讀取）
- `check_team_status` 擴展為查詢所有 Paperclip agents 狀態
- 簡報加入 CIO 系統健康摘要 + CHO 績效摘要
- 新增能力：透過 Paperclip issue creation 向其他 agent 下達指令

**Paperclip 配置**：

```json
{
  "name": "secretary-cc",
  "role": "Secretary — Board Direct Report",
  "adapter": "process",
  "config": {
    "note": "Long-running Telegram bot, registered for identity/visibility only"
  },
  "reports_to": null,
  "permissions": ["read:all_issues", "read:all_agents", "create:issues"]
}
```

---

### 3.2 CFO — Hayek（財務長）

> 管理全部財務 | 股票投資組合 | Agent 支出監控 | SEC 監控上級

**身份**：以海耶克命名的 AI 財務長，基於 Gemini 3.1 Pro + Google Search

**現有元件**：
- `daily_report.py` — 核心：eToro 持倉同步、Finnhub 報價、Gemini AI 分析（含 Google Search）
- `secretary/services/portfolio_store.py` — 持倉數據（Supabase `portfolio_holdings`）

**職責清單**：

| 職責 | 說明 | 現有/新增 |
|------|------|----------|
| 投資組合報告 | 每日 pre/post-market 分析，含持倉新聞、事件預告、操作建議 | 現有 |
| eToro 持倉同步 | 從 eToro API 取即時倉位，回退到 Supabase | 現有 |
| AI 財務分析 | Gemini + Google Search 生成技術/基本面分析 | 現有 |
| SEC 監控管理 | 管理 SEC Monitor 子 Agent，整合警報到報告中 | 新增 |
| Agent 支出追蹤 | 讀取 Paperclip cost API，追蹤各 agent 的 Gemini API 費用 | 新增 |
| 預算管理 | 設定 Paperclip 月度預算上限，80% 警告、100% 暫停 | 新增 |

**心跳排程**：
- HKT 07:00（UTC 23:00 前日）— 美股收盤後報告
- HKT 21:00（UTC 13:00）— 美股開盤前報告
- 跳過週末和 NYSE 假日

**數據存取**：
- **擁有**：`portfolio_holdings` 表、eToro API
- **讀取**：`whale_alerts` 表（整合 SEC Monitor 結果）、Finnhub API
- **寫入**：Telegram 私人頻道（`TELEGRAM_CHAT_ID_PRIVATE`）

**Paperclip 配置**：

```json
{
  "name": "cfo-hayek",
  "role": "Chief Financial Officer",
  "adapter": "shell",
  "config": {
    "command": "python daily_report.py",
    "workdir": "/app"
  },
  "heartbeat_interval": "12h",
  "budget": {
    "monthly_limit_usd": 15,
    "alert_threshold_pct": 80
  },
  "reports_to": null,
  "subordinates": ["sec-monitor"]
}
```

---

### 3.3 SEC Monitor（SEC 申報監控 — CFO 子 Agent）

> CFO 下屬 | 即時監控 SEC 內線交易申報 | 4 個引擎合一

**為什麼合併為一個子 Agent？**
- 4 個引擎共用同一個 GitHub Actions workflow（`run.yml`）
- 共用同一個 Supabase 表（`whale_alerts`）
- 共用同一個 Telegram 頻道（`TELEGRAM_CHAT_ID_WHALE`）
- 拆成 4 個 agent 只會增加 Paperclip 心跳開銷，無實質收益

**包含的引擎**：

| 引擎 | 檔案 | 監控內容 | AI 功能 |
|------|------|----------|---------|
| Form 4 | `whale.py` | 內線人買賣（S&P 500，≥$500K） | 意圖分析（首次建倉/全部清倉） |
| Form 144 | `form144.py` | 內線預告賣出（市值 >$50 億） | Gemini 二層篩選：常規 vs 異常 |
| SC 13D/G | `institutional.py` | 機構持股變動（>5%） | Gemini 機構背景調查 + 威脅評估 |
| 8-K | `ai_analyst.py` | 重大公司事件 | Gemini 摘要 + 情緒分析 |

**心跳排程**：每 5 分鐘，週一至五 UTC 13:00-21:00（= ET 09:00-17:00）

**向 CFO 回報**：每次心跳後 issue comment：
```json
{
  "engines_run": 4,
  "alerts_generated": 3,
  "tickers": ["AAPL", "TSLA", "NVDA"],
  "failures": []
}
```

**Paperclip 配置**：

```json
{
  "name": "sec-monitor",
  "role": "SEC Filing Monitor",
  "adapter": "shell",
  "config": {
    "command": "python run_all_engines.py",
    "workdir": "/app",
    "timeout_seconds": 300
  },
  "heartbeat_interval": "5m",
  "heartbeat_window": {
    "days": "mon-fri",
    "hours": "13:00-21:00 UTC"
  },
  "reports_to": "cfo-hayek",
  "budget": {
    "monthly_limit_usd": 8,
    "alert_threshold_pct": 80
  }
}
```

---

### 3.4 CIO — 資訊長（新增）

> IT 策略 | 數位轉型 | 資訊安全 | 資源管理

**核心職責**：

#### 3.4.1 戰略規劃 — IT 策略與業務目標對齊

| 任務 | 具體行動 | 數據來源 |
|------|----------|----------|
| 技術路線評估 | 追蹤 Paperclip 版本更新，評估新功能對 whale-rader 的影響 | GitHub Releases API |
| API 策略 | 監控各 API 的可靠性和成本效益，建議替代方案 | 歷史 health logs |
| 架構建議 | 分析系統瓶頸，建議優化（如快取策略、批次處理） | system_health_logs |

#### 3.4.2 數位轉型 — 新技術優化工作流程

| 任務 | 具體行動 |
|------|----------|
| AI 模型評估 | 追蹤 Gemini 新版本，評估升級收益 |
| 自動化改進 | 識別手動流程，建議自動化方案 |
| 雲端優化 | 評估 Railway vs 其他平台的成本效益 |

#### 3.4.3 資訊安全 — 防禦網路威脅

| 任務 | 具體行動 | 頻率 |
|------|----------|------|
| 環境變數稽核 | 檢查所有必要 secrets 是否設定（非 null） | 每 6 小時 |
| API Key 暴露掃描 | 掃描最近 commits 有無洩漏 API key | 每日 |
| 依賴漏洞 | 檢查 Python 依賴是否有已知 CVE | 每週 |
| Supabase RLS | 驗證 Row Level Security 政策是否啟用 | 每日 |

#### 3.4.4 資源管理 — IT 預算與基礎設施

| 任務 | 具體行動 | 數據來源 |
|------|----------|----------|
| GitHub Actions 用量 | 追蹤每月消耗分鐘數 | GitHub Billing API |
| Supabase 用量 | 監控列數、儲存空間、API 請求數 | Supabase Management API |
| API 限額監控 | Finnhub（60 req/min）、SEC EDGAR（10 req/sec）、Gemini 配額 | Response Headers |
| 依賴可用性 | Ping 外部服務回應時間：SEC EDGAR, Finnhub, eToro, Supabase, Telegram | HTTP Health Check |
| 成本報告 | 匯總所有基礎設施費用，與 CFO 共享 | 多來源匯總 |

**心跳排程**：每 6 小時（00:00, 06:00, 12:00, 18:00 HKT）

**產出**：
- 寫入 Supabase `system_health_logs` 表
- 異常時建立 Paperclip `[ALERT]` issue（所有 agent 可見）

**Paperclip 配置**：

```json
{
  "name": "cio",
  "role": "Chief Information Officer",
  "adapter": "shell",
  "config": {
    "command": "python cio_agent.py",
    "workdir": "/app"
  },
  "heartbeat_interval": "6h",
  "budget": {
    "monthly_limit_usd": 3,
    "alert_threshold_pct": 80
  },
  "reports_to": null
}
```

---

### 3.5 CHO — 人資長（新增）

> 人力資源戰略 | Agent 績效管理 | 組織優化 | 企業文化

**核心職責**：

#### 3.5.1 戰略規劃 — 集團化人力資源戰略

| 任務 | 具體行動 |
|------|----------|
| 人力規劃 | 根據業務需求評估是否需要新增 agent（如 13F 季度機構持倉、proxy 投票、選擇權異常） |
| 編制管理 | 維護 agent 清單、角色描述、上下級關係 |
| 招聘計劃 | 當 gap analysis 發現監控缺口時，提出新 agent 提案 |

#### 3.5.2 人才管理 — Agent 引進、績效與培訓

| 任務 | 具體行動 | 數據來源 |
|------|----------|----------|
| 績效評分 | 每個引擎的 alerts/run 比率、成功率、覆蓋 ticker 數 | `whale_alerts` + GitHub Actions API |
| 質量評估 | 分析警報的 false-positive 率（同一 ticker 反覆觸發但股價無變動） | `whale_alerts` + Finnhub |
| 靜默偵測 | 引擎連續成功但零警報 → 可能有解析問題 | GitHub Actions + `whale_alerts` |
| 效率分析 | 各引擎平均執行時間、Gemini API token 消耗 | GitHub Actions logs |

**績效記分卡（週報）**：

```
Agent Performance Scorecard — Week of 2026-03-10
─────────────────────────────────────────────────
Agent          Runs  Success  Fail  Alerts  Tickers
─────────────────────────────────────────────────
Form 4 (whale)  300    298     2     45      28
Form 144        300    295     5     12      10
SC 13D/G        300    300     0      8       7
8-K Analyst     300    290    10     35      22
─────────────────────────────────────────────────
CFO (Hayek)      10     10     0     10       -
CIO               4      4     0      -       -
─────────────────────────────────────────────────
```

#### 3.5.3 組織變革 — 優化組織結構

| 任務 | 具體行動 |
|------|----------|
| 缺口分析 | 比對已監控 vs SEC EDGAR 全部表格類型，找出未覆蓋的重要表格 |
| 冗餘偵測 | 檢查是否有多個 agent 重複監控相同數據 |
| 重組建議 | 根據績效數據建議合併/拆分 agent |
| Gemini AI 建議 | 用 AI 分析歷史績效，生成組織優化報告 |

#### 3.5.4 企業文化 — 對齊戰略目標

| 任務 | 具體行動 |
|------|----------|
| 使命對齊 | 確保每個 agent 的目標鏈（goal ancestry）對齊公司使命：「發現高價值內線交易信號」 |
| 品質標準 | 定義各 agent 的最低績效標準（如 Form 4 每週至少 20 條有效警報） |
| 入職流程 | 為新 agent 制定標準入職檢查清單（Paperclip 註冊、Supabase 權限、Telegram 頻道） |
| 文化宣導 | 在 Paperclip skill 中注入「公司價值觀」—— 準確性 > 數量，安全 > 速度 |

**心跳排程**：每日 HKT 08:30（在早間簡報數據可用之後）

**產出**：
- 寫入 Supabase `agent_performance` 表
- 每週一建立 Paperclip 績效報告 issue
- C.C. 在每週一早間簡報中加入 CHO 週報摘要

**Paperclip 配置**：

```json
{
  "name": "cho",
  "role": "Chief Human Resources Officer",
  "adapter": "shell",
  "config": {
    "command": "python cho_agent.py",
    "workdir": "/app"
  },
  "heartbeat_interval": "24h",
  "heartbeat_window": {
    "start_time": "00:30 UTC"
  },
  "budget": {
    "monthly_limit_usd": 5,
    "alert_threshold_pct": 80
  },
  "reports_to": null
}
```

---

## 4. Agent 間通訊

所有 agent 透過 **Paperclip issues/comments** 進行非同步通訊。

### 4.1 通訊矩陣

| 發送方 | 接收方 | 通訊方式 | 內容 |
|--------|--------|----------|------|
| SEC Monitor | CFO | Issue comment | 每次掃描結果摘要 |
| CFO | C.C. (可見) | Issue comment | 每日財務報告摘要 |
| CIO | 全體 | `[ALERT]` issue | 系統異常警報 |
| CHO | Board (via C.C.) | Weekly issue | 每週績效報告 |
| User | 任何 Agent | C.C. → Paperclip issue | C.C. 轉譯用戶指令為 issue |

### 4.2 數據流圖

```
User ←── Telegram ──→ C.C. (Secretary)
                        │
                        ├── Paperclip API ──→ 讀取所有 agents 的 issues/status
                        ├── Supabase ──────→ whale_alerts, portfolio, tasks, settings
                        │
CFO (Hayek) ── Paperclip comments ──→ C.C. 可見
  │
  └── SEC Monitor ── writes ──→ Supabase whale_alerts
                   ── comments ──→ CFO 的 Paperclip issues
                   ── sends ──→ Telegram (公開警報頻道)
  │
  └── reads ──→ portfolio_holdings, eToro API, Finnhub
  └── sends ──→ Telegram (私人報告頻道)

CIO ── writes ──→ system_health_logs (Supabase)
    ── creates ──→ [ALERT] issues (Paperclip, 全體可見)
    ── reads ──→ GitHub API, Finnhub headers, Supabase stats

CHO ── writes ──→ agent_performance (Supabase)
    ── creates ──→ 每週 review issues (Paperclip)
    ── reads ──→ whale_alerts (統計), GitHub Actions (成功率)
```

### 4.3 Secretary 全域閱讀權技術實現

C.C. 的「全域閱讀權」透過兩條路徑實現：

1. **Paperclip API**：`GET /api/companies/{companyId}/issues`（不帶 `assigneeAgentId` 過濾）→ 返回所有 agent 的 issues
2. **Supabase 直連**：C.C. 已有 service key，可直接查詢 `whale_alerts`、`portfolio_holdings`、`system_health_logs`、`agent_performance` 等所有表

無需額外權限設定。

---

## 5. 新增 Supabase 表

### 5.1 `system_health_logs`（CIO 使用）

```sql
CREATE TABLE IF NOT EXISTS system_health_logs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    check_type TEXT NOT NULL,          -- 'github_actions' | 'api_rate_limit' | 'dependency_ping' | 'security_audit' | 'cost_report'
    status TEXT NOT NULL,              -- 'healthy' | 'warning' | 'critical'
    details JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_health_logs_type_time ON system_health_logs (check_type, created_at DESC);
```

### 5.2 `agent_performance`（CHO 使用）

```sql
CREATE TABLE IF NOT EXISTS agent_performance (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    agent_name TEXT NOT NULL,          -- 'form4' | 'form144' | 'sc13' | '8k' | 'cfo' | 'cio'
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    runs INTEGER DEFAULT 0,
    successes INTEGER DEFAULT 0,
    failures INTEGER DEFAULT 0,
    alerts_count INTEGER DEFAULT 0,
    unique_tickers INTEGER DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_agent_perf_name_period ON agent_performance (agent_name, period_end DESC);
```

---

## 6. 實施路線圖

### Phase 1：基礎整合（第 1-2 週）

- [ ] 安裝 Paperclip：`npx paperclipai onboard --yes`
- [ ] 註冊 CFO (Hayek) + SEC Monitor 為 Paperclip agents
- [ ] 擴展 `secretary/services/team_monitor.py`：新增 Paperclip API 查詢
- [ ] C.C. 新增 `check_paperclip_status` 工具
- [ ] 保留 GitHub Actions 作為備份

### Phase 2：CIO 上線（第 3-4 週）

- [ ] 建立 `system_health_logs` Supabase 表
- [ ] 開發 `cio_agent.py`：系統健康、API 限額、安全稽核
- [ ] 註冊 CIO 到 Paperclip
- [ ] C.C. 簡報加入 CIO 健康摘要

### Phase 3：CHO 上線（第 5-6 週）

- [ ] 建立 `agent_performance` Supabase 表
- [ ] 開發 `cho_agent.py`：績效評分、缺口分析、AI 建議
- [ ] 註冊 CHO 到 Paperclip
- [ ] C.C. 週一簡報加入 CHO 週報

### Phase 4：全面整合（第 7-8 週）

- [ ] Paperclip 心跳取代 GitHub Actions cron
- [ ] 實作 agent 間 Paperclip issue 通訊
- [ ] 啟用 Paperclip 預算控制
- [ ] C.C. 可透過 Paperclip issue 向任何 agent 下達指令
- [ ] 停用 GitHub Actions 排程（保留手動觸發）

---

## 7. 風險與注意事項

| 風險 | 等級 | 緩解措施 |
|------|------|----------|
| Paperclip API 不穩定（v0.3.x） | 🟡 中 | Phase 1-3 保留 GitHub Actions 備份 |
| C.C. 非心跳模型 | 🟢 低 | 註冊為 agent 僅供身份/可見性，執行不依賴 Paperclip |
| Gemini API 成本上升 | 🟡 中 | CIO 追蹤用量 + CFO 管理預算 + Paperclip 自動暫停 |
| 新 agent 開發時間 | 🟡 中 | CIO/CHO 可先用簡單版本，逐步增加功能 |
| 單點故障（Paperclip server） | 🟡 中 | 所有 agent 保留獨立運行能力，Paperclip 僅為協調層 |

---

## 參考

- [Paperclip 整合研究報告](paperclip-integration-research.md)
- [paperclipai/paperclip — GitHub](https://github.com/paperclipai/paperclip)
- [Paperclip Core Concepts](https://github.com/paperclipai/paperclip/blob/master/docs/start/core-concepts.md)
- [Heartbeat Protocol Guide](https://github.com/paperclipai/paperclip/blob/master/docs/guides/agent-developer/heartbeat-protocol.md)
