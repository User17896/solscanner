import requests
import time
from datetime import datetime, timezone

# ============================================================
#  CONFIG
# ============================================================
import os
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8739546604:AAE_TY1c9MPXarPrQFLLi1PBMYFdRjaEF_A")
CHAT_ID        = os.environ.get("CHAT_ID", "5959009671")
SCAN_INTERVAL  = 120  # 2 minutes

# ============================================================

NARRATIVES = {
    "ai": 20, "agent": 20, "gpt": 20, "neural": 20,
    "trump": 20, "elon": 20, "maga": 20, "doge": 20,
    "pepe": 20, "frog": 20, "wojak": 20, "chad": 20,
    "cat": 15, "dog": 15, "inu": 15, "shib": 15,
    "biden": 15, "pump": 15, "moon": 15, "based": 15,
    "bonk": 15, "wif": 15, "hat": 15, "baby": 15,
    "giga": 15, "sigma": 15, "sol": 10, "solana": 10,
    "fire": 10, "ape": 10, "monkey": 10, "bear": 10,
    "bull": 10, "rocket": 10, "king": 10, "rich": 10,
    "turbo": 10, "ultra": 10, "zeus": 10, "god": 10,
}

alerted = set()


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if not r.ok:
            print(f"[TG ERROR] {r.status_code} — {r.text[:200]}")
    except Exception as e:
        print(f"[TG EXCEPTION] {e}")


def fetch_pairs():
    urls = [
        "https://api.dexscreener.com/latest/dex/search/?q=solana+pump",
        "https://api.dexscreener.com/latest/dex/search/?q=new+solana",
        "https://api.dexscreener.com/latest/dex/search/?q=meme+solana",
    ]
    all_pairs = []
    seen = set()
    for url in urls:
        try:
            r = requests.get(url, headers={"Accept": "application/json"}, timeout=15)
            if not r.ok:
                continue
            pairs = r.json().get("pairs", [])
            for p in pairs:
                addr = p.get("pairAddress", "")
                if addr and addr not in seen:
                    seen.add(addr)
                    all_pairs.append(p)
        except Exception as e:
            print(f"[FETCH ERROR] {e}")
        time.sleep(1)
    return all_pairs


def get_rugcheck(token_address):
    try:
        r = requests.get(
            f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report/summary",
            timeout=10
        )
        if not r.ok:
            return {}
        data = r.json()
        risks = data.get("risks", [])
        mint_ok   = True
        freeze_ok = True
        for risk in risks:
            name  = risk.get("name",  "").lower()
            level = risk.get("level", "").lower()
            if "mint" in name and level in ["warn", "danger"]:
                mint_ok = False
            if "freeze" in name and level == "danger":
                freeze_ok = False
        return {
            "mint_ok":   mint_ok,
            "freeze_ok": freeze_ok,
            "risks":     risks
        }
    except:
        return {}


def score_narrative(name, ticker):
    combined = (name + " " + ticker).lower()
    score = 0
    matched = []
    for kw, pts in NARRATIVES.items():
        if kw in combined:
            score += pts
            matched.append(kw.upper())
    return min(score, 40), matched


def score_momentum(pair):
    score = 0
    signals = []
    txns = pair.get("txns", {})
    h1   = txns.get("h1",  {})
    buys_h1  = h1.get("buys",  0)
    sells_h1 = h1.get("sells", 0)
    total_h1 = buys_h1 + sells_h1
    vol      = pair.get("volume", {})
    vol_h1   = vol.get("h1",  0) or 0
    price_ch = pair.get("priceChange", {})
    change_h1= price_ch.get("h1", 0) or 0

    if total_h1 > 0:
        ratio = buys_h1 / total_h1
        if ratio >= 0.70:
            score += 15; signals.append(f"🟢 Buys {int(ratio*100)}%")
        elif ratio >= 0.60:
            score += 10; signals.append(f"🟡 Buys {int(ratio*100)}%")
        elif ratio >= 0.55:
            score += 5;  signals.append(f"Buys {int(ratio*100)}%")
        else:
            signals.append(f"🔴 Buys only {int(ratio*100)}%")

    if total_h1 >= 200:
        score += 10; signals.append(f"⚡ {total_h1} txns/hr")
    elif total_h1 >= 100:
        score += 7;  signals.append(f"⚡ {total_h1} txns/hr")
    elif total_h1 >= 50:
        score += 4;  signals.append(f"{total_h1} txns/hr")
    elif total_h1 >= 20:
        score += 2;  signals.append(f"{total_h1} txns/hr (low)")

    if change_h1 > 50:
        score += 10; signals.append(f"🚀 +{change_h1:.0f}% 1H")
    elif change_h1 > 20:
        score += 7;  signals.append(f"📈 +{change_h1:.0f}% 1H")
    elif change_h1 > 0:
        score += 3;  signals.append(f"+{change_h1:.0f}% 1H")
    elif change_h1 < -20:
        score -= 5;  signals.append(f"📉 {change_h1:.0f}% 1H")

    if vol_h1 > 50000:
        score += 10; signals.append(f"💰 ${vol_h1/1000:.0f}K vol/hr")
    elif vol_h1 > 20000:
        score += 7;  signals.append(f"💰 ${vol_h1/1000:.0f}K vol/hr")
    elif vol_h1 > 5000:
        score += 4;  signals.append(f"${vol_h1/1000:.0f}K vol/hr")

    return min(score, 35), signals, buys_h1, sells_h1


def score_liquidity(pair):
    score = 0
    liq     = pair.get("liquidity", {})
    liq_usd = liq.get("usd", 0) or 0
    mcap    = pair.get("marketCap", 0) or pair.get("fdv", 0) or 1
    if liq_usd < 2000:
        return -999, liq_usd
    ratio = (liq_usd / mcap) * 100
    if ratio >= 25:   score = 25
    elif ratio >= 15: score = 18
    elif ratio >= 10: score = 12
    elif ratio >= 5:  score = 5
    return min(score, 25), liq_usd


def fmt(n):
    if n is None: return "N/A"
    n = float(n)
    if n >= 1_000_000: return f"${n/1_000_000:.2f}M"
    if n >= 1_000:     return f"${n/1_000:.1f}K"
    return f"${n:.2f}"


def get_age(pair):
    created = pair.get("pairCreatedAt")
    if not created:
        return "Unknown", 9999
    try:
        dt   = datetime.fromtimestamp(created / 1000, tz=timezone.utc)
        mins = int((datetime.now(tz=timezone.utc) - dt).total_seconds() / 60)
        if mins < 60:
            return f"{mins}m", mins
        return f"{mins//60}h {mins%60}m", mins
    except:
        return "Unknown", 9999


def scan_and_alert():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🔍 Scanning...")
    pairs = fetch_pairs()
    print(f"[SCAN] {len(pairs)} pairs found")

    candidates = []

    for pair in pairs:
        if pair.get("chainId") != "solana":
            continue

        pair_addr  = pair.get("pairAddress", "")
        token_addr = pair.get("baseToken", {}).get("address", "")
        ticker     = pair.get("baseToken", {}).get("symbol", "?")
        name       = pair.get("baseToken", {}).get("name",   "?")

        if pair_addr in alerted:
            continue

        mcap = pair.get("marketCap", 0) or pair.get("fdv", 0) or 0
        if mcap <= 0 or mcap > 100_000:
            continue

        txns    = pair.get("txns", {})
        h1      = txns.get("h1",  {})
        h24     = txns.get("h24", {})
        total_t = (h1.get("buys",0)+h1.get("sells",0)+
                   h24.get("buys",0)+h24.get("sells",0))
        if total_t < 10:
            continue

        age_str, age_mins = get_age(pair)
        if age_mins > 1440:
            continue

        liq_score, liq_usd = score_liquidity(pair)
        if liq_score == -999:
            continue

        mom_score, mom_signals, buys_h1, sells_h1 = score_momentum(pair)
        narr_score, narr_matches = score_narrative(name, ticker)
        total_score = liq_score + mom_score + narr_score

        if total_score < 45:
            continue

        rug = {}
        if token_addr:
            rug = get_rugcheck(token_addr)

        candidates.append({
            "pair":        pair,
            "score":       total_score,
            "mom_signals": mom_signals,
            "narr_matches":narr_matches,
            "age_str":     age_str,
            "age_mins":    age_mins,
            "mcap":        mcap,
            "liq_usd":     liq_usd,
            "ticker":      ticker,
            "name":        name,
            "pair_addr":   pair_addr,
            "token_addr":  token_addr,
            "buys_h1":     buys_h1,
            "sells_h1":    sells_h1,
            "rug":         rug,
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)

    sent = 0
    for c in candidates[:5]:
        pair       = c["pair"]
        score      = c["score"]
        ticker     = c["ticker"]
        name       = c["name"]
        mcap       = c["mcap"]
        liq_usd    = c["liq_usd"]
        age_str    = c["age_str"]
        pair_addr  = c["pair_addr"]
        token_addr = c["token_addr"]
        rug        = c["rug"]
        buys_h1    = c["buys_h1"]
        sells_h1   = c["sells_h1"]

        if score >= 85:   label = "🔴 SEND IT"
        elif score >= 75: label = "🟠 LOOKS LIVE"
        elif score >= 60: label = "🟡 ON THE RADAR"
        else:             label = "👀 EARLY RADAR"

        price     = pair.get("priceUsd", "?")
        price_str = f"${float(price):.8f}" if price and price != "?" else "N/A"

        vol       = pair.get("volume",      {})
        vol_h1    = vol.get("h1",  0) or 0
        vol_h24   = vol.get("h24", 0) or 0
        price_ch  = pair.get("priceChange", {})
        ch_h1     = price_ch.get("h1",  0) or 0
        ch_h24    = price_ch.get("h24", 0) or 0

        liq_pct   = f"{(liq_usd/mcap*100):.0f}%" if mcap > 0 else "?"
        liq_sol   = f"{(liq_usd/180):.1f} SOL" if liq_usd else "?"  # rough SOL price

        supply    = pair.get("baseToken", {}).get("totalSupply", "N/A")
        if supply and supply != "N/A":
            try:
                s = float(supply)
                if s >= 1e9:   supply = f"{s/1e9:.0f}B"
                elif s >= 1e6: supply = f"{s/1e6:.0f}M"
            except:
                supply = "N/A"

        mint_icon   = "✅ Disabled" if rug.get("mint_ok",   False) else "❌ Active"
        freeze_icon = "✅ Disabled" if rug.get("freeze_ok", False) else "❌ Active"
        lp_status   = "❌ Not Burned"  # DexScreener doesn't give LP burn status directly

        narr_str = ", ".join(c["narr_matches"][:3]) if c["narr_matches"] else "No strong meta"
        mom_str  = "\n".join(c["mom_signals"][:3])  if c["mom_signals"]  else "Low momentum"

        total_h1  = buys_h1 + sells_h1
        buy_pct   = f"{int(buys_h1/total_h1*100)}%" if total_h1 > 0 else "?"
        sell_pct  = f"{int(sells_h1/total_h1*100)}%" if total_h1 > 0 else "?"

        dex_url      = f"https://dexscreener.com/solana/{pair_addr}"
        rugcheck_url = f"https://rugcheck.xyz/tokens/{token_addr}" if token_addr else "https://rugcheck.xyz"
        photon_url   = f"https://photon-sol.tinyastro.io/en/lp/{pair_addr}" if pair_addr else "#"
        bundle_url   = f"https://trench.bot/bundles/{token_addr}" if token_addr else "#"

        msg = (
            f"{label} — <b>{score}/100</b>\n"
            f"\n"
            f"<b>{name} | {ticker} | Pump 🎯</b>\n"
            f"\n"
            f"📋 Token Address:\n"
            f"<code>{token_addr}</code>\n"
            f"\n"
            f"📦 Supply: {supply}\n"
            f"📊 MC: {fmt(mcap)}\n"
            f"💧 Liquidity: {liq_sol} | {fmt(liq_usd)} ({liq_pct} of MC)\n"
            f"🕐 Age: {age_str}\n"
            f"💲 Price: {price_str}\n"
            f"\n"
            f"📈 <b>MOMENTUM</b>\n"
            f"{mom_str}\n"
            f"Buys: {buys_h1} ({buy_pct}) | Sells: {sells_h1} ({sell_pct})\n"
            f"Vol 1H: {fmt(vol_h1)} | 24H: {fmt(vol_h24)}\n"
            f"1H: {'+' if ch_h1>=0 else ''}{ch_h1:.0f}% | 24H: {'+' if ch_h24>=0 else ''}{ch_h24:.0f}%\n"
            f"\n"
            f"❄️ FREEZE: {freeze_icon}\n"
            f"🪙 MINT: {mint_icon}\n"
            f"🔥 LP STATUS: {lp_status}\n"
            f"\n"
            f"🎯 NARRATIVE: {narr_str}\n"
            f"\n"
            f"💰 <b>TARGETS</b>\n"
            f"3x = {fmt(mcap * 3)} MC\n"
            f"10x = {fmt(mcap * 10)} MC\n"
            f"\n"
            f"🔗 <a href='{dex_url}'>SCREEN</a> | "
            f"<a href='{rugcheck_url}'>RUGCHECK</a> | "
            f"<a href='{photon_url}'>PHOTON</a> | "
            f"<a href='{bundle_url}'>BUNDLE</a>\n"
            f"\n"
            f"<i>NFA — DYOR — could go zero</i>"
        )

        send_telegram(msg)
        alerted.add(pair_addr)
        sent += 1
        print(f"[ALERT] {ticker} score {score}")
        time.sleep(1)

    if sent == 0:
        print("[SCAN] No coins passed filters")
    else:
        print(f"[SCAN] {sent} alert(s) sent")


def send_startup():
    msg = (
        "🤖 <b>CHAINSCAN BOT ONLINE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Scanning Solana micro-cap runners\n"
        "MC filter: Under $100K\n"
        "Scan interval: Every 2 mins\n"
        "Min score: 45/100\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🟢 Bot is live. Alerts incoming."
    )
    send_telegram(msg)


if __name__ == "__main__":
    print("=" * 50)
    print("  CHAINSCAN — Solana Meme Coin Scanner")
    print("=" * 50)
    send_startup()
    while True:
        try:
            scan_and_alert()
        except Exception as e:
            print(f"[MAIN ERROR] {e}")
        print(f"[SLEEP] Next scan in {SCAN_INTERVAL}s...")
        time.sleep(SCAN_INTERVAL)
