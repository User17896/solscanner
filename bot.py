import requests
import time
import re
from datetime import datetime, timezone

# ============================================================
#  PASTE YOUR DETAILS HERE
# ============================================================
TELEGRAM_TOKEN = "8739546604:AAE_TY1c9MPXarPrQFLLi1PBMYFdRjaEF_A"
CHAT_ID        = "5959009671"
SCAN_INTERVAL  = 120   # 15 minutes in seconds
# ============================================================

# ── NARRATIVE KEYWORDS ───────────────────────────────────────
# These are the metas that actually pump on Solana right now.
# Bot checks if the token name/ticker matches any of these.
NARRATIVES = {
    # Tier 1 — hottest metas (+20)
    "ai":        20, "agent":    20, "gpt":      20, "neural":   20,
    "trump":     20, "elon":     20, "maga":     20, "doge":     20,
    "pepe":      20, "frog":     20, "wojak":    20, "chad":     20,

    # Tier 2 — solid metas (+15)
    "cat":       15, "dog":      15, "inu":      15, "shib":     15,
    "biden":     15, "pump":     15, "moon":     15, "based":    15,
    "bonk":      15, "wif":      15, "hat":      15, "sick":     15,
    "baby":      15, "mini":     15, "giga":     15, "sigma":    15,

    # Tier 3 — decent (+10)
    "sol":       10, "solana":   10, "sun":      10, "fire":     10,
    "ape":       10, "monkey":   10, "bear":     10, "bull":     10,
    "rocket":    10, "zeus":     10, "god":      10, "king":     10,
    "rich":      10, "gains":    10, "turbo":    10, "ultra":    10,
}

# Tokens we have already alerted on — avoid duplicates
alerted = set()


# ── TELEGRAM ─────────────────────────────────────────────────
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id":    CHAT_ID,
        "text":       message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if not r.ok:
            print(f"[TG ERROR] {r.status_code} — {r.text[:100]}")
    except Exception as e:
        print(f"[TG EXCEPTION] {e}")


# ── DEXSCREENER ──────────────────────────────────────────────
def fetch_new_solana_pairs():
    """Fetch latest Solana pairs from DexScreener."""
    url = "https://api.dexscreener.com/latest/dex/tokens/solana"
    headers = {"Accept": "application/json"}
    try:
        # Search for newest pairs via the search endpoint
        r = requests.get(
            "https://api.dexscreener.com/latest/dex/search/?q=solana",
            headers=headers,
            timeout=15
        )
        if not r.ok:
            print(f"[DEX ERROR] {r.status_code}")
            return []
        data = r.json()
        return data.get("pairs", [])
    except Exception as e:
        print(f"[DEX EXCEPTION] {e}")
        return []


def fetch_trending_solana():
    """Also check DexScreener trending for Solana."""
    try:
        r = requests.get(
            "https://api.dexscreener.com/latest/dex/search/?q=pump+solana",
            headers={"Accept": "application/json"},
            timeout=15
        )
        if not r.ok:
            return []
        return r.json().get("pairs", [])
    except Exception as e:
        print(f"[TRENDING EXCEPTION] {e}")
        return []


# ── HONEYPOT CHECK ───────────────────────────────────────────
def is_honeypot(token_address):
    """Basic honeypot check viaRugCheck public API."""
    try:
        r = requests.get(
            f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report/summary",
            timeout=10
        )
        if not r.ok:
            return False  # Can't confirm, don't block
        data = r.json()
        risks = data.get("risks", [])
        # Flag as honeypot if any critical risk
        for risk in risks:
            name = risk.get("name", "").lower()
            level = risk.get("level", "").lower()
            if "honeypot" in name or ("freeze" in name and level == "danger"):
                return True
        return False
    except:
        return False  # If check fails, don't block the coin


def get_mint_status(token_address):
    """Check if mint authority is renounced."""
    try:
        r = requests.get(
            f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report/summary",
            timeout=10
        )
        if not r.ok:
            return "unknown"
        data = r.json()
        risks = data.get("risks", [])
        for risk in risks:
            if "mint" in risk.get("name", "").lower():
                return "active"  # Mint authority still active = risk
        return "renounced"
    except:
        return "unknown"


# ── NARRATIVE SCORER ─────────────────────────────────────────
def score_narrative(name, ticker):
    """Score how well a token fits current hot metas."""
    combined = (name + " " + ticker).lower()
    score = 0
    matched = []
    for keyword, points in NARRATIVES.items():
        if keyword in combined:
            score += points
            matched.append(keyword)
    return min(score, 40), matched  # Cap at 40


# ── MOMENTUM SCORER ──────────────────────────────────────────
def score_momentum(pair):
    """Score momentum signals from pair data."""
    score = 0
    signals = []

    txns = pair.get("txns", {})
    h1   = txns.get("h1", {})
    h24  = txns.get("h24", {})

    buys_h1  = h1.get("buys",  0)
    sells_h1 = h1.get("sells", 0)
    total_h1 = buys_h1 + sells_h1

    buys_h24  = h24.get("buys",  0)
    sells_h24 = h24.get("sells", 0)
    total_h24 = buys_h24 + sells_h24

    vol   = pair.get("volume", {})
    vol_h1  = vol.get("h1",  0) or 0
    vol_h24 = vol.get("h24", 0) or 0

    price_change = pair.get("priceChange", {})
    change_h1  = price_change.get("h1",  0) or 0
    change_h24 = price_change.get("h24", 0) or 0

    # Buy pressure
    if total_h1 > 0:
        buy_ratio = buys_h1 / total_h1
        if buy_ratio >= 0.70:
            score += 15
            signals.append(f"🟢 Buys {int(buy_ratio*100)}%")
        elif buy_ratio >= 0.60:
            score += 10
            signals.append(f"🟡 Buys {int(buy_ratio*100)}%")
        elif buy_ratio >= 0.55:
            score += 5
            signals.append(f"Buys {int(buy_ratio*100)}%")
        else:
            signals.append(f"🔴 Buys only {int(buy_ratio*100)}%")

    # Transaction velocity
    if total_h1 >= 200:
        score += 10
        signals.append(f"⚡ {total_h1} txns/hr (HIGH)")
    elif total_h1 >= 100:
        score += 7
        signals.append(f"⚡ {total_h1} txns/hr")
    elif total_h1 >= 50:
        score += 4
        signals.append(f"{total_h1} txns/hr")
    elif total_h1 >= 20:
        score += 2
        signals.append(f"{total_h1} txns/hr (low)")

    # Price momentum
    if change_h1 > 50:
        score += 10
        signals.append(f"🚀 +{change_h1:.0f}% in 1hr")
    elif change_h1 > 20:
        score += 7
        signals.append(f"📈 +{change_h1:.0f}% in 1hr")
    elif change_h1 > 0:
        score += 3
        signals.append(f"+{change_h1:.0f}% in 1hr")
    elif change_h1 < -20:
        score -= 5
        signals.append(f"📉 {change_h1:.0f}% in 1hr")

    # Volume health
    if vol_h1 > 50000:
        score += 10
        signals.append(f"💰 ${vol_h1/1000:.0f}K vol/hr")
    elif vol_h1 > 20000:
        score += 7
        signals.append(f"💰 ${vol_h1/1000:.0f}K vol/hr")
    elif vol_h1 > 5000:
        score += 4
        signals.append(f"${vol_h1/1000:.0f}K vol/hr")

    return min(score, 35), signals  # Cap at 35


# ── LIQUIDITY SCORER ─────────────────────────────────────────
def score_liquidity(pair):
    """Score liquidity health."""
    score = 0
    signals = []

    liq = pair.get("liquidity", {})
    liq_usd  = liq.get("usd", 0) or 0
    mcap     = pair.get("marketCap", 0) or pair.get("fdv", 0) or 1

    # Hard kill — under $2K liquidity
    if liq_usd < 2000:
        return -999, ["🚫 Liquidity too low (<$2K)"]

    liq_ratio = (liq_usd / mcap) * 100

    if liq_ratio >= 25:
        score += 25
        signals.append(f"💧 Liq {liq_ratio:.0f}% of MC ✅")
    elif liq_ratio >= 15:
        score += 18
        signals.append(f"💧 Liq {liq_ratio:.0f}% of MC ✅")
    elif liq_ratio >= 10:
        score += 12
        signals.append(f"💧 Liq {liq_ratio:.0f}% of MC")
    elif liq_ratio >= 5:
        score += 5
        signals.append(f"⚠️ Liq only {liq_ratio:.0f}% of MC")
    else:
        score += 0
        signals.append(f"🔴 Liq {liq_ratio:.0f}% of MC (risky)")

    return min(score, 25), signals


# ── FORMAT NUMBER ─────────────────────────────────────────────
def fmt(n):
    if n is None: return "N/A"
    n = float(n)
    if n >= 1_000_000: return f"${n/1_000_000:.2f}M"
    if n >= 1_000:     return f"${n/1_000:.1f}K"
    return f"${n:.2f}"


# ── PAIR AGE ─────────────────────────────────────────────────
def get_age_str(pair):
    created = pair.get("pairCreatedAt")
    if not created:
        return "Unknown", 9999
    try:
        created_dt = datetime.fromtimestamp(created / 1000, tz=timezone.utc)
        now        = datetime.now(tz=timezone.utc)
        mins       = int((now - created_dt).total_seconds() / 60)
        if mins < 60:
            return f"{mins}m", mins
        else:
            hrs = mins // 60
            m   = mins % 60
            return f"{hrs}h {m}m", mins
    except:
        return "Unknown", 9999


# ── MAIN SCANNER ─────────────────────────────────────────────
def scan_and_alert():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🔍 Scanning Solana pairs...")

    # Fetch from multiple sources and merge
    pairs1 = fetch_new_solana_pairs()
    pairs2 = fetch_trending_solana()

    # Deduplicate by pair address
    seen_addrs = set()
    all_pairs  = []
    for p in pairs1 + pairs2:
        addr = p.get("pairAddress", "")
        if addr and addr not in seen_addrs:
            seen_addrs.add(addr)
            all_pairs.append(p)

    print(f"[SCAN] Found {len(all_pairs)} total pairs to evaluate")

    candidates = []

    for pair in all_pairs:
        # Only Solana
        if pair.get("chainId") != "solana":
            continue

        # Already alerted
        pair_addr = pair.get("pairAddress", "")
        if pair_addr in alerted:
            continue

        mcap = pair.get("marketCap", 0) or pair.get("fdv", 0) or 0
        token_addr = pair.get("baseToken", {}).get("address", "")
        ticker     = pair.get("baseToken", {}).get("symbol", "?")
        name       = pair.get("baseToken", {}).get("name", "?")

        # ── HARD FILTERS ─────────────────────────────────────
        # Must have some market cap data
        if mcap <= 0:
            continue

        # MC must be under $100K
        if mcap > 100_000:
            continue

        # Must have at least 10 transactions
        txns = pair.get("txns", {})
        h1   = txns.get("h1", {})
        h24  = txns.get("h24", {})
        total_txns = (h1.get("buys", 0) + h1.get("sells", 0) +
                      h24.get("buys", 0) + h24.get("sells", 0))
        if total_txns < 10:
            continue

        # Age check — skip if over 24 hours with no traction
        age_str, age_mins = get_age_str(pair)
        if age_mins > 1440:  # older than 24 hours
            continue

        # Liquidity hard kill
        liq = pair.get("liquidity", {})
        liq_usd = liq.get("usd", 0) or 0
        if liq_usd < 2000:
            continue

        # ── SCORING ──────────────────────────────────────────
        liq_score,  liq_signals  = score_liquidity(pair)
        mom_score,  mom_signals  = score_momentum(pair)
        narr_score, narr_matches = score_narrative(name, ticker)

        # Kill if liquidity returned -999
        if liq_score == -999:
            continue

        total_score = liq_score + mom_score + narr_score

        if total_score < 45:
            continue

        # Honeypot check for higher scoring coins
        honeypot = False
        mint_status = "unknown"
        if total_score >= 60 and token_addr:
            honeypot    = is_honeypot(token_addr)
            mint_status = get_mint_status(token_addr)

        if honeypot:
            print(f"[SKIP] {ticker} — honeypot detected")
            continue

        candidates.append({
            "pair":         pair,
            "score":        total_score,
            "liq_score":    liq_score,
            "mom_score":    mom_score,
            "narr_score":   narr_score,
            "liq_signals":  liq_signals,
            "mom_signals":  mom_signals,
            "narr_matches": narr_matches,
            "mint_status":  mint_status,
            "age_str":      age_str,
            "age_mins":     age_mins,
            "mcap":         mcap,
            "liq_usd":      liq_usd,
            "ticker":       ticker,
            "name":         name,
            "pair_addr":    pair_addr,
            "token_addr":   token_addr,
        })

    # Sort by score descending
    candidates.sort(key=lambda x: x["score"], reverse=True)

    # Alert on top candidates (max 5 per scan to avoid spam)
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

        # Conviction label
        if score >= 85:
            label = "🔴 SEND IT"
        elif score >= 75:
            label = "🟠 LOOKS LIVE"
        elif score >= 60:
            label = "🟡 ON THE RADAR"
        else:
            label = "👀 EARLY RADAR"

        # Price info
        price     = pair.get("priceUsd", "?")
        price_str = f"${float(price):.8f}" if price and price != "?" else "N/A"

        vol   = pair.get("volume", {})
        vol_h1  = vol.get("h1",  0) or 0
        vol_h24 = vol.get("h24", 0) or 0

        price_change = pair.get("priceChange", {})
        change_h1  = price_change.get("h1",  0) or 0
        change_h24 = price_change.get("h24", 0) or 0

        # 3x and 10x targets
        target_3x  = fmt(mcap * 3)
        target_10x = fmt(mcap * 10)

        # Narrative display
        narr_str = ", ".join(c["narr_matches"][:3]).upper() if c["narr_matches"] else "No strong meta"

        # Mint status display
        mint_icon = "✅" if c["mint_status"] == "renounced" else "⚠️" if c["mint_status"] == "active" else "❓"
        mint_str  = f"Mint: {c['mint_status'].capitalize()} {mint_icon}"

        # Liq ratio
        liq_pct = f"{(liq_usd/mcap*100):.0f}%" if mcap > 0 else "?"

        # DexScreener link
        dex_url     = f"https://dexscreener.com/solana/{pair_addr}"
        rugcheck_url= f"https://rugcheck.xyz/tokens/{token_addr}" if token_addr else "https://rugcheck.xyz"

        # Momentum signals (top 3)
        mom_str = "\n".join(c["mom_signals"][:3]) if c["mom_signals"] else "No momentum data"

        msg = (
            f"{label} — <b>{score}/100</b>\n"
            f"\n"
            f"<b>${ticker}</b> — {name}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Age: {age_str} | Solana\n"
            f"Price: {price_str}\n"
            f"MC: {fmt(mcap)}\n"
            f"Liq: {fmt(liq_usd)} ({liq_pct} of MC)\n"
            f"{mint_str}\n"
            f"\n"
            f"📊 <b>MOMENTUM</b>\n"
            f"{mom_str}\n"
            f"Vol 1H: {fmt(vol_h1)} | 24H: {fmt(vol_h24)}\n"
            f"1H: {'+' if change_h1>=0 else ''}{change_h1:.0f}% | 24H: {'+' if change_h24>=0 else ''}{change_h24:.0f}%\n"
            f"\n"
            f"🎯 <b>NARRATIVE</b>: {narr_str}\n"
            f"\n"
            f"💰 <b>TARGETS</b>\n"
            f"3x = {target_3x} MC\n"
            f"10x = {target_10x} MC\n"
            f"\n"
            f"🔗 <a href='{dex_url}'>DexScreener</a> | <a href='{rugcheck_url}'>RugCheck</a>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>NFA — DYOR — could go zero</i>"
        )

        send_telegram(msg)
        alerted.add(pair_addr)
        sent += 1
        print(f"[ALERT] Sent: {ticker} (score {score})")
        time.sleep(1)  # small delay between messages

    if sent == 0:
        print("[SCAN] No coins passed filters this round")
    else:
        print(f"[SCAN] Sent {sent} alert(s)")


# ── STARTUP MESSAGE ───────────────────────────────────────────
def send_startup():
    msg = (
        "🤖 <b>CHAINSCAN BOT ONLINE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Scanning Solana for micro-cap runners\n"
        "MC filter: Under $100K\n"
        "Scan interval: Every 15 mins\n"
        "Min score to alert: 45/100\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🟢 Bot is live. Alerts incoming."
    )
    send_telegram(msg)


# ── MAIN LOOP ─────────────────────────────────────────────────
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
            # Don't crash the bot on errors, just wait and retry
        print(f"[SLEEP] Next scan in {SCAN_INTERVAL//60} minutes...")
        time.sleep(SCAN_INTERVAL)
