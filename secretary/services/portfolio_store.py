import logging
import requests

import config

logger = logging.getLogger(__name__)


class PortfolioStore:
    """Manages portfolio_holdings in Supabase for CFO daily_report fallback."""

    def _headers(self):
        return {
            "apikey": config.SUPABASE_KEY,
            "Authorization": f"Bearer {config.SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def _ok(self):
        return bool(config.SUPABASE_URL and config.SUPABASE_KEY)

    def list_holdings(self) -> str:
        if not self._ok():
            return "❌ Supabase 未設定"
        try:
            r = requests.get(
                f"{config.SUPABASE_URL}/rest/v1/portfolio_holdings",
                headers=self._headers(),
                params={"order": "ticker", "active": "eq.true"},
            )
            items = r.json() if r.status_code == 200 else []
        except Exception as e:
            return f"查詢失敗：{e}"
        if not items:
            return "📊 目前沒有持倉記錄"
        lines = ["📊 持倉記錄（CFO fallback）："]
        for h in items:
            lines.append(f"  {h['ticker']}  {h['shares']} 股 @ {h['open_price']}  {h.get('open_date','')}")
        return "\n".join(lines)

    def upsert(self, ticker: str, shares: float, open_price: float, open_date: str = None) -> str:
        if not self._ok():
            return "❌ Supabase 未設定"
        ticker = ticker.upper()
        try:
            # Check if exists
            r = requests.get(
                f"{config.SUPABASE_URL}/rest/v1/portfolio_holdings",
                headers=self._headers(),
                params={"ticker": f"eq.{ticker}"},
            )
            exists = r.status_code == 200 and len(r.json()) > 0

            data = {"ticker": ticker, "shares": shares, "open_price": open_price, "active": True}
            if open_date:
                data["open_date"] = open_date

            if exists:
                r = requests.patch(
                    f"{config.SUPABASE_URL}/rest/v1/portfolio_holdings",
                    headers=self._headers(),
                    params={"ticker": f"eq.{ticker}"},
                    json=data,
                )
            else:
                r = requests.post(
                    f"{config.SUPABASE_URL}/rest/v1/portfolio_holdings",
                    headers=self._headers(),
                    json=data,
                )
            if r.status_code in (200, 201):
                return f"✅ {ticker} 已{'更新' if exists else '新增'}：{shares} 股 @ {open_price}"
            return f"❌ 失敗：{r.status_code} {r.text[:200]}"
        except Exception as e:
            return f"錯誤：{e}"

    def remove(self, ticker: str) -> str:
        if not self._ok():
            return "❌ Supabase 未設定"
        ticker = ticker.upper()
        try:
            r = requests.patch(
                f"{config.SUPABASE_URL}/rest/v1/portfolio_holdings",
                headers=self._headers(),
                params={"ticker": f"eq.{ticker}"},
                json={"active": False},
            )
            if r.status_code in (200, 204):
                return f"✅ {ticker} 已從持倉移除"
            return f"❌ 失敗：{r.status_code} {r.text[:200]}"
        except Exception as e:
            return f"錯誤：{e}"
