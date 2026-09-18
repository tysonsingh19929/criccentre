import os
import re
import json
import time
import urllib.request
from bs4 import BeautifulSoup
from typing import Dict, Any, List, Optional, Tuple

class CrexFeedEngine:
    """
    Exhaustive CREX Cricket Data Engine:
    Ingests all cricket events and tournaments worldwide from crex.com:
    1. All series & tournaments from https://crex.com/series
    2. All active & upcoming fixtures from https://crex.com/fixtures/match-list
    3. Comprehensive tournament match fixtures from https://crex.com/series/<slug>/matches
    4. Deterministic Unique Match IDs (M-<CAT>-<KEY>) and Series IDs (S-<CAT>-<KEY>)
    """

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9'
    }

    @classmethod
    def _fetch_html(cls, url: str, timeout: int = 10) -> str:
        req = urllib.request.Request(url, headers=cls.HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode('utf-8', errors='ignore')

    @classmethod
    def _categorize(cls, text: str) -> str:
        t = text.lower()
        if any(w in t for w in ["women", "womens", "women's", "wcpl", "wbbl", "wpl", "w- asian", "-w-", "-women"]):
            return "women"
        elif any(w in t for w in [
            "caribbean premier league", "premier league", "cpl", "ipl", "bbl", "psl", "etpl", "super smash",
            "triangular", "t10", "league", "t20 blast", "hundred"
        ]):
            return "league"
        elif any(w in t for w in [
            "trophy", "shield", "ranji", "county", "csa provincial", "marsh cup",
            "president", "duleep", "deodhar", "domestic"
        ]):
            return "domestic"
        return "international"

    @classmethod
    def _format_date(cls, start_dt: str) -> str:
        if not start_dt or start_dt == "Today":
            return "Today"
        try:
            raw = start_dt.split("T")[0]
            parts = raw.split("-")
            if len(parts) == 3:
                months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                m_idx = int(parts[1]) - 1
                return f"{months[m_idx]} {int(parts[2])}, {parts[0]}"
        except Exception:
            pass
        return start_dt[:10]

    @classmethod
    def _clean_team_name(cls, raw: str) -> str:
        s = raw.strip()
        # Clean common abbreviations if raw slug passed
        mapping = {
            "gaw": "Guyana Amazon Warriors",
            "abf": "Antigua & Barbuda Falcons",
            "bbt": "Barbados Tridents",
            "bt": "Barbados Tridents",
            "jkm": "Jamaica Kingsmen",
            "tkr": "Trinbago Knight Riders",
            "slk": "St Lucia Kings",
            "sknp": "St Kitts and Nevis Patriots",
            "ind": "India",
            "aus": "Australia",
            "eng": "England",
            "sl": "Sri Lanka",
            "pak": "Pakistan",
            "sa": "South Africa",
            "afg": "Afghanistan",
            "nz": "New Zealand",
            "wi": "West Indies",
            "ban": "Bangladesh",
            "zim": "Zimbabwe",
            "ire": "Ireland",
            "sl-w": "Sri Lanka Women",
            "mas-w": "Malaysia Women"
        }
        low = s.lower().replace("-", " ")
        if s.lower() in mapping:
            return mapping[s.lower()]
        return mapping.get(low, s.replace("-", " ").title())

    # =========================================================================
    # 1. Fetch All Series from https://crex.com/series
    # =========================================================================
    @classmethod
    def fetch_all_series(cls) -> List[Dict[str, Any]]:
        url = "https://crex.com/series"
        series_list = []
        seen_keys = set()

        try:
            html = cls._fetch_html(url)
            soup = BeautifulSoup(html, "html.parser")

            # Extract from links like /series/caribbean-premier-league-2026-2E2
            series_links = soup.find_all("a", href=re.compile(r'/series/([a-z0-9-]+?)-([0-9A-Za-z]{2,5})(?:/|$)'))
            for a in series_links:
                m = re.search(r'/series/([a-z0-9-]+?)-([0-9A-Za-z]{2,5})(?:/|$)', a['href'])
                if not m:
                    continue

                slug = m.group(1)
                s_key = m.group(2)
                if s_key in seen_keys or s_key in ["list", "table"]:
                    continue

                seen_keys.add(s_key)
                full_slug = f"{slug}-{s_key}"

                # Title extraction
                p = a.find_parent(["div", "li", "tr"])
                parent_text = p.get_text(" | ", strip=True) if p else ""
                link_text = a.get_text(strip=True)

                title = slug.replace("-", " ").title()
                if "202" not in title and any(y in slug for y in ["2024", "2025", "2026", "2027"]):
                    m_yr = re.search(r'(202\d(?:-\d+)?)', slug)
                    if m_yr:
                        title += f" {m_yr.group(1)}"

                # Dates extraction if in parent
                dates = "2026 Season"
                m_dt = re.search(r'(\d{1,2}\s+[A-Za-z]+\s*-\s*\d{1,2}\s+[A-Za-z]+)', parent_text)
                if m_dt:
                    dates = m_dt.group(1)
                elif any(m_name in parent_text for m_name in ["September", "October", "November", "August"]):
                    for mn in ["August", "September", "October", "November", "December"]:
                        if mn in parent_text:
                            dates = f"{mn} 2026"
                            break

                cat = cls._categorize(title + " " + slug)
                cat_code = cat[:3].upper()
                unique_sid = f"S-{cat_code}-{s_key.upper()}"

                series_list.append({
                    "unique_series_id": unique_sid,
                    "series_key": s_key,
                    "title": title,
                    "slug": full_slug,
                    "category": cat,
                    "dates": dates,
                    "crex_url": f"https://crex.com/series/{full_slug}",
                    "matches_url": f"https://crex.com/series/{full_slug}/matches",
                    "status": "Ongoing / Scheduled"
                })

        except Exception as e:
            print(f"[CrexFeedEngine] Error fetching series from crex.com/series: {e}")

        # Fallback guarantee for active major tournaments if scrape was partial
        known_defaults = [
            {"title": "Caribbean Premier League 2026", "slug": "caribbean-premier-league-2026-2E2", "key": "2E2", "cat": "league", "dates": "Aug 28 - Sep 21, 2026"},
            {"title": "Afghanistan vs India in India 2026", "slug": "afghanistan-vs-india-in-india-2026-2LR", "key": "2LR", "cat": "international", "dates": "Sep 15 - Sep 24, 2026"},
            {"title": "Sri Lanka tour of England 2026", "slug": "sri-lanka-tour-of-england-2026-1WT", "key": "1WT", "cat": "international", "dates": "Sep 11 - Oct 02, 2026"},
            {"title": "Women's Asian Games T20 2026", "slug": "womens-asian-games-t20-2026-2JY", "key": "2JY", "cat": "women", "dates": "Sep 14 - Sep 28, 2026"},
            {"title": "Australia tour of Zimbabwe 2026", "slug": "australia-tour-of-zimbabwe-2026-2GK", "key": "2GK", "cat": "international", "dates": "Sep 15 - Sep 24, 2026"},
            {"title": "Australia Domestic One-Day Cup 2026-27", "slug": "australia-domestic-one-day-cup-2026-27-2KN", "key": "2KN", "cat": "domestic", "dates": "Sep 18 - Oct 25, 2026"},
            {"title": "President Trophy 2026", "slug": "president-trophy-2026-2MQ", "key": "2MQ", "cat": "domestic", "dates": "Sep 18 - Oct 30, 2026"},
            {"title": "Women's Caribbean Premier League 2026", "slug": "womens-caribbean-premier-league-2026-2E1", "key": "2E1", "cat": "women", "dates": "Sep 04 - Sep 16, 2026"},
            {"title": "European T20 Premier League 2026", "slug": "european-t20-premier-league-2026-1RN", "key": "1RN", "cat": "league", "dates": "Sep 05 - Sep 22, 2026"},
            {"title": "Africa Continental Cup 2026", "slug": "africa-continental-cup-2026-2MM", "key": "2MM", "cat": "international", "dates": "Sep 10 - Sep 20, 2026"}
        ]
        for kd in known_defaults:
            if not any(s["series_key"] == kd["key"] for s in series_list):
                unique_sid = f"S-{kd['cat'][:3].upper()}-{kd['key']}"
                series_list.append({
                    "unique_series_id": unique_sid,
                    "series_key": kd["key"],
                    "title": kd["title"],
                    "slug": kd["slug"],
                    "category": kd["cat"],
                    "dates": kd["dates"],
                    "crex_url": f"https://crex.com/series/{kd['slug']}",
                    "matches_url": f"https://crex.com/series/{kd['slug']}/matches",
                    "status": "Ongoing / Scheduled"
                })

        return series_list

    # =========================================================================
    # 2. Fetch Active Live Matches directly from https://crex.com/cricket-live-score
    # =========================================================================
    @classmethod
    def fetch_active_live_matches(cls) -> List[Dict[str, Any]]:
        """
        Scrapes https://crex.com/cricket-live-score to extract only the matches
        that are ACTUALLY live on CREX, along with their live scores, overs, toss, and venue.
        """
        url = "https://crex.com/cricket-live-score"
        live_list = []
        seen = set()
        try:
            html = cls._fetch_html(url)
            soup = BeautifulSoup(html, "html.parser")
            cards = soup.find_all("div", class_=lambda c: c and "live-card" in c)
            for card in cards:
                a_match = card.find("a", href=re.compile(r'/cricket-live-score/([a-z0-9-]+?)-match-updates-([0-9A-Za-z]+)'))
                if not a_match:
                    continue
                m = re.search(r'/cricket-live-score/([a-z0-9-]+?)-match-updates-([0-9A-Za-z]+)', a_match["href"])
                slug = m.group(1)
                m_id = m.group(2)
                if m_id in seen:
                    continue
                seen.add(m_id)

                card_txt = card.get_text()
                is_live = bool(card.find(class_=lambda c: c and "live" in c.lower())) or "live" in card_txt.lower()
                is_done = any(w in card_txt.lower() for w in ["won by", "won", "result", "tied", "abandoned"])

                # Series
                a_ser = card.find("a", href=re.compile(r'/series/'))
                ser_name = a_ser.get_text(strip=True).replace("Live", "").strip() if a_ser else ""
                if not ser_name:
                    ser_name = slug.replace("-", " ").title()

                lines = [l.strip() for l in card.get_text("\n").split("\n") if l.strip() and l.strip() != ","]

                stage = "Match"
                venue = ""
                for l in lines:
                    if any(w in l.lower() for w in ["t20", "odi", "test", "final", "qualifier", "eliminator", "match"]):
                        stage = l
                        break
                for l in lines:
                    if any(w in l.lower() for w in ["stadium", "oval", "ground", "park", "cricket"]):
                        venue = l
                        break

                teams_found = []
                for idx, l in enumerate(lines):
                    if re.match(r'^[A-Z]{2,5}(?:-[A-Z]+)?$', l) and l not in ["LIVE", "T20", "ODI", "TEST"]:
                        teams_found.append((l, idx))

                t1_code = teams_found[0][0] if len(teams_found) > 0 else "Team 1"
                t2_code = teams_found[1][0] if len(teams_found) > 1 else "Team 2"

                s1, s2 = "", ""
                if len(teams_found) > 0:
                    idx1 = teams_found[0][1]
                    if idx1 + 1 < len(lines) and re.match(r'^\d+(?:-\d+)?$', lines[idx1 + 1]):
                        s1 = lines[idx1 + 1]
                        if idx1 + 2 < len(lines) and re.match(r'^\d+\.\d+$', lines[idx1 + 2]):
                            s1 += f" ({lines[idx1 + 2]} ov)"

                if len(teams_found) > 1:
                    idx2 = teams_found[1][1]
                    if idx2 + 1 < len(lines):
                        next_val = lines[idx2 + 1]
                        if re.match(r'^\d+(?:-\d+)?$', next_val):
                            s2 = next_val
                            if idx2 + 2 < len(lines) and re.match(r'^\d+\.\d+$', lines[idx2 + 2]):
                                s2 += f" ({lines[idx2 + 2]} ov)"
                        elif "yet to bat" in next_val.lower():
                            s2 = "Yet to bat"

                situation = ""
                for l in reversed(lines):
                    if any(w in l.lower() for w in ["needed", "opt to", "trail", "lead", "won", "toss", "break"]):
                        situation = l
                        break

                t1_full = cls._clean_team_name(t1_code)
                t2_full = cls._clean_team_name(t2_code)
                title = f"{t1_full} vs {t2_full}"

                cat = cls._categorize(ser_name + " " + slug)
                unique_mid = f"M-{cat[:3].upper()}-{m_id}"

                live_list.append({
                    "unique_match_id": unique_mid,
                    "match_id": m_id,
                    "title": title,
                    "team_1": t1_full,
                    "team_1_code": t1_code,
                    "team_1_score": s1,
                    "team_2": t2_full,
                    "team_2_code": t2_code,
                    "team_2_score": s2,
                    "series": ser_name,
                    "stage": stage,
                    "venue": venue,
                    "category": cat,
                    "scheduled_time": "Live",
                    "date_str": "Today",
                    "status": "Live In Progress" if is_live and not is_done else ("Result" if is_done else "Scheduled"),
                    "situation": situation,
                    "crex_url": f"https://crex.com{a_match['href']}",
                    "is_live": is_live and not is_done,
                    "is_completed": is_done
                })
        except Exception as e:
            print(f"[CrexFeedEngine] Error fetching crex.com/cricket-live-score: {e}")
        return live_list

    # =========================================================================
    # 3. Fetch All Events & Fixtures from CREX
    # =========================================================================
    @classmethod
    def fetch_all_events(cls) -> List[Dict[str, Any]]:
        events = []
        seen_keys = set()

        # 1. Scrape crex.com/fixtures/match-list via JSON-LD + HTML
        fixtures_url = "https://crex.com/fixtures/match-list"
        try:
            html = cls._fetch_html(fixtures_url)
            soup = BeautifulSoup(html, "html.parser")

            # Parse JSON-LD SportsEvents
            for s in soup.find_all('script', type='application/ld+json'):
                txt = s.string or ''
                if 'CollectionPage' in txt or 'SportsEvent' in txt:
                    try:
                        d = json.loads(txt)
                        items = d.get('mainEntity', {}).get('itemListElement', [])
                        for it in items:
                            ev = it.get('item', {})
                            if not ev:
                                continue
                            ev_url = ev.get('url', '')
                            m_key = re.search(r'-match-updates-([0-9A-Za-z]{2,6})$', ev_url)
                            if not m_key:
                                continue

                            m_id = m_key.group(1)
                            if m_id in seen_keys:
                                continue
                            seen_keys.add(m_id)

                            name = ev.get('name', 'Cricket Match')
                            cat = cls._categorize(name + " " + ev_url)
                            unique_mid = f"M-{cat[:3].upper()}-{m_id}"

                            t1, t2 = "", ""
                            if " vs " in name:
                                t1, t2 = [x.strip() for x in name.split(" vs ", 1)]
                            elif " v " in name:
                                t1, t2 = [x.strip() for x in name.split(" v ", 1)]

                            # Stage extraction from URL slug
                            stage = "Match"
                            m_st = re.search(r'-(qualifier-\d+|eliminator-\d*|final|\d+st-match|\d+nd-match|\d+rd-match|\d+th-match|\d+(?:st|nd|rd|th)-[a-z0-9]+)-', ev_url)
                            if m_st:
                                stage = m_st.group(1).replace("-", " ").title()

                            # Series name extraction from URL slug
                            series_name = "Cricket Tournament"
                            m_ser = re.search(r'-([a-z0-9-]+)-match-updates-', ev_url)
                            if m_ser:
                                raw_s = m_ser.group(1)
                                if m_st and m_st.group(0).strip("-") in raw_s:
                                    raw_s = raw_s.split(m_st.group(0).strip("-"))[-1].strip("-")
                                series_name = raw_s.replace("-", " ").title()

                            start_dt = ev.get('startDate', '')
                            events.append({
                                "unique_match_id": unique_mid,
                                "match_id": m_id,
                                "title": name,
                                "team_1": t1,
                                "team_2": t2,
                                "series": series_name,
                                "stage": stage,
                                "category": cat,
                                "scheduled_time": start_dt,
                                "date_str": cls._format_date(start_dt),
                                "status": "Scheduled",
                                "crex_url": ev_url,
                                "is_live": False,
                                "is_completed": False
                            })
                    except Exception:
                        pass
        except Exception as e:
            print(f"[CrexFeedEngine] Error in fixtures/match-list: {e}")

        # 2. Ingest Active Live Matches directly from https://crex.com/cricket-live-score
        try:
            live_matches = cls.fetch_active_live_matches()
            for lm in live_matches:
                m_id = lm["match_id"]
                if m_id in seen_keys:
                    for ev in events:
                        if ev["match_id"] == m_id:
                            ev["is_live"] = lm["is_live"]
                            ev["is_completed"] = lm.get("is_completed", False)
                            ev["status"] = lm["status"]
                            ev["team_1_score"] = lm.get("team_1_score", "")
                            ev["team_2_score"] = lm.get("team_2_score", "")
                            ev["situation"] = lm.get("situation", "")
                            ev["venue"] = lm.get("venue", ev.get("venue", ""))
                            ev["stage"] = lm.get("stage", ev.get("stage", "Match"))
                            ev["series"] = lm.get("series", ev.get("series", ""))
                            break
                else:
                    seen_keys.add(m_id)
                    events.insert(0, lm)
        except Exception as e:
            print(f"[CrexFeedEngine] Error integrating live matches: {e}")

        # 3. Pull Detailed Tournament Matches for CPL (all 39 matches)
        try:
            cpl_matches = cls.fetch_series_matches("caribbean-premier-league-2026-2E2", "2E2", "Caribbean Premier League 2026")
            for cm in cpl_matches:
                if cm["match_id"] not in seen_keys:
                    seen_keys.add(cm["match_id"])
                    events.append(cm)
        except Exception as e:
            print(f"[CrexFeedEngine] Error fetching CPL full matches: {e}")

        return events

    # =========================================================================
    # 3. Fetch Series Full Match Schedule (e.g. CPL all 39 matches)
    # =========================================================================
    @classmethod
    def fetch_series_matches(cls, series_slug: str, series_key: str, series_name: str = "") -> List[Dict[str, Any]]:
        url = f"https://crex.com/series/{series_slug}/matches"
        matches = []
        try:
            html = cls._fetch_html(url)
            soup = BeautifulSoup(html, "html.parser")

            match_links = soup.find_all("a", href=re.compile(r'/cricket-live-score/([a-z0-9-]+?)-match-updates-([0-9A-Za-z]{2,6})$'))
            for a in match_links:
                m = re.search(r'/cricket-live-score/([a-z0-9-]+?)-match-updates-([0-9A-Za-z]{2,6})$', a['href'])
                if not m:
                    continue

                slug = m.group(1)
                m_id = m.group(2)
                p = a.find_parent("div")
                p_text = p.get_text(" | ", strip=True) if p else ""

                stage = "Match"
                m_st = re.search(r'(\d+(?:st|nd|rd|th)?)\s*\|\s*(?:T20|ODI|Test)', p_text)
                if m_st:
                    stage = f"{m_st.group(1)} Match"
                elif "qualifier" in slug:
                    stage = "Qualifier"
                elif "eliminator" in slug:
                    stage = "Eliminator"
                elif "final" in slug:
                    stage = "Final"

                # Extract score & status
                is_won = "won" in p_text.lower()
                status_text = "Scheduled"
                m_res = re.search(r'([A-Z0-9\s]+?Won(?:\s+by\s+[^\n\|]+|\s*\(DLS\s+Method\))?)', p_text, re.I)
                if m_res:
                    status_text = f"Result — {m_res.group(1).strip()}"
                elif is_won:
                    status_text = "Result"

                teams_raw = slug.split("-match-")[0].split("-qualifier-")[0].split("-eliminator-")[0].split("-final")[0]
                t1, t2 = "Team 1", "Team 2"
                if "-vs-" in teams_raw:
                    parts = teams_raw.split("-vs-")
                    t1 = cls._clean_team_name(parts[0])
                    t2 = cls._clean_team_name(parts[1])

                cat = cls._categorize(series_slug + " " + slug)
                unique_mid = f"M-{cat[:3].upper()}-{m_id}"

                matches.append({
                    "unique_match_id": unique_mid,
                    "match_id": m_id,
                    "title": f"{t1} vs {t2}",
                    "team_1": t1,
                    "team_2": t2,
                    "series": series_name or series_slug.replace("-", " ").title(),
                    "stage": stage,
                    "category": cat,
                    "scheduled_time": "Completed" if is_won else "Scheduled",
                    "date_str": "Aug - Sep 2026",
                    "status": status_text,
                    "crex_url": f"https://crex.com{a['href']}",
                    "is_live": False,
                    "is_completed": is_won
                })

        except Exception as e:
            print(f"[CrexFeedEngine] Error fetching {url}: {e}")

        return matches

    # =========================================================================
    # 4. Master Catalog Sync & State Persistence
    # =========================================================================
    @classmethod
    def sync_catalog(cls, output_dir: str = "output") -> Dict[str, Any]:
        data_dir = os.path.join(output_dir, "data")
        os.makedirs(data_dir, exist_ok=True)

        print("[CrexFeedEngine] Ingesting all cricket series from https://crex.com/series...")
        series_list = cls.fetch_all_series()

        print(f"[CrexFeedEngine] Ingesting all active & upcoming match events from CREX...")
        events_list = cls.fetch_all_events()

        # Categorize series for the UI
        categorized_series = {
            "all": series_list,
            "international": [s for s in series_list if s["category"] == "international"],
            "league": [s for s in series_list if s["category"] == "league"],
            "domestic": [s for s in series_list if s["category"] == "domestic"],
            "women": [s for s in series_list if s["category"] == "women"],
            "current": series_list[:12]
        }

        # Build Schedule Format (for Cricinfo 2-Column UI)
        cricinfo_schedule = []
        for s in series_list:
            cricinfo_schedule.append({
                "unique_series_id": s["unique_series_id"],
                "series_name": s["title"],
                "category": s["category"].title(),
                "dates": s["dates"],
                "month": "September 2026",
                "status": s["status"],
                "fixtures_url": s["matches_url"],
                "squads_url": f"/series/{s['series_key']}"
            })

        # Save crex_catalog.json
        with open(os.path.join(data_dir, "crex_catalog.json"), "w", encoding="utf-8") as f:
            json.dump({
                "total_events": len(events_list),
                "total_series": len(series_list),
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                "events": events_list,
                "series": series_list
            }, f, indent=2)

        # Save series.json
        with open(os.path.join(data_dir, "series.json"), "w", encoding="utf-8") as f:
            json.dump(categorized_series, f, indent=2)

        # Save schedule.json
        with open(os.path.join(data_dir, "schedule.json"), "w", encoding="utf-8") as f:
            json.dump(cricinfo_schedule, f, indent=2)

        print(f"[CrexFeedEngine] Catalog synchronized: {len(events_list)} events, {len(series_list)} series.")
        return {
            "events_count": len(events_list),
            "series_count": len(series_list),
            "events": events_list,
            "series": series_list
        }

if __name__ == "__main__":
    CrexFeedEngine.sync_catalog()
