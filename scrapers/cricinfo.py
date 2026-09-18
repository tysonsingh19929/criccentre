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

@register_scraper(["cricinfo.com", "espncricinfo.com"])
class CricinfoScraper(BaseScraper):
    """
    Scraper implementation for ESPNcricinfo (cricinfo.com & espncricinfo.com).
    Connects directly to ESPN's official REST API endpoints to extract complete
    match metadata, multi-innings scorecards, extras, fall of wickets,
    milestone partnerships, and complete ball-by-ball commentary streams.
    """
    @property
    def platform_name(self) -> str:
        return "ESPNcricinfo"

    def __init__(self, raw_url: str):
        super().__init__(raw_url)
        self.series_id, self.match_id_extracted = self._extract_ids(raw_url)

    def extract_match_id(self, url: str) -> str:
        s_id, m_id = self._extract_ids(url)
        return m_id if m_id else "unknown"

    def _extract_ids(self, url: str) -> Tuple[str, str]:
        # Pattern 1: /series/<series-slug>-<series-id>/<match-slug>-<match-id>/...
        m1 = re.search(r'/series/[^/]+-(\d+)/[^/]+-(\d+)', url)
        if m1:
            return m1.group(1), m1.group(2)

        # Pattern 2: /series/(\d+)/.*?/(\d+)
        m2 = re.search(r'/series/(\d+)/[^/]+/(\d+)', url)
        if m2:
            return m2.group(1), m2.group(2)

        # Pattern 3: general digits extraction
        digits = re.findall(r'\b\d{6,8}\b', url)
        if len(digits) >= 2:
            return digits[0], digits[1]
        elif len(digits) == 1:
            return "", digits[0]
        return "", "unknown"

    def _fetch_json(self, url: str) -> Dict[str, Any]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.espncricinfo.com/"
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    async def fetch_and_parse(self, browser_mgr: BrowserManager) -> MatchData:
        series_id = self.series_id
        match_id = self.match_id
        if not match_id or match_id == "unknown":
            raise ValueError(f"Could not extract a valid match ID from URL: {self.raw_url}")

        summary_url = f"https://site.web.api.espn.com/apis/site/v2/sports/cricket/{series_id}/summary?event={match_id}"
        print(f"[{self.platform_name}] 1/2 Fetching match summary & scorecard: {summary_url}")
        summary_data = await asyncio.to_thread(self._fetch_json, summary_url)

        # Fetch Ball-by-Ball Commentary for all innings
        print(f"[{self.platform_name}] 2/2 Fetching ball-by-ball commentary stream...")
        all_balls, dismissal_map = await self._fetch_all_commentary(series_id, match_id)

        # Parse Metadata & Scorecards with dismissal text
        metadata, innings, all_partnerships = self._parse_summary(summary_data, dismissal_map)

        # Merge commentary into corresponding innings
        for inn in innings:
            inn_clean = inn.inning_name.lower().replace("innings", "inning").strip()
            inn_balls = [
                b for b in all_balls
                if b.inning_name.lower().replace("innings", "inning").strip() == inn_clean
            ]
            inn.ball_by_ball = inn_balls

        return MatchData(
            metadata=metadata,
            innings=innings,
            partnerships=all_partnerships,
            all_balls=all_balls
        )

    def _parse_summary(self, data: Dict[str, Any], dismissal_map: Dict[str, str]) -> Tuple[MatchMetadata, List[Inning], List[Partnership]]:
        header = data.get("header", {})
        comp = header.get("competitions", [{}])[0]
        match_title = header.get("name") or comp.get("description", "Cricket Match")

        # Series name
        series_name = ""
        season = header.get("season", {})
        if isinstance(season, dict) and season.get("name"):
            series_name = season.get("name")
        elif header.get("league", {}).get("description"):
            series_name = header.get("league", {}).get("description")

        # Venue
        venue_name = comp.get("venue", {}).get("fullName", "")
        if not venue_name and data.get("gameInfo", {}).get("venue"):
            venue_name = data.get("gameInfo", {}).get("venue", {}).get("fullName", "")

        # Toss
        toss = ""
        for n in data.get("notes", []):
            if n.get("type") == "toss":
                toss = n.get("text", "").strip()

        # Status & Live Detection
        status_state = comp.get("status", {}).get("type", {}).get("state", "").lower()
        status_desc = comp.get("status", {}).get("type", {}).get("description", "")
        status_detail = comp.get("status", {}).get("summary") or comp.get("status", {}).get("type", {}).get("detail", "")

        # Determine whether match is actively live or concluded
        if status_state == "in":
            is_live = True
        elif status_state == "post" or any(k in (status_desc + " " + status_detail).lower() for k in ["won by", "completed", "result", "abandoned", "concluded", "match tied"]):
            is_live = False
        else:
            is_live = any(k in (status_desc + " " + status_detail).lower() for k in ["live", "require", "need", "trail", "lead", "stumps", "break", "delayed", "in progress"])

        metadata = MatchMetadata(
            match_id=self.match_id,
            match_title=match_title,
            series=series_name,
            venue=venue_name,
            toss=toss,
            status=status_desc,
            status_note=status_detail,
            source_url=self.raw_url,
            source_platform=self.platform_name,
            is_live=is_live
        )

        competitors = comp.get("competitors", [])
        rosters = data.get("rosters", [])
        innings: List[Inning] = []
        all_partnerships: List[Partnership] = []

        # Find all periods across competitors linescores
        periods_found = set()
        for c in competitors:
            for ls in c.get("linescores", []):
                p = ls.get("period")
                if p:
                    periods_found.add(int(p))

        # Build each inning
        for period in sorted(periods_found):
            # Identify batting team
            batting_team_name = ""
            batting_team_id = ""
            bowling_team_name = ""
            bowling_team_id = ""
            batting_linescore = None

            for c in competitors:
                t_id = str(c.get("team", {}).get("id"))
                for ls in c.get("linescores", []):
                    if ls.get("period") == period and ls.get("score"):
                        batting_team_name = c.get("team", {}).get("displayName", "")
                        batting_team_id = t_id
                        batting_linescore = ls
                        break
                if batting_team_id:
                    break

            # Identify bowling team (the opposite competitor)
            for c in competitors:
                t_id = str(c.get("team", {}).get("id"))
                if t_id != batting_team_id:
                    bowling_team_name = c.get("team", {}).get("displayName", "")
                    bowling_team_id = t_id
                    break

            if not batting_team_name:
                continue

            # Inning Name & Header Summary
            inn_name = f"{batting_team_name} Inning"
            total_runs = batting_linescore.get("runs") or batting_linescore.get("score", "")
            overs_val = str(batting_linescore.get("overs", ""))
            wickets_val = str(batting_linescore.get("wickets", ""))
            score_summary = f"{batting_team_name} Inning {total_runs}/{wickets_val} ({overs_val} ov)"

            # Batting rows
            batters: List[BattingRow] = []
            for r in rosters:
                if str(r.get("team", {}).get("id")) == batting_team_id:
                    for p in r.get("roster", []):
                        ath = p.get("athlete", {})
                        p_name = ath.get("displayName", "")
                        for ls in p.get("linescores", []):
                            if ls.get("period") == period:
                                stats_dict = self._flatten_stats(ls)
                                if stats_dict.get("batted") == "1":
                                    r_val = int(stats_dict.get("runs", 0))
                                    b_val = int(stats_dict.get("ballsFaced", 0))
                                    fours_val = int(stats_dict.get("fours", 0))
                                    sixes_val = int(stats_dict.get("sixes", 0))
                                    sr_str = stats_dict.get("strikeRate", "0.0")
                                    sr_val = float(sr_str) if sr_str and sr_str != "-" else 0.0

                                    if stats_dict.get("notouts") == "1":
                                        d_card = "not out"
                                    else:
                                        d_card = dismissal_map.get(p_name)
                                        if not d_card:
                                            # Try matching by last name or partial name
                                            p_parts = [part.lower() for part in p_name.split() if len(part) > 2]
                                            for k, v in dismissal_map.items():
                                                if k and (k in p_name or p_name in k or any(part in k.lower() for part in p_parts)):
                                                    d_card = v
                                                    break
                                        if not d_card:
                                            d_card = stats_dict.get("dismissalCard") or "out"

                                    pos = int(stats_dict.get("battingPosition", 99))

                                    batters.append((pos, BattingRow(
                                        batter=p_name,
                                        dismissal=d_card,
                                        runs=r_val,
                                        balls=b_val,
                                        fours=fours_val,
                                        sixes=sixes_val,
                                        strike_rate=sr_val
                                    )))
            # Sort batters by batting order
            batters.sort(key=lambda x: x[0])
            sorted_batters = [b[1] for b in batters]

            # Bowling rows
            bowlers: List[BowlingRow] = []
            for r in rosters:
                if str(r.get("team", {}).get("id")) == bowling_team_id:
                    for p in r.get("roster", []):
                        ath = p.get("athlete", {})
                        p_name = ath.get("displayName", "")
                        for ls in p.get("linescores", []):
                            if ls.get("period") == period:
                                stats_dict = self._flatten_stats(ls)
                                if stats_dict.get("overs") and stats_dict.get("overs") != "0":
                                    o_val = float(stats_dict.get("overs", 0.0))
                                    m_val = int(stats_dict.get("maidens", 0))
                                    r_conc = int(stats_dict.get("conceded", 0))
                                    w_val = int(stats_dict.get("wickets", 0))
                                    econ_str = stats_dict.get("economyRate", "0.0")
                                    econ_val = float(econ_str) if econ_str and econ_str != "-" else 0.0
                                    b_order = int(stats_dict.get("bowlingPosition", 99))

                                    bowlers.append((b_order, BowlingRow(
                                        bowler=p_name,
                                        overs=o_val,
                                        maidens=m_val,
                                        runs=r_conc,
                                        wickets=w_val,
                                        economy=econ_val
                                    )))
            # Sort bowlers by bowling order
            bowlers.sort(key=lambda x: x[0])
            sorted_bowlers = [bo[1] for bo in bowlers]

            # Extras
            extras_dict = self._flatten_stats(batting_linescore)
            extras_total = int(extras_dict.get("extras", 0)) if extras_dict.get("extras", "").isdigit() else 0
            byes = int(extras_dict.get("byes", 0)) if extras_dict.get("byes", "").isdigit() else 0
            leg_byes = int(extras_dict.get("legbyes", 0)) if extras_dict.get("legbyes", "").isdigit() else 0
            wides = int(extras_dict.get("wides", 0)) if extras_dict.get("wides", "").isdigit() else 0
            no_balls = int(extras_dict.get("noballs", 0)) if extras_dict.get("noballs", "").isdigit() else 0

            extras_info = ExtrasInfo(
                total=extras_total,
                byes=byes,
                leg_byes=leg_byes,
                wides=wides,
                no_balls=no_balls,
                raw=f"{extras_total} (b {byes}, w {wides}, nb {no_balls}, lb {leg_byes})"
            )

            # Total
            total_info = TotalInfo(raw=f"{total_runs}/{wickets_val} ({overs_val} ov)", overs=overs_val)

            # Fall of Wickets
            fows: List[FallOfWicket] = []
            for f in batting_linescore.get("fow", []):
                if isinstance(f, dict):
                    w_num = int(f.get("wicketNumber", 0))
                    t_score = int(f.get("runs", 0))
                    b_out = f.get("athlete", {}).get("displayName") or f.get("batsman", {}).get("displayName", "")
                    o_fow = float(f.get("wicketOver", f.get("overs", 0.0)))
                    fows.append(FallOfWicket(
                        wicket_num=w_num,
                        team_score=t_score,
                        batter_out=b_out,
                        over=o_fow
                    ))

            # Partnerships
            inn_parts: List[Partnership] = []
            for p in batting_linescore.get("partnerships", []):
                if isinstance(p, dict):
                    m_runs = int(p.get("runs", 0))
                    p_overs = float(p.get("overs", 0.0))
                    b_list = p.get("batsmen", [])
                    b1 = BatterContribution(name="", runs=0, balls=0)
                    b2 = BatterContribution(name="", runs=0, balls=0)
                    if len(b_list) >= 1:
                        b1 = BatterContribution(
                            name=b_list[0].get("athlete", {}).get("displayName", ""),
                            runs=int(b_list[0].get("runs", 0)),
                            balls=int(b_list[0].get("balls", 0)) if str(b_list[0].get("balls", "0")).isdigit() else 0
                        )
                    if len(b_list) >= 2:
                        b2 = BatterContribution(
                            name=b_list[1].get("athlete", {}).get("displayName", ""),
                            runs=int(b_list[1].get("runs", 0)),
                            balls=int(b_list[1].get("balls", 0)) if str(b_list[1].get("balls", "0")).isdigit() else 0
                        )

                    p_balls = p.get('balls')
                    if p_balls is not None and str(p_balls).isdigit() and int(p_balls) > 0:
                        total_p_balls = int(p_balls)
                    elif (b1.balls > 0 or b2.balls > 0):
                        total_p_balls = b1.balls + b2.balls
                    else:
                        o_str = str(p.get("overs", "0"))
                        if "." in o_str:
                            ov_comp, bl_comp = o_str.split(".", 1)
                            total_p_balls = int(ov_comp) * 6 + int(bl_comp[:1])
                        else:
                            total_p_balls = int(float(o_str)) * 6

                    raw_desc = f"{m_runs} runs ({total_p_balls} balls) - {b1.name} & {b2.name}"
                    part = Partnership(
                        milestone_runs=m_runs,
                        balls=total_p_balls,
                        batter_1=b1,
                        batter_2=b2,
                        raw_text=raw_desc,
                        source_day=inn_name
                    )
                    inn_parts.append(part)
                    all_partnerships.append(part)

            # Reviews
            reviews = batting_linescore.get("reviews", {})

            innings.append(Inning(
                inning_name=inn_name,
                header_summary=score_summary,
                batting=sorted_batters,
                bowling=sorted_bowlers,
                extras=extras_info,
                total=total_info,
                fall_of_wickets=fows,
                reviews=reviews if isinstance(reviews, dict) else {}
            ))

        return metadata, innings, all_partnerships

    def _flatten_stats(self, linescore: Dict[str, Any]) -> Dict[str, Any]:
        stats_dict = {}
        for cat in linescore.get("statistics", {}).get("categories", []):
            for s in cat.get("stats", []):
                stats_dict[s.get("name")] = str(s.get("displayValue", ""))
        return stats_dict

    async def _fetch_all_commentary(self, series_id: str, match_id: str) -> Tuple[List[BallByBallEvent], Dict[str, str]]:
        all_events: List[BallByBallEvent] = []
        dismissal_map: Dict[str, str] = {}

        # Fetch for both period 1 and period 2 (up to 4 periods for test matches)
        for period in [1, 2, 3, 4]:
            p1_url = f"https://site.web.api.espn.com/apis/site/v2/sports/cricket/{series_id}/playbyplay?contentorigin=espn&event={match_id}&page=1&period={period}&section=cricinfo"
            try:
                p1_data = await asyncio.to_thread(self._fetch_json, p1_url)
            except Exception:
                break

            comm = p1_data.get("commentary", {})
            page_count = int(comm.get("pageCount", 1))
            items = comm.get("items", [])
            if not items:
                continue

            for item in items:
                ev = self._parse_commentary_item(item, dismissal_map)
                if ev:
                    all_events.append(ev)

            # Fetch remaining pages if any
            for page in range(2, page_count + 1):
                p_url = f"https://site.web.api.espn.com/apis/site/v2/sports/cricket/{series_id}/playbyplay?contentorigin=espn&event={match_id}&page={page}&period={period}&section=cricinfo"
                try:
                    p_data = await asyncio.to_thread(self._fetch_json, p_url)
                    p_items = p_data.get("commentary", {}).get("items", [])
                    for item in p_items:
                        ev = self._parse_commentary_item(item, dismissal_map)
                        if ev:
                            all_events.append(ev)
                except Exception:
                    pass

        return all_events, dismissal_map

    def _parse_commentary_item(self, item: Dict[str, Any], dismissal_map: Dict[str, str]) -> Optional[BallByBallEvent]:
        over_info = item.get("over", {})
        actual_over = over_info.get("actual")
        if actual_over is None:
            return None

        over_str = str(actual_over)
        over_num = int(over_info.get("number", 0))
        ball_num = int(over_info.get("ball", 0))
        runs = int(item.get("scoreValue", 0))

        team_name = item.get("team", {}).get("displayName", "Inning")
        inning_name = f"{team_name} Inning"

        bowler_name = item.get("bowler", {}).get("athlete", {}).get("displayName", "")
        batter_name = item.get("batsman", {}).get("athlete", {}).get("displayName", "")
        outcome = item.get("playType", {}).get("description", "")
        comm_text = item.get("text") or item.get("shortText", "")
        raw_text = item.get("shortText", "") + (" - " + comm_text if comm_text else "")

        # Check dismissal
        d_info = item.get("dismissal", {})
        is_wicket = bool(d_info.get("dismissal"))
        if is_wicket:
            out_batter = d_info.get("batsman", {}).get("athlete", {}).get("displayName") or batter_name
            f_name = d_info.get("fielder", {}).get("athlete", {}).get("displayName")
            b_name = d_info.get("bowler", {}).get("athlete", {}).get("displayName") or bowler_name
            d_type = d_info.get("type", "").strip()
            
            # Format dismissal description with robust defaults
            d_desc = d_type or "out"
            if d_type == "caught":
                if f_name and b_name and f_name == b_name:
                    d_desc = f"c & b {b_name}"
                elif f_name and b_name:
                    d_desc = f"c {f_name} b {b_name}"
                elif b_name:
                    d_desc = f"c {b_name}"
            elif d_type == "bowled":
                d_desc = f"b {b_name}" if b_name else "bowled"
            elif d_type == "lbw":
                d_desc = f"lbw b {b_name}" if b_name else "lbw"
            elif d_type == "run out":
                d_desc = f"run out ({f_name})" if f_name else "run out"
            elif d_type == "stumped":
                d_desc = f"st †{f_name} b {b_name}" if f_name and b_name else (f"st {f_name}" if f_name else f"st b {b_name}")
            elif d_type == "hit wicket":
                d_desc = f"hit wicket b {b_name}" if b_name else "hit wicket"
            elif "retired" in d_type.lower():
                d_desc = d_type
            elif d_info.get("text"):
                d_desc = d_info.get("text")

            d_desc = d_desc.replace("&dagger;", "†").replace("&amp;", "&").strip()
            if out_batter:
                dismissal_map[out_batter] = d_desc

        is_four = runs == 4 or "four" in outcome.lower() or "4" in outcome
        is_six = runs == 6 or "six" in outcome.lower() or "6" in outcome

        is_extra = bool(over_info.get("wide") or over_info.get("noBall") or over_info.get("legByes") or over_info.get("byes"))
        extra_type = ""
        if over_info.get("wide"): extra_type = "wide"
        elif over_info.get("noBall"): extra_type = "no_ball"
        elif over_info.get("legByes"): extra_type = "leg_bye"
        elif over_info.get("byes"): extra_type = "bye"

        return BallByBallEvent(
            inning_name=inning_name,
            over_str=over_str,
            over_num=over_num,
            ball_num=ball_num,
            runs=runs,
            bowler=bowler_name,
            batter=batter_name,
            outcome=outcome,
            commentary_text=comm_text,
            is_four=is_four,
            is_six=is_six,
            is_wicket=is_wicket,
            is_extra=is_extra,
            extra_type=extra_type,
            raw_event=raw_text
        )
