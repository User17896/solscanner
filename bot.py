import requests
import time
import os
import threading
from datetime import datetime, timezone

# ============================================================
#  CONFIG
# ============================================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8739546604:AAE_TY1c9MPXarPrQFLLi1PBMYFdRjaEF_A")
CHAT_ID        = os.environ.get("CHAT_ID", "5959009671")
SCAN_INTERVAL        = 120   # scan every 2 mins
BEST_AVAILABLE_EVERY = 600   # force send best coin every 10 mins if nothing passed
UPDATE_TIMES         = [600, 1800, 3600]  # reply updates at 10m, 30m, 1hr
# ============================================================

ALERTED_FILE = "/tmp/alerted_pairs.txt"

def load_alerted():
    try:
        if os.path.exists(ALERTED_FILE):
            with open(ALERTED_FILE, "r") as f:
                return set(line.strip() for line in f if line.strip())
    except: pass
    return set()

def save_alerted(pair_addr):
    try:
        with open(ALERTED_FILE, "a") as f:
            f.write(pair_addr + "\n")
    except: pass

alerted = load_alerted()
tracked  = {}
last_forced_alert = 0

META_CONTEXT = {
    "pepe":   ("🐸 Frog meta",        "PEPE still one of the strongest meme narratives. Frog coins historically run hard in bull cycles."),
    "frog":   ("🐸 Frog meta",        "Frog meta coins consistently outperform. Strong community culture on X."),
    "wojak":  ("😭 Wojak meta",       "Wojak/feels meta has loyal community. Tends to pump when broader meme season is hot."),
    "trump":  ("🇺🇸 Political meta",  "Political meme coins explosive right now. High volatility, high upside."),
    "maga":   ("🇺🇸 Political meta",  "MAGA coins riding political narrative. Fast pumps but watch exit timing."),
    "elon":   ("⚡ Elon meta",        "Elon-themed coins get viral traction fast. One tweet can 10x these."),
    "doge":   ("🐶 Doge meta",        "OG meme narrative. Still one of the most recognised meme categories globally."),
    "ai":     ("🤖 AI meta",          "AI tokens are the hottest narrative in crypto right now."),
    "agent":  ("🤖 AI Agent meta",    "AI agent tokens exploding. Autonomous treasury mechanics driving speculation."),
    "gpt":    ("🤖 AI meta",          "GPT-branded tokens ride the AI hype cycle hard. Fast entry, fast exit needed."),
    "chad":   ("💪 Chad meta",        "Chad/sigma meme culture strong on X. Younger crypto demographic loves this."),
    "sigma":  ("💪 Sigma meta",       "Sigma meme narrative popular with retail. Viral potential if branding is strong."),
    "cat":    ("🐱 Cat meta",         "Cat coins had massive runs recently. Strong rival to dog coins."),
    "dog":    ("🐶 Dog meta",         "Dog meta is evergreen in crypto. Deep retail familiarity drives volume."),
    "inu":    ("🐶 Inu meta",         "Inu coins have proven track record. SHIB showed the ceiling is very high."),
    "baby":   ("👶 Baby meta",        "Baby prefix coins often ride parent token narratives."),
    "moon":   ("🌙 Moon meta",        "Classic crypto branding. Retail friendly, easy to understand narrative."),
    "based":  ("🔵 Based meta",       "Based culture strong in crypto Twitter. Coinbase ecosystem association helps."),
    "bonk":   ("🐶 BONK meta",        "BONK is the OG Solana meme. Strong ecosystem loyalty."),
    "wif":    ("🐶 WIF meta",         "WIF proved Solana memes can reach billions. Similar tokens get speculative premium."),
    "pump":   ("🚀 Pump meta",        "Pump.fun launched token — native to the hottest Solana launchpad."),
    "giga":   ("💪 Gigabrain meta",   "Gigabrain/giga culture popular in DeFi circles. Niche but loyal community."),
    "turbo":  ("⚡ Turbo meta",       "Turbo branding popular for high-energy meme coins. Fast pump potential."),
    "ape":    ("🦍 Ape meta",         "Ape culture deeply embedded in crypto. NFT crossover audience adds depth."),
    "bull":   ("🐂 Bull meta",        "Bull meta coins ride market sentiment. Strong in uptrends."),
    "sol":    ("☀️ Solana ecosystem", "Native Solana narrative. Benefits from SOL price action and ecosystem growth."),
    "fire":   ("🔥 Fire meta",        "High energy branding. Viral potential if meme format catches on X."),
    "king":   ("👑 King meta",        "Royalty branding has proven appeal. Easy meme format for X virality."),
    "rich":   ("💰 Wealth meta",      "Aspirational narrative resonates with retail. Strong emotional hook."),
    "zeus":   ("⚡ Zeus meta",        "Mythology meta gaining traction. Distinctive branding stands out."),
    "god":    ("🙏 God meta",         "Bold branding gets attention. Memorable ticker if short enough."),
}
DEFAULT_NARRATIVE = ("🎰 Unclassified", "New token with no established meta. Pure momentum play.")


# ── TELEGRAM ─────────────────────────────────────────────────
def send_telegram(message, reply_to=None):
    url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id":    CHAT_ID,
        "text":       message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    try:
        r    = requests.post(url, json=payload, timeout=10)
        data = r.json()
        if r.ok and data.get("ok"):
            return data["result"]["message_id"]
        else:
            print(f"[TG ERROR] {r.status_code} — {r.text[:200]}")
    except Exception as e:
        print(f"[TG EXCEPTION] {e}")
    return None


# ── FETCH CURRENT PRICE ───────────────────────────────────────
def fetch_current_data(pair_addr):
    try:
        r = requests.get(
            f"https://api.dexscreener.com/latest/dex/pairs/solana/{pair_addr}",
            headers={"Accept": "application/json"}, timeout=10
        )
        if not r.ok: return None
        pairs = r.json().get("pairs", [])
        if not pairs: return None
        p = pairs[0]
        return {
            "mcap":     p.get("marketCap", 0) or 0,
            "price":    p.get("priceUsd",  "0") or "0",
            "vol_h1":   p.get("volume", {}).get("h1", 0) or 0,
            "ch_h1":    p.get("priceChange", {}).get("h1",  0) or 0,
            "ch_h24":   p.get("priceChange", {}).get("h24", 0) or 0,
            "buys_h1":  p.get("txns", {}).get("h1", {}).get("buys",  0),
            "sells_h1": p.get("txns", {}).get("h1", {}).get("sells", 0),
        }
    except Exception as e:
        print(f"[PRICE FETCH ERROR] {e}")
        return None


# ── GAIN UPDATE ───────────────────────────────────────────────
def send_gain_update(pair_addr, minutes_elapsed):
    if pair_addr not in tracked: return
    t       = tracked[pair_addr]
    current = fetch_current_data(pair_addr)
    if not current or current["mcap"] <= 0: return

    entry_mcap   = t["entry_mcap"]
    current_mcap = current["mcap"]
    pct_change   = ((current_mcap - entry_mcap) / entry_mcap * 100) if entry_mcap > 0 else 0
    multiplier   = (current_mcap / entry_mcap) if entry_mcap > 0 else 1

    if multiplier >= 5:     perf = "🔥🔥🔥 MASSIVE RUNNER"
    elif multiplier >= 3:   perf = "🚀🚀 3X+ HIT"
    elif multiplier >= 2:   perf = "📈📈 2X HIT"
    elif multiplier >= 1.5: perf = "📈 +50% GAIN"
    elif multiplier >= 1.1: perf = "🟡 Slight gain"
    elif multiplier >= 0.8: perf = "🔴 Down from entry"
    else:                   perf = "💀 Dumped hard"

    try:    price_str = f"${float(current['price']):.8f}"
    except: price_str = "N/A"

    total_h1 = current["buys_h1"] + current["sells_h1"]
    buy_pct  = f"{int(current['buys_h1']/total_h1*100)}%" if total_h1 > 0 else "?"

    msg = (
        f"📊 <b>UPDATE — ${t['ticker']} ({minutes_elapsed} mins)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{perf}\n\n"
        f"Entry MC:   {fmt(entry_mcap)}\n"
        f"Current MC: {fmt(current_mcap)}\n"
        f"Change: {'+' if pct_change>=0 else ''}{pct_change:.0f}% ({multiplier:.2f}x)\n"
        f"Price: {price_str}\n\n"
        f"1H: {'+' if current['ch_h1']>=0 else ''}{current['ch_h1']:.0f}% | "
        f"Vol 1H: {fmt(current['vol_h1'])}\n"
        f"Buy pressure: {buy_pct}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>NFA — take profit if up, cut if down</i>"
    )
    send_telegram(msg, reply_to=t["message_id"])
    print(f"[UPDATE] {t['ticker']} {minutes_elapsed}min — {multiplier:.2f}x")


def schedule_updates(pair_addr):
    for delay in UPDATE_TIMES:
        def send_update(addr=pair_addr, mins=delay//60):
            time.sleep(delay)
            try:
                send_gain_update(addr, mins)
                if addr in tracked:
                    tracked[addr]["updates_sent"] += 1
            except Exception as e:
                print(f"[UPDATE ERROR] {e}")
        threading.Thread(target=send_update, daemon=True).start()


# ── DATA SOURCES ─────────────────────────────────────────────
def fetch_dexscreener():
    queries = ["solana pump", "new solana", "meme solana", "solana token"]
    pairs   = []
    seen    = set()
    for q in queries:
        try:
            r = requests.get(
                f"https://api.dexscreener.com/latest/dex/search/?q={q.replace(' ','+')}",
                headers={"Accept": "application/json"}, timeout=15
            )
            if r.ok:
                for p in r.json().get("pairs", []):
                    addr = p.get("pairAddress", "")
                    if addr and addr not in seen:
                        seen.add(addr); pairs.append(p)
            else:
                print(f"[DEX] {r.status_code}")
        except Exception as e:
            print(f"[DEX ERROR] {e}")
        time.sleep(0.5)
    return pairs


def fetch_geckoterminal():
    pairs   = []
    seen    = set()
    headers = {"Accept": "application/json;version=20230302"}
    for url in [
        "https://api.geckoterminal.com/api/v2/networks/solana/new_pools?page=1",
        "https://api.geckoterminal.com/api/v2/networks/solana/trending_pools?page=1",
    ]:
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if not r.ok: continue
            for pool in r.json().get("data", []):
                attr = pool.get("attributes", {})
                addr = pool.get("id", "").replace("solana_", "")
                if not addr or addr in seen: continue
                seen.add(addr)
                base_name = attr.get("name", "").split(" / ")[0]
                try:    mcap = float(attr.get("market_cap_usd") or 0)
                except: mcap = 0
                try:    liq  = float(attr.get("reserve_in_usd") or 0)
                except: liq  = 0
                vol = attr.get("volume_usd", {})
                pch = attr.get("price_change_percentage", {})
                created_at = attr.get("pool_created_at")
                created_ts = None
                if created_at:
                    try:
                        dt = datetime.fromisoformat(created_at.replace("Z","+00:00"))
                        created_ts = int(dt.timestamp()*1000)
                    except: pass
                pairs.append({
                    "chainId": "solana", "pairAddress": addr,
                    "baseToken": {"symbol": base_name[:10], "name": base_name, "address": ""},
                    "marketCap": mcap, "liquidity": {"usd": liq},
                    "volume":    {"h1": float(vol.get("h1",0) or 0), "h24": float(vol.get("h24",0) or 0)},
                    "priceChange":{"h1": float(pch.get("h1",0) or 0), "h24": float(pch.get("h24",0) or 0)},
                    "priceUsd":  attr.get("base_token_price_usd","0"),
                    "pairCreatedAt": created_ts,
                    "txns": {"h1":{"buys":0,"sells":0},"h24":{"buys":0,"sells":0}},
                    "info": {},
                })
        except Exception as e:
            print(f"[GECKO ERROR] {e}")
        time.sleep(0.5)
    return pairs


def fetch_all_pairs():
    print("[FETCH] Querying all sources...")
    seen = set(); pairs = []
    for p in fetch_dexscreener() + fetch_geckoterminal():
        addr = p.get("pairAddress","")
        if addr and addr not in seen:
            seen.add(addr); pairs.append(p)
    print(f"[FETCH] {len(pairs)} unique pairs")
    return pairs


# ── RUGCHECK ─────────────────────────────────────────────────
def get_rugcheck(token_address):
    if not token_address: return {}
    try:
        r = requests.get(f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report/summary", timeout=10)
        if not r.ok: return {}
        risks = r.json().get("risks",[])
        mint_ok = freeze_ok = True
        for risk in risks:
            n = risk.get("name","").lower(); l = risk.get("level","").lower()
            if "mint"   in n and l in ["warn","danger"]: mint_ok   = False
            if "freeze" in n and l == "danger":          freeze_ok = False
        return {"mint_ok": mint_ok, "freeze_ok": freeze_ok}
    except: return {}


# ── NARRATIVE ────────────────────────────────────────────────
def get_narrative(name, ticker):
    combined = (name+" "+ticker).lower()
    for kw,(label,desc) in META_CONTEXT.items():
        if kw in combined:
            runner_str = None
            try:
                r = requests.get(
                    f"https://api.dexscreener.com/latest/dex/search/?q={kw}+solana",
                    headers={"Accept":"application/json"}, timeout=10
                )
                if r.ok:
                    runners = [p.get("priceChange",{}).get("h24",0) or 0
                               for p in r.json().get("pairs",[])
                               if p.get("chainId")=="solana"
                               and (p.get("priceChange",{}).get("h24",0) or 0) > 50
                               and (p.get("marketCap",0) or 0) > 10000]
                    if runners:
                        runner_str = f"{len(runners)} similar tokens up avg +{sum(runners)/len(runners):.0f}% today 🔥"
            except: pass
            return label, desc, runner_str
    return DEFAULT_NARRATIVE[0], DEFAULT_NARRATIVE[1], None


# ── SOCIALS ───────────────────────────────────────────────────
def check_socials(pair):
    info = pair.get("info",{})
    twitter = telegram_link = website = None
    for s in info.get("socials",[]):
        t = s.get("type","").lower(); u = s.get("url","")
        if "twitter" in t or "x.com" in u.lower(): twitter       = u
        if "telegram" in t:                         telegram_link = u
    ws = info.get("websites",[])
    if ws: website = ws[0].get("url")
    return twitter, telegram_link, website


# ── SCORING ───────────────────────────────────────────────────
def score_narrative_num(name, ticker):
    combined = (name+" "+ticker).lower()
    return 20 if any(kw in combined for kw in META_CONTEXT) else 0


def score_momentum(pair):
    score = 0; signals = []
    h1       = pair.get("txns",{}).get("h1",{})
    buys_h1  = h1.get("buys",  0)
    sells_h1 = h1.get("sells", 0)
    total_h1 = buys_h1 + sells_h1
    vol_h1   = pair.get("volume",{}).get("h1",0) or 0
    ch_h1    = pair.get("priceChange",{}).get("h1",0) or 0

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

    if vol_h1 > 50000:   score += 10; signals.append(f"💰 ${vol_h1/1000:.0f}K vol/hr")
    elif vol_h1 > 20000: score += 7;  signals.append(f"💰 ${vol_h1/1000:.0f}K vol/hr")
    elif vol_h1 > 5000:  score += 4;  signals.append(f"${vol_h1/1000:.0f}K vol/hr")

    return min(score, 35), signals, buys_h1, sells_h1


def score_liquidity(pair):
    liq_usd = pair.get("liquidity",{}).get("usd",0) or 0
    mcap    = pair.get("marketCap",0) or pair.get("fdv",0) or 1
    if liq_usd < 2000: return -999, liq_usd
    ratio = (liq_usd/mcap)*100
    if ratio >= 25:   score = 25
    elif ratio >= 15: score = 18
    elif ratio >= 10: score = 12
    elif ratio >= 5:  score = 5
    else:             score = 0
    return min(score, 25), liq_usd


# ── HELPERS ───────────────────────────────────────────────────
def fmt(n):
    if not n: return "N/A"
    n = float(n)
    if n >= 1_000_000: return f"${n/1_000_000:.2f}M"
    if n >= 1_000:     return f"${n/1_000:.1f}K"
    return f"${n:.2f}"


def get_age(pair):
    created = pair.get("pairCreatedAt")
    if not created: return "Unknown", 9999
    try:
        dt   = datetime.fromtimestamp(created/1000, tz=timezone.utc)
        mins = int((datetime.now(tz=timezone.utc)-dt).total_seconds()/60)
        return (f"{mins}m", mins) if mins < 60 else (f"{mins//60}h {mins%60}m", mins)
    except: return "Unknown", 9999


# ── BUILD & SEND ALERT ────────────────────────────────────────
def build_and_send(c, forced=False):
    global last_forced_alert
    pair       = c["pair"]
    score      = c["score"]
    ticker     = c["ticker"]
    name       = c["name"]
    mcap       = c["mcap"]
    liq_usd    = c["liq_usd"]
    pair_addr  = c["pair_addr"]
    token_addr = c["token_addr"]
    rug        = c["rug"]
    buys_h1    = c["buys_h1"]
    sells_h1   = c["sells_h1"]

    if forced:
        label = f"🔎 BEST AVAILABLE — {score}/100"
        note  = "⚠️ <i>No high conviction coins right now — this is the best of current market. Lower confidence. DYOR harder.</i>\n\n"
    else:
        if score >= 85:   label = "🔴 SEND IT"
        elif score >= 75: label = "🟠 LOOKS LIVE"
        elif score >= 60: label = "🟡 ON THE RADAR"
        else:             label = "👀 EARLY RADAR"
        note = ""

    price = pair.get("priceUsd","0") or "0"
    try:    price_str = f"${float(price):.8f}"
    except: price_str = "N/A"

    vol    = pair.get("volume",{})
    vol_h1 = vol.get("h1",0) or 0; vol_h24 = vol.get("h24",0) or 0
    ch     = pair.get("priceChange",{})
    ch_h1  = ch.get("h1",0) or 0;  ch_h24  = ch.get("h24",0) or 0

    liq_pct = f"{(liq_usd/mcap*100):.0f}%" if mcap > 0 else "?"
    liq_sol = f"{(liq_usd/170):.1f} SOL"   if liq_usd else "?"

    supply = pair.get("baseToken",{}).get("totalSupply","N/A")
    if supply and supply != "N/A":
        try:
            s = float(supply)
            supply = f"{s/1e9:.0f}B" if s>=1e9 else f"{s/1e6:.0f}M" if s>=1e6 else str(s)
        except: supply = "N/A"

    mint_icon   = "✅ Disabled" if rug.get("mint_ok",False)   else "❌ Active"
    freeze_icon = "✅ Disabled" if rug.get("freeze_ok",False) else "❌ Active"

    meta_label, meta_desc, runner_str = get_narrative(name, ticker)

    twitter, telegram_link, website = check_socials(pair)
    social_parts = []
    if twitter:       social_parts.append(f"<a href='{twitter}'>X/Twitter</a>")
    if telegram_link: social_parts.append(f"<a href='{telegram_link}'>Telegram</a>")
    if website:       social_parts.append(f"<a href='{website}'>Website</a>")
    socials_str = " | ".join(social_parts) if social_parts else "No socials found ⚠️"

    total_h1 = buys_h1 + sells_h1
    buy_pct  = f"{int(buys_h1/total_h1*100)}%" if total_h1 > 0 else "?"
    sell_pct = f"{int(sells_h1/total_h1*100)}%" if total_h1 > 0 else "?"
    mom_str  = "\n".join(c["mom_signals"][:3]) if c["mom_signals"] else "Low momentum"

    dex_url      = f"https://dexscreener.com/solana/{pair_addr}"
    rugcheck_url = f"https://rugcheck.xyz/tokens/{token_addr}" if token_addr else "https://rugcheck.xyz"
    photon_url   = f"https://photon-sol.tinyastro.io/en/lp/{pair_addr}"
    bundle_url   = f"https://trench.bot/bundles/{token_addr}" if token_addr else "#"

    msg = (
        f"{label}\n\n"
        f"{note}"
        f"<b>{name} | {ticker} | Pump 🎯</b>\n\n"
        f"📋 Token Address:\n<code>{token_addr}</code>\n\n"
        f"📦 Supply: {supply}\n"
        f"📊 MC: {fmt(mcap)}\n"
        f"💧 Liquidity: {liq_sol} | {fmt(liq_usd)} ({liq_pct} of MC)\n"
        f"🕐 Age: {c['age_str']}\n"
        f"💲 Price: {price_str}\n\n"
        f"📈 <b>MOMENTUM</b>\n"
        f"{mom_str}\n"
        f"Buys: {buys_h1} ({buy_pct}) | Sells: {sells_h1} ({sell_pct})\n"
        f"Vol 1H: {fmt(vol_h1)} | 24H: {fmt(vol_h24)}\n"
        f"1H: {'+' if ch_h1>=0 else ''}{ch_h1:.0f}% | 24H: {'+' if ch_h24>=0 else ''}{ch_h24:.0f}%\n\n"
        f"❄️ FREEZE: {freeze_icon}\n"
        f"🪙 MINT: {mint_icon}\n"
        f"🔥 LP STATUS: ❌ Not Burned\n\n"
        f"🎯 <b>NARRATIVE: {meta_label}</b>\n"
        f"{meta_desc}\n"
        + (f"📊 {runner_str}\n" if runner_str else "")
        + f"\n🌐 SOCIALS: {socials_str}\n\n"
        f"💰 <b>TARGETS</b>\n"
        f"3x = {fmt(mcap*3)} MC\n"
        f"10x = {fmt(mcap*10)} MC\n\n"
        f"🔗 <a href='{dex_url}'>SCREEN</a> | "
        f"<a href='{rugcheck_url}'>RUGCHECK</a> | "
        f"<a href='{photon_url}'>PHOTON</a> | "
        f"<a href='{bundle_url}'>BUNDLE</a>\n\n"
        f"<i>NFA — DYOR — could go zero</i>\n"
        f"<i>⏱ Updates at 10m, 30m, 1hr</i>"
    )

    message_id = send_telegram(msg)
    alerted.add(pair_addr)
    save_alerted(pair_addr)
    if forced:
        last_forced_alert = time.time()

    if message_id:
        tracked[pair_addr] = {
            "ticker": ticker, "name": name,
            "entry_mcap": mcap, "entry_price": price,
            "token_addr": token_addr,
            "alerted_at": time.time(),
            "message_id": message_id,
            "updates_sent": 0,
        }
        schedule_updates(pair_addr)

    print(f"[ALERT{'*FORCED*' if forced else ''}] {ticker} score {score}")


# ── MAIN SCAN ─────────────────────────────────────────────────
def scan_and_alert():
    global last_forced_alert
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🔍 Scanning...")
    pairs = fetch_all_pairs()

    all_candidates  = []  # everything scored above 0
    good_candidates = []  # passed filters (score >= 45)

    for pair in pairs:
        if pair.get("chainId") != "solana": continue
        pair_addr  = pair.get("pairAddress","")
        token_addr = pair.get("baseToken",{}).get("address","")
        ticker     = pair.get("baseToken",{}).get("symbol","?")
        name       = pair.get("baseToken",{}).get("name","?")
        if pair_addr in alerted: continue

        mcap = pair.get("marketCap",0) or pair.get("fdv",0) or 0
        if mcap <= 0 or mcap > 100_000: continue

        txns = pair.get("txns",{})
        h1 = txns.get("h1",{}); h24 = txns.get("h24",{})
        if (h1.get("buys",0)+h1.get("sells",0)+h24.get("buys",0)+h24.get("sells",0)) < 5: continue

        age_str, age_mins = get_age(pair)
        if age_mins > 1440: continue

        liq_score, liq_usd = score_liquidity(pair)
        if liq_score == -999: continue

        mom_score, mom_signals, buys_h1, sells_h1 = score_momentum(pair)
        narr_score  = score_narrative_num(name, ticker)
        total_score = liq_score + mom_score + narr_score

        rug = get_rugcheck(token_addr)

        c = {
            "pair": pair, "score": total_score,
            "mom_signals": mom_signals, "age_str": age_str,
            "mcap": mcap, "liq_usd": liq_usd,
            "ticker": ticker, "name": name,
            "pair_addr": pair_addr, "token_addr": token_addr,
            "buys_h1": buys_h1, "sells_h1": sells_h1, "rug": rug,
        }

        all_candidates.append(c)
        if total_score >= 45:
            good_candidates.append(c)

    good_candidates.sort(key=lambda x: x["score"], reverse=True)
    all_candidates.sort(key=lambda x: x["score"],  reverse=True)

    sent = 0

    # Send high conviction alerts normally
    for c in good_candidates[:5]:
        build_and_send(c, forced=False)
        sent += 1
        time.sleep(1)

    # If nothing passed AND it's been 10+ mins since last forced alert → send best available
    if sent == 0:
        time_since_forced = time.time() - last_forced_alert
        # Only send best available if it scores at least 20 (has some signal)
        all_candidates = [c for c in all_candidates if c["score"] >= 20]
        if time_since_forced >= BEST_AVAILABLE_EVERY and all_candidates:
            best = all_candidates[0]
            print(f"[FORCED] Sending best available: {best['ticker']} score {best['score']}")
            build_and_send(best, forced=True)
            sent += 1

    if sent == 0:
        print("[SCAN] Nothing to send this round")
    else:
        print(f"[SCAN] {sent} alert(s) sent")


def send_startup():
    send_telegram(
        "🤖 <b>CHAINSCAN BOT ONLINE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Sources: DexScreener + GeckoTerminal\n"
        "MC filter: Under $100K\n"
        "Scan: Every 2 mins\n"
        "High conviction: score 45+/100\n"
        "Best available: every 10 mins\n"
        "Updates: replies at 10m/30m/1hr\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🟢 Bot is live. Alerts incoming."
    )


if __name__ == "__main__":
    print("="*50)
    print("  CHAINSCAN — Solana Meme Coin Scanner")
    print("="*50)
    send_startup()
    while True:
        try:
            scan_and_alert()
        except Exception as e:
            print(f"[MAIN ERROR] {e}")
        print(f"[SLEEP] {SCAN_INTERVAL}s...")
        time.sleep(SCAN_INTERVAL)