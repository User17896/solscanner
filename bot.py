import requests
import time
import re
from datetime import datetime, timezone

# ============================================================
#  CONFIG
# ============================================================
import os
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8739546604:AAE_TY1c9MPXarPrQFLLi1PBMYFdRjaEF_A")
CHAT_ID        = os.environ.get("CHAT_ID", "5959009671")
SCAN_INTERVAL  = 120  # 2 minutes
# ============================================================

# Meta categories with context
META_CONTEXT = {
    # Tier 1 — hottest
    "pepe":   ("🐸 Frog meta", "PEPE still one of the strongest meme narratives. Frog coins historically run hard in bull cycles."),
    "frog":   ("🐸 Frog meta", "Frog meta coins consistently outperform. Strong community culture on X."),
    "wojak":  ("😭 Wojak meta", "Wojak/feels meta has loyal community. Tends to pump when broader meme season is hot."),
    "trump":  ("🇺🇸 Political meta", "Political meme coins are explosive right now. High volatility, high upside."),
    "maga":   ("🇺🇸 Political meta", "MAGA coins riding political narrative. Fast pumps but watch exit timing."),
    "elon":   ("⚡ Elon meta", "Elon-themed coins get viral traction fast. One tweet can 10x these."),
    "doge":   ("🐶 Doge meta", "OG meme narrative. Still one of the most recognised meme categories globally."),
    "ai":     ("🤖 AI meta", "AI tokens are the hottest narrative in crypto right now. Strong institutional and retail interest."),
    "agent":  ("🤖 AI Agent meta", "AI agent tokens exploding in 2025. Autonomous treasury mechanics driving speculation."),
    "gpt":    ("🤖 AI meta", "GPT-branded tokens ride the AI hype cycle hard. Fast entry, fast exit needed."),
    "chad":   ("💪 Chad meta", "Chad/sigma meme culture strong on X. Younger crypto demographic loves this narrative."),
    "sigma":  ("💪 Sigma meta", "Sigma meme narrative popular with retail. Viral potential if branding is strong."),
    # Tier 2
    "cat":    ("🐱 Cat meta", "Cat coins had massive runs recently. Strong rival to dog coins for meme dominance."),
    "dog":    ("🐶 Dog meta", "Dog meta is evergreen in crypto. Deep retail familiarity drives volume."),
    "inu":    ("🐶 Inu meta", "Inu coins have proven track record. SHIB showed the ceiling is very high."),
    "baby":   ("👶 Baby meta", "Baby prefix coins often ride parent token narratives. Watch parent token price action."),
    "moon":   ("🌙 Moon meta", "Classic crypto branding. Retail friendly, easy to understand narrative."),
    "based":  ("🔵 Based meta", "Based culture strong in crypto Twitter. Coinbase ecosystem association helps."),
    "bonk":   ("🐶 BONK meta", "BONK is the OG Solana meme. Tokens riding BONK narrative benefit from ecosystem loyalty."),
    "wif":    ("🐶 WIF meta", "WIF proved Solana memes can reach billions. Similar tokens get speculative premium."),
    "pump":   ("🚀 Pump meta", "Pump.fun launched token — native to the hottest Solana launchpad. High visibility."),
    "giga":   ("💪 Gigabrain meta", "Gigabrain/giga culture popular in DeFi circles. Niche but loyal community."),
    "turbo":  ("⚡ Turbo meta", "Turbo branding popular for high-energy meme coins. Fast pump potential."),
    "ape":    ("🦍 Ape meta", "Ape culture deeply embedded in crypto. NFT crossover audience adds depth."),
    "bear":   ("🐻 Bear meta", "Contrarian narrative. Can pump hard when market sentiment shifts."),
    "bull":   ("🐂 Bull meta", "Bull meta coins ride market sentiment. Strong in uptrends."),
    "sol":    ("☀️ Solana ecosystem", "Native Solana narrative. Benefits from SOL price action and ecosystem growth."),
    "fire":   ("🔥 Fire meta", "High energy branding. Viral potential if meme format catches on X."),
    "king":   ("👑 King meta", "Royalty branding has proven appeal. Easy meme format for X virality."),
    "rich":   ("💰 Wealth meta", "Aspirational narrative resonates with retail. Strong emotional hook."),
    "zeus":   ("⚡ Zeus meta", "Mythology meta gaining traction. Distinctive branding stands out."),
    "god":    ("🙏 God meta", "Bold branding gets attention. Memorable ticker if short enough."),
}

DEFAULT_NARRATIVE = ("🎰 Unclassified", "New token with no established meta. Pure momentum play — entry and exit timing is everything.")

alerted = set()


# ── TELEGRAM ─────────────────────────────────────────────────
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


# ── FETCH PAIRS ───────────────────────────────────────────────
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
                print(f"[DEX ERROR] {r.status_code}")
                continue
            for p in r.json().get("pairs", []):
                addr = p.get("pairAddress", "")
                if addr and addr not in seen:
                    seen.add(addr)
                    all_pairs.append(p)
        except Exception as e:
            print(f"[FETCH ERROR] {e}")
        time.sleep(1)
    return all_pairs


# ── SIMILAR TOKENS CHECK ──────────────────────────────────────
def find_similar_runners(keyword):
    """Check if similar tokens are pumping right now."""
    try:
        r = requests.get(
            f"https://api.dexscreener.com/latest/dex/search/?q={keyword}+solana",
            headers={"Accept": "application/json"},
            timeout=10
        )
        if not r.ok:
            return None
        pairs = r.json().get("pairs", [])
        runners = []
        for p in pairs:
            if p.get("chainId") != "solana":
                continue
            ch24 = p.get("priceChange", {}).get("h24", 0) or 0
            mcap = p.get("marketCap", 0) or 0
            if ch24 > 50 and mcap > 10000:
                runners.append(ch24)
        if runners:
            avg = sum(runners) / len(runners)
            return len(runners), avg
        return None
    except:
        return None


# ── SOCIAL CHECK ─────────────────────────────────────────────
def check_socials(pair):
    """Extract social links from pair data."""
    info     = pair.get("info", {})
    socials  = info.get("socials", [])
    websites = info.get("websites", [])

    twitter  = None
    telegram = None
    website  = None

    for s in socials:
        stype = s.get("type", "").lower()
        url   = s.get("url", "")
        if "twitter" in stype or "x.com" in url.lower():
            twitter  = url
        if "telegram" in stype:
            telegram = url

    if websites:
        website = websites[0].get("url", None)

    return twitter, telegram, website


# ── RUGCHECK ─────────────────────────────────────────────────
def get_rugcheck(token_address):
    try:
        r = requests.get(
            f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report/summary",
            timeout=10
        )
        if not r.ok:
            return {}
        data  = r.json()
        risks = data.get("risks", [])
        mint_ok = freeze_ok = True
        for risk in risks:
            name  = risk.get("name",  "").lower()
            level = risk.get("level", "").lower()
            if "mint"   in name and level in ["warn", "danger"]:
                mint_ok   = False
            if "freeze" in name and level == "danger":
                freeze_ok = False
        return {"mint_ok": mint_ok, "freeze_ok": freeze_ok}
    except:
        return {}


# ── NARRATIVE ────────────────────────────────────────────────
def get_narrative(name, ticker, keyword_matched):
    """Build a rich narrative with similar token data."""
    combined = (name + " " + ticker).lower()

    # Find best matching meta
    best_key     = None
    best_context = None
    for kw, ctx in META_CONTEXT.items():
        if kw in combined:
            best_key     = kw
            best_context = ctx
            break

    if not best_context:
        return DEFAULT_NARRATIVE[0], DEFAULT_NARRATIVE[1], None

    meta_label, meta_desc = best_context

    # Check similar runners
    runner_data = find_similar_runners(best_key)
    runner_str  = None
    if runner_data:
        count, avg = runner_data
        runner_str = f"{count} similar tokens up avg +{avg:.0f}% today 🔥"

    return meta_label, meta_desc, runner_str


# ── SCORING ───────────────────────────────────────────────────
def score_narrative_num(name, ticker):
    combined = (name + " " + ticker).lower()
    score    = 0
    matched  = []
    for kw in META_CONTEXT:
        if kw in combined:
            score  += 20
            matched.append(kw)
    return min(score, 40), matched


def score_momentum(pair):
    score = 0
    signals  = []
    txns     = pair.get("txns", {})
    h1       = txns.get("h1", {})
    buys_h1  = h1.get("buys",  0)
    sells_h1 = h1.get("sells", 0)
    total_h1 = buys_h1 + sells_h1
    vol_h1   = pair.get("volume", {}).get("h1", 0) or 0
    ch_h1    = pair.get("priceChange", {}).get("h1", 0) or 0

    if total_h1 > 0:
        ratio = buys_h1 / total_h1
        if ratio >= 0.70:   score += 15; signals.append(f"🟢 Buys {int(ratio*100)}%")
        elif ratio >= 0.60: score += 10; signals.append(f"🟡 Buys {int(ratio*100)}%")
        elif ratio >= 0.55: score += 5;  signals.append(f"Buys {int(ratio*100)}%")
        else:               signals.append(f"🔴 Buys only {int(ratio*100)}%")

    if total_h1 >= 200:   score += 10; signals.append(f"⚡ {total_h1} txns/hr")
    elif total_h1 >= 100: score += 7;  signals.append(f"⚡ {total_h1} txns/hr")
    elif total_h1 >= 50:  score += 4;  signals.append(f"{total_h1} txns/hr")
    elif total_h1 >= 20:  score += 2;  signals.append(f"{total_h1} txns/hr (low)")

    if ch_h1 > 50:    score += 10; signals.append(f"🚀 +{ch_h1:.0f}% 1H")
    elif ch_h1 > 20:  score += 7;  signals.append(f"📈 +{ch_h1:.0f}% 1H")
    elif ch_h1 > 0:   score += 3;  signals.append(f"+{ch_h1:.0f}% 1H")
    elif ch_h1 < -20: score -= 5;  signals.append(f"📉 {ch_h1:.0f}% 1H")

    if vol_h1 > 50000:  score += 10; signals.append(f"💰 ${vol_h1/1000:.0f}K vol/hr")
    elif vol_h1 > 20000:score += 7;  signals.append(f"💰 ${vol_h1/1000:.0f}K vol/hr")
    elif vol_h1 > 5000: score += 4;  signals.append(f"${vol_h1/1000:.0f}K vol/hr")

    return min(score, 35), signals, buys_h1, sells_h1


def score_liquidity(pair):
    liq_usd = pair.get("liquidity", {}).get("usd", 0) or 0
    mcap    = pair.get("marketCap", 0) or pair.get("fdv", 0) or 1
    if liq_usd < 2000:
        return -999, liq_usd
    ratio = (liq_usd / mcap) * 100
    if ratio >= 25:   score = 25
    elif ratio >= 15: score = 18
    elif ratio >= 10: score = 12
    elif ratio >= 5:  score = 5
    else:             score = 0
    return min(score, 25), liq_usd


# ── FORMAT ────────────────────────────────────────────────────
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
        return (f"{mins}m", mins) if mins < 60 else (f"{mins//60}h {mins%60}m", mins)
    except:
        return "Unknown", 9999


# ── MAIN SCAN ─────────────────────────────────────────────────
def scan_and_alert():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🔍 Scanning...")
    pairs = fetch_pairs()
    print(f"[SCAN] {len(pairs)} pairs")

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
        narr_score, narr_matched = score_narrative_num(name, ticker)
        total_score = liq_score + mom_score + narr_score

        if total_score < 45:
            continue

        rug = get_rugcheck(token_addr) if token_addr else {}

        candidates.append({
            "pair": pair, "score": total_score,
            "mom_signals": mom_signals, "narr_matched": narr_matched,
            "age_str": age_str, "age_mins": age_mins,
            "mcap": mcap, "liq_usd": liq_usd,
            "ticker": ticker, "name": name,
            "pair_addr": pair_addr, "token_addr": token_addr,
            "buys_h1": buys_h1, "sells_h1": sells_h1, "rug": rug,
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

        vol    = pair.get("volume", {})
        vol_h1 = vol.get("h1",  0) or 0
        vol_h24= vol.get("h24", 0) or 0
        ch     = pair.get("priceChange", {})
        ch_h1  = ch.get("h1",  0) or 0
        ch_h24 = ch.get("h24", 0) or 0

        liq_pct = f"{(liq_usd/mcap*100):.0f}%" if mcap > 0 else "?"
        liq_sol = f"{(liq_usd/170):.1f} SOL" if liq_usd else "?"

        supply = pair.get("baseToken", {}).get("totalSupply", "N/A")
        if supply and supply != "N/A":
            try:
                s = float(supply)
                supply = f"{s/1e9:.0f}B" if s>=1e9 else f"{s/1e6:.0f}M" if s>=1e6 else str(s)
            except: supply = "N/A"

        mint_icon   = "✅ Disabled" if rug.get("mint_ok",   False) else "❌ Active"
        freeze_icon = "✅ Disabled" if rug.get("freeze_ok", False) else "❌ Active"

        # Rich narrative
        meta_label, meta_desc, runner_str = get_narrative(name, ticker, c["narr_matched"])

        # Socials
        twitter, telegram_link, website = check_socials(pair)
        social_parts = []
        if twitter:        social_parts.append(f"<a href='{twitter}'>X/Twitter</a>")
        if telegram_link:  social_parts.append(f"<a href='{telegram_link}'>Telegram</a>")
        if website:        social_parts.append(f"<a href='{website}'>Website</a>")
        socials_str = " | ".join(social_parts) if social_parts else "No socials found ⚠️"

        total_h1 = buys_h1 + sells_h1
        buy_pct  = f"{int(buys_h1/total_h1*100)}%" if total_h1 > 0 else "?"
        sell_pct = f"{int(sells_h1/total_h1*100)}%" if total_h1 > 0 else "?"

        mom_str = "\n".join(c["mom_signals"][:3]) if c["mom_signals"] else "Low momentum"

        dex_url      = f"https://dexscreener.com/solana/{pair_addr}"
        rugcheck_url = f"https://rugcheck.xyz/tokens/{token_addr}" if token_addr else "https://rugcheck.xyz"
        photon_url   = f"https://photon-sol.tinyastro.io/en/lp/{pair_addr}"
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
            f"🔥 LP STATUS: ❌ Not Burned\n"
            f"\n"
            f"🎯 <b>NARRATIVE: {meta_label}</b>\n"
            f"{meta_desc}\n"
            + (f"📊 {runner_str}\n" if runner_str else "")
            + f"\n"
            f"🌐 SOCIALS: {socials_str}\n"
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
        print(f"[SCAN] {sent} alerts sent")


def send_startup():
    send_telegram(
        "🤖 <b>CHAINSCAN BOT ONLINE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Scanning Solana micro-cap runners\n"
        "MC filter: Under $100K\n"
        "Scan: Every 2 mins\n"
        "Min score: 45/100\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🟢 Bot is live. Alerts incoming."
    )


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
        print(f"[SLEEP] {SCAN_INTERVAL}s...")
        time.sleep(SCAN_INTERVAL)