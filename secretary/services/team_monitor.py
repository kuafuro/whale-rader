import logging
import requests
from datetime import datetime, timezone, timedelta

import config

logger = logging.getLogger(__name__)
HKT = timezone(timedelta(hours=8))


async def get_team_status_raw() -> str:
    lines = ["<b>👥 團隊狀態報告</b>\n"]

    # CFO — Whale Radar GitHub Actions
    lines.append("<b>🐋 CFO — Whale Radar</b>")
    cfo_status = _check_github_workflow("5-Minute Whale Alert")
    lines.append(cfo_status)

    lines.append("")

    # CFO Daily Report
    lines.append("<b>📊 CFO — 每日簡報</b>")
    report_status = _check_github_workflow("Daily Portfolio Report")
    lines.append(report_status)

    lines.append("")

    # Latest alert count from Supabase
    alert_summary = _get_alert_summary()
    lines.append(alert_summary)

    return "\n".join(lines)


async def get_team_status() -> str:
    return await get_team_status_raw()


def _check_github_workflow(workflow_name: str) -> str:
    if not config.GITHUB_TOKEN or not config.WHALE_RADAR_REPO:
        return "  ⚠️ GITHUB_TOKEN 未設定，無法查詢"
    try:
        owner, repo = config.WHALE_RADAR_REPO.split("/")
        headers = {
            "Authorization": f"Bearer {config.GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json"
        }
        r = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}/actions/runs",
            headers=headers,
            params={"per_page": 5}
        )
        if r.status_code != 200:
            return f"  ⚠️ GitHub API 錯誤：{r.status_code}"

        runs = [run for run in r.json().get("workflow_runs", [])
                if run.get("name") == workflow_name]

        if not runs:
            return f"  ❓ 找不到工作流程記錄"

        latest = runs[0]
        status = latest.get("conclusion", latest.get("status", "unknown"))
        run_at = latest.get("updated_at", "")
        if run_at:
            dt = datetime.fromisoformat(run_at.replace("Z", "+00:00")).astimezone(HKT)
            run_at = dt.strftime("%m/%d %H:%M HKT")

        icon = "✅" if status == "success" else ("❌" if status == "failure" else "🔄")
        return f"  {icon} 狀態：{status}（最後執行：{run_at}）"

    except Exception as e:
        return f"  ⚠️ 查詢失敗：{e}"


def _get_alert_summary() -> str:
    if not config.SUPABASE_URL or not config.SUPABASE_KEY:
        return "⚠️ Supabase 未設定"
    try:
        headers = {"apikey": config.SUPABASE_KEY, "Authorization": f"Bearer {config.SUPABASE_KEY}"}
        today = datetime.now(HKT).strftime("%Y-%m-%d")
        r = requests.get(
            f"{config.SUPABASE_URL}/rest/v1/whale_alerts",
            headers=headers,
            params={"created_at": f"gte.{today}T00:00:00+08:00", "select": "source,ticker"}
        )
        if r.status_code != 200:
            return f"⚠️ Supabase 查詢失敗：{r.status_code}"
        data = r.json()
        if not data:
            return f"<b>📡 今日警報：</b>暫無"
        count = len(data)
        tickers = list({a["ticker"] for a in data if a.get("ticker") and a["ticker"] != "N/A"})[:5]
        return f"<b>📡 今日警報：</b>{count} 條（涉及：{', '.join(tickers) if tickers else '無'}）"
    except Exception as e:
        return f"⚠️ 錯誤：{e}"
