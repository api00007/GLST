import os
import re
import sys
import json
import time
import random
import shutil
from datetime import datetime, timezone, timedelta
from collections import OrderedDict
from urllib.parse import urljoin
import cloudscraper

API_ORIGIN = "https://streamcenter.st"
OUTPUT_FILE = "glst.json"
BACKUP_LOGO = "https://i.ibb.co/1Yh8PdLH/1000459066.jpg"

DEFAULT_SPORTS = [
    "football", "soccer", "basketball", 
    "baseball", "hockey", "racing", 
    "fighting", "boxing"
]

SPORT_DISPLAY_MAP = {
    "football": "American Football",
    "soccer": "Soccer",
    "basketball": "Basketball",
    "baseball": "Baseball",
    "hockey": "Hockey",
    "racing": "Racing",
    "fighting": "Fighting",
    "boxing": "Boxing",
    "motorsport": "Racing"
}

SOFASCORE_LEAGUE_LOGOS = {
    "NFL": "https://api.sofascore.app/api/v1/unique-tournament/9464/image",
    "NCAA Football": "https://api.sofascore.app/api/v1/unique-tournament/11200/image",
    "NBA": "https://api.sofascore.app/api/v1/unique-tournament/132/image",
    "WNBA": "https://api.sofascore.app/api/v1/unique-tournament/11186/image",
    "EuroLeague": "https://api.sofascore.app/api/v1/unique-tournament/138/image",
    "MLB": "https://api.sofascore.app/api/v1/unique-tournament/11205/image",
    "NHL": "https://api.sofascore.app/api/v1/unique-tournament/234/image",
    "Premier League": "https://api.sofascore.app/api/v1/unique-tournament/17/image",
    "LaLiga": "https://api.sofascore.app/api/v1/unique-tournament/8/image",
    "Serie A": "https://api.sofascore.app/api/v1/unique-tournament/23/image",
    "Bundesliga": "https://api.sofascore.app/api/v1/unique-tournament/35/image",
    "Ligue 1": "https://api.sofascore.app/api/v1/unique-tournament/34/image",
    "Champions League": "https://api.sofascore.app/api/v1/unique-tournament/7/image",
    "Europa League": "https://api.sofascore.app/api/v1/unique-tournament/679/image",
    "MLS": "https://api.sofascore.app/api/v1/unique-tournament/242/image",
    "Saudi Pro League": "https://api.sofascore.app/api/v1/unique-tournament/955/image",
    "Formula 1": "https://api.sofascore.app/api/v1/unique-tournament/10839/image",
    "UFC": "https://api.sofascore.app/api/v1/unique-tournament/11187/image",
    "Boxing": "https://api.sofascore.app/api/v1/unique-tournament/11235/image"
}

def get_ist_time():
    ist_offset = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist_offset).strftime('%d/%m/%y %H:%M:%S IST')

def log_to_console(message):
    print(message, file=sys.stderr)

def deduplicate(seq):
    seen = set()
    return [x for x in seq if not (x in seen or seen.add(x))]

def safe_json_parse(text):
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        if "][" in text:
            first_part = text.split("][")[0] + "]"
            try:
                return json.loads(first_part)
            except Exception:
                pass
        match = re.search(r'(\[.*\]|\{.*\})', text, re.S)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass
    return None

def detect_league(mid, raw_league, sport_name):
    mid_lower = mid.lower()
    raw_lower = raw_league.lower() if raw_league else ""
    
    if "nfl" in mid_lower or "nfl" in raw_lower:
        return "NFL"
    elif "college-football" in mid_lower or "ncaa" in mid_lower or "cfb" in mid_lower:
        return "NCAA Football"
    elif "wnba" in mid_lower or "wnba" in raw_lower:
        return "WNBA"
    elif "nba" in mid_lower or "nba" in raw_lower:
        return "NBA"
    elif "mlb" in mid_lower or "mlb" in raw_lower:
        return "MLB"
    elif "nhl" in mid_lower or "nhl" in raw_lower:
        return "NHL"
    elif "premier-league" in mid_lower or "epl" in raw_lower:
        return "Premier League"
    elif "la-liga" in mid_lower or "laliga" in raw_lower:
        return "LaLiga"
    elif "serie-a" in mid_lower or "serie a" in raw_lower:
        return "Serie A"
    elif "bundesliga" in mid_lower or "bundesliga" in raw_lower:
        return "Bundesliga"
    elif "ligue-1" in mid_lower or "ligue 1" in raw_lower:
        return "Ligue 1"
    elif "champions-league" in mid_lower or "ucl" in raw_lower:
        return "Champions League"
    elif "europa-league" in mid_lower or "uel" in raw_lower:
        return "Europa League"
    elif "mls" in mid_lower or "mls" in raw_lower:
        return "MLS"
    elif "f1" in mid_lower or "formula" in mid_lower or "formula 1" in raw_lower:
        return "Formula 1"
    elif "ufc" in mid_lower or "ufc" in raw_lower:
        return "UFC"
    elif raw_league and len(raw_league.strip()) > 1:
        return raw_league.strip().upper()
        
    return SPORT_DISPLAY_MAP.get(sport_name, sport_name.title())

def get_league_logo(league_name, fallback_badge):
    for key, logo_url in SOFASCORE_LEAGUE_LOGOS.items():
        if key.lower() in league_name.lower():
            return logo_url
    return fallback_badge if fallback_badge else BACKUP_LOGO

def push_to_github():
    GITHUB_TOKEN = os.getenv("GH_TOKEN")
    GITHUB_USER = os.getenv("TGITHUB_USER")
    GITHUB_REPO = os.getenv("TGITHUB_REPO")
    GITHUB_EMAIL = os.getenv("TGITHUB_EMAIL")
    
    if not GITHUB_TOKEN or not GITHUB_USER or not GITHUB_REPO:
        log_to_console("[INFO] GitHub secrets missing. Skipping push.")
        return

    temp_dir = "temp_external_repo"
    remote_url = f"https://{GITHUB_TOKEN}@github.com/{GITHUB_USER}/{GITHUB_REPO}.git"

    try:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            
        clone_status = os.system(f"git clone --depth 1 {remote_url} {temp_dir}")
        if clone_status != 0:
            raise Exception("Git clone failed. Please check repository permissions or token.")
        
        shutil.copy(OUTPUT_FILE, os.path.join(temp_dir, OUTPUT_FILE))
        
        current_dir = os.getcwd()
        os.chdir(temp_dir)
        
        os.system(f'git config user.email "{GITHUB_EMAIL if GITHUB_EMAIL else "action@github.com"}"')
        os.system(f'git config user.name "{GITHUB_USER}"')
        os.system(f"git add {OUTPUT_FILE}")
        os.system(f'git commit -m "Auto Update: {get_ist_time()}" --allow-empty')
        push_status = os.system("git push origin main")
        
        os.chdir(current_dir)
        shutil.rmtree(temp_dir)
        
        if push_status == 0:
            log_to_console(f"[SUCCESS] {OUTPUT_FILE} successfully updated in {GITHUB_USER}/{GITHUB_REPO}.")
        else:
            log_to_console("[ERROR] Git push command failed.")
            
    except Exception as e:
        log_to_console(f"[ERROR] Push failed: {e}")

def scan_m3u8_from_html(html_text):
    tokens = re.findall(r'(?:stream=|hls\.php\?stream=)([a-zA-Z0-9_.-]+)', html_text)
    for token in tokens:
        return f"https://edgestream2.pro/hls/{token}.m3u8|Referer=https://streame.center"
        
    direct_m3u8 = re.findall(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html_text)
    for link in direct_m3u8:
        clean_link = link.replace('\\/', '/').strip('"\';')
        return f"{clean_link}|Referer=https://streame.center"
        
    return None

def extract_stream_from_embed(scraper, embed_url):
    try:
        headers = {
            'Referer': f"{API_ORIGIN}/",
            'Origin': API_ORIGIN
        }
        res = scraper.get(embed_url, headers=headers, timeout=12)
        res.encoding = 'utf-8'
        html = res.text
        
        link = scan_m3u8_from_html(html)
        if link:
            return link

        iframes = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.I)
        for ifr in iframes:
            if ifr.startswith('//'):
                ifr_url = 'https:' + ifr
            elif not ifr.startswith('http'):
                ifr_url = urljoin(embed_url, ifr)
            else:
                ifr_url = ifr

            time.sleep(random.uniform(0.3, 0.5))
            ifr_res = scraper.get(ifr_url, headers={'Referer': embed_url}, timeout=10)
            ifr_res.encoding = 'utf-8'
            ifr_link = scan_m3u8_from_html(ifr_res.text)
            if ifr_link:
                return ifr_link
    except Exception as e:
        log_to_console(f"    [!] Error loading embed {embed_url}: {e}")
        
    return None

def run_scraper():
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'android', 'desktop': False})
    
    log_to_console(f"[*] Connecting to: {API_ORIGIN}")
    sports_slugs = []

    try:
        sports_res = scraper.get(f"{API_ORIGIN}/api/sports", timeout=12)
        if sports_res.status_code == 200:
            parsed = safe_json_parse(sports_res.text)
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict) and "id" in item:
                        sports_slugs.append(item["id"])
                    elif isinstance(item, str):
                        sports_slugs.append(item)
    except Exception as e:
        log_to_console(f"[!] Failed to fetch sports catalog: {e}")

    for fb in DEFAULT_SPORTS:
        if fb not in sports_slugs:
            sports_slugs.append(fb)

    sports_slugs = deduplicate(sports_slugs)
    log_to_console(f"[+] Total sports categories: {len(sports_slugs)}")

    all_live_matches = []
    seen_match_ids = set()
    ist = timezone(timedelta(hours=5, minutes=30))

    for sport in sports_slugs:
        log_to_console(f"[*] Scanning matches for sport: {sport}")
        try:
            time.sleep(random.uniform(0.4, 0.7))
            matches_res = scraper.get(f"{API_ORIGIN}/api/matches/{sport}", timeout=12)
            if matches_res.status_code != 200:
                continue

            matches_data = safe_json_parse(matches_res.text)
            if not isinstance(matches_data, list):
                continue

            for match in matches_data:
                match_id = match.get("id")
                if not match_id or match_id in seen_match_ids:
                    continue

                seen_match_ids.add(match_id)
                raw_title = match.get("title", "")
                clean_rivals = re.sub(r'\s+@\s+|\s+\|\s+', ' vs ', raw_title).strip()
                cat_name = SPORT_DISPLAY_MAP.get(sport.lower(), sport.replace("-", " ").title())
                raw_league = match.get("leagueName") or match.get("categoryName") or ""
                league_name = detect_league(match_id, raw_league, sport)

                ts = match.get("date", int(time.time() * 1000))
                
                dt_utc = datetime.fromtimestamp(ts / 1000, timezone.utc)
                end_utc = dt_utc + timedelta(hours=3)
                utc_start_str = dt_utc.strftime("%Y/%m/%d %H:%M:%S +0000")
                utc_end_str = end_utc.strftime("%Y/%m/%d %H:%M:%S +0000")

                start_dt = datetime.fromtimestamp(ts / 1000, ist)
                end_dt = start_dt + timedelta(hours=3)
                start_time_str = start_dt.strftime("%d/%m/%Y; %H:%M:%S IST")
                end_time_str = end_dt.strftime("%d/%m/%Y; %H:%M:%S IST")

                t_home = match.get("teams", {}).get("home", {})
                t_away = match.get("teams", {}).get("away", {})

                team_a_name = t_away.get("name") or league_name
                team_b_name = t_home.get("name") or league_name

                team_a_badge = f"{API_ORIGIN}/api/images/badge/{t_away.get('badge')}.webp" if t_away.get("badge") else BACKUP_LOGO
                team_b_badge = f"{API_ORIGIN}/api/images/badge/{t_home.get('badge')}.webp" if t_home.get("badge") else BACKUP_LOGO

                fallback_badge = team_a_badge if team_a_badge != BACKUP_LOGO else team_b_badge
                league_logo = get_league_logo(league_name, fallback_badge)

                sources = match.get("sources", [])
                if not sources:
                    continue

                for s_idx, src in enumerate(sources, 1):
                    src_type = src.get("source", "iframe")
                    src_id = src.get("id")
                    if not src_id:
                        continue

                    time.sleep(random.uniform(0.3, 0.6))
                    stream_api = f"{API_ORIGIN}/api/stream/{src_type}/{src_id}"
                    
                    try:
                        stream_res = scraper.get(stream_api, timeout=10)
                        if stream_res.status_code != 200:
                            continue

                        streams_info = safe_json_parse(stream_res.text)
                        if not isinstance(streams_info, list) or not streams_info:
                            continue

                        for stream_entry in streams_info:
                            embed_url = stream_entry.get("embedUrl")
                            stream_num = stream_entry.get("streamNo", s_idx)
                            
                            if not embed_url:
                                continue

                            final_m3u8 = extract_stream_from_embed(scraper, embed_url)
                            if final_m3u8:
                                if stream_num == 1:
                                    server_name = f"{league_name.upper()} SERVER"
                                else:
                                    server_name = "HD SERVER" if stream_num == 2 else f"HD SERVER {stream_num - 1}"

                                iframe_link = f'<iframe src="https://ivan-player.vercel.app/?play=https://stream-proxy.goalzen.site/proxy/php?url={final_m3u8}" style="width: 100%; aspect-ratio: 16/9; border: none;" allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowfullscreen></iframe>'

                                log_to_console(f"    [+] Link Created: {clean_rivals} ({server_name})")
                                all_live_matches.append(OrderedDict([
                                    ("Id", str(len(all_live_matches) + 1)),
                                    ("Category", cat_name),
                                    ("Event_Name", clean_rivals),
                                    ("League_Name", league_name),
                                    ("League_Logo", league_logo),
                                    ("Stream_Name", server_name),
                                    ("Team_A", team_a_name),
                                    ("Team_A_Logo", team_a_badge),
                                    ("Team_B", team_b_name),
                                    ("Team_B_Logo", team_b_badge),
                                    ("Start_Time", start_time_str),
                                    ("End_Time", end_time_str),
                                    ("UTC_Start", utc_start_str),
                                    ("UTC_End", utc_end_str),
                                    ("Link", iframe_link)
                                ]))
                    except Exception:
                        continue
        except Exception:
            continue

    log_to_console(f"\n[+] Total Live Streams Collected: {len(all_live_matches)}")

    final_package = OrderedDict([
        ("Owner", "Ivan-FluX"),
        ("App name", "glst-scraper"),
        ("Last update", get_ist_time()),
        ("Total_Matches", len(all_live_matches)),
        ("Live_Data", all_live_matches)
    ])

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_package, f, indent=4, ensure_ascii=False)

    push_to_github()
    print(json.dumps(final_package, indent=4, ensure_ascii=False))

if __name__ == "__main__":
    run_scraper()
