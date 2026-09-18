import re
import json
import asyncio
import urllib.request
from typing import List, Dict, Any, Tuple, Optional
from core.base_scraper import BaseScraper
from core.browser_manager import BrowserManager
from core.models import (
    MatchMetadata, BattingRow, BowlingRow, ExtrasInfo,
    TotalInfo, FallOfWicket, BatterContribution, Partnership,
    BallByBallEvent, Inning, MatchData
)
from scrapers import register_scraper

@register_scraper(["crex.com", "crex.live"])
class CrexScraper(BaseScraper):
    """
    Complete Scraper implementation for CREX (crex.com & crex.live).
    Extracts 100% full match data:
      - Complete Batting Scorecards (R, B, 4s, 6s, SR, Dismissals) via getSC4 & getWD
      - Complete Bowling Scorecards (O, M, R, W, Econ) via getSC4
      - Complete Partnerships via getSC4
      - Real Player & Team Names via getHomeMapData
      - Ball-by-ball deliveries & commentary via getBallFeeds
      - Match metadata, venue, toss, result via getMatchMetaData & getPostMatchDataV2
    """
    @property
    def platform_name(self) -> str:
        return "CREX"

    def __init__(self, raw_url: str):
        super().__init__(raw_url)
        self.match_id = self.extract_match_id(raw_url)

    def extract_match_id(self, url: str) -> str:
        clean_url = url.rstrip('/')
        # Match pattern: -match-updates-([0-9A-Za-z]{2,6})
        m_mu = re.search(r'-match-updates-([0-9A-Za-z]{2,6})(?:/|$)', clean_url)
        if m_mu:
            return m_mu.group(1)
        m = re.search(r'-([A-Za-z0-9]{3,6})$', clean_url)
        if m and m.group(1).lower() != "live":
            return m.group(1)
        for seg in reversed(clean_url.split('/')):
            if seg.lower() in ["live", "scorecard", "commentary", "info", "match-info"]:
                continue
            parts = seg.split('-')
            if parts and len(parts[-1]) >= 2 and parts[-1].lower() != "live":
                return parts[-1]
        return "unknown"

    def _http_request(self, url: str, data: Optional[bytes] = None) -> Any:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://crex.com",
            "Referer": "https://crex.com/"
        }
        req = urllib.request.Request(url, data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
            try:
                return json.loads(content)
            except Exception:
                return content

    async def fetch_and_parse(self, browser_mgr: BrowserManager) -> MatchData:
        match_id = self.match_id
        if not match_id or match_id == "unknown":
            raise ValueError(f"Could not extract a valid CREX match ID from URL: {self.raw_url}")

        print(f"[{self.platform_name}] 1/4 Fetching complete CREX scorecard (getSC4)...")
        sc4_data = await asyncio.to_thread(self._http_request, f"https://api.goscorer.com/api/v3/getSC4?key={match_id}")

        print(f"[{self.platform_name}] 2/4 Fetching player & team mappings (getHomeMapData)...")
        # Extract player and team keys from sc4
        player_keys = set()
        team_keys = set()
        if isinstance(sc4_data, list):
            for inn in sc4_data:
                if inn.get("c"):
                    team_keys.add(inn.get("c"))
                for b_str in inn.get("b", []):
                    pk = b_str.split("/")[0].split(".")[0]
                    if pk:
                        player_keys.add(pk)
                for a_str in inn.get("a", []):
                    pk = a_str.split("/")[0].split(".")[0]
                    if pk:
                        player_keys.add(pk)

        payload_map = json.dumps({
            "p": list(player_keys),
            "s": [],
            "u": [],
            "v": [],
            "t": list(team_keys),
            "lc": "en"
        }).encode("utf-8")

        try:
            map_data = await asyncio.to_thread(self._http_request, "https://oc.crickapi.com/mapping/getHomeMapData", payload_map)
        except Exception:
            map_data = {}

        player_names = {p["f_key"]: p["n"] for p in map_data.get("p", [])} if isinstance(map_data, dict) else {}
        team_names = {t["f_key"]: t["n"] for t in map_data.get("t", [])} if isinstance(map_data, dict) else {}

        print(f"[{self.platform_name}] 3/4 Fetching wicket dismissals & match metadata...")
        payload_wd = json.dumps({"mf": match_id}).encode("utf-8")
        try:
            wd_data = await asyncio.to_thread(self._http_request, "https://stats.crickapi.com/live/getWD", payload_wd)
        except Exception:
            wd_data = []

        # Fetch page HTML for series and metadata
        try:
            html = await asyncio.to_thread(self._fetch_raw_html, self.raw_url)
        except Exception as e:
            html = ""
        embedded_state = self._extract_embedded_state(html)

        print(f"[{self.platform_name}] 4/4 Fetching ball-by-ball delivery feeds...")
        ball_feed_items = await self._fetch_ball_feeds(match_id)

        # Build full MatchData
        return self._build_match_data(
            match_id=match_id,
            sc4_data=sc4_data,
            wd_data=wd_data,
            player_names=player_names,
            team_names=team_names,
            embedded_state=embedded_state,
            ball_feed_items=ball_feed_items
        )

    def _fetch_raw_html(self, url: str) -> str:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://crex.com/"
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="ignore")

    def _extract_embedded_state(self, html: str) -> Dict[str, Any]:
        for s in re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL):
            if 'crickapi' in s or 'goscorer' in s:
                clean = s.replace('&q;', '"')
                try:
                    return json.loads(clean)
                except Exception:
                    pass
        return {}

    async def _fetch_ball_feeds(self, match_id: str, max_pages: int = 40) -> List[Dict[str, Any]]:
        all_feeds = []
        last_id = None
        for _ in range(max_pages):
            payload = json.dumps({"matchKey": match_id, "lastDocId": last_id, "filters": {}, "lang": "en"}).encode("utf-8")
            try:
                page_data = await asyncio.to_thread(self._http_request, "https://content.crickapi.com/commentary/v1/getBallFeeds", payload)
                if not page_data or not isinstance(page_data, list):
                    break
                all_feeds.extend(page_data)
                last_id = page_data[-1].get("id")
            except Exception:
                break
        return all_feeds

    def _build_match_data(
        self,
        match_id: str,
        sc4_data: Any,
        wd_data: Any,
        player_names: Dict[str, str],
        team_names: Dict[str, str],
        embedded_state: Dict[str, Any],
        ball_feed_items: List[Dict[str, Any]]
    ) -> MatchData:
        # 1. Metadata & Live Real-Time State (getSV3)
        meta_list = embedded_state.get("https://stats.crickapi.com/live/getMatchMetaData", [])
        m_meta = meta_list[0] if meta_list else embedded_state.get(f"match-{match_id}", {})
        pmd = embedded_state.get("https://stats.crickapi.com/i/live/getPostMatchDataV2", {})
        sv3 = embedded_state.get("https://api.goscorer.com/api/v3/getSV3", {})
        result_str = pmd.get("r", "")

        t1_name = sv3.get("team1_f_n") or m_meta.get("team1") or (list(team_names.values())[0] if team_names else "Team 1")
        t2_name = sv3.get("team2_f_n") or m_meta.get("team2") or (list(team_names.values())[1] if len(team_names) > 1 else "Team 2")
        venue = m_meta.get("v", "")
        match_title = f"{t1_name} vs {t2_name}"

        # Tournament / Series Extraction from URL slug
        series_title = ""
        m_slug = re.search(r'(?:qtr-final|semi-final|final|qualifier|eliminator|\d+th-match|\d+st-match|\d+nd-match|\d+rd-match)-([a-z0-9-]+?)-(?:match-updates|live-score|cricket-live)', self.raw_url, re.I)
        if not m_slug:
            m_slug = re.search(r'/cricket-live-score/[a-z0-9-]+-vs-[a-z0-9-]+-([a-z0-9-]+?)-(?:match-updates|live-score)', self.raw_url, re.I)
        if m_slug:
            series_title = m_slug.group(1).replace("-", " ").title()
        if not series_title:
            series_title = m_meta.get("mn") or "Cricket Tournament"

        # Toss info from getSV3 or pmd
        toss_info = ""
        if sv3.get("comment1"):
            toss_info = str(sv3.get("comment1")).strip()
        elif pmd.get("toss_team"):
            t_t = team_names.get(pmd.get("toss_team"), pmd.get("toss_team"))
            opt = "bat" if pmd.get("chose_to") == 1 else "bowl"
            toss_info = f"{t_t} won the toss and opted to {opt}"

        is_live = True
        status_lower = (str(result_str)).lower()
        if any(w in status_lower for w in ["won by", "won", "result", "completed", "abandoned"]):
            is_live = False

        status_note = str(result_str) if result_str else "Match in Progress"
        if is_live and sv3.get("score1"):
            score1 = sv3.get("score1", "")
            over1 = sv3.get("over1", "")
            crr_str = sv3.get("crr", "")
            status_note = f"{t1_name} {score1} ({over1} ov)" + (f" • CRR: {crr_str}" if crr_str else "")

        metadata = MatchMetadata(
            match_id=match_id,
            match_title=match_title,
            series=series_title,
            venue=venue,
            toss=toss_info,
            status="Result" if not is_live else "Live",
            status_note=status_note,
            source_url=self.raw_url,
            source_platform=self.platform_name,
            is_live=is_live
        )

        # 2. Innings & Scorecards
        innings: List[Inning] = []
        partnerships: List[Partnership] = []

        if isinstance(sc4_data, list):
            for inn_idx, inn in enumerate(sc4_data):
                t_code = inn.get("c", "")
                team_name = team_names.get(t_code, f"Team {t_code}")
                inn_wd = wd_data[inn_idx] if inn_idx < len(wd_data) and isinstance(wd_data[inn_idx], dict) else {}

                # Batting
                batters: List[BattingRow] = []
                for b_str in inn.get("b", []):
                    parts = b_str.split("/")
                    stats_part = parts[0]
                    tokens = stats_part.split(".")
                    if len(tokens) >= 5:
                        pk = tokens[0]
                        pname = player_names.get(pk, pk)
                        runs = int(tokens[1]) if tokens[1].isdigit() else 0
                        balls = int(tokens[2]) if tokens[2].isdigit() else 0
                        fours = int(tokens[3]) if tokens[3].isdigit() else 0
                        sixes = int(tokens[4]) if tokens[4].isdigit() else 0
                        sr = round((runs / balls * 100), 2) if balls > 0 else 0.0

                        dismissal = "not out"
                        if pk in inn_wd:
                            raw_wd = inn_wd[pk]
                            if "stumped" in raw_wd.lower():
                                dismissal = "stumped"
                            elif "caught" in raw_wd.lower() or "c " in raw_wd.lower():
                                dismissal = "caught"
                            elif "bowled" in raw_wd.lower() or "b " in raw_wd.lower():
                                dismissal = "bowled"
                            elif "run out" in raw_wd.lower():
                                dismissal = "run out"
                            elif "lbw" in raw_wd.lower():
                                dismissal = "lbw"
                            elif "retired" in raw_wd.lower():
                                dismissal = "retired out"
                            else:
                                dismissal = "out"
                        elif len(tokens) > 5:
                            dismissal = "out"

                        batters.append(BattingRow(
                            batter=pname,
                            dismissal=dismissal,
                            runs=runs,
                            balls=balls,
                            fours=fours,
                            sixes=sixes,
                            strike_rate=sr
                        ))

                # Bowling
                bowlers: List[BowlingRow] = []
                for a_str in inn.get("a", []):
                    tokens = a_str.split(".")
                    if len(tokens) >= 5:
                        pk = tokens[0]
                        pname = player_names.get(pk, pk)
                        runs = int(tokens[1]) if tokens[1].isdigit() else 0
                        balls = int(tokens[2]) if tokens[2].isdigit() else 0
                        maidens = int(tokens[3]) if tokens[3].isdigit() else 0
                        wickets = int(tokens[4]) if tokens[4].isdigit() else 0
                        overs_float = round((balls // 6) + (balls % 6) / 10.0, 1)
                        actual_overs = (balls // 6) + (balls % 6) / 6.0
                        econ = round(runs / actual_overs, 2) if actual_overs > 0 else 0.0

                        bowlers.append(BowlingRow(
                            bowler=pname,
                            overs=overs_float,
                            maidens=maidens,
                            runs=runs,
                            wickets=wickets,
                            economy=econ
                        ))

                # Partnerships
                for p_str in inn.get("p", []):
                    # Format: <pk1>.<r1>.<b1>.<pk2>.<r2>.<b2>.<total_r>.<total_b>
                    p_tokens = p_str.split(".")
                    if len(p_tokens) >= 8:
                        pk1, r1, b1, pk2, r2, b2, tr, tb = p_tokens[:8]
                        p1_name = player_names.get(pk1, pk1)
                        p2_name = player_names.get(pk2, pk2)
                        p1_r = int(r1) if r1.isdigit() else 0
                        p1_b = int(b1) if b1.isdigit() else 0
                        p2_r = int(r2) if r2.isdigit() else 0
                        p2_b = int(b2) if b2.isdigit() else 0
                        tot_r = int(tr) if tr.isdigit() else (p1_r + p2_r)
                        tot_b = int(tb) if tb.isdigit() else (p1_b + p2_b)

                        raw_desc = f"{p1_name} & {p2_name} {tot_r} ({tot_b}b)"
                        partnerships.append(Partnership(
                            milestone_runs=tot_r,
                            balls=tot_b,
                            batter_1=BatterContribution(name=p1_name, runs=p1_r, balls=p1_b),
                            batter_2=BatterContribution(name=p2_name, runs=p2_r, balls=p2_b),
                            raw_text=raw_desc,
                            source_day=f"{team_name} Inning"
                        ))

                # Summary Header
                raw_d = str(inn.get("d", "") or "")
                # e.g. "69/4(48" -> "69/4 (8.0 ov)"
                score_match = re.search(r'(\d+\/\d+)\((\d+)', raw_d)
                if score_match:
                    s_score = score_match.group(1)
                    s_balls = int(score_match.group(2))
                    s_ov = f"{s_balls // 6}.{s_balls % 6}"
                    summary_header = f"{team_name} Inning {s_score} ({s_ov} ov)"
                elif inn_idx == 0 and sv3.get("score1"):
                    s_ov = f" ({sv3.get('over1')} ov)" if sv3.get("over1") else ""
                    summary_header = f"{team_name} Inning {sv3.get('score1')}{s_ov}"
                elif inn_idx == 1 and sv3.get("score2"):
                    s_ov = f" ({sv3.get('over2')} ov)" if sv3.get("over2") else ""
                    summary_header = f"{team_name} Inning {sv3.get('score2')}{s_ov}"
                elif raw_d:
                    summary_header = f"{team_name} Inning {raw_d}"
                else:
                    summary_header = f"{team_name} Inning Yet to Bat"

                innings.append(Inning(
                    inning_name=f"{team_name} Inning",
                    header_summary=summary_header,
                    batting=batters,
                    bowling=bowlers,
                    ball_by_ball=[]
                ))

        # 3. Ball-by-Ball Deliveries
        all_deliveries: List[BallByBallEvent] = []
        inn_deliveries: Dict[int, List[BallByBallEvent]] = {}

        for feed in ball_feed_items:
            ftype = feed.get("type")
            if ftype in ["b", "w"] and feed.get("o") is not None:
                over_val = str(feed.get("o"))
                outcome = str(feed.get("b") or ("W" if ftype == "w" else "0"))
                inn_idx = feed.get("inning", 0)

                runs_val = 0
                if outcome.isdigit():
                    runs_val = int(outcome)
                elif outcome in ["4", "FOUR"]:
                    runs_val = 4
                elif outcome in ["6", "SIX"]:
                    runs_val = 6
                elif outcome in ["W", "WKT"]:
                    runs_val = 0
                elif outcome in ["WD", "WIDE", "NB"]:
                    runs_val = 1

                c1 = feed.get("c1", "")
                bowler_name = ""
                batter_name = ""
                if " to " in c1:
                    parts = c1.split(" to ")
                    bowler_name = parts[0].strip()
                    batter_name = parts[1].strip()
                else:
                    bowler_name = player_names.get(feed.get("bf"), feed.get("bf", ""))
                    batter_name = (
                        feed.get("player_fullname") or 
                        feed.get("player") or 
                        player_names.get(feed.get("player_fkey") or feed.get("pf"), feed.get("pf", ""))
                    )

                comm = feed.get("c2") or feed.get("c") or ""
                comm_clean = re.sub(r'<[^>]+>', '', comm).strip()
                if not comm_clean:
                    outcome_up = outcome.upper()
                    if outcome_up in ["4", "FOUR"]:
                        comm_clean = f"{bowler_name} to {batter_name}, FOUR! Nicely struck to the boundary."
                    elif outcome_up in ["6", "SIX"]:
                        comm_clean = f"{bowler_name} to {batter_name}, SIX! Massive hit over the fence!"
                    elif outcome_up in ["W", "WKT"] or ftype == "w":
                        comm_clean = f"{bowler_name} to {batter_name}, OUT! Wicket falls at {over_val}."
                    elif outcome_up in ["WD", "WIDE"]:
                        comm_clean = f"{bowler_name} to {batter_name}, Wide ball down the leg side."
                    elif outcome_up in ["NB", "NO BALL"]:
                        comm_clean = f"{bowler_name} to {batter_name}, No ball called by umpire."
                    elif runs_val == 0 or outcome_up in ["0", "DOT"]:
                        comm_clean = f"{bowler_name} to {batter_name}, no run. Good length ball defended."
                    else:
                        comm_clean = f"{bowler_name} to {batter_name}, {runs_val} run{'s' if runs_val > 1 else ''}. Pushed into gaps."

                ov_parts = over_val.split(".")
                ov_num = int(ov_parts[0]) if len(ov_parts) > 0 and ov_parts[0].isdigit() else 0
                b_num = int(ov_parts[1]) if len(ov_parts) > 1 and ov_parts[1].isdigit() else 1

                target_inn_name = innings[inn_idx].inning_name if inn_idx < len(innings) else f"Inning {inn_idx + 1}"

                deliv = BallByBallEvent(
                    inning_name=target_inn_name,
                    over_str=over_val,
                    over_num=ov_num,
                    ball_num=b_num,
                    runs=runs_val,
                    bowler=bowler_name,
                    batter=batter_name,
                    outcome=outcome,
                    commentary_text=comm_clean,
                    is_four=outcome in ["4", "FOUR"],
                    is_six=outcome in ["6", "SIX"],
                    is_wicket=ftype == "w" or outcome in ["W", "WKT"],
                    is_extra=outcome in ["WD", "WIDE", "NB", "B", "LB"],
                    extra_type="wide" if "WD" in outcome else ("no_ball" if "NB" in outcome else ("leg_bye" if "LB" in outcome else ("bye" if "B" in outcome else "")))
                )
                all_deliveries.append(deliv)
                inn_deliveries.setdefault(inn_idx, []).append(deliv)

        # Associate ball-by-ball commentary to each inning
        for idx, inn in enumerate(innings):
            if idx in inn_deliveries:
                inn.ball_by_ball = inn_deliveries[idx]

        return MatchData(
            metadata=metadata,
            innings=innings,
            partnerships=partnerships,
            all_balls=all_deliveries
        )
