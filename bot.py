# CHAINSCAN v3.1 - age filter 3 days
import requests
import time
import os
import threading
from datetime import datetime, timezone

# ============================================================
#  CONFIG
# ============================================================
TELEGRAM_TOKEN     = os.environ.get("TELEGRAM_TOKEN", "8739546604:AAE_TY1c9MPXarPrQFLLi1PBMYFdRjaEF_A")
CHAT_ID            = os.environ.get("CHAT_ID", "5959009671")
SCAN_INTERVAL      = 120
UPDATE_TIMES       = [600, 1800, 3600]
MIN_GAIN_FOR_REPLY = 1.5

# Blocked token names (permanent garbage)
BLOCKED = ["define", "memecoins", "test", "scam"]
# ============================================================

# ── REDIS ────────────────────────────────────────────────────
import redis as redis_lib
REDIS_URL    = os.environ.get("REDIS_URL", None)
redis_client = None

def init_redis():
    global redis_client
    if REDIS_URL:
        try:
            redis_client = redis_lib.from_url(REDIS_URL, decode_responses=True)
            redis_client.ping()
            print("[REDIS] Connected OK")
        except Exception as e:
            print(f"[REDIS] Failed: {e}")
    else:
        print("[REDIS] No REDIS_URL")

def load_alerted():
    if redis_client:
        try:
            m = redis_client.smembers("alerted_pairs")
            print(f"[REDIS] Loaded {len(m)} alerted pairs")
            return set(m)
        except: pass
    return set()

def save_alerted(addr):
    if redis_client:
        try: redis_client.sadd("alerted_pairs", addr)
        except: pass

init_redis()
alerted         = load_alerted()
tracked         = {}
last_alert_time = 0


# ── TELEGRAM ─────────────────────────────────────────────────
def send_photo(image_url, caption):
    if len(caption) > 1024:
        caption = caption[:1020] + "..."
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
            json={"chat_id": CHAT_ID, "photo": image_url, "caption": caption, "parse_mode": "HTML"},
            timeout=15
        )
        data = r.json()
        if r.ok and data.get("ok"):
            return data["result"]["message_id"]
    except Exception as e:
        print(f"[TG PHOTO] {e}")
    return None


def send_text(msg, reply_to=None):
    payload = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML", "disable_web_page_preview": True}
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    try:
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json=payload, timeout=10)
        data = r.json()
        if r.ok and data.get("ok"):
            return data["result"]["message_id"]
        print(f"[TG] {r.status_code} {r.text[:100]}")
    except Exception as e:
        print(f"[TG] {e}")
    return None


# ── GAIN TRACKING ─────────────────────────────────────────────
def fetch_current(pair_addr):
    try:
        r = requests.get(f"https://api.dexscreener.com/latest/dex/pairs/solana/{pair_addr}", timeout=10)
        if not r.ok: return None
        pairs = r.json().get("pairs", [])
        if not pairs: return None
        p = pairs[0]
        return {
            "mcap":  p.get("marketCap", 0) or 0,
            "price": p.get("priceUsd", "0") or "0",
            "ch_h1": p.get("priceChange", {}).get("h1", 0) or 0,
            "vol_h1":p.get("volume", {}).get("h1", 0) or 0,
        }
    except: return None


def check_and_reply(pair_addr, mins):
    if pair_addr not in tracked: return
    t = tracked[pair_addr]
    c = fetch_current(pair_addr)
    if not c or c["mcap"] <= 0: return

    entry = t["entry_mcap"]
    curr  = c["mcap"]
    mult  = curr / entry if entry > 0 else 1

    # Only reply if 1.5x or more
    if mult < MIN_GAIN_FOR_REPLY: return

    pct = (mult - 1) * 100
    if mult >= 5:     perf = "🔥🔥🔥 MASSIVE RUNNER"
    elif mult >= 3:   perf = "🚀🚀 3X HIT"
    elif mult >= 2:   perf = "📈📈 2X HIT"
    else:             perf = "📈 1.5X+"

    try:    price_str = f"${float(c['price']):.8f}"
    except: price_str = "N/A"

    msg = (
        f"📊 <b>UPDATE — ${t['ticker']} ({mins}m)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{perf}\n\n"
        f"Entry: {fmt(entry)} → Now: {fmt(curr)}\n"
        f"+{pct:.0f}% ({mult:.2f}x) 🚀\n"
        f"Price: {price_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Take profit or trail stop — NFA</i>"
    )
    send_text(msg, reply_to=t["message_id"])
    print(f"[REPLY] {t['ticker']} {mins}m — {mult:.2f}x")


def schedule_updates(pair_addr):
    for delay in UPDATE_TIMES:
        def go(addr=pair_addr, mins=delay//60):
            time.sleep(delay)
            try: check_and_reply(addr, mins)
            except Exception as e: print(f"[UPDATE ERR] {e}")
        threading.Thread(target=go, daemon=True).start()


# ── HELPERS ───────────────────────────────────────────────────
def fmt(n):
    if not n: return "N/A"
    n = float(n)
    if n >= 1_000_000: return f"${n/1_000_000:.2f}M"
    if n >= 1_000:     return f"${n/1_000:.1f}K"
    return f"${n:.2f}"


def get_age(created_ts):
    if not created_ts: return "Unknown", 9999
    try:
        if created_ts > 1e12:
            dt = datetime.fromtimestamp(created_ts/1000, tz=timezone.utc)
        else:
            dt = datetime.fromtimestamp(created_ts, tz=timezone.utc)
        mins = int((datetime.now(tz=timezone.utc) - dt).total_seconds() / 60)
        return (f"{mins}m", mins) if mins < 60 else (f"{mins//60}h {mins%60}m", mins)
    except: return "Unknown", 9999


def is_blocked(name, ticker):
    combined = (name + " " + ticker).lower()
    return any(b in combined for b in BLOCKED)


# ── DATA SOURCES ─────────────────────────────────────────────

def fetch_pumpfun_new():
    """Newest coins from pump.fun sorted by creation time."""
    coins = []
    try:
        r = requests.get(
            "https://client-api-2-74b1891ee9f9.herokuapp.com/coins?offset=0&limit=50&sort=created_timestamp&order=DESC&includeNsfw=true",
            timeout=15
        )
        if r.ok:
            for c in r.json():
                coins.append(c)
            print(f"[PUMP NEW] {len(coins)} coins")
    except Exception as e:
        print(f"[PUMP NEW ERR] {e}")
    return coins


def fetch_pumpfun_trending():
    """Most actively traded pump.fun coins right now."""
    coins = []
    try:
        r = requests.get(
            "https://client-api-2-74b1891ee9f9.herokuapp.com/coins?offset=0&limit=50&sort=last_trade_timestamp&order=DESC&includeNsfw=true",
            timeout=15
        )
        if r.ok:
            for c in r.json():
                coins.append(c)
            print(f"[PUMP TREND] {len(coins)} coins")
    except Exception as e:
        print(f"[PUMP TREND ERR] {e}")
    return coins


def fetch_pumpfun_about_to_graduate():
    """Coins close to graduating (high market cap on pump.fun)."""
    coins = []
    try:
        r = requests.get(
            "https://client-api-2-74b1891ee9f9.herokuapp.com/coins?offset=0&limit=50&sort=market_cap&order=DESC&includeNsfw=true",
            timeout=15
        )
        if r.ok:
            for c in r.json():
                usd_mc = c.get("usd_market_cap", 0) or 0
                if 40_000 <= usd_mc <= 69_000:
                    coins.append(c)
            print(f"[PUMP GRAD] {len(coins)} about to graduate")
    except Exception as e:
        print(f"[PUMP GRAD ERR] {e}")
    return coins


def fetch_gmgn():
    """GMGN trending tokens — smart money tracked."""
    tokens = []
    try:
        r = requests.get(
            "https://gmgn.ai/defi/quotation/v1/rank/sol/swaps/1h?orderby=swaps&direction=desc&filters[]=not_wash_trade",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
                "Referer": "https://gmgn.ai/"
            },
            timeout=15
        )
        if r.ok:
            data = r.json()
            rank = data.get("data", {}).get("rank", [])
            for t in rank[:30]:
                tokens.append(t)
            print(f"[GMGN] {len(tokens)} tokens")
        else:
            print(f"[GMGN] {r.status_code}")
    except Exception as e:
        print(f"[GMGN ERR] {e}")
    return tokens


def fetch_dexscreener_new():
    """New Solana pairs from DexScreener."""
    pairs = []
    seen  = set()
    for q in ["new solana meme", "solana pump fun"]:
        try:
            r = requests.get(
                f"https://api.dexscreener.com/latest/dex/search/?q={q.replace(' ','+')}",
                timeout=15
            )
            if r.ok:
                for p in r.json().get("pairs", []):
                    if p.get("chainId") != "solana": continue
                    addr = p.get("pairAddress", "")
                    if addr and addr not in seen:
                        seen.add(addr)
                        pairs.append(p)
        except Exception as e:
            print(f"[DEX ERR] {e}")
        time.sleep(0.5)
    print(f"[DEX] {len(pairs)} pairs")
    return pairs


def fetch_graduated():
    """Recently graduated pump.fun coins on Raydium."""
    pairs = []
    try:
        r = requests.get(
            "https://api.dexscreener.com/latest/dex/search/?q=pump+fun+raydium+solana",
            timeout=15
        )
        if r.ok:
            for p in r.json().get("pairs", []):
                if p.get("chainId") != "solana": continue
                # Check if pair is very new (under 10 mins)
                created = p.get("pairCreatedAt", 0) or 0
                if created:
                    mins = int((time.time() - created/1000) / 60)
                    if mins <= 10:
                        pairs.append(p)
    except Exception as e:
        print(f"[GRAD ERR] {e}")
    print(f"[GRADUATED] {len(pairs)} recent graduates")
    return pairs


# ── SCORING ───────────────────────────────────────────────────
def score_pumpfun_coin(coin):
    """Score a pump.fun coin. Returns score 0-100 and signals."""
    score   = 0
    signals = []
    risks   = []

    usd_mc       = coin.get("usd_market_cap", 0) or 0
    virtual_sol  = coin.get("virtual_sol_reserves", 0) or 0
    real_sol     = coin.get("real_sol_reserves", 0) or 0
    reply_count  = coin.get("reply_count", 0) or 0
    complete     = coin.get("complete", False)
    twitter      = coin.get("twitter", "")
    telegram     = coin.get("telegram", "")
    website      = coin.get("website", "")
    description  = coin.get("description", "") or ""
    created_ts   = coin.get("created_timestamp", 0) or 0
    name         = coin.get("name", "?")
    symbol       = coin.get("symbol", "?")

    age_str, age_mins = get_age(created_ts)

    # Estimate liq from virtual reserves
    sol_price = 170
    liq_usd   = (virtual_sol / 1e9) * sol_price if virtual_sol else 0

    # Bonding curve progress (0-100%)
    bonding_pct = 0
    if virtual_sol > 0:
        # pump.fun starts at ~79 SOL virtual, graduation at ~120 SOL
        bonding_pct = min(100, ((virtual_sol / 1e9) / 120) * 100)

    # ── SCORING ──────────────────────────────────────────────

    # Age scoring — newer = more opportunity
    if age_mins <= 5:
        score += 20; signals.append("🆕 Under 5 mins old")
    elif age_mins <= 15:
        score += 15; signals.append(f"🆕 {age_mins}m old")
    elif age_mins <= 30:
        score += 10; signals.append(f"{age_mins}m old")
    elif age_mins <= 60:
        score += 5;  signals.append(f"{age_mins}m old")
    else:
        risks.append(f"⏰ {age_str} old")

    # Community engagement
    if reply_count >= 50:
        score += 20; signals.append(f"💬 {reply_count} replies 🔥")
    elif reply_count >= 20:
        score += 15; signals.append(f"💬 {reply_count} replies")
    elif reply_count >= 10:
        score += 10; signals.append(f"💬 {reply_count} replies")
    elif reply_count >= 5:
        score += 5;  signals.append(f"💬 {reply_count} replies")
    else:
        risks.append(f"💬 Only {reply_count} replies")

    # Bonding curve velocity
    if bonding_pct >= 80:
        score += 20; signals.append(f"🌋 {bonding_pct:.0f}% bonding — GRADUATING SOON")
    elif bonding_pct >= 60:
        score += 15; signals.append(f"📈 {bonding_pct:.0f}% bonding curve")
    elif bonding_pct >= 40:
        score += 10; signals.append(f"📈 {bonding_pct:.0f}% bonding curve")
    elif bonding_pct >= 20:
        score += 5;  signals.append(f"{bonding_pct:.0f}% bonding curve")

    # Socials
    social_count = sum([1 for s in [twitter, telegram, website] if s])
    if social_count >= 3:
        score += 15; signals.append("🌐 Full socials ✅")
    elif social_count == 2:
        score += 10; signals.append("🌐 2 socials")
    elif social_count == 1:
        score += 5;  signals.append("🌐 1 social")
    else:
        risks.append("⚠️ No socials")

    # Description quality
    if len(description) > 50:
        score += 5; signals.append("📝 Has description")

    # MC scoring
    if 5_000 <= usd_mc <= 30_000:
        score += 10; signals.append(f"💰 MC: {fmt(usd_mc)} (sweet spot)")
    elif usd_mc < 5_000:
        score += 5; risks.append(f"💰 Very low MC: {fmt(usd_mc)}")
    else:
        risks.append(f"💰 MC: {fmt(usd_mc)}")

    return min(score, 100), signals, risks, age_str, age_mins, liq_usd, bonding_pct


def score_dex_pair(pair):
    """Score a DexScreener pair."""
    score   = 0
    signals = []
    risks   = []

    mcap    = pair.get("marketCap", 0) or 0
    liq_usd = pair.get("liquidity", {}).get("usd", 0) or 0
    vol_h1  = pair.get("volume", {}).get("h1", 0) or 0
    ch_h1   = pair.get("priceChange", {}).get("h1", 0) or 0
    ch_h24  = pair.get("priceChange", {}).get("h24", 0) or 0
    h1txns  = pair.get("txns", {}).get("h1", {})
    buys    = h1txns.get("buys",  0)
    sells   = h1txns.get("sells", 0)
    total   = buys + sells
    created = pair.get("pairCreatedAt", 0) or 0

    age_str, age_mins = get_age(created)

    # Liquidity
    if liq_usd >= 10_000:
        score += 15; signals.append(f"💧 Liq: {fmt(liq_usd)} ✅")
    elif liq_usd >= 5_000:
        score += 10; signals.append(f"💧 Liq: {fmt(liq_usd)}")
    elif liq_usd >= 2_000:
        score += 5;  signals.append(f"💧 Liq: {fmt(liq_usd)}")
    elif liq_usd < 1_000:
        risks.append(f"⚠️ Very low liq: {fmt(liq_usd)}")

    # Buy pressure
    if total > 0:
        ratio = buys / total
        if ratio >= 0.70:   score += 20; signals.append(f"🟢 Buys {int(ratio*100)}%")
        elif ratio >= 0.60: score += 15; signals.append(f"🟡 Buys {int(ratio*100)}%")
        elif ratio >= 0.50: score += 8;  signals.append(f"Buys {int(ratio*100)}%")
        else:               risks.append(f"🔴 Buys only {int(ratio*100)}%")

    # Tx velocity
    if total >= 200:   score += 15; signals.append(f"⚡ {total} txns/hr")
    elif total >= 100: score += 10; signals.append(f"⚡ {total} txns/hr")
    elif total >= 50:  score += 5;  signals.append(f"{total} txns/hr")
    elif total >= 20:  score += 2;  signals.append(f"{total} txns/hr")

    # Price action
    if ch_h1 > 50:    score += 15; signals.append(f"🚀 +{ch_h1:.0f}% 1H")
    elif ch_h1 > 20:  score += 10; signals.append(f"📈 +{ch_h1:.0f}% 1H")
    elif ch_h1 > 0:   score += 5;  signals.append(f"+{ch_h1:.0f}% 1H")
    elif ch_h1 < -30: risks.append(f"📉 {ch_h1:.0f}% 1H")

    # Volume
    if vol_h1 > 50_000:  score += 15; signals.append(f"💰 ${vol_h1/1000:.0f}K vol/hr")
    elif vol_h1 > 20_000:score += 10; signals.append(f"💰 ${vol_h1/1000:.0f}K vol/hr")
    elif vol_h1 > 5_000: score += 5;  signals.append(f"${vol_h1/1000:.0f}K vol/hr")

    # Age bonus
    if age_mins <= 10:
        score += 10; signals.append("🆕 Under 10 mins")
    elif age_mins <= 30:
        score += 5;  signals.append(f"🆕 {age_mins}m old")

    return min(score, 100), signals, risks, age_str, age_mins, liq_usd, buys, sells


def score_gmgn_token(token):
    """Score a GMGN token."""
    score   = 0
    signals = []
    risks   = []

    swaps_1h     = token.get("swaps_1h",     0) or 0
    buy_vol_1h   = token.get("buy_volume_1h", 0) or 0
    sell_vol_1h  = token.get("sell_volume_1h",0) or 0
    price_change = token.get("price_change_percent", 0) or 0
    smart_buys   = token.get("smart_buy_24h", 0) or 0
    mcap         = token.get("market_cap",    0) or 0
    liq          = token.get("liquidity",     0) or 0

    if smart_buys >= 10:
        score += 30; signals.append(f"🧠 {smart_buys} smart money buys!")
    elif smart_buys >= 5:
        score += 20; signals.append(f"🧠 {smart_buys} smart buys")
    elif smart_buys >= 2:
        score += 10; signals.append(f"🧠 {smart_buys} smart buys")

    if swaps_1h >= 500:
        score += 20; signals.append(f"⚡ {swaps_1h} swaps/hr")
    elif swaps_1h >= 200:
        score += 15; signals.append(f"⚡ {swaps_1h} swaps/hr")
    elif swaps_1h >= 100:
        score += 10; signals.append(f"{swaps_1h} swaps/hr")

    if price_change > 50:
        score += 20; signals.append(f"🚀 +{price_change:.0f}%")
    elif price_change > 20:
        score += 10; signals.append(f"📈 +{price_change:.0f}%")
    elif price_change < -30:
        risks.append(f"📉 {price_change:.0f}%")

    total_vol = buy_vol_1h + sell_vol_1h
    if total_vol > 0:
        buy_ratio = buy_vol_1h / total_vol
        if buy_ratio >= 0.65:
            score += 15; signals.append(f"🟢 Buy vol {int(buy_ratio*100)}%")
        elif buy_ratio >= 0.50:
            score += 8;  signals.append(f"Buy vol {int(buy_ratio*100)}%")
        else:
            risks.append(f"Sell pressure {int((1-buy_ratio)*100)}%")

    return min(score, 100), signals, risks, liq


# ── RISK LABEL ────────────────────────────────────────────────
def risk_label(score):
    if score >= 75: return "🟢 LOW-MED RISK"
    if score >= 55: return "🟡 MEDIUM RISK"
    if score >= 35: return "🟠 HIGH RISK"
    return "🔴 VERY HIGH RISK"

def conviction_label(score):
    if score >= 80: return "🔴 SEND IT"
    if score >= 65: return "🟠 LOOKS LIVE"
    if score >= 50: return "🟡 ON THE RADAR"
    if score >= 35: return "👀 EARLY RADAR"
    return "⚪ LOW CONFIDENCE"

def potential_label(score, mc):
    if score >= 70:
        return f"🎯 HIGH POTENTIAL\n3x = {fmt(mc*3)} | 5x = {fmt(mc*5)} | 10x = {fmt(mc*10)}"
    elif score >= 45:
        return f"🎯 MODERATE POTENTIAL\n3x = {fmt(mc*3)} | 5x = {fmt(mc*5)}"
    else:
        return f"🎯 SPECULATIVE\n2x = {fmt(mc*2)} | 3x = {fmt(mc*3)}"


# ── BUILD & SEND ──────────────────────────────────────────────
def send_coin_alert(data):
    global last_alert_time

    score    = data["score"]
    name     = data["name"]
    ticker   = data["ticker"]
    mc       = data["mc"]
    liq      = data["liq"]
    age_str  = data["age_str"]
    addr     = data["addr"]
    pair_addr= data["pair_addr"]
    image    = data.get("image")
    signals  = data.get("signals", [])
    risks    = data.get("risks",   [])
    alert_type = data.get("type", "")
    description= data.get("description", "")
    twitter  = data.get("twitter", "")
    telegram_link = data.get("telegram", "")
    website  = data.get("website", "")
    bonding  = data.get("bonding_pct", 0)
    price    = data.get("price", "N/A")
    supply   = data.get("supply", "1B")
    buys     = data.get("buys", 0)
    sells    = data.get("sells", 0)

    conv  = conviction_label(score)
    risk  = risk_label(score)
    pot   = potential_label(score, mc)

    # Social links
    socials = []
    if twitter:       socials.append(f"<a href='{twitter}'>Twitter</a>")
    if telegram_link: socials.append(f"<a href='{telegram_link}'>Telegram</a>")
    if website:       socials.append(f"<a href='{website}'>Website</a>")
    soc_str = " | ".join(socials) if socials else "None ⚠️"

    # Signal/risk display
    sig_str  = "\n".join(signals[:4]) if signals else "—"
    risk_str = "\n".join(risks[:2])   if risks   else "—"

    # Type badge
    type_badge = {
        "new":      "🆕 JUST LAUNCHED",
        "trending": "🔥 TRENDING",
        "graduate": "🌋 ABOUT TO MIGRATE",
        "migrated": "⚡ JUST MIGRATED TO RAYDIUM",
        "gmgn":     "🧠 SMART MONEY ALERT",
        "dex":      "📊 DEX SCANNER",
        "forced":   "🔎 BEST AVAILABLE",
    }.get(alert_type, "📡 SCAN")

    # Short caption for image (under 1024 chars)
    short_cap = (
        f"{type_badge}\n"
        f"{conv} — {score}/100 | {risk}\n\n"
        f"<b>{name} | ${ticker}</b>\n"
        f"MC: {fmt(mc)} | Liq: {fmt(liq)} | Age: {age_str}\n"
        f"Price: {price}\n\n"
        f"{sig_str}"
    )

    # Full analysis as follow-up text
    bonding_str = f"🌋 Bonding: {bonding:.0f}%\n" if bonding > 0 else ""
    desc_str    = f"📝 {description[:100]}...\n\n" if len(description) > 20 else ""
    buysell_str = f"Buys: {buys} | Sells: {sells}\n" if buys or sells else ""

    dex_url     = f"https://dexscreener.com/solana/{pair_addr}"
    pump_url    = f"https://pump.fun/{addr}"
    rug_url     = f"https://rugcheck.xyz/tokens/{addr}"
    photon_url  = f"https://photon-sol.tinyastro.io/en/lp/{pair_addr}"
    bundle_url  = f"https://trench.bot/bundles/{addr}"

    full_msg = (
        f"{type_badge} — <b>{score}/100</b>\n"
        f"{conv} | {risk}\n\n"
        f"<b>{name} | ${ticker}</b>\n"
        f"{desc_str}"
        f"📋 <code>{addr}</code>\n\n"
        f"📦 Supply: {supply}\n"
        f"📊 MC: {fmt(mc)}\n"
        f"💧 Liq: {fmt(liq)}\n"
        f"🕐 Age: {age_str}\n"
        f"💲 Price: {price}\n"
        f"{bonding_str}\n"
        f"✅ <b>SIGNALS</b>\n{sig_str}\n\n"
        f"⚠️ <b>RISKS</b>\n{risk_str}\n\n"
        f"{buysell_str}"
        f"🌐 {soc_str}\n\n"
        f"{pot}\n\n"
        f"🔗 <a href='{dex_url}'>DEX</a> | "
        f"<a href='{pump_url}'>PUMP</a> | "
        f"<a href='{rug_url}'>RUG</a> | "
        f"<a href='{photon_url}'>PHOTON</a> | "
        f"<a href='{bundle_url}'>BUNDLE</a>\n\n"
        f"<i>NFA — DYOR — 99% go zero</i>\n"
        f"<i>📊 Reply if 1.5x+ at 10m/30m/1hr</i>"
    )

    # Send
    msg_id = None
    if image:
        msg_id = send_photo(image, short_cap)
        if msg_id:
            time.sleep(0.3)
            send_text(full_msg, reply_to=msg_id)
    if not msg_id:
        msg_id = send_text(full_msg)

    # Track
    alerted.add(pair_addr)
    alerted.add(addr)
    save_alerted(pair_addr)
    save_alerted(addr)
    last_alert_time = time.time()

    if msg_id:
        tracked[pair_addr] = {
            "ticker":     ticker,
            "entry_mcap": mc,
            "message_id": msg_id,
        }
        schedule_updates(pair_addr)

    print(f"[SENT] {ticker} {score}/100 [{alert_type}]")
    return msg_id


# ── MAIN SCAN ─────────────────────────────────────────────────
def scan():
    global last_alert_time
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Scanning...")

    all_coins = []  # (score, data_dict)

    # ── PUMP.FUN NEW ──────────────────────────────────────────
    for coin in fetch_pumpfun_new():
        name   = coin.get("name",   "?")
        ticker = coin.get("symbol", "?")
        mint   = coin.get("mint",   "")
        if not mint or mint in alerted: continue
        if is_blocked(name, ticker):    continue

        score, signals, risks, age_str, age_mins, liq_usd, bonding = score_pumpfun_coin(coin)
        mc = coin.get("usd_market_cap", 0) or 0

        price_raw = coin.get("price", 0) or 0
        try:    price_str = f"${float(price_raw):.8f}"
        except: price_str = "N/A"

        data = {
            "score": score, "name": name, "ticker": ticker,
            "mc": mc, "liq": liq_usd, "age_str": age_str,
            "addr": mint, "pair_addr": mint,
            "image": coin.get("image_uri"),
            "signals": signals, "risks": risks,
            "type": "new" if age_mins <= 10 else "trending",
            "description": coin.get("description",""),
            "twitter":  coin.get("twitter",""),
            "telegram": coin.get("telegram",""),
            "website":  coin.get("website",""),
            "bonding_pct": bonding,
            "price": price_str, "supply": "1B",
            "buys": 0, "sells": 0,
        }
        all_coins.append((score, data))

    # ── PUMP.FUN ABOUT TO GRADUATE ────────────────────────────
    for coin in fetch_pumpfun_about_to_graduate():
        name   = coin.get("name",   "?")
        ticker = coin.get("symbol", "?")
        mint   = coin.get("mint",   "")
        if not mint or mint in alerted: continue
        if is_blocked(name, ticker):    continue

        score, signals, risks, age_str, age_mins, liq_usd, bonding = score_pumpfun_coin(coin)
        score = min(100, score + 20)  # Bonus for being near graduation
        mc    = coin.get("usd_market_cap", 0) or 0

        data = {
            "score": score, "name": name, "ticker": ticker,
            "mc": mc, "liq": liq_usd, "age_str": age_str,
            "addr": mint, "pair_addr": mint,
            "image": coin.get("image_uri"),
            "signals": [f"🌋 {bonding:.0f}% bonding curve — GRADUATING SOON"] + signals,
            "risks": risks, "type": "graduate",
            "description": coin.get("description",""),
            "twitter":  coin.get("twitter",""),
            "telegram": coin.get("telegram",""),
            "website":  coin.get("website",""),
            "bonding_pct": bonding,
            "price": "N/A", "supply": "1B",
            "buys": 0, "sells": 0,
        }
        all_coins.append((score, data))

    # ── GMGN SMART MONEY ──────────────────────────────────────
    for token in fetch_gmgn():
        addr   = token.get("address", "")
        name   = token.get("name",    "?")
        ticker = token.get("symbol",  "?")
        if not addr or addr in alerted: continue
        if is_blocked(name, ticker):    continue

        mc  = token.get("market_cap", 0) or 0
        if mc > 500_000: continue  # Skip large caps

        score, signals, risks, liq = score_gmgn_token(token)
        price_raw = token.get("price", 0) or 0
        try:    price_str = f"${float(price_raw):.8f}"
        except: price_str = "N/A"

        data = {
            "score": score, "name": name, "ticker": ticker,
            "mc": mc, "liq": liq, "age_str": "N/A",
            "addr": addr, "pair_addr": addr,
            "image": token.get("logo", None),
            "signals": signals, "risks": risks,
            "type": "gmgn",
            "description": "",
            "twitter": "", "telegram": "", "website": "",
            "bonding_pct": 0,
            "price": price_str, "supply": "N/A",
            "buys": 0, "sells": 0,
        }
        all_coins.append((score, data))

    # ── DEXSCREENER ───────────────────────────────────────────
    for pair in fetch_dexscreener_new():
        pair_addr = pair.get("pairAddress", "")
        addr      = pair.get("baseToken", {}).get("address", "")
        name      = pair.get("baseToken", {}).get("name",    "?")
        ticker    = pair.get("baseToken", {}).get("symbol",  "?")
        if not pair_addr or pair_addr in alerted: continue
        if is_blocked(name, ticker):               continue

        mc = pair.get("marketCap", 0) or 0
        if mc > 200_000: continue
        if age_mins > 4320: continue  # max 3 days old

        score, signals, risks, age_str, age_mins, liq_usd, buys, sells = score_dex_pair(pair)
        price_raw = pair.get("priceUsd", "0") or "0"
        try:    price_str = f"${float(price_raw):.8f}"
        except: price_str = "N/A"

        # check socials from info
        info      = pair.get("info", {})
        twitter   = next((s.get("url","") for s in info.get("socials",[]) if "twitter" in s.get("type","").lower()), "")
        telegram  = next((s.get("url","") for s in info.get("socials",[]) if "telegram" in s.get("type","").lower()), "")
        website   = info.get("websites",[{}])[0].get("url","") if info.get("websites") else ""

        alert_type = "migrated" if age_mins <= 10 else "dex"

        data = {
            "score": score, "name": name, "ticker": ticker,
            "mc": mc, "liq": liq_usd, "age_str": age_str,
            "addr": addr, "pair_addr": pair_addr,
            "image": info.get("imageUrl", None),
            "signals": signals, "risks": risks,
            "type": alert_type,
            "description": "",
            "twitter": twitter, "telegram": telegram, "website": website,
            "bonding_pct": 0,
            "price": price_str, "supply": "N/A",
            "buys": buys, "sells": sells,
        }
        all_coins.append((score, data))

    # ── SORT & SEND ───────────────────────────────────────────
    all_coins.sort(key=lambda x: x[0], reverse=True)
    print(f"[SCAN] {len(all_coins)} candidates total")

    sent = 0

    # Send top coins that score 40+
    for score, data in all_coins:
        if sent >= 3: break  # Max 3 per scan
        if score < 40: break
        pair_addr = data["pair_addr"]
        addr      = data["addr"]
        if pair_addr in alerted or addr in alerted: continue
        send_coin_alert(data)
        sent += 1
        time.sleep(1)

    # If nothing sent and 2+ mins since last alert, send best available (any score)
    if sent == 0:
        time_since = time.time() - last_alert_time
        if time_since >= SCAN_INTERVAL and all_coins:
            # Find best non-alerted coin regardless of score
            for score, data in all_coins:
                pair_addr = data["pair_addr"]
                addr      = data["addr"]
                if pair_addr in alerted or addr in alerted: continue
                data["type"] = "forced"
                send_coin_alert(data)
                sent += 1
                break

    if sent == 0:
        print("[SCAN] Nothing to send")
    else:
        print(f"[SCAN] Sent {sent}")


# ── STARTUP ───────────────────────────────────────────────────
def startup():
    send_text(
        "🤖 <b>CHAINSCAN BOT ONLINE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Sources: Pump.fun + GMGN + DexScreener\n"
        "🆕 New launches scored live\n"
        "🧠 Smart money tracking (GMGN)\n"
        "🌋 Pre-migration alerts\n"
        "⚡ Post-migration (first 5 mins)\n"
        "📊 Every score shown — high & low risk\n"
        "💬 Replies ONLY if 1.5x+\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🟢 Live. Alerts every 2 mins."
    )


if __name__ == "__main__":
    print("="*50)
    print("  CHAINSCAN — Solana Scanner")
    print("="*50)
    startup()
    while True:
        try:
            scan()
        except Exception as e:
            print(f"[MAIN ERR] {e}")
        print(f"[SLEEP] {SCAN_INTERVAL}s")
        time.sleep(SCAN_INTERVAL)