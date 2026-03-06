# ==================== form144.py V23 ====================
# Engine 2: Form 144 Insider Selling Alert
# Sector + AI upgrade
# =========================================================
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timezone, timedelta
import os, re, json
from google import genai
from google.genai import types

from utils.supabase import supabase_insert, supabase_link_exists, supabase_patch, supabase_ticker_recent
from utils.finnhub import get_stock_quote, get_company_profile
from utils.telegram import send_whale_telegram

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

gemini_client = None
if GEMINI_API_KEY:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    print("Gemini 3.1 Pro engine ready")

SEC_HEADERS = {'User-Agent': 'WhaleRadarBot Admin@kuafuorhk.com'}

SECTOR_EMOJI = {
    "Technology": "💻", "Healthcare": "🏥", "Financial Services": "🏦",
    "Energy": "⛽", "Consumer Cyclical": "🛍️", "Industrials": "🏭",
    "Communication Services": "📡", "Consumer Defensive": "🛒",
    "Real Estate": "🏠", "Utilities": "💡", "Basic Materials": "⛏️"
}


def get_sector_emoji(sector):
    for k, v in SECTOR_EMOJI.items():
        if k.lower() in sector.lower():
            return v
    return "📈"


def get_sec_ticker_map():
    try:
        resp = requests.get("https://www.sec.gov/files/company_tickers.json", headers=SEC_HEADERS)
        return {str(v['cik_str']): v['ticker'] for v in resp.json().values()}
    except Exception as e:
        print(f"⚠️ SEC ticker map failed: {e}")
        return {}


def ai_is_routine_selling(company_name, ticker):
    """AI pre-screen: return True if this is routine selling (tax/vesting), skip it"""
    if not gemini_client:
        return False
    try:
        prompt = (
            f"Company: {company_name} ({ticker}) filed Form 144 with SEC.\n"
            f"Search latest news. Is this most likely ROUTINE selling "
            f"(restricted stock vesting, tax withholding, 10b5-1 plan, scheduled sale)?\n"
            f"Reply ONLY 'ROUTINE' or 'NOT_ROUTINE'. One word only."
        )
        resp = gemini_client.models.generate_content(
            model="gemini-3.1-pro-preview", contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                http_options=types.HttpOptions(timeout=20000),
            ))
        answer = resp.text.strip().upper()
        is_routine = "ROUTINE" in answer and "NOT" not in answer
        print(f"    AI pre-screen: {answer} -> {'SKIP' if is_routine else 'ALERT'}")
        return is_routine
    except Exception as e:
        print(f"    AI pre-screen error: {e}")
        return False


def ai_explain_selling(company_name, ticker, sector, market_cap_m):
    if not gemini_client:
        return "⚠️ 有內部人士已提交拋售意向書"
    try:
        mc = f"市值：${market_cap_m/1000:.1f}B。" if market_cap_m >= 1000 else ""
        prompt = (
            f"公司：{company_name} ({ticker})，板塊：{sector}。{mc}\n"
            f"內部人士向 SEC 提交 Form 144 拋售意向書。\n\n"
            f"請用繁體中文，80字內，簡潔分析：\n"
            f"1. {sector} 板塊趨勢（看多或看空，一句）\n"
            f"2. 拋售原因（搜尋新聞）\n"
            f"3. 風險判斷\n\n"
            f"結尾：🔴高風險 / 🟡中風險 / 🟢低風險\n"
            f"禁 markdown。禁廢話。Bloomberg 風格。"
        )
        resp = gemini_client.models.generate_content(
            model="gemini-3.1-pro-preview", contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                http_options=types.HttpOptions(timeout=20000),
            ))
        return resp.text.strip()
    except Exception as e:
        print(f"  Gemini error: {e}")
        return "⚠️ 有內部人士已提交拋售意向書"


def main():
    cik_ticker_map = get_sec_ticker_map()
    print(f"Loaded {len(cik_ticker_map)} CIK-Ticker mappings")

    url = 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=144&owner=only&count=40&output=atom'
    now_utc = datetime.now(timezone.utc)
    time_limit = now_utc - timedelta(minutes=30)

    response = requests.get(url, headers=SEC_HEADERS)
    soup = BeautifulSoup(response.content, 'xml')
    entries = soup.find_all('entry')
    print(f"Found {len(entries)} Form 144 entries")
    found_count = 0

    for entry in entries:
        updated_tag = entry.find('updated')
        if not updated_tag:
            continue
        try:
            if datetime.fromisoformat(updated_tag.text.replace('Z', '+00:00')).astimezone(timezone.utc) < time_limit:
                break
        except Exception:
            continue

        link = entry.link['href']
        if supabase_link_exists(link):
            continue

        title_text = entry.title.text if entry.title else ""
        txt_link = link.replace('-index.htm', '.txt')
        txt_response = requests.get(txt_link, headers=SEC_HEADERS)

        if txt_response.status_code != 200:
            continue

        txt_content = txt_response.text
        ticker = "N/A"
        issuer_name = "未知公司"

        sym = re.search(r'<(?:issuerSymbol|issuerTradingSymbol)>\s*([^<]+?)\s*</(?:issuerSymbol|issuerTradingSymbol)>', txt_content, re.IGNORECASE)
        if sym:
            ticker = sym.group(1).strip().upper()
        nm = re.search(r'<(?:nameOfIssuer|issuerName)>\s*([^<]+?)\s*</(?:nameOfIssuer|issuerName)>', txt_content, re.IGNORECASE)
        if nm:
            issuer_name = nm.group(1).strip()

        if ticker == "N/A" or issuer_name == "未知公司":
            sgml = re.search(r'(?:SUBJECT COMPANY|ISSUER)[:\s]*(.*?)(?:FILED BY:|REPORTING-OWNER:|<SEC-DOCUMENT>|</SEC-HEADER>|\Z)', txt_content[:5000], re.DOTALL | re.IGNORECASE)
            if sgml:
                block = sgml.group(1)
                if issuer_name == "未知公司":
                    cn = re.search(r'COMPANY CONFORMED NAME:\s*([^\n\r]+)', block)
                    if cn:
                        issuer_name = cn.group(1).strip()
                if ticker == "N/A":
                    ck = re.search(r'CENTRAL INDEX KEY:\s*(\d+)', block)
                    if ck:
                        ticker = cik_ticker_map.get(str(int(ck.group(1).strip())), "N/A")

        if ticker == "N/A":
            cm = re.search(r'\((\d+)\)\s*\(Subject\)', title_text)
            if cm:
                ticker = cik_ticker_map.get(str(int(cm.group(1))), "N/A")
        if issuer_name == "未知公司":
            tn = re.search(r'144\s*-\s*(.+?)\s*\(\d+\)', title_text)
            if tn:
                issuer_name = tn.group(1).strip()
        if issuer_name == "未知公司":
            alt = re.search(r'COMPANY CONFORMED NAME:\s*([^\n\r]+)', txt_content[:5000])
            if alt:
                issuer_name = alt.group(1).strip()

        print(f"  {issuer_name} ({ticker})")

        # Dedup: skip if same ticker already alerted recently (multiple insiders filing)
        if ticker != "N/A" and supabase_ticker_recent("form144", ticker, minutes=60):
            print(f"    Skipped: {ticker} already alerted within 60 min")
            continue

        price_str, change_str, current_price, change_pct = get_stock_quote(ticker)
        profile = get_company_profile(ticker)
        sector = profile["sector"]
        market_cap_m = profile["marketCap"]
        sector_emoji = get_sector_emoji(sector)

        # Gate 1: market cap > $5B only
        MIN_MARKET_CAP = 5000
        if market_cap_m < MIN_MARKET_CAP:
            print(f"    Skipped: market cap ${market_cap_m:.0f}M < ${MIN_MARKET_CAP}M")
            continue

        # Gate 2: AI pre-screen - skip routine selling
        if ai_is_routine_selling(issuer_name, ticker):
            print("    Skipped: routine selling (tax/vesting)")
            supabase_insert({
                "source": "form144", "ticker": ticker, "company_name": issuer_name,
                "action": "✅ 常規拋售（已過濾）",
                "price": current_price, "change_pct": change_pct,
                "sec_link": link,
                "extra_data": json.dumps({"sector": sector, "market_cap_m": market_cap_m, "filtered": True})
            })
            continue

        inserted = supabase_insert({
            "source": "form144", "ticker": ticker, "company_name": issuer_name,
            "action": "⚠️ Form 144 拋售預警",
            "price": current_price, "change_pct": change_pct,
            "sec_link": link,
            "extra_data": json.dumps({"sector": sector, "industry": profile["industry"], "market_cap_m": market_cap_m})
        })
        if not inserted:
            print("    Skipped: already in DB or insert failed")
            continue

        ai_analysis = ai_explain_selling(issuer_name, ticker, sector, market_cap_m)
        msg = "🚨 <b>【Form 144 內部高管逃生預警】</b>\n"
        msg += f"🏢 公司：<b>{issuer_name} ({ticker})</b>\n"
        msg += f"{sector_emoji} 板塊：<b>{sector}</b>\n"
        msg += f"💲 股價：<b>{price_str}</b>  {change_str}\n"
        msg += f"💰 市值：<b>${market_cap_m/1000:.1f}B</b>\n"
        msg += f"🧠 <b>AI 分析：</b>\n{ai_analysis}\n"
        msg += f"🔗 <a href='{link}'>查看 SEC 原文</a>"
        send_whale_telegram(msg)

        # Update DB with AI summary
        supabase_patch(link, {"ai_summary": ai_analysis})

        found_count += 1
        time.sleep(2)

        if found_count >= 5:
            break


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Form 144 engine error: {e}")
