import os
import re
import glob
import json
import time
import threading
from typing import List, Dict, Any, Tuple, Optional
from core.models import (
    MatchData, Inning, BattingRow, BowlingRow, 
    Partnership, BallByBallEvent, FallOfWicket, ExtrasInfo, TotalInfo
)

class HermesBrain:
    """
    Hermes Brain Engine:
    Unified master orchestrator powering:
    1. Scorecard Audit & Self-Healing: guarantees complete extras, batting strike rates, boundaries, FOW.
    2. Autonomous Background Scheduler:
       - 10-minute live matches directory refresh from Cricinfo/Cricbuzz.
       - 1-hour schedule/fixtures refresh (Cricinfo 2-column format).
       - 1-hour live cricket news & high-res images refresh.
       - 1-hour tournament standings & points table refresh.
       - 24-hour teams directory refresh.
       - 24-hour ICC rankings refresh.
    3. Master State & Platform Matches Provider:
       - Merges scraped match JSONs with feed matches.
       - Prioritizes target matches from urls.txt and match_mappings.json.
       - Auto-transitions match states (Upcoming -> Live -> Recent).
       - Populates top carousel strip with clean pills (LIVE, Result, Preview - NO emojis).
    4. Match Mapping & URL Router:
       - Binds any match to Cricinfo, Cricbuzz, or CREX.
       - Syncs urls.txt and triggers immediate background ingestion.
    5. Bowler Dot Balls: Wickets, Leg-byes, and Byes are considered as Dot Balls in the bowler session.
    6. Partnership Boundaries: Calculates 4s, 6s, boundary runs, and handles Retired Hurt vs Retired Out rules.
    7. Impact Overs: Detects high-momentum overs with 10 or more runs, per inning and match-wide.
    """

    _scheduler_thread: Optional[threading.Thread] = None
    _scheduler_running: bool = False
    _scheduler_lock = threading.Lock()

    @classmethod
    def analyze(cls, match_data: MatchData) -> MatchData:
        if not match_data:
            return match_data

        # 0. Audit & Self-Heal scorecard (guarantee full extras, strike rates, boundaries, FOW)
        match_data = cls.audit_and_heal_scorecard(match_data)

        # 1. Compute bowler dot balls for each inning
        for inn in match_data.innings:
            cls._compute_bowler_dot_balls(inn)

        # 2. Compute partnership boundaries and enforce retired hurt/out rules
        cls._enrich_partnerships(match_data)

        # 3. Compute impact overs (>= 10 runs) per inning and match total
        total_match_impact_overs = 0
        for inn in match_data.innings:
            impact_cnt, impact_list = cls._compute_impact_overs(inn)
            inn.impact_overs_count = impact_cnt
            inn.impact_overs_list = impact_list
            total_match_impact_overs += impact_cnt

        match_data.metadata.match_impact_overs = total_match_impact_overs

        # 4. Generate holistic Hermes Analysis payload
        match_data.hermes_analysis = cls._build_hermes_analysis(match_data)

        return match_data

    # =========================================================================
    # 1. Bowler Dot Balls Engine
    # =========================================================================
    @classmethod
    def _compute_bowler_dot_balls(cls, inning: Inning):
        """
        Rule: Wickets, Leg byes and Byes are Considered as DotBall in Bowler Session.
        A delivery is a dot ball for the bowler if:
        - 0 runs scored off the bat (and not wide/no-ball)
        - OR wicket fell (is_wicket is True)
        - OR extra_type is 'leg_bye' or 'bye'
        """
        bowler_dots: Dict[str, int] = {}

        for b in inning.ball_by_ball:
            b_name = b.bowler.strip()
            if not b_name:
                continue

            outcome_clean = b.outcome.lower().strip()
            is_extra_wide_nb = b.extra_type in ['wide', 'no_ball'] or 'wide' in outcome_clean or 'no ball' in outcome_clean

            is_dot = False
            if not is_extra_wide_nb:
                if b.is_wicket or 'out' in outcome_clean or 'wicket' in outcome_clean:
                    is_dot = True
                elif b.extra_type in ['bye', 'leg_bye'] or 'bye' in outcome_clean:
                    is_dot = True
                elif b.runs == 0 or outcome_clean in ['no run', 'dot', '0', '0 runs', 'dot ball']:
                    is_dot = True

            if is_dot:
                bowler_dots[b_name] = bowler_dots.get(b_name, 0) + 1

        for bo in inning.bowling:
            b_name = bo.bowler.strip()
            dots = bowler_dots.get(b_name)
            if dots is None:
                for k, v in bowler_dots.items():
                    if k in b_name or b_name in k or (k.split() and b_name.split() and k.split()[-1] == b_name.split()[-1]):
                        dots = v
                        break
            bo.dot_balls = dots if dots is not None else 0

    # =========================================================================
    # 2. Partnership Boundaries & Retirement Rules
    # =========================================================================
    @classmethod
    def _enrich_partnerships(cls, match_data: MatchData):
        """
        Rule:
        - Display partnership boundaries next to runs.
        - Retired Hurt Means Not Counted as Wicket, Partnership will be Continued with Next Batsman.
        - Retired Out will Be Considered as Wicket.
        """
        for p in match_data.partnerships:
            b1_name = p.batter_1.name.strip().lower()
            b2_name = p.batter_2.name.strip().lower()

            fours = 0
            sixes = 0

            relevant_balls = []
            for b in match_data.all_balls:
                b_bat = b.batter.strip().lower()
                if (b1_name in b_bat or b_bat in b1_name) or (b2_name in b_bat or b_bat in b2_name):
                    relevant_balls.append(b)

            for b in relevant_balls:
                if b.is_four or 'four' in b.outcome.lower() or b.runs == 4:
                    fours += 1
                elif b.is_six or 'six' in b.outcome.lower() or b.runs == 6:
                    sixes += 1

            boundary_runs = (fours * 4) + (sixes * 6)
            if boundary_runs > p.milestone_runs and p.milestone_runs > 0:
                max_fours = p.milestone_runs // 4
                fours = min(fours, max_fours)
                rem_runs = p.milestone_runs - (fours * 4)
                sixes = min(sixes, rem_runs // 6)
                boundary_runs = (fours * 4) + (sixes * 6)

            p.fours = fours
            p.sixes = sixes
            p.boundary_runs = boundary_runs

            if fours > 0 or sixes > 0:
                p.boundary_str = f"{fours}x4, {sixes}x6" if sixes > 0 else f"{fours}x4"
            else:
                p.boundary_str = "0x4, 0x6"

    # =========================================================================
    # 3. Impact Overs Engine (>= 10 runs per over)
    # =========================================================================
    @classmethod
    def _compute_impact_overs(cls, inning: Inning) -> Tuple[int, List[Dict[str, Any]]]:
        """
        Rule:
        Impact Over's: Number of Over's Scored 10 Runs or above.
        If a Team all out or Match Resulted in 15.1 then Considered as 16 Over.
        """
        if not inning.ball_by_ball:
            return 0, []

        overs_map: Dict[int, List[BallByBallEvent]] = {}
        for b in inning.ball_by_ball:
            o_idx = b.over_num + 1 if b.over_num < 50 else b.over_num
            overs_map.setdefault(o_idx, []).append(b)

        impact_list: List[Dict[str, Any]] = []

        for o_num in sorted(overs_map.keys()):
            balls = overs_map[o_num]
            total_runs = sum(b.runs for b in balls)
            wickets = sum(1 for b in balls if b.is_wicket or b.outcome.lower().strip() in ('w', 'out') or 'wicket' in b.outcome.lower())
            bowler = balls[-1].bowler if balls else 'Unknown'
            outcomes = [b.outcome for b in balls]

            if total_runs >= 10:
                impact_list.append({
                    'over_number': o_num,
                    'over_label': f'Over {o_num}',
                    'runs': total_runs,
                    'wickets': wickets,
                    'bowler': bowler,
                    'ball_outcomes': outcomes,
                    'ball_count': len(balls)
                })

        return len(impact_list), impact_list

    @classmethod
    def _build_hermes_analysis(cls, match_data: MatchData) -> Dict[str, Any]:
        inn_summaries = []
        total_match_runs = 0
        total_match_wickets = 0
        total_match_dots = 0

        for idx, inn in enumerate(match_data.innings, 1):
            inn_runs = sum(b.runs for b in inn.batting)
            inn_dots = sum(bo.dot_balls for bo in inn.bowling)
            inn_wkts = sum(bo.wickets for bo in inn.bowling)

            total_match_runs += inn_runs
            total_match_wickets += inn_wkts
            total_match_dots += inn_dots

            inn_summaries.append({
                'inning_index': idx,
                'inning_name': inn.inning_name,
                'header_summary': inn.header_summary,
                'impact_overs_count': inn.impact_overs_count,
                'impact_overs': inn.impact_overs_list,
                'total_dot_balls': inn_dots,
                'total_wickets': inn_wkts
            })

        return {
            'engine': 'Hermes Brain Analytics v2.0',
            'match_id': match_data.metadata.match_id,
            'match_title': match_data.metadata.match_title,
            'is_live': match_data.metadata.is_live,
            'match_impact_overs': match_data.metadata.match_impact_overs,
            'total_match_dots': total_match_dots,
            'innings_analysis': inn_summaries
        }

    # =========================================================================
    # 4. Scorecard Self-Healing & Data Integrity Auditor
    # =========================================================================
    @classmethod
    def audit_and_heal_scorecard(cls, match_data: MatchData) -> MatchData:
        """
        Self-heals scorecards when scrapers (like CREX) omit extras or batter statistics:
        - If extras is missing or total == 0, calculates exact extras from ball-by-ball deliveries.
        - Recalculates strike rates and guarantees non-negative integer boundaries.
        - Reconstructs Fall of Wickets from ball-by-ball feed if omitted by source.
        - Verifies and restores TotalInfo (sum of batter runs + extras).
        """
        for inn in match_data.innings:
            # 1. Audit Batting Strike Rates & Boundaries
            for b in inn.batting:
                if b.balls > 0 and (b.strike_rate == 0.0 or b.strike_rate is None):
                    b.strike_rate = round((b.runs / b.balls) * 100, 2)
                b.fours = max(0, int(b.fours or 0))
                b.sixes = max(0, int(b.sixes or 0))

                # If boundaries are 0 but batter scored runs and ball deliveries exist, count them
                if b.runs > 0 and b.fours == 0 and b.sixes == 0 and inn.ball_by_ball:
                    b_last = b.batter.split()[-1].lower() if b.batter.split() else b.batter.lower()
                    f_cnt = 0
                    s_cnt = 0
                    for ball in inn.ball_by_ball:
                        ball_bat = (ball.batter or "").lower()
                        if b_last in ball_bat or ball_bat in b.batter.lower():
                            if ball.is_four or ball.runs == 4 or 'four' in ball.outcome.lower():
                                f_cnt += 1
                            elif ball.is_six or ball.runs == 6 or 'six' in ball.outcome.lower():
                                s_cnt += 1
                    if f_cnt > 0 or s_cnt > 0:
                        b.fours = f_cnt
                        b.sixes = s_cnt

            # 2. Audit Extras from Ball Feed if missing or empty
            needs_extras_healing = inn.extras is None or (inn.extras.total == 0 and inn.extras.wides == 0 and inn.extras.no_balls == 0)
            if needs_extras_healing and inn.ball_by_ball:
                wides = 0
                no_balls = 0
                byes = 0
                leg_byes = 0
                for ball in inn.ball_by_ball:
                    outc = (ball.outcome or '').strip().lower()
                    xtype = (getattr(ball, 'extra_type', '') or '').strip().lower()
                    r = ball.runs
                    if 'wide' in outc or 'wd' in outc or xtype == 'wide':
                        wides += r if r > 0 else 1
                    elif 'no ball' in outc or 'nb' in outc or xtype in ('no_ball', 'no ball'):
                        no_balls += r if r > 0 else 1
                    elif 'leg bye' in outc or 'lb' in outc or xtype in ('leg_bye', 'leg bye'):
                        leg_byes += r if r > 0 else 1
                    elif 'bye' in outc or xtype == 'bye':
                        byes += r if r > 0 else 1

                total_calc = wides + no_balls + byes + leg_byes
                if total_calc > 0:
                    raw_str = f"{total_calc} (b {byes}, lb {leg_byes}, w {wides}, nb {no_balls})"
                    inn.extras = ExtrasInfo(
                        raw=raw_str,
                        byes=byes,
                        leg_byes=leg_byes,
                        wides=wides,
                        no_balls=no_balls,
                        penalty=0,
                        total=total_calc
                    )

            # 3. Fall of Wickets Self-Healing if missing from scraper
            if not inn.fall_of_wickets and inn.ball_by_ball:
                fow_list = []
                running_score = 0
                wkt_num = 0
                for ball in inn.ball_by_ball:
                    running_score += ball.runs
                    outc = (ball.outcome or '').lower()
                    if ball.is_wicket or 'out' in outc or 'wicket' in outc or outc.startswith('w'):
                        wkt_num += 1
                        try:
                            ball_ov = float(ball.over_str) if ball.over_str else float(f"{ball.over_num}.{getattr(ball, 'ball_num', 1)}")
                        except Exception:
                            ball_ov = float(ball.over_num)
                        fow_list.append(FallOfWicket(
                            wicket_num=wkt_num,
                            team_score=running_score,
                            batter_out=ball.batter or f"Batter {wkt_num}",
                            over=ball_ov
                        ))
                if fow_list:
                    inn.fall_of_wickets = fow_list

            # 4. TotalInfo Self-Healing
            if inn.total is None or not inn.total.raw or inn.total.raw == "0/0":
                sum_bat_runs = sum(b.runs for b in inn.batting)
                extras_tot = inn.extras.total if inn.extras else 0
                total_runs = sum_bat_runs + extras_tot
                wkts = sum(1 for b in inn.batting if b.dismissal and "not out" not in b.dismissal.lower())
                total_balls = len(inn.ball_by_ball)
                ov_str = f"{total_balls // 6}.{total_balls % 6}" if total_balls > 0 else "0.0"
                inn.total = TotalInfo(
                    raw=f"{total_runs}/{wkts}",
                    overs=f"({ov_str} ov)",
                    run_rate=f"{(total_runs / (total_balls / 6.0)):.2f}" if total_balls >= 6 else ""
                )

        return match_data

    ABBREV_MAP = {
        'gaw': 'Guyana Amazon Warriors',
        'abf': 'Antigua & Barbuda Falcons',
        'bbt': 'Barbados Tridents',
        'bt': 'Barbados Tridents',
        'jkm': 'Jamaica Kingsmen',
        'jk': 'Jamaica Kingsmen',
        'tkr': 'Trinbago Knight Riders',
        'tk': 'Trinbago Knight Riders',
        'slk': 'St Lucia Kings',
        'sknp': 'St Kitts and Nevis Patriots',
        'gaww': 'Guyana Amazon Warriors Women',
        'tkrw': 'Trinbago Knight Riders Women',
        'brw': 'Barbados Royals Women',
        'ind': 'India',
        'aus': 'Australia',
        'eng': 'England',
        'sl': 'Sri Lanka',
        'pak': 'Pakistan',
        'sa': 'South Africa',
        'afg': 'Afghanistan',
        'nz': 'New Zealand',
        'wi': 'West Indies',
        'ban': 'Bangladesh',
        'zim': 'Zimbabwe',
        'ire': 'Ireland',
        'e': 'England',
        'ga': 'Guyana Amazon Warriors'
    }

    @classmethod
    def clean_team_name(cls, name: str) -> str:
        if not name:
            return ''
        s = name.replace('&a;', '&').replace('&l;', '<').replace('&g;', '>').replace('&s;', "'").replace('&nbsp;', ' ').strip()
        s = re.sub(r'(?i)\b(LIVE|RECENT|PREVIEW|UPCOMING)\b$', '', s).strip()
        s = re.sub(r'(?i)(LIVE|RECENT|PREVIEW|UPCOMING)$', '', s).strip()
        low = s.lower().replace('.', '').strip()
        if low in cls.ABBREV_MAP:
            return cls.ABBREV_MAP[low]
        return s

    @classmethod
    def clean_match_item(cls, item: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitizes match title, teams, stage, and ensures clean readable text."""
        # Unescape &a; entities across all text fields
        for k in ["title", "team_1", "team_2", "series", "status", "stage", "venue", "situation"]:
            if k in item and isinstance(item[k], str):
                item[k] = item[k].replace('&a;', '&').replace('&l;', '<').replace('&g;', '>').replace('&s;', "'").replace('&nbsp;', ' ').strip()

        title = item.get("title", "").strip()
        title = re.sub(r'(?i)\b(LIVE|RECENT|PREVIEW|UPCOMING)\b$', '', title).strip()
        title = re.sub(r'(?i)(LIVE|RECENT|PREVIEW|UPCOMING)$', '', title).strip()

        stage = item.get("stage", "Match") or "Match"
        m_st = re.search(r'([A-Za-z0-9\s]+?)(Qualifier\s*\d*|Eliminator\s*\d*|Final|\d+(?:st|nd|rd|th)?\s*(?:unofficial\s*)?(?:T20I?|ODI|Test|Match|Quarter\s*Final|Semi\s*Final))$', title, re.I)
        if m_st and len(m_st.group(1).strip()) > 3:
            extracted_stage = m_st.group(2).strip().title()
            title = m_st.group(1).strip()
            if stage == "Match" or not stage:
                stage = extracted_stage

        t1 = item.get("team_1", "")
        t2 = item.get("team_2", "")
        if " vs " in title:
            p1, p2 = title.split(" vs ", 1)
            t1 = cls.clean_team_name(p1)
            t2 = cls.clean_team_name(p2)
            title = f"{t1} vs {t2}"
        elif " v " in title:
            p1, p2 = title.split(" v ", 1)
            t1 = cls.clean_team_name(p1)
            t2 = cls.clean_team_name(p2)
            title = f"{t1} vs {t2}"
        else:
            if t1:
                t1 = cls.clean_team_name(t1)
            if t2:
                t2 = cls.clean_team_name(t2)
            if t1 and t2:
                title = f"{t1} vs {t2}"

        item["title"] = title
        item["team_1"] = t1
        item["team_2"] = t2
        item["stage"] = stage

        # Clean status text: remove brackets around (35b rem)
        st = item.get("status", "")
        if "(" in st and ")" in st:
            m_b = re.search(r'\((\d+)\s*(?:b|balls)?\s*(?:rem|remaining)?\)', st, re.I)
            if m_b:
                item["balls_remaining"] = f"{m_b.group(1)} balls remaining"
                item["status"] = st[:m_b.start()].strip() + " " + st[m_b.end():].strip()
        return item

    # =========================================================================
    # 5. Match Lifecycle Automation (Upcoming -> Live -> Recent)
    # =========================================================================
    @classmethod
    def update_match_lifecycle(cls, matches_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Hermes Brain automated lifecycle processor:
        - Detects started matches in 'upcoming' and shifts them to 'live'.
        - Detects concluded matches in 'live' and shifts them to 'recent'.
        - Deduplicates and synchronizes all categories and top carousel.
        """
        live_list = matches_data.get("live", [])
        recent_list = matches_data.get("recent", [])
        upcoming_list = matches_data.get("upcoming", [])

        all_matches_map: Dict[str, Dict[str, Any]] = {}
        for m in upcoming_list + live_list + recent_list:
            mid = str(m.get("match_id", ""))
            if mid:
                all_matches_map[mid] = m

        new_live = []
        new_recent = []
        new_upcoming = []

        completed_indicators = ["won by", "won", "result", "completed", "abandoned", "match tied", "tied", "concluded", "no result"]
        scheduled_indicators = ["scheduled", "preview", "starts at", "match begins", "starts in"]
        live_indicators = ["live in progress", "opt to bat", "opt to bowl", "require ", "need "]

        for mid, m in all_matches_map.items():
            cls.clean_match_item(m)
            status_text = (m.get("status", "") + " " + m.get("title", "")).lower()
            is_done = m.get("is_completed", False) or any(k in status_text for k in completed_indicators)
            is_scheduled = any(k in status_text for k in scheduled_indicators)
            is_stumps = any(k in status_text for k in ["stumps", "day 1 -", "day 2 -", "day 3 -", "day 4 -"])

            # A match is active/live only if explicitly live in progress or active situation, not completed, not scheduled, and not stumps
            is_active = (m.get("is_live", False) or any(k in status_text for k in live_indicators)) and not is_done and not is_scheduled and not is_stumps

            if is_done:
                m["is_live"] = False
                m["is_completed"] = True
                new_recent.append(m)
            elif is_active:
                m["is_live"] = True
                m["is_completed"] = False
                new_live.append(m)
            else:
                m["is_live"] = False
                m["is_completed"] = False
                new_upcoming.append(m)

        matches_data["live"] = new_live
        matches_data["recent"] = new_recent
        matches_data["upcoming"] = new_upcoming

        # Update Top Carousel Pills
        top_carousel = matches_data.get("top_carousel", [])
        for c in top_carousel:
            c_mid = str(c.get("match_id", ""))
            if c_mid in all_matches_map:
                m_info = all_matches_map[c_mid]
                if m_info.get("is_live"):
                    c["status_pill"] = "LIVE"
                elif m_info.get("is_completed"):
                    c["status_pill"] = "Result"
                else:
                    c["status_pill"] = "Preview"

        # Update Drawer Matches Lifecycle (Prevents "LIVE england won by 6 wkts" anomalies)
        drawer = matches_data.get("drawer", {})
        for cat, d_list in drawer.items():
            for m in d_list:
                cls.clean_match_item(m)
                st_text = (str(m.get("status", "")) + " " + str(m.get("title", ""))).lower()
                is_done = m.get("is_completed", False) or any(k in st_text for k in completed_indicators)
                is_sched = any(k in st_text for k in scheduled_indicators)
                is_stumps = any(k in st_text for k in ["stumps", "day 1 -", "day 2 -", "day 3 -", "day 4 -", "break", "tea", "lunch"])
                is_active = (m.get("is_live", False) or any(k in st_text for k in live_indicators)) and not is_done and not is_sched and not is_stumps
                if is_done:
                    m["is_live"] = False
                    m["is_completed"] = True
                    m["status_pill"] = "Result"
                elif is_active:
                    m["is_live"] = True
                    m["is_completed"] = False
                    m["status_pill"] = "LIVE"
                else:
                    m["is_live"] = False
                    m["is_completed"] = False
                    m["status_pill"] = "Preview" if is_sched else ("Stumps" if is_stumps else "Result")

        return matches_data

    # =========================================================================
    # 6. Master Platform Matches Provider
    # =========================================================================
    @classmethod
    def get_platform_matches_data(cls, output_dir: str = "output") -> Dict[str, Any]:
        """
        Hermes Brain Master Matches Data Provider:
        - Reads matches.json
        - Scans scraped match files (match_*_full.json)
        - Reads urls.txt and match_mappings.json for target prioritization
        - Normalizes team names, scores, status, balls remaining
        - Applies automated lifecycle (Upcoming -> Live -> Recent)
        - Synchronizes top carousel strip with clean CSS pills (LIVE, Result, Preview - NO emojis)
        - Returns unified structured dictionary.
        """
        data_dir = os.path.join(output_dir, "data")
        matches_file = os.path.join(data_dir, "matches.json")
        base_data = {}
        if os.path.exists(matches_file):
            try:
                with open(matches_file, "r", encoding="utf-8") as f:
                    base_data = json.load(f)
            except Exception:
                base_data = {}

        base_data.setdefault("top_carousel", [])
        base_data.setdefault("drawer", {"international": [], "league": [], "domestic": [], "women": []})
        base_data.setdefault("live", [])
        base_data.setdefault("recent", [])
        base_data.setdefault("upcoming", [])
        base_data["tracked"] = []

        # Read urls.txt and mappings to find target IDs
        urls_file = os.path.join(os.path.dirname(os.path.abspath(output_dir)), "urls.txt")
        if not os.path.exists(urls_file):
            urls_file = os.path.join(os.getcwd(), "urls.txt")
        
        target_ids = set()
        if os.path.exists(urls_file):
            try:
                with open(urls_file, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            m = re.search(r'[-/](\d{5,8})(?:/|$|\?)', line)
                            if m:
                                target_ids.add(m.group(1))
            except Exception:
                pass

        mappings = cls.load_mappings(data_dir)
        for mid in mappings.keys():
            target_ids.add(str(mid))

        # Scan output/match_*_full.json
        json_files = glob.glob(os.path.join(output_dir, "match_*_full.json"))
        scraped_items = []

        for jf in json_files:
            try:
                with open(jf, "r", encoding="utf-8") as f:
                    d = json.load(f)
                meta = d.get("metadata", {})
                mid = str(meta.get("match_id", "") or "")
                if not mid:
                    continue

                title = meta.get("match_title", "")
                src_url = meta.get("source_url", "")
                is_live = meta.get("is_live", False)
                status_note = meta.get("status_note", "") or meta.get("status", "")

                series = meta.get("series") or ""
                if not series and "/series/" in src_url:
                    m_s = re.search(r'/series/([a-z0-9-]+?)-\d+/', src_url)
                    if m_s:
                        series = m_s.group(1).replace("-", " ").title()
                if not series:
                    series = "Cricket Tournament"

                stage = "Match"
                m_st = re.search(r'(Final|Eliminator|Qualifier|1st|2nd|3rd|\d+th)\s*(?:T20I|ODI|Test|Match)?', title + " " + src_url, re.I)
                if m_st:
                    stage = m_st.group(0).strip().title()

                cat = "league"
                low = (title + " " + series + " " + src_url).lower()
                if any(w in low for w in ["women", "wom", "wpl", "wbbl", "wcpl"]):
                    cat = "women"
                elif any(w in low for w in ["t20i", "odi", "test", "england", "sri lanka", "india", "australia", "pakistan"]):
                    cat = "international"
                elif any(w in low for w in ["county", "ranji", "domestic"]):
                    cat = "domestic"

                inns = d.get("innings", [])
                t1, s1 = "", ""
                t2, s2 = "", ""
                if len(inns) >= 1:
                    inn1 = inns[0]
                    t1 = inn1.get("inning_name", "").replace(" Inning", "").replace(" Innings", "").strip()
                    h1 = inn1.get("header_summary", "")
                    s1 = h1.replace(inn1.get("inning_name", ""), "").strip()
                if len(inns) >= 2:
                    inn2 = inns[1]
                    t2 = inn2.get("inning_name", "").replace(" Inning", "").replace(" Innings", "").strip()
                    h2 = inn2.get("header_summary", "")
                    s2 = h2.replace(inn2.get("inning_name", ""), "").strip()

                if not t1:
                    if " v " in title:
                        t1, t2 = [x.strip() for x in title.split(" v ", 1)]
                    elif " vs " in title:
                        t1, t2 = [x.strip() for x in title.split(" vs ", 1)]

                balls_rem = ""
                m_b = re.search(r'\((\d+)\s*(?:b|balls)?\s*(?:rem|remaining)?\)', status_note, re.I)
                if m_b:
                    balls_rem = f"{m_b.group(1)} balls remaining"
                    status_clean = status_note[:m_b.start()].strip() + " " + status_note[m_b.end():].strip()
                else:
                    status_clean = status_note

                is_in_targets = mid in target_ids
                mtime = os.path.getmtime(jf)

                item = {
                    "match_id": mid,
                    "title": title,
                    "team_1": t1,
                    "team_1_score": s1,
                    "team_2": t2,
                    "team_2_score": s2,
                    "series": series,
                    "stage": stage,
                    "venue": meta.get("venue", ""),
                    "status": status_clean,
                    "balls_remaining": balls_rem,
                    "is_live": is_live,
                    "is_completed": not is_live,
                    "is_tracked": is_in_targets,
                    "category": cat,
                    "url": f"/match/{mid}",
                    "mtime": mtime
                }
                scraped_items.append(item)
            except Exception:
                pass

        scraped_items.sort(key=lambda x: (x["is_tracked"], x["mtime"]), reverse=True)

        for it in scraped_items:
            if it["is_tracked"] or len(base_data["tracked"]) < 5:
                base_data["tracked"].append(it)

        # Merge carousel
        carousel_prepends = []
        for it in scraped_items:
            short_t1 = "".join([w[0] for w in it["team_1"].split()[:2]]).upper() or it["team_1"][:4]
            short_t2 = "".join([w[0] for w in it["team_2"].split()[:2]]).upper() or it["team_2"][:4]
            pill = "LIVE" if it["is_live"] else "Result"
            txt = f"{short_t1} vs {short_t2} - {it['status'][:20]}"
            carousel_prepends.append({
                "match_id": it["match_id"],
                "text": txt,
                "status_pill": pill,
                "href": it["url"]
            })
        base_data["top_carousel"] = carousel_prepends + [m for m in base_data["top_carousel"] if m.get("match_id") not in {x["match_id"] for x in carousel_prepends}]

        # Merge live & recent
        for it in reversed(scraped_items):
            if it["is_live"]:
                base_data["live"] = [m for m in base_data["live"] if m.get("match_id") != it["match_id"]]
                base_data["live"].insert(0, it)
            else:
                base_data["recent"] = [m for m in base_data["recent"] if m.get("match_id") != it["match_id"]]
                base_data["recent"].insert(0, it)

        # Ingest full CREX Event Catalog (72+ matches across International, League, Domestic, Women)
        catalog_file = os.path.join(data_dir, "crex_catalog.json")
        if os.path.exists(catalog_file):
            try:
                with open(catalog_file, "r", encoding="utf-8") as f:
                    cat_json = json.load(f)
                existing_mids = {str(m.get("match_id")) for m in scraped_items}
                for ev in cat_json.get("events", []):
                    ev_mid = str(ev.get("match_id", ""))
                    if not ev_mid or ev_mid in existing_mids:
                        continue
                    existing_mids.add(ev_mid)

                    ev_unique = ev.get("unique_match_id", f"M-{ev_mid}")
                    cat = ev.get("category", "international")
                    is_live = ev.get("is_live", False)
                    is_done = ev.get("is_completed", False) or "won" in ev.get("status", "").lower()
                    is_in_targets = ev_mid in target_ids or ev_unique in target_ids

                    c_item = {
                        "match_id": ev_mid,
                        "unique_match_id": ev_unique,
                        "title": ev.get("title", ""),
                        "team_1": ev.get("team_1", ""),
                        "team_1_score": "",
                        "team_2": ev.get("team_2", ""),
                        "team_2_score": "",
                        "series": ev.get("series", "Cricket Tournament"),
                        "stage": ev.get("stage", "Match"),
                        "venue": "",
                        "status": ev.get("status", "Scheduled"),
                        "balls_remaining": "",
                        "is_live": is_live,
                        "is_completed": is_done,
                        "is_tracked": is_in_targets,
                        "category": cat,
                        "url": f"/match/{ev_mid}",
                        "mtime": 0
                    }

                    if is_in_targets:
                        base_data["tracked"].append(c_item)

                    if is_live:
                        base_data["live"].append(c_item)
                    elif is_done:
                        base_data["recent"].append(c_item)
                    else:
                        base_data["upcoming"].append(c_item)

                    if cat in base_data["drawer"]:
                        base_data["drawer"][cat].append(c_item)
            except Exception:
                pass

        return cls.update_match_lifecycle(base_data)

    @classmethod
    def resolve_match_id(cls, mid: str, output_dir: str = "output") -> str:
        """
        Resolves a match ID or Unique Match ID (e.g. M-CPL-11UV, 11UV, 1540220)
        to the existing dashboard HTML file basename.
        """
        clean_id = str(mid).strip().replace(".html", "")
        if os.path.exists(os.path.join(output_dir, f"dashboard_{clean_id}.html")):
            return clean_id

        data_dir = os.path.join(output_dir, "data")
        mappings = cls.load_mappings(data_dir)
        if clean_id in mappings:
            mapped_mid = mappings[clean_id].get("match_id", clean_id)
            if os.path.exists(os.path.join(output_dir, f"dashboard_{mapped_mid}.html")):
                return mapped_mid

        # Cross-platform known alias groupings (e.g. CPL Qualifier 1: 11UW <-> 154689 <-> 1534215)
        known_alias_groups = [
            {"11UW", "154689", "1534215", "M-LEA-11UW"},
            {"11UV", "12LV", "1534214", "M-LEA-11UV"},
            {"1540220", "M-WOM-1540220"}
        ]
        for group in known_alias_groups:
            if clean_id in group or any(clean_id.endswith(k) for k in group):
                for candidate in group:
                    if os.path.exists(os.path.join(output_dir, f"dashboard_{candidate}.html")):
                        return candidate

        # Check M-<CAT>-<KEY>
        parts = clean_id.split("-")
        if len(parts) >= 3 and parts[0] == "M":
            raw_key = parts[-1]
            if os.path.exists(os.path.join(output_dir, f"dashboard_{raw_key}.html")):
                return raw_key
            if raw_key in mappings:
                mapped_mid = mappings[raw_key].get("match_id", raw_key)
                if os.path.exists(os.path.join(output_dir, f"dashboard_{mapped_mid}.html")):
                    return mapped_mid

        return clean_id

    # =========================================================================
    # 7. Admin Match Mapping & URL Router
    # =========================================================================
    @classmethod
    def load_mappings(cls, data_dir: str = "output/data") -> Dict[str, Any]:
        """Loads match-to-URL mappings from match_mappings.json."""
        os.makedirs(data_dir, exist_ok=True)
        mappings_file = os.path.join(data_dir, "match_mappings.json")
        if os.path.exists(mappings_file):
            try:
                with open(mappings_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    @classmethod
    def save_mapping(
        cls,
        match_id: str,
        url: str,
        title: str = "",
        category: str = "international",
        data_dir: str = "output/data",
        urls_file: str = "urls.txt"
    ) -> Dict[str, Any]:
        """
        Binds a match entity to a Cricinfo, Cricbuzz, or CREX URL:
        1. Identifies platform.
        2. Saves mapping to match_mappings.json.
        3. Updates urls.txt so scraper picks it up immediately.
        """
        clean_url = (url or "").strip()
        if not clean_url:
            raise ValueError("URL cannot be empty")

        platform = "Unknown"
        if "cricinfo" in clean_url or "espn" in clean_url:
            platform = "ESPNcricinfo"
        elif "cricbuzz" in clean_url:
            platform = "Cricbuzz"
        elif "crex" in clean_url:
            platform = "CREX"

        mappings = cls.load_mappings(data_dir)
        mappings[str(match_id)] = {
            "match_id": str(match_id),
            "url": clean_url,
            "platform": platform,
            "title": title or f"Match {match_id}",
            "category": category,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        }

        mappings_file = os.path.join(data_dir, "match_mappings.json")
        with open(mappings_file, "w", encoding="utf-8") as f:
            json.dump(mappings, f, indent=2)

        cls.sync_urls_file(urls_file, data_dir)
        return mappings[str(match_id)]

    @classmethod
    def delete_mapping(cls, match_id: str, data_dir: str = "output/data", urls_file: str = "urls.txt") -> bool:
        mappings = cls.load_mappings(data_dir)
        mid_str = str(match_id)
        if mid_str in mappings:
            del mappings[mid_str]
            mappings_file = os.path.join(data_dir, "match_mappings.json")
            with open(mappings_file, "w", encoding="utf-8") as f:
                json.dump(mappings, f, indent=2)
            cls.sync_urls_file(urls_file, data_dir)
            return True
        return False

    @classmethod
    def sync_urls_file(cls, urls_file: str = "urls.txt", data_dir: str = "output/data"):
        """Synchronizes urls.txt with active mapped URLs while preserving existing comments/manual entries."""
        mappings = cls.load_mappings(data_dir)
        mapped_urls = [m["url"] for m in mappings.values() if m.get("url")]

        existing_lines = []
        if os.path.exists(urls_file):
            with open(urls_file, "r", encoding="utf-8") as f:
                existing_lines = f.readlines()

        cleaned_urls = set()
        for line in existing_lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                cleaned_urls.add(stripped)

        for u in mapped_urls:
            cleaned_urls.add(u)

        header = [
            "# ===========================================================================\n",
            "# Cricket Match URLs to Scrape (Managed by Hermes Brain & Admin Panel)\n",
            "# ===========================================================================\n"
        ]
        with open(urls_file, "w", encoding="utf-8") as f:
            f.writelines(header)
            for u in sorted(cleaned_urls):
                f.write(f"{u}\n\n")

    # =========================================================================
    # 8. Autonomous Background Scheduler & Feeds Ingestion
    # =========================================================================
    @classmethod
    def start_autonomous_scheduler(cls, output_dir: str = "output"):
        """
        Starts the Hermes Brain autonomous background supervisor daemon:
        - Refreshes live matches directory every 10 minutes (600s).
        - Refreshes cricket schedule/fixtures every 1 hour (3600s).
        - Refreshes live cricket news with real images every 1 hour (3600s).
        - Refreshes tournament standings & points table every 1 hour (3600s).
        - Refreshes teams directory every 24 hours (86400s).
        """
        with cls._scheduler_lock:
            if cls._scheduler_running:
                return
            cls._scheduler_running = True
            cls._scheduler_thread = threading.Thread(target=cls._scheduler_loop, args=(output_dir,), daemon=True)
            cls._scheduler_thread.start()
            print("[HermesBrain] Autonomous background data scheduler initialized (10m live, 1h news/fixtures, 24h teams)", flush=True)

    @classmethod
    def _scheduler_loop(cls, output_dir: str):
        from scrapers.feed_scraper import CricketFeedEngine
        data_dir = os.path.join(output_dir, "data")
        os.makedirs(data_dir, exist_ok=True)

        while cls._scheduler_running:
            now = time.time()
            try:
                # 1. Matches Directory: refresh every 10 minutes (600s)
                matches_file = os.path.join(data_dir, "matches.json")
                m_age = now - (os.path.getmtime(matches_file) if os.path.exists(matches_file) else 0)
                if m_age >= 600:
                    try:
                        print("[HermesBrain Scheduler] 10m cycle: Refreshing live match directory...", flush=True)
                        m_data = CricketFeedEngine.fetch_matches_directory()
                        m_data = cls.update_match_lifecycle(m_data)
                        with open(matches_file, "w", encoding="utf-8") as f:
                            json.dump(m_data, f, indent=2)
                    except Exception as e:
                        print(f"[HermesBrain Scheduler] Error refreshing matches: {e}", flush=True)

                # 2. Schedule / Fixtures: refresh every 1 hour (3600s)
                sched_file = os.path.join(data_dir, "schedule.json")
                s_age = now - (os.path.getmtime(sched_file) if os.path.exists(sched_file) else 0)
                if s_age >= 3600:
                    try:
                        print("[HermesBrain Scheduler] 1h cycle: Refreshing cricket fixtures & schedule...", flush=True)
                        s_data = CricketFeedEngine.fetch_schedule()
                        with open(sched_file, "w", encoding="utf-8") as f:
                            json.dump(s_data, f, indent=2)
                    except Exception as e:
                        print(f"[HermesBrain Scheduler] Error refreshing schedule: {e}", flush=True)

                # 3. News with real images: refresh every 1 hour (3600s)
                news_file = os.path.join(data_dir, "news.json")
                n_age = now - (os.path.getmtime(news_file) if os.path.exists(news_file) else 0)
                if n_age >= 3600:
                    try:
                        print("[HermesBrain Scheduler] 1h cycle: Refreshing cricket news and images...", flush=True)
                        n_data = CricketFeedEngine.fetch_news()
                        with open(news_file, "w", encoding="utf-8") as f:
                            json.dump(n_data, f, indent=2)
                    except Exception as e:
                        print(f"[HermesBrain Scheduler] Error refreshing news: {e}", flush=True)

                # 4. Points Table: refresh every 1 hour (3600s)
                pt_file = os.path.join(data_dir, "points_table.json")
                p_age = now - (os.path.getmtime(pt_file) if os.path.exists(pt_file) else 0)
                if p_age >= 3600:
                    try:
                        pt_data = CricketFeedEngine.fetch_points_table("1534175")
                        with open(pt_file, "w", encoding="utf-8") as f:
                            json.dump(pt_data, f, indent=2)
                    except Exception as e:
                        pass

                # 5. Teams: refresh every 24 hours (86400s)
                teams_file = os.path.join(data_dir, "teams.json")
                t_age = now - (os.path.getmtime(teams_file) if os.path.exists(teams_file) else 0)
                if t_age >= 86400:
                    try:
                        print("[HermesBrain Scheduler] 24h cycle: Refreshing teams directory...", flush=True)
                        t_data = CricketFeedEngine.fetch_teams()
                        with open(teams_file, "w", encoding="utf-8") as f:
                            json.dump(t_data, f, indent=2)
                    except Exception as e:
                        print(f"[HermesBrain Scheduler] Error refreshing teams: {e}", flush=True)

            except Exception as loop_e:
                print(f"[HermesBrain Scheduler] Exception in loop: {loop_e}", flush=True)

            time.sleep(30)

    @classmethod
    def sync_all_feeds(cls, output_dir: str = "output") -> Dict[str, Any]:
        """Manually or programmatically triggers a full sync of all cricket feeds."""
        from scrapers.feed_scraper import CricketFeedEngine
        return CricketFeedEngine.sync_all(output_dir)

    @classmethod
    def trigger_match_ingestion(cls, url: str, output_dir: str = "output", port: int = 8080):
        """
        Asynchronously triggers live ingestion for a specific match URL in a worker thread.
        Automatically runs Hermes Brain analysis, scorecard audit, and generates dashboard HTML.
        """
        def _worker():
            import asyncio
            from core.browser_manager import BrowserManager
            from scrapers import get_scraper_for_url
            from core.exporter import DataExporter
            from core.dashboard_generator import DashboardGenerator

            async def _run():
                try:
                    scraper = get_scraper_for_url(url)
                    async with BrowserManager(headless=True) as bm:
                        match_data = await scraper.fetch_and_parse(bm)
                        if match_data:
                            match_data = cls.analyze(match_data)
                            DataExporter.export(match_data, output_dir=output_dir)
                            DashboardGenerator.generate(match_data, output_dir=output_dir, port=port)
                            print(f"[HermesBrain] Successfully ingested and generated dashboard for: {url}", flush=True)
                except Exception as e:
                    print(f"[HermesBrain] Ingestion error for {url}: {e}", flush=True)

            try:
                asyncio.run(_run())
            except Exception as e:
                print(f"[HermesBrain] Worker error: {e}", flush=True)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
