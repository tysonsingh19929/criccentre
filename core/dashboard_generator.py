import os
import glob
import json
import re
import html as html_escape
from typing import Dict, Any, List, Tuple
from core.models import MatchData, BallByBallEvent, Inning, Partnership
from core.page_templates import PageTemplates

def is_ball_wicket(b: BallByBallEvent) -> bool:
    """Accurately checks if a delivery resulted in a wicket without false positives on wides or other text."""
    if getattr(b, 'is_wicket', False):
        return True
    outc = (b.outcome or '').strip().lower()
    return outc in ('w', 'out') or 'wicket' in outc or 'run out' in outc or 'bowled' in outc or 'caught' in outc or 'lbw' in outc or 'stumped' in outc

def format_ball_token(b: BallByBallEvent) -> Tuple[str, str, str]:
    """
    Returns (display_token, css_class, badge_category)
    CREX numerical style:
    - 6: green circle, bold white '6'
    - 4: blue circle, bold white '4'
    - W: red circle, bold white 'W'
    - 0: gray circle, dark '0'
    - 1, 2, 3: emerald/light circle, dark '1', '2', '3'
    - Wd: amber circle, bold 'Wd' or '1w' / '2w'
    - Nb: amber circle, bold 'Nb' or '1nb'
    - Lb: amber/slate circle, bold '1lb' or 'Lb'
    - B: amber/slate circle, bold '1b' or 'B'
    """
    outc = (b.outcome or '').strip().lower()
    is_wkt_flag = is_ball_wicket(b)
    is_six_flag = b.is_six or outc == '6' or 'six' in outc
    is_four_flag = b.is_four or outc == '4' or 'four' in outc
    is_extra_flag = b.is_extra or any(x in outc for x in ('wide', 'wd', 'nb', 'no ball', 'bye', 'leg bye', 'lb', 'b'))

    if is_wkt_flag:
        return 'W', 'bg-red-600 text-white font-black shadow-xs ring-1 ring-red-400', 'wkt'
    if is_six_flag:
        return '6', 'bg-[#009270] text-white font-black shadow-xs ring-1 ring-emerald-400', 'six'
    if is_four_flag:
        return '4', 'bg-blue-600 text-white font-black shadow-xs ring-1 ring-blue-400', 'four'
    if 'wide' in outc or 'wd' in outc:
        tok = f'{b.runs}w' if b.runs > 1 else 'Wd'
        return tok, 'bg-amber-100 text-amber-900 border border-amber-300 font-bold', 'extra'
    if 'leg bye' in outc or 'lb' in outc:
        tok = f'{b.runs}lb' if b.runs > 0 else 'Lb'
        return tok, 'bg-slate-100 text-slate-700 border border-slate-300 font-medium', 'extra'
    if 'bye' in outc and 'leg' not in outc:
        tok = f'{b.runs}b' if b.runs > 0 else 'B'
        return tok, 'bg-slate-100 text-slate-700 border border-slate-300 font-medium', 'extra'
    if 'no ball' in outc or 'nb' in outc:
        tok = f'{b.runs}nb' if b.runs > 1 else 'Nb'
        return tok, 'bg-amber-100 text-amber-900 border border-amber-300 font-bold', 'extra'
    if outc.isdigit():
        val = int(outc)
        if val == 4: return '4', 'bg-blue-600 text-white font-black shadow-xs', 'four'
        if val == 6: return '6', 'bg-[#009270] text-white font-black shadow-xs', 'six'
        if val == 0: return '0', 'bg-slate-200 text-slate-600 font-semibold', 'dot'
        return str(val), 'bg-emerald-100 text-emerald-800 font-bold border border-emerald-300', 'run'
    if outc in ('no run', '0', 'dot') or (b.runs == 0 and not is_extra_flag):
        return '0', 'bg-slate-200 text-slate-600 font-semibold', 'dot'
    if b.runs > 0:
        if b.runs == 4: return '4', 'bg-blue-600 text-white font-black shadow-xs', 'four'
        if b.runs == 6: return '6', 'bg-[#009270] text-white font-black shadow-xs', 'six'
        return str(b.runs), 'bg-emerald-100 text-emerald-800 font-bold border border-emerald-300', 'run'
    return '0', 'bg-slate-200 text-slate-600 font-semibold', 'dot'

def format_raw_outcome(outc: str) -> Tuple[str, str]:
    o = (outc or '').strip().lower()
    if o in ('w', 'out') or 'wicket' in o:
        return 'W', 'bg-red-600 text-white font-black'
    if o in ('6', 'six') or 'six' in o:
        return '6', 'bg-[#009270] text-white font-black'
    if o in ('4', 'four') or 'four' in o:
        return '4', 'bg-blue-600 text-white font-black'
    if 'wide' in o or 'wd' in o:
        return 'Wd', 'bg-amber-100 text-amber-900 border border-amber-300 font-bold'
    if 'leg bye' in o or 'lb' in o:
        return '1lb', 'bg-slate-100 text-slate-700 border border-slate-300 font-medium'
    if 'bye' in o and 'leg' not in o:
        return '1b', 'bg-slate-100 text-slate-700 border border-slate-300 font-medium'
    if 'no ball' in o or 'nb' in o:
        return 'Nb', 'bg-amber-100 text-amber-900 border border-amber-300 font-bold'
    if o in ('no run', '0', 'dot'):
        return '0', 'bg-slate-200 text-slate-600 font-semibold'
    if o.isdigit():
        return o, 'bg-emerald-100 text-emerald-800 font-bold border border-emerald-300'
    if o == 'run':
        return '1', 'bg-emerald-100 text-emerald-800 font-bold border border-emerald-300'
    return '0', 'bg-slate-200 text-slate-600 font-semibold'


class DashboardGenerator:
    """
    Independent Professional Cricket Match Center.
    - 80% Cricbuzz Layout & 20% CREX smooth styling.
    - Dedicated 'Overs' tab (Cricbuzz over-by-over with team switcher pills).
    - Dedicated 'Points Table' tab (Tournament standings).
    - Exact Cricbuzz Over End card structure (Over #, score, ball tokens, on-crease batters, bowler figures).
    - Zero impact over clutter in commentary or live hub.
    - Clean status formatting without brackets: '35 balls remaining'.
    - Unified with global navigation, top carousel, and mega-drawer.
    """

    @classmethod
    def generate(cls, match_data: MatchData, output_dir: str = "output", port: int = 8080) -> str:
        os.makedirs(output_dir, exist_ok=True)
        meta = match_data.metadata
        safe_mid = str(meta.match_id or "live").strip()

        html_path = os.path.join(output_dir, "dashboard.html")
        match_html_path = os.path.join(output_dir, f"dashboard_{safe_mid}.html")

        # Load global datasets if available for shared header
        data_dir = os.path.join(output_dir, "data")
        matches_feed = {}
        series_feed = {}
        points_table_feed = {}
        try:
            from core.hermes_brain import HermesBrain
            matches_feed = HermesBrain.get_platform_matches_data(output_dir)
        except Exception:
            try:
                m_path = os.path.join(data_dir, "matches.json")
                if os.path.exists(m_path):
                    with open(m_path, "r", encoding="utf-8") as f:
                        matches_feed = json.load(f)
            except Exception:
                pass
            s_path = os.path.join(data_dir, "series.json")
            if os.path.exists(s_path):
                with open(s_path, "r", encoding="utf-8") as f:
                    series_feed = json.load(f)
            pt_path = os.path.join(data_dir, "points_table.json")
            if os.path.exists(pt_path):
                with open(pt_path, "r", encoding="utf-8") as f:
                    points_table_feed = json.load(f)
        except Exception:
            pass

        # Inning mapping for strict separation
        inn_order_map: Dict[str, int] = {}
        for idx, inn in enumerate(match_data.innings, 1):
            inn_order_map[inn.inning_name] = idx
            inn_order_map[inn.inning_name.lower()] = idx
            inn_order_map[inn.inning_name.lower().replace("innings", "inning").strip()] = idx
            inn_order_map[f"Inning {idx}"] = idx
            inn_order_map[f"Innings {idx}"] = idx
            inn_order_map[f"inning {idx}"] = idx
            inn_order_map[f"innings {idx}"] = idx
            inn_order_map[str(idx)] = idx

        # -------------------------------------------------------------
        # 1. Compute Active Inning, Top Batters, Top Bowler, & Partnership
        # -------------------------------------------------------------
        # Active in-progress inning: pick latest inning with batting or deliveries
        active_inn = None
        active_inn_idx = 1
        for idx, inn in enumerate(reversed(match_data.innings)):
            actual_idx = len(match_data.innings) - idx
            if inn.batting or (getattr(inn, 'ball_by_ball', None) and len(inn.ball_by_ball) > 0):
                active_inn = inn
                active_inn_idx = actual_idx
                break
        if not active_inn and match_data.innings:
            active_inn = match_data.innings[0]
            active_inn_idx = 1

        latest_inn = active_inn

        sorted_batters = []
        if active_inn and active_inn.batting:
            sorted_batters = sorted(active_inn.batting, key=lambda b: (1 if "not out" in b.dismissal.lower() else 0, b.runs), reverse=True)
        top_batters = sorted_batters[:2]

        top_bowler = None
        if active_inn and active_inn.bowling:
            top_bowler = sorted(active_inn.bowling, key=lambda bo: (bo.wickets, -bo.economy), reverse=True)[0]

        active_partnership = match_data.partnerships[-1] if match_data.partnerships else None
        if match_data.partnerships:
            highest_p = max(match_data.partnerships, key=lambda p: p.milestone_runs)
            if highest_p.milestone_runs >= (active_partnership.milestone_runs if active_partnership else 0):
                active_partnership = highest_p

        last_wkt_str = "None"
        if active_inn and active_inn.fall_of_wickets:
            last_w = active_inn.fall_of_wickets[-1]
            last_wkt_str = f"{last_w.batter_out} ({last_w.over} ov)"

        # -------------------------------------------------------------
        # 2. Compute Recent Overs Strip & Hero Ball Outcome (Image 5)
        # -------------------------------------------------------------
        latest_balls = []
        if active_inn:
            if getattr(active_inn, 'ball_by_ball', None) and len(active_inn.ball_by_ball) > 0:
                latest_balls = active_inn.ball_by_ball
            else:
                latest_balls = [
                    b for b in match_data.all_balls
                    if inn_order_map.get(b.inning_name, 0) == active_inn_idx or len(match_data.innings) == 1
                ]

        hero_ball_tok = "-"
        hero_ball_badge_cls = "bg-slate-200 text-slate-700"
        hero_over_str = ""
        current_over_tokens_html = ""

        if latest_balls:
            latest_deliv = latest_balls[0]
            hero_ball_tok, hero_ball_badge_cls, _ = format_ball_token(latest_deliv)
            hero_over_str = f"{latest_deliv.over_str} Ov"
            target_ov_num = latest_deliv.over_str.split('.')[0] if '.' in latest_deliv.over_str else str(latest_deliv.over_num)
            this_over_balls = [b for b in latest_balls if (b.over_str.split('.')[0] if '.' in b.over_str else str(b.over_num)) == target_ov_num]
            for ob in reversed(this_over_balls):
                tok_o, badge_o, _ = format_ball_token(ob)
                current_over_tokens_html += f'<span class="w-6 h-6 rounded-full inline-flex items-center justify-center text-2xs font-black {badge_o} shadow-2xs">{tok_o}</span> '
        elif active_inn and active_inn.header_summary:
            m_ov = re.search(r'\((\d+\.?\d*)\s*ov', active_inn.header_summary)
            if m_ov:
                hero_over_str = f"{m_ov.group(1)} Ov"

        recent_overs_html = ""
        if latest_balls:
            overs_dict: Dict[int, List[BallByBallEvent]] = {}
            for b in latest_balls:
                ov_int = int(b.over_str.split('.')[0]) if '.' in b.over_str else b.over_num
                overs_dict.setdefault(ov_int, []).append(b)

            sorted_overs = sorted(overs_dict.keys())
            for ov_num in sorted_overs[-6:]:
                balls = overs_dict[ov_num]
                display_over_num = ov_num + 1
                o_runs = sum(b.runs for b in balls)
                o_wkts = sum(1 for b in balls if is_ball_wicket(b))
                bowler_name = balls[-1].bowler if balls else ""

                ball_tokens = ""
                for b in reversed(balls) if len(balls) > 1 and balls[0].ball_num > balls[-1].ball_num else balls:
                    tok, t_class, _ = format_ball_token(b)
                    ball_tokens += f'<span class="w-6 h-6 sm:w-7 sm:h-7 rounded-full inline-flex items-center justify-center text-2xs sm:text-xs font-black {t_class}">{tok}</span> '

                recent_overs_html += f"""
                <div class="px-3 py-2 rounded-xl border border-slate-200 bg-white shrink-0 flex items-center gap-2 sm:gap-3 shadow-2xs">
                    <div class="text-xs font-bold text-slate-800 whitespace-nowrap">
                        Over {display_over_num} <span class="text-2xs font-normal text-slate-500">({html_escape.escape(bowler_name)})</span>
                    </div>
                    <div class="flex items-center gap-1">
                        {ball_tokens}
                    </div>
                    <div class="text-xs font-black text-slate-800 whitespace-nowrap">
                        = {o_runs} Runs {f'<span class="text-red-600 font-bold">({o_wkts}W)</span>' if o_wkts else ''}
                    </div>
                </div>
                """

        # Build CREX Big Ball Hero & Equation Banner (Image 5)
        crr_display = "0.00"
        m_crr = re.search(r'CRR:\s*([\d\.]+)', meta.status_note or "")
        if m_crr:
            crr_display = m_crr.group(1)
        elif active_inn and active_inn.total and active_inn.total.run_rate:
            crr_display = active_inn.total.run_rate

        toss_str = meta.toss or ""

        crex_hero_ball_html = f"""
        <div class="bg-gradient-to-r from-slate-900 via-[#0a2318] to-slate-900 rounded-2xl p-4 sm:p-5 text-white border border-emerald-900/60 shadow-md mb-3.5 flex flex-col sm:flex-row items-center justify-between gap-4">
            <div class="flex items-center gap-4 w-full sm:w-auto">
                <div class="w-16 h-16 sm:w-20 sm:h-20 rounded-2xl flex flex-col items-center justify-center shadow-lg border-2 border-white/20 {hero_ball_badge_cls} shrink-0">
                    <span class="text-2xl sm:text-3xl font-black">{hero_ball_tok}</span>
                    <span class="text-4xs uppercase tracking-widest font-black opacity-80 -mt-1">Last Ball</span>
                </div>
                <div class="min-w-0">
                    <div class="flex items-center gap-2">
                        <span class="text-xs sm:text-sm font-black text-emerald-400 font-mono tracking-tight">{hero_over_str}</span>
                        {f'<span class="px-2 py-0.5 rounded-full text-3xs font-extrabold bg-red-600 text-white animate-pulse">LIVE</span>' if meta.is_live else ''}
                    </div>
                    <div class="flex items-center gap-1.5 mt-1.5 flex-wrap">
                        {current_over_tokens_html if current_over_tokens_html else '<span class="text-xs text-slate-400">Current Over</span>'}
                    </div>
                    {f'<div class="text-3xs text-emerald-200/80 font-medium mt-1 truncate">Toss: {html_escape.escape(toss_str)}</div>' if toss_str else ''}
                </div>
            </div>
            <div class="flex items-center gap-3 sm:gap-6 self-end sm:self-center border-t sm:border-t-0 sm:border-l border-white/10 pt-3 sm:pt-0 sm:pl-6 w-full sm:w-auto justify-between sm:justify-end">
                <div class="text-center sm:text-right">
                    <div class="text-3xs uppercase font-bold text-slate-400 tracking-wider">Current RR</div>
                    <div class="text-base sm:text-xl font-black text-emerald-400 mt-0.5">{crr_display}</div>
                </div>
                <div class="text-center sm:text-right">
                    <div class="text-3xs uppercase font-bold text-slate-400 tracking-wider">Match Status</div>
                    <div class="text-xs sm:text-sm font-bold text-amber-300 mt-0.5 max-w-[220px] truncate">{html_escape.escape(meta.status_note or 'Live')}</div>
                </div>
            </div>
        </div>
        """

        # -------------------------------------------------------------
        # 3. Live Hub Batters & Bowler Card
        # -------------------------------------------------------------
        batters_hub_html = ""
        for b in top_batters:
            is_no = "not out" in b.dismissal.lower()
            star = "*" if is_no else ""
            batters_hub_html += f"""
            <div class="bg-white p-3 sm:p-3.5 rounded-xl border border-slate-200 shadow-2xs flex items-center justify-between">
                <div class="flex items-center gap-2.5 min-w-0">
                    <div class="w-9 h-9 rounded-full bg-emerald-100 text-emerald-800 font-black flex items-center justify-center text-sm border border-emerald-300 shrink-0">
                        {b.batter[:1]}
                    </div>
                    <div class="min-w-0">
                        <div class="text-xs sm:text-sm font-black text-slate-900 flex items-center gap-1 truncate">
                            <span class="truncate">{html_escape.escape(b.batter)}{star}</span>
                            {f'<span class="text-3xs text-emerald-700 font-extrabold bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200 shrink-0">ON CREASE</span>' if is_no else ''}
                        </div>
                        <div class="flex items-center gap-2 mt-1 flex-wrap">
                            <span class="inline-flex items-center gap-1 bg-blue-50 border border-blue-200 px-1.5 py-0.5 rounded text-2xs font-bold text-blue-700">
                                <span class="w-3.5 h-3.5 rounded-full bg-blue-600 text-white flex items-center justify-center text-3xs font-black">4</span>
                                {b.fours}
                            </span>
                            <span class="inline-flex items-center gap-1 bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 rounded text-2xs font-bold text-emerald-700">
                                <span class="w-3.5 h-3.5 rounded-full bg-[#009270] text-white flex items-center justify-center text-3xs font-black">6</span>
                                {b.sixes}
                            </span>
                            <span class="text-2xs text-slate-500 font-medium">SR: <strong class="text-slate-800">{b.strike_rate:.1f}</strong></span>
                        </div>
                    </div>
                </div>
                <div class="text-right shrink-0 pl-2">
                    <div class="text-lg sm:text-xl font-black text-slate-900">{b.runs}</div>
                    <div class="text-2xs sm:text-xs text-slate-500 font-medium">{b.balls} balls</div>
                </div>
            </div>
            """

        bowler_hub_html = ""
        if top_bowler:
            bowler_hub_html = f"""
            <div class="bg-white p-3 sm:p-3.5 rounded-xl border border-slate-200 shadow-2xs flex items-center justify-between">
                <div class="flex items-center gap-2.5 min-w-0">
                    <div class="w-9 h-9 rounded-full bg-amber-100 text-amber-800 font-black flex items-center justify-center text-sm border border-amber-300 shrink-0">
                        {top_bowler.bowler[:1]}
                    </div>
                    <div class="min-w-0">
                        <div class="text-xs sm:text-sm font-black text-slate-900 truncate">{html_escape.escape(top_bowler.bowler)}</div>
                        <div class="text-2xs sm:text-xs text-slate-500 mt-1">Econ: <span class="font-bold text-slate-700">{top_bowler.economy:.2f}</span> • Maidens: <span class="font-bold text-slate-700">{top_bowler.maidens}</span></div>
                    </div>
                </div>
                <div class="text-right shrink-0 pl-2">
                    <div class="text-lg sm:text-xl font-black text-red-600">{top_bowler.wickets}-{top_bowler.runs}</div>
                    <div class="text-2xs sm:text-xs font-semibold text-slate-500">{top_bowler.overs} ov • <span class="text-emerald-700 font-bold">{top_bowler.dot_balls} Dots</span></div>
                </div>
            </div>
            """

        # Partnership & Numerical Boundaries Strip
        p_runs_str = "0"
        p_balls_str = "0"
        p_names_str = "None"
        p_fours = 0
        p_sixes = 0
        if active_partnership:
            p_runs_str = str(active_partnership.milestone_runs)
            p_balls_str = str(active_partnership.balls)
            p_names_str = f"{active_partnership.batter_1.name} & {active_partnership.batter_2.name}"
            p_fours = active_partnership.fours
            p_sixes = active_partnership.sixes
            if not p_fours and not p_sixes and active_partnership.boundary_str:
                m_f = re.search(r'(\d+)x4', active_partnership.boundary_str)
                m_s = re.search(r'(\d+)x6', active_partnership.boundary_str)
                if m_f: p_fours = int(m_f.group(1))
                if m_s: p_sixes = int(m_s.group(1))

        # -------------------------------------------------------------
        # 4. Generate Inning-by-Inning Feed (Cricbuzz Over-End Structure)
        # -------------------------------------------------------------
        all_deliveries_total = sum(len(getattr(i, 'ball_by_ball', [])) for i in match_data.innings)
        total_deliveries_count = max(len(match_data.all_balls), all_deliveries_total)
        live_feed_items = ""
        all_innings_desc = list(reversed(list(enumerate(match_data.innings, 1))))

        # Data structure for the new "Overs" Tab
        overs_tab_data: Dict[int, List[Dict[str, Any]]] = {}

        for inn_idx, inn in all_innings_desc:
            inn_balls = getattr(inn, 'ball_by_ball', [])
            if not inn_balls:
                inn_balls = [
                    b for b in match_data.all_balls
                    if inn_order_map.get(b.inning_name, 0) == inn_idx or (len(match_data.innings) == 1)
                ]
            if not inn_balls:
                continue

            # Inning Header Banner
            live_feed_items += f"""
            <div class="inning-header my-5 p-3 rounded-xl bg-gradient-to-r from-emerald-900 to-slate-900 text-white flex items-center justify-between shadow-xs">
                <div>
                    <span class="text-3xs uppercase font-extrabold tracking-widest text-emerald-400">INNINGS {inn_idx}</span>
                    <h3 class="text-sm sm:text-base font-black tracking-tight">{html_escape.escape(inn.inning_name)}</h3>
                </div>
                <div class="text-right">
                    <div class="text-sm sm:text-base font-black text-amber-300">{html_escape.escape(inn.header_summary.split(' Inning ')[-1] if ' Inning ' in inn.header_summary else inn.header_summary)}</div>
                </div>
            </div>
            """

            # Group this inning's balls by over
            inn_overs_dict: Dict[int, List[BallByBallEvent]] = {}
            for b in inn_balls:
                ov_int = int(b.over_str.split('.')[0]) if '.' in b.over_str else b.over_num
                inn_overs_dict.setdefault(ov_int, []).append(b)

            # Pre-compute cumulative score for each over
            cum_runs = 0
            cum_wkts = 0
            over_cum_map: Dict[int, str] = {}
            for ov_int in sorted(inn_overs_dict.keys()):
                o_bls = inn_overs_dict[ov_int]
                cum_runs += sum(x.runs for x in o_bls)
                cum_wkts += sum(1 for x in o_bls if is_ball_wicket(x))
                over_cum_map[ov_int] = f"{cum_runs}-{cum_wkts}"

            # Prepare list for the dedicated "Overs" tab
            overs_tab_data[inn_idx] = []

            # Sort overs descending (latest over first)
            for ov_int in sorted(inn_overs_dict.keys(), reverse=True):
                o_balls = inn_overs_dict[ov_int]
                display_ov_num = ov_int + 1
                o_runs = sum(x.runs for x in o_balls)
                o_wkts = sum(1 for x in o_balls if is_ball_wicket(x))
                bowler_nm = o_balls[-1].bowler if o_balls else "Bowler"
                team_score_at_over = over_cum_map.get(ov_int, f"{o_runs}-{o_wkts}")

                # Batters involved in this over
                batters_in_over = list(dict.fromkeys([b.batter for b in o_balls if b.batter]))
                batter1_name = batters_in_over[0] if len(batters_in_over) > 0 else "Batter 1"
                batter2_name = batters_in_over[1] if len(batters_in_over) > 1 else (batters_in_over[0] if len(batters_in_over) > 0 else "Batter 2")

                # Find bowler figures in inning bowling card if present
                bowler_fig_str = f"1-0-{o_runs}-{o_wkts}"
                for bo in inn.bowling:
                    if bo.bowler.lower() in bowler_nm.lower() or bowler_nm.lower() in bo.bowler.lower():
                        bowler_fig_str = f"{bo.overs}-{bo.maidens}-{bo.runs}-{bo.wickets}"
                        break

                # Over Ball Tokens
                over_tokens_compact = ""
                for b in o_balls:
                    tok, _, _ = format_ball_token(b)
                    tok_color = "text-red-600 font-bold" if tok == "W" else ("text-blue-600 font-bold" if tok == "4" else ("text-emerald-700 font-bold" if tok == "6" else "text-slate-700"))
                    over_tokens_compact += f'<span class="px-1 {tok_color} font-mono">{tok}</span> '

                # Save over for the "Overs" tab
                overs_tab_data[inn_idx].append({
                    "over_num": display_ov_num,
                    "cum_score": team_score_at_over,
                    "bowler": bowler_nm,
                    "batters": f"{batter1_name} & {batter2_name}" if len(batters_in_over) > 1 else batter1_name,
                    "tokens_html": over_tokens_compact,
                    "runs": o_runs
                })

                # EXACT CRICBUZZ OVER END CARD STRUCTURE (Image 3) - NO IMPACT OVER CLUTTER!
                live_feed_items += f"""
                <div class="cricbuzz-over-card my-4 p-3.5 sm:p-4 bg-white rounded-xl border border-slate-200 shadow-2xs hover:shadow-xs transition">
                    <!-- Top Line: Over # | Score | Ball Outcomes (Runs) -->
                    <div class="flex flex-wrap items-center justify-between text-xs sm:text-sm font-black text-slate-900 gap-2">
                        <div class="flex items-center gap-2.5">
                            <span class="text-emerald-800 text-sm font-black">Over {display_ov_num}</span>
                            <span class="text-slate-400 font-normal">|</span>
                            <span class="text-slate-800 font-extrabold">{team_score_at_over}</span>
                        </div>
                        <div class="flex items-center gap-1.5 font-bold">
                            <div class="flex items-center">{over_tokens_compact}</div>
                            <span class="text-xs font-semibold text-slate-500">({o_runs} runs)</span>
                        </div>
                    </div>

                    <!-- Dashed Divider -->
                    <div class="border-t border-dashed border-slate-200 my-2.5"></div>

                    <!-- Middle Line: Batters on Crease (Left) | Bowler Figures (Right) -->
                    <div class="flex items-center justify-between text-xs text-slate-700">
                        <div class="space-y-0.5 min-w-0">
                            <div class="font-semibold text-slate-900 truncate">
                                {html_escape.escape(batter1_name)}
                            </div>
                            {f'<div class="font-semibold text-slate-900 truncate">{html_escape.escape(batter2_name)}</div>' if len(batters_in_over) > 1 else ''}
                        </div>
                        <div class="text-right shrink-0 font-medium">
                            <div class="font-bold text-slate-900">{html_escape.escape(bowler_nm)}</div>
                            <div class="text-3xs text-slate-500 font-mono">{bowler_fig_str}</div>
                        </div>
                    </div>

                    <!-- Bottom Line: Over Summary & View All Overs Links -->
                    <div class="flex items-center gap-3 text-3xs font-bold text-emerald-700 mt-2.5 pt-2 border-t border-slate-100">
                        <button onclick="switchTab('overs')" class="hover:text-emerald-950 hover:underline flex items-center gap-0.5">
                            Over Summary &raquo;
                        </button>
                        <span class="text-slate-300">&bull;</span>
                        <button onclick="switchTab('overs')" class="hover:text-emerald-950 hover:underline flex items-center gap-0.5">
                            View all overs &raquo;
                        </button>
                    </div>
                </div>
                """

                # Render deliveries within this over
                def get_ball_num(b: BallByBallEvent):
                    if '.' in b.over_str:
                        try: return float(b.over_str)
                        except: pass
                    return float(b.ball_num)

                for b in sorted(o_balls, key=get_ball_num, reverse=True):
                    tok, badge_cls, cat = format_ball_token(b)
                    is_wkt = cat == 'wkt'
                    is_six = cat == 'six'
                    is_four = cat == 'four'
                    is_highlight = is_wkt or is_six or is_four
                    actor_str = f"{html_escape.escape(b.bowler)} to {html_escape.escape(b.batter)}" if b.bowler or b.batter else "Match Delivery"

                    tags = ["all"]
                    if is_highlight: tags.append("highlights")
                    if is_wkt: tags.append("w")
                    if is_six: tags.append("6s")
                    if is_four: tags.append("4s")
                    tags.append(f"inn{inn_idx}")
                    tags_attr = " ".join(tags)

                    highlight_callout = ""
                    if is_six:
                        highlight_callout = '<span class="text-3xs font-black px-1.5 py-0.5 rounded bg-[#009270] text-white uppercase tracking-wider">SIX</span>'
                    elif is_four:
                        highlight_callout = '<span class="text-3xs font-black px-1.5 py-0.5 rounded bg-blue-600 text-white uppercase tracking-wider">FOUR</span>'
                    elif is_wkt:
                        highlight_callout = '<span class="text-3xs font-black px-1.5 py-0.5 rounded bg-red-600 text-white uppercase tracking-wider">WICKET</span>'

                    live_feed_items += f"""
                    <div class="live-comm-item py-3 px-2 sm:px-3.5 hover:bg-slate-50 transition border-b border-slate-100 last:border-0" data-tags="{tags_attr}">
                        <div class="flex items-start gap-2.5 sm:gap-3.5">
                            <div class="flex items-center gap-2 shrink-0 pt-0.5">
                                <span class="text-xs font-mono font-bold text-slate-500 w-8 sm:w-10 text-right">{b.over_str}</span>
                                <span class="w-7 h-7 sm:w-8 sm:h-8 rounded-full flex items-center justify-center text-xs font-black {badge_cls}">{tok}</span>
                            </div>
                            <div class="flex-1 min-w-0">
                                <div class="text-xs sm:text-sm font-bold text-slate-900 flex flex-wrap items-center gap-1.5">
                                    <span>{actor_str}</span>
                                    {highlight_callout}
                                    <span class="text-2xs font-semibold px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">{b.runs} run{'' if b.runs == 1 else 's'}</span>
                                </div>
                                <div class="text-xs sm:text-sm text-slate-600 mt-1 leading-relaxed">
                                    {html_escape.escape(b.commentary_text)}
                                </div>
                            </div>
                        </div>
                    </div>
                    """

        # -------------------------------------------------------------
        # 5. Build the New "Overs" Tab (Cricbuzz Over-by-Over, Image 1)
        # -------------------------------------------------------------
        overs_tab_pills = '<div class="flex items-center gap-2 mb-4 overflow-x-auto no-scrollbar">'
        overs_tab_tables = ""

        latest_inn_idx = len(match_data.innings) - 1 if match_data.innings else 0

        for idx, inn in enumerate(match_data.innings):
            active_btn_cls = "bg-[#009270] text-white shadow-2xs font-bold" if idx == latest_inn_idx else "bg-white text-slate-700 border border-slate-300 font-medium hover:bg-slate-50"
            inn_human_idx = idx + 1
            overs_tab_pills += f"""
            <button onclick="switchOversInn({idx})" id="ovInnBtn-{idx}" class="ov-inn-btn px-4 py-1.5 rounded-full text-xs transition whitespace-nowrap shrink-0 {active_btn_cls}">
                {html_escape.escape(inn.inning_name)} ({inn_human_idx}{'st' if inn_human_idx == 1 else 'nd'} Inn)
            </button>
            """

            # Build rows for this inning's overs
            rows_html = ""
            inn_overs_list = overs_tab_data.get(inn_human_idx, [])
            for ov_item in inn_overs_list:
                rows_html += f"""
                <tr class="hover:bg-slate-50 transition border-b border-slate-100 last:border-0">
                    <td class="py-3 px-3 sm:px-4 align-top w-24">
                        <div class="font-black text-slate-900 text-sm">Ov {ov_item['over_num']}</div>
                        <div class="text-xs font-semibold text-slate-500 font-mono mt-0.5">{ov_item['cum_score']}</div>
                    </td>
                    <td class="py-3 px-3 sm:px-4 align-top">
                        <div class="text-xs font-bold text-slate-800">{html_escape.escape(ov_item['bowler'])} to {html_escape.escape(ov_item['batters'])}</div>
                        <div class="mt-1.5 flex items-center gap-1">{ov_item['tokens_html']}</div>
                    </td>
                    <td class="py-3 px-3 sm:px-4 align-top text-right font-black text-slate-900 text-base w-16">
                        {ov_item['runs']}
                    </td>
                </tr>
                """

            hidden_cls = "" if idx == latest_inn_idx else "hidden"
            overs_tab_tables += f"""
            <div id="ov-inn-{idx}" class="ov-inn-container bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden mb-6 {hidden_cls}">
                <div class="bg-[#009270] px-4 sm:px-6 py-3 text-white flex items-center justify-between">
                    <h3 class="font-extrabold text-sm sm:text-base tracking-wide uppercase">
                        {html_escape.escape(inn.inning_name)} - Over by Over Breakdown
                    </h3>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs sm:text-sm">
                        <thead class="bg-slate-100 text-slate-600 uppercase font-semibold text-3xs tracking-wider border-b border-slate-200">
                            <tr>
                                <th class="py-2.5 px-3 sm:px-4">Overs</th>
                                <th class="py-2.5 px-3 sm:px-4">Balls</th>
                                <th class="py-2.5 px-3 sm:px-4 text-right">Runs</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-100">
                            {rows_html if rows_html else '<tr><td colspan="3" class="py-6 text-center text-slate-400">No overs recorded yet</td></tr>'}
                        </tbody>
                    </table>
                </div>
            </div>
            """

        overs_tab_pills += '</div>'
        overs_section_html = f"""
        <div id="section-overs" class="tab-content mb-6 hidden">
            {overs_tab_pills}
            {overs_tab_tables}
        </div>
        """

        # -------------------------------------------------------------
        # 6. Build the New "Points Table" Tab
        # -------------------------------------------------------------
        pt_standings = points_table_feed.get("standings", [])
        pt_tournament = points_table_feed.get("tournament", "Caribbean Premier League 2026")
        pt_rows = ""
        for s in pt_standings:
            highlight = "bg-emerald-50/70 font-bold" if s.get("pos") <= 4 else ""
            pt_rows += f"""
            <tr class="hover:bg-slate-50 transition border-b border-slate-100 last:border-0 {highlight}">
                <td class="py-2.5 px-3 text-center font-black text-slate-700">{s.get('pos')}</td>
                <td class="py-2.5 px-3 sm:px-4 font-bold text-slate-900 flex items-center gap-2">
                    <span class="w-6 h-6 rounded-full bg-emerald-100 text-emerald-800 text-3xs font-black flex items-center justify-center border border-emerald-300 shrink-0">
                        {s.get('short_name', '')[:3]}
                    </span>
                    <span>{html_escape.escape(s.get('team', ''))}</span>
                </td>
                <td class="py-2.5 px-2 text-right font-medium text-slate-700">{s.get('matches')}</td>
                <td class="py-2.5 px-2 text-right font-semibold text-emerald-800">{s.get('won')}</td>
                <td class="py-2.5 px-2 text-right font-medium text-slate-600">{s.get('lost')}</td>
                <td class="py-2.5 px-2 text-right font-medium text-slate-500">{s.get('tied')}</td>
                <td class="py-2.5 px-2 text-right font-medium text-slate-500">{s.get('nr')}</td>
                <td class="py-2.5 px-2 text-right font-black text-slate-900 text-sm">{s.get('pts')}</td>
                <td class="py-2.5 px-3 text-right font-mono font-semibold text-slate-700">{s.get('nrr')}</td>
            </tr>
            """

        points_table_section_html = f"""
        <div id="section-points" class="tab-content mb-6 hidden">
            <div class="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
                <div class="bg-[#009270] px-4 sm:px-6 py-3 text-white flex items-center justify-between">
                    <div>
                        <h3 class="font-extrabold text-sm sm:text-base tracking-wide uppercase">
                            {html_escape.escape(pt_tournament)} — Standings
                        </h3>
                        <p class="text-3xs text-emerald-100 mt-0.5">Top 4 teams qualify for playoffs & eliminators</p>
                    </div>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs sm:text-sm whitespace-nowrap sm:whitespace-normal">
                        <thead class="bg-slate-100 text-slate-600 uppercase font-semibold text-3xs tracking-wider border-b border-slate-200">
                            <tr>
                                <th class="py-2.5 px-3 text-center">Pos</th>
                                <th class="py-2.5 px-3 sm:px-4">Team</th>
                                <th class="py-2.5 px-2 text-right">P</th>
                                <th class="py-2.5 px-2 text-right">W</th>
                                <th class="py-2.5 px-2 text-right">L</th>
                                <th class="py-2.5 px-2 text-right">T</th>
                                <th class="py-2.5 px-2 text-right">NR</th>
                                <th class="py-2.5 px-2 text-right font-bold text-slate-900">PTS</th>
                                <th class="py-2.5 px-3 text-right">NRR</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-100">
                            {pt_rows if pt_rows else '<tr><td colspan="9" class="py-6 text-center text-slate-400">No standings data available</td></tr>'}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        """

        # -------------------------------------------------------------
        # 7. Live Hub Section (Clean without impact clutter)
        # -------------------------------------------------------------
        live_hub_section = f"""
        <div id="section-live" class="tab-content mb-6">
            {crex_hero_ball_html}

            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5 sm:gap-3.5 mb-3.5">
                {batters_hub_html}
                {bowler_hub_html}
            </div>

            <!-- Prominent Live Partnership & Numerical Boundaries Bar -->
            <div class="bg-gradient-to-r from-emerald-50 via-teal-50 to-slate-50 p-3.5 sm:p-4 rounded-xl border border-emerald-200/80 shadow-xs mb-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div class="flex items-center gap-3">
                    <div class="w-8 h-8 rounded-lg bg-[#009270] text-white flex items-center justify-center font-bold text-xs shadow-2xs shrink-0">
                        P
                    </div>
                    <div>
                        <div class="text-3xs sm:text-2xs font-bold uppercase tracking-wider text-emerald-900">Key / Active Partnership</div>
                        <div class="text-sm sm:text-base font-black text-slate-900 mt-0.5">
                            {html_escape.escape(p_names_str)}: <span class="text-emerald-700">{p_runs_str}</span> <span class="text-xs font-normal text-slate-500">({p_balls_str} balls)</span>
                        </div>
                    </div>
                </div>
                <div class="flex items-center gap-3 self-start sm:self-center flex-wrap sm:flex-nowrap">
                    <div class="text-left sm:text-right">
                        <div class="text-3xs uppercase font-bold text-slate-500">Partnership Boundaries</div>
                        <div class="mt-0.5 flex items-center gap-1.5">
                            <span class="inline-flex items-center gap-1 bg-white border border-blue-300 px-2 py-0.5 rounded-full text-xs font-bold text-blue-800 shadow-2xs">
                                <span class="w-3.5 h-3.5 rounded-full bg-blue-600 text-white flex items-center justify-center text-3xs font-black">4</span> {p_fours} Fours
                            </span>
                            <span class="inline-flex items-center gap-1 bg-white border border-emerald-400 px-2 py-0.5 rounded-full text-xs font-black text-[#009270] shadow-2xs">
                                <span class="w-3.5 h-3.5 rounded-full bg-[#009270] text-white flex items-center justify-center text-3xs font-black">6</span> {p_sixes} Sixes
                            </span>
                        </div>
                    </div>
                    <div class="border-l border-slate-200 pl-3 text-left sm:text-right">
                        <div class="text-3xs uppercase font-bold text-slate-500">Last Wicket</div>
                        <div class="text-xs font-bold text-slate-700 mt-0.5">{html_escape.escape(last_wkt_str)}</div>
                    </div>
                </div>
            </div>

            <!-- Recent Overs Breakdown (Clean) -->
            <div class="bg-slate-100/80 p-3 sm:p-3.5 rounded-xl border border-slate-200 mb-4">
                <div class="text-3xs sm:text-2xs uppercase font-bold tracking-wider text-slate-600 mb-2 flex items-center justify-between">
                    <span>Recent Overs Breakdown (Numerical Outcomes)</span>
                    <button onclick="switchTab('overs')" class="text-emerald-700 font-bold hover:underline text-3xs">View All Overs &raquo;</button>
                </div>
                <div class="flex items-center gap-2 overflow-x-auto no-scrollbar pb-1">
                    {recent_overs_html if recent_overs_html else '<div class="text-xs text-slate-400 py-2">No over breakdown available yet</div>'}
                </div>
            </div>

            <!-- LIVE STREAM FEED -->
            <div class="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
                <div class="bg-[#009270] px-4 sm:px-6 py-3 text-white flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div>
                        <div class="font-extrabold text-sm sm:text-base tracking-wide uppercase flex items-center gap-2">
                            <span>Live Match Updates & All Overs</span>
                            <span class="bg-[#124d38] text-emerald-200 text-xs px-2.5 py-0.5 rounded-full font-mono font-bold">
                                {total_deliveries_count} Deliveries
                            </span>
                        </div>
                    </div>
                </div>

                <!-- Filter Pills -->
                <div class="px-3 sm:px-6 py-2 bg-slate-100 border-b border-slate-200 flex items-center gap-1.5 overflow-x-auto no-scrollbar">
                    <span class="text-3xs uppercase font-bold text-slate-500 mr-1 shrink-0">Filter:</span>
                    <button onclick="filterLiveComm('all')" id="livePill-all" class="live-pill px-3 py-1 rounded-full text-xs font-bold bg-[#009270] text-white shadow-2xs shrink-0">All</button>
                    <button onclick="filterLiveComm('highlights')" id="livePill-highlights" class="live-pill px-3 py-1 rounded-full text-xs font-medium bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 shrink-0">Highlights</button>
                    <button onclick="filterLiveComm('w')" id="livePill-w" class="live-pill px-3 py-1 rounded-full text-xs font-medium bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 shrink-0">Wickets (W)</button>
                    <button onclick="filterLiveComm('6s')" id="livePill-6s" class="live-pill px-3 py-1 rounded-full text-xs font-medium bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 shrink-0">Sixes (6s)</button>
                    <button onclick="filterLiveComm('4s')" id="livePill-4s" class="live-pill px-3 py-1 rounded-full text-xs font-medium bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 shrink-0">Fours (4s)</button>
                    <button onclick="filterLiveComm('inn1')" id="livePill-inn1" class="live-pill px-3 py-1 rounded-full text-xs font-medium bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 shrink-0">Inning 1</button>
                    <button onclick="filterLiveComm('inn2')" id="livePill-inn2" class="live-pill px-3 py-1 rounded-full text-xs font-medium bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 shrink-0">Inning 2</button>
                </div>

                <div id="liveStreamFeed" class="divide-y divide-slate-100 p-2 sm:p-4">
                    {live_feed_items if live_feed_items else '<div class="py-8 text-center text-slate-400">No ball updates recorded yet</div>'}
                </div>
            </div>
        </div>
        """

        # -------------------------------------------------------------
        # 8. Full Scorecard Section (Team Switching Tabs & Extras)
        # -------------------------------------------------------------
        team_tabs_html = '<div class="flex items-center gap-2 mb-4 overflow-x-auto no-scrollbar">'
        scorecard_innings_html = ""

        for idx, inn in enumerate(match_data.innings):
            active_btn_cls = "bg-[#009270] text-white shadow-2xs font-bold" if idx == latest_inn_idx else "bg-white text-slate-700 border border-slate-300 font-medium hover:bg-slate-50"
            team_tabs_html += f"""
            <button onclick="switchScorecardInn({idx})" id="scInnBtn-{idx}" class="sc-inn-btn px-4 py-1.5 rounded-full text-xs transition whitespace-nowrap shrink-0 {active_btn_cls}">
                {html_escape.escape(inn.inning_name)} ({idx + 1}{'st' if idx == 0 else 'nd'} Inn)
            </button>
            """

            bat_rows = ""
            for b in inn.batting:
                is_notout = "not out" in b.dismissal.lower()
                star = '<span class="text-xs text-emerald-600 font-bold">*</span>' if is_notout else ''
                bat_rows += f"""
                <tr class="hover:bg-slate-50 transition">
                    <td class="py-2.5 px-3 sm:px-4 font-bold text-slate-900">{html_escape.escape(b.batter)} {star}</td>
                    <td class="py-2.5 px-3 sm:px-4 text-slate-500 font-normal">{html_escape.escape(b.dismissal)}</td>
                    <td class="py-2.5 px-2 sm:px-3 text-right font-extrabold text-slate-900">{b.runs}</td>
                    <td class="py-2.5 px-2 sm:px-3 text-right text-slate-600">{b.balls}</td>
                    <td class="py-2.5 px-2 sm:px-3 text-right text-slate-600 font-semibold">{b.fours}</td>
                    <td class="py-2.5 px-2 sm:px-3 text-right text-slate-600 font-semibold">{b.sixes}</td>
                    <td class="py-2.5 px-3 sm:px-4 text-right font-semibold text-slate-700">{b.strike_rate:.2f}</td>
                </tr>
                """

            extras_str = inn.extras.raw if inn.extras else "0 (b 0, lb 0, w 0, nb 0, p 0)"
            extras_total = inn.extras.total if inn.extras else 0
            extras_row = f"""
            <tr class="bg-slate-50 border-t border-slate-200 text-xs sm:text-sm font-medium">
                <td class="py-2.5 px-3 sm:px-4 font-bold text-slate-800">Extras</td>
                <td class="py-2.5 px-3 sm:px-4 text-slate-600">{html_escape.escape(extras_str)}</td>
                <td class="py-2.5 px-2 sm:px-3 text-right font-black text-slate-900">{extras_total}</td>
                <td colspan="4"></td>
            </tr>
            """

            total_raw = inn.total.raw if inn.total else inn.header_summary.split(' Inning ')[-1]
            total_overs = inn.total.overs if inn.total else ""
            total_rr = inn.total.run_rate if (inn.total and inn.total.run_rate) else ""
            total_row = f"""
            <tr class="bg-slate-100 border-t-2 border-slate-200 text-xs sm:text-sm font-bold">
                <td class="py-3 px-3 sm:px-4 font-black text-slate-900">Total</td>
                <td class="py-3 px-3 sm:px-4 text-slate-600 font-normal">
                    {f'({total_overs} Overs{f", RR: {total_rr}" if total_rr else ""})' if total_overs else ''}
                </td>
                <td class="py-3 px-2 sm:px-3 text-right font-black text-slate-900 text-base">{html_escape.escape(total_raw)}</td>
                <td colspan="4"></td>
            </tr>
            """

            bowl_rows = ""
            for bo in inn.bowling:
                bowl_rows += f"""
                <tr class="hover:bg-slate-50 transition">
                    <td class="py-2.5 px-3 sm:px-4 font-bold text-slate-900">{html_escape.escape(bo.bowler)}</td>
                    <td class="py-2.5 px-2 sm:px-3 text-right text-slate-700">{bo.overs}</td>
                    <td class="py-2.5 px-2 sm:px-3 text-right text-slate-600">{bo.maidens}</td>
                    <td class="py-2.5 px-2 sm:px-3 text-right font-semibold text-slate-900">{bo.runs}</td>
                    <td class="py-2.5 px-2 sm:px-3 text-right font-extrabold text-red-600">{bo.wickets}</td>
                    <td class="py-2.5 px-2 sm:px-3 text-right font-black text-emerald-800 bg-emerald-50/70">{bo.dot_balls}</td>
                    <td class="py-2.5 px-3 sm:px-4 text-right font-semibold text-slate-700">{bo.economy:.2f}</td>
                </tr>
                """

            fow_section = ""
            if inn.fall_of_wickets:
                fow_chips = " &nbsp;•&nbsp; ".join([
                    f"<span class='font-bold text-slate-800'>{w.wicket_num}-{w.team_score}</span> <span class='text-slate-500'>({html_escape.escape(w.batter_out)}, {w.over} ov)</span>"
                    for w in inn.fall_of_wickets
                ])
                fow_section = f"""
                <div class="px-4 sm:px-6 py-2.5 bg-slate-50 border-t border-slate-200 text-xs text-slate-700 flex flex-wrap items-center">
                    <span class="font-bold text-slate-900 uppercase tracking-wider text-3xs sm:text-2xs mr-2 shrink-0">Fall of Wickets:</span>
                    <div class="flex flex-wrap gap-1 leading-relaxed">
                        {fow_chips}
                    </div>
                </div>
                """

            hidden_cls = "" if idx == latest_inn_idx else "hidden"
            scorecard_innings_html += f"""
            <div id="sc-inn-{idx}" class="sc-inn-container bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden mb-6 {hidden_cls}">
                <div class="bg-[#009270] px-4 sm:px-6 py-3 text-white flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <h3 class="font-extrabold text-sm sm:text-base tracking-wide uppercase">
                        {html_escape.escape(inn.header_summary)}
                    </h3>
                </div>

                <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs sm:text-sm whitespace-nowrap sm:whitespace-normal">
                        <thead class="bg-slate-100 text-slate-600 uppercase font-semibold text-3xs sm:text-2xs tracking-wider border-b border-slate-200">
                            <tr>
                                <th class="py-2.5 px-3 sm:px-4">Batter</th>
                                <th class="py-2.5 px-3 sm:px-4">Dismissal</th>
                                <th class="py-2.5 px-2 sm:px-3 text-right">R</th>
                                <th class="py-2.5 px-2 sm:px-3 text-right">B</th>
                                <th class="py-2.5 px-2 sm:px-3 text-right">4s</th>
                                <th class="py-2.5 px-2 sm:px-3 text-right">6s</th>
                                <th class="py-2.5 px-3 sm:px-4 text-right">SR</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-100 font-medium">
                            {bat_rows if bat_rows else '<tr><td colspan="7" class="py-4 text-center text-slate-400">No batting data recorded</td></tr>'}
                            {extras_row}
                            {total_row}
                        </tbody>
                    </table>
                </div>

                <div class="border-t-2 border-slate-100">
                    <div class="px-4 py-2 bg-slate-50 font-bold text-xs uppercase tracking-wider text-slate-600 border-b border-slate-200 flex justify-between items-center">
                        <span>Bowling Figures</span>
                        <span class="text-3xs sm:text-2xs font-normal text-slate-500">* Dot Balls = Wickets, Leg-byes, Byes & 0s</span>
                    </div>
                    <div class="overflow-x-auto">
                        <table class="w-full text-left text-xs sm:text-sm whitespace-nowrap sm:whitespace-normal">
                            <thead class="bg-slate-100 text-slate-600 uppercase font-semibold text-3xs sm:text-2xs tracking-wider border-b border-slate-200">
                                <tr>
                                    <th class="py-2.5 px-3 sm:px-4">Bowler</th>
                                    <th class="py-2.5 px-2 sm:px-3 text-right">O</th>
                                    <th class="py-2.5 px-2 sm:px-3 text-right">M</th>
                                    <th class="py-2.5 px-2 sm:px-3 text-right">R</th>
                                    <th class="py-2.5 px-2 sm:px-3 text-right">W</th>
                                    <th class="py-2.5 px-2 sm:px-3 text-right font-black text-emerald-800 bg-emerald-50">DOTS</th>
                                    <th class="py-2.5 px-3 sm:px-4 text-right">ECON</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-100 font-medium">
                                {bowl_rows if bowl_rows else '<tr><td colspan="7" class="py-4 text-center text-slate-400">No bowling data recorded</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>

                {fow_section}
            </div>
            """

        team_tabs_html += '</div>'
        full_scorecard_section = f"""
        <div id="section-scorecard" class="tab-content mb-6 hidden">
            {team_tabs_html}
            {scorecard_innings_html}
        </div>
        """

        # -------------------------------------------------------------
        # 9. Dedicated Commentary Tab Section
        # -------------------------------------------------------------
        commentary_tab_section = f"""
        <div id="section-commentary" class="tab-content mb-6 hidden">
            <div class="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
                <div class="bg-[#009270] px-4 sm:px-6 py-3 text-white flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div>
                        <div class="font-extrabold text-sm sm:text-base tracking-wide uppercase flex items-center gap-2">
                            <span>Ball-by-Ball Commentary Stream</span>
                            <span class="bg-[#124d38] text-emerald-200 text-xs px-2.5 py-0.5 rounded-full font-mono font-bold">
                                {total_deliveries_count} Deliveries (A-Z All Innings)
                            </span>
                        </div>
                    </div>
                </div>

                <div class="px-3 sm:px-6 py-2 bg-slate-100 border-b border-slate-200 flex items-center gap-1.5 overflow-x-auto no-scrollbar">
                    <span class="text-3xs uppercase font-bold text-slate-500 mr-1 shrink-0">Filter:</span>
                    <button onclick="filterLiveComm('all')" class="live-pill px-3 py-1 rounded-full text-xs font-bold bg-[#009270] text-white shadow-2xs shrink-0">All</button>
                    <button onclick="filterLiveComm('highlights')" class="live-pill px-3 py-1 rounded-full text-xs font-medium bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 shrink-0">Highlights</button>
                    <button onclick="filterLiveComm('w')" class="live-pill px-3 py-1 rounded-full text-xs font-medium bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 shrink-0">Wickets (W)</button>
                    <button onclick="filterLiveComm('6s')" class="live-pill px-3 py-1 rounded-full text-xs font-medium bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 shrink-0">Sixes (6s)</button>
                    <button onclick="filterLiveComm('4s')" class="live-pill px-3 py-1 rounded-full text-xs font-medium bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 shrink-0">Fours (4s)</button>
                    <button onclick="filterLiveComm('inn1')" class="live-pill px-3 py-1 rounded-full text-xs font-medium bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 shrink-0">Inning 1</button>
                    <button onclick="filterLiveComm('inn2')" class="live-pill px-3 py-1 rounded-full text-xs font-medium bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 shrink-0">Inning 2</button>
                </div>

                <div class="divide-y divide-slate-100 p-2 sm:p-4">
                    {live_feed_items if live_feed_items else '<div class="py-8 text-center text-slate-400">No commentary recorded</div>'}
                </div>
            </div>
        </div>
        """

        # -------------------------------------------------------------
        # 10. Key Partnerships Section
        # -------------------------------------------------------------
        part_rows = ""
        for p in match_data.partnerships:
            b1 = p.batter_1
            b2 = p.batter_2
            b_str = p.boundary_str or f"{p.fours}x4, {p.sixes}x6"
            part_rows += f"""
            <tr class="hover:bg-slate-50 transition">
                <td class="py-3 px-3 sm:px-4 font-semibold text-slate-800">{html_escape.escape(b1.name)} <span class="text-slate-500 text-xs font-normal">{b1.runs}({b1.balls})</span></td>
                <td class="py-3 px-3 sm:px-4 text-center font-black text-slate-900 text-sm sm:text-base">{p.milestone_runs} <span class="text-slate-500 text-xs font-normal">({p.balls})</span></td>
                <td class="py-3 px-3 sm:px-4 text-center font-black text-emerald-800 bg-emerald-50/60">
                    <span class="bg-white border border-emerald-300 px-3 py-1 rounded-full text-xs shadow-2xs font-extrabold text-[#009270]">
                        {html_escape.escape(b_str)}
                    </span>
                </td>
                <td class="py-3 px-3 sm:px-4 text-right font-semibold text-slate-800"><span class="text-slate-500 text-xs font-normal">{b2.runs}({b2.balls})</span> {html_escape.escape(b2.name)}</td>
            </tr>
            """

        partnerships_section = f"""
        <div id="section-partnerships" class="tab-content mb-6 hidden">
            <div class="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
                <div class="bg-[#009270] px-4 sm:px-6 py-3 text-white font-extrabold text-sm sm:text-base tracking-wide uppercase flex items-center justify-between">
                    <span>Key Partnerships & Adjacent Boundaries</span>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs sm:text-sm">
                        <thead class="bg-slate-100 text-slate-600 uppercase font-semibold text-3xs sm:text-2xs tracking-wider border-b border-slate-200">
                            <tr>
                                <th class="py-3 px-3 sm:px-4">Batter 1</th>
                                <th class="py-3 px-3 sm:px-4 text-center">Partnership Runs</th>
                                <th class="py-3 px-3 sm:px-4 text-center">Boundaries</th>
                                <th class="py-3 px-3 sm:px-4 text-right">Batter 2</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-100">
                            {part_rows if part_rows else '<tr><td colspan="4" class="py-6 text-center text-slate-400">No partnership data available</td></tr>'}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        """

        # -------------------------------------------------------------
        # 11. Dedicated Impact Overs Tab (Kept isolated as requested)
        # -------------------------------------------------------------
        all_impact_cards = ""
        for inn in match_data.innings:
            io_list = getattr(inn, 'impact_overs_list', []) or getattr(inn, 'impact_overs', [])
            for io in io_list:
                w_str = f"({io.get('wickets', 0)}W)" if io.get('wickets', 0) > 0 else ""
                raw_balls = io.get('ball_outcomes', [])
                tokens = [format_raw_outcome(x)[0] for x in raw_balls]
                ball_str = " ".join(tokens)
                bowler_str = io.get('bowler', 'Bowler')
                over_lbl = io.get('over_label', f"Over {io.get('over_number', 0)}")
                all_impact_cards += f"""
                <div class="bg-white p-3.5 sm:p-4 rounded-xl border-2 border-amber-400 shadow-2xs bg-gradient-to-br from-amber-50/40 via-white to-amber-50/20">
                    <div class="flex justify-between items-center text-xs">
                        <span class="font-bold text-slate-800">{over_lbl} ({html_escape.escape(bowler_str)})</span>
                        <span class="text-3xs uppercase tracking-wider font-bold text-amber-700 bg-amber-100 px-2 py-0.5 rounded">{inn.inning_name}</span>
                    </div>
                    <div class="text-xl sm:text-2xl font-black text-amber-600 mt-1">
                        {io.get('runs', 0)} Runs <span class="text-xs font-bold text-red-600">{w_str}</span>
                    </div>
                    <div class="mt-2 text-3xs sm:text-2xs text-slate-600 font-mono bg-slate-50 p-1.5 rounded border border-slate-100">
                        Deliveries: {html_escape.escape(ball_str)}
                    </div>
                </div>
                """

        impact_overs_section = f"""
        <div id="section-impact" class="tab-content mb-6 hidden">
            <div class="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
                <div class="bg-[#009270] px-4 sm:px-6 py-3 text-white flex items-center justify-between">
                    <div class="font-extrabold text-sm sm:text-base tracking-wide uppercase">
                        Impact Overs Breakdown (Scored 10+ Runs)
                    </div>
                    <span class="bg-[#186047] px-2.5 py-1 rounded font-bold text-amber-300 text-xs">
                        Total {meta.match_impact_overs} Impact Overs
                    </span>
                </div>
                <div class="p-3.5 sm:p-6 bg-slate-50/50">
                    <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 sm:gap-4">
                        {all_impact_cards if all_impact_cards else '<div class="col-span-3 text-center py-6 text-slate-400">No impact overs (>= 10 runs) in this match</div>'}
                    </div>
                </div>
            </div>
        </div>
        """

        # -------------------------------------------------------------
        # 12. Match Status Line without Brackets ('35 balls remaining')
        # -------------------------------------------------------------
        raw_status = f"{meta.status} — {meta.status_note}" if meta.status_note else meta.status
        
        # Chase equation if live
        if meta.is_live and len(match_data.innings) >= 2:
            inn1 = match_data.innings[0]
            inn2 = match_data.innings[1]
            try:
                m_score1 = re.search(r'(\d+)/', inn1.header_summary)
                m_score2 = re.search(r'(\d+)/', inn2.header_summary)
                m_ov2 = re.search(r'\((\d+)\.?(\d+)?', inn2.header_summary)
                if m_score1 and m_score2:
                    target = int(m_score1.group(1)) + 1
                    current_runs = int(m_score2.group(1))
                    runs_needed = max(0, target - current_runs)
                    ov_int = int(m_ov2.group(1)) if m_ov2 else 0
                    bl_int = int(m_ov2.group(2)) if (m_ov2 and m_ov2.group(2)) else 0
                    balls_bowled = ov_int * 6 + bl_int
                    max_balls = 120
                    balls_rem = max(0, max_balls - balls_bowled)
                    rrr = (runs_needed * 6 / balls_rem) if balls_rem > 0 else 0.0
                    chasing_team = inn2.inning_name.replace("Inning", "").replace("Innings", "").strip()
                    raw_status = f"Live — {chasing_team} require {runs_needed} runs from {balls_rem} balls (RRR: {rrr:.2f})"
            except Exception:
                pass

        # Clean status line: remove (35b rem) -> 35 balls remaining
        balls_rem_extra = ""
        m_b = re.search(r'\((\d+)\s*(?:b|balls)?\s*(?:rem|remaining)?\)', raw_status, re.I)
        if m_b:
            balls_cnt = m_b.group(1)
            balls_rem_extra = f"{balls_cnt} balls remaining"
            raw_status = raw_status[:m_b.start()].strip() + " " + raw_status[m_b.end():].strip()
            raw_status = raw_status.strip()

        status_line_html = f"<strong>Status:</strong> {html_escape.escape(raw_status)}"
        if balls_rem_extra:
            status_line_html += f' <span class="text-xs text-slate-500 font-normal ml-1.5">{html_escape.escape(balls_rem_extra)}</span>'

        score_boxes = ""
        for inn in match_data.innings:
            score_txt = inn.header_summary.split(' Inning ')[-1] if ' Inning ' in inn.header_summary else inn.header_summary
            score_boxes += f"""
            <div class="bg-white p-3.5 sm:p-4 rounded-xl border border-slate-200 shadow-2xs flex items-center justify-between">
                <div>
                    <div class="text-xs sm:text-sm font-bold text-slate-800">{html_escape.escape(inn.inning_name)}</div>
                </div>
                <div class="text-right">
                    <div class="text-base sm:text-xl font-black text-slate-900">{html_escape.escape(score_txt)}</div>
                </div>
            </div>
            """

        live_pill = '<span class="w-2 h-2 rounded-full bg-red-500 mr-1.5 animate-ping inline-block"></span>LIVE' if meta.is_live else 'COMPLETED'
        live_pill_class = 'bg-red-500/20 text-red-200 border border-red-400/30 font-bold' if meta.is_live else 'bg-slate-700 text-slate-300 font-bold'

        # Match Info Card
        match_info_section = f"""
        <div id="section-info" class="tab-content mb-6 hidden">
            <div class="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
                <div class="bg-[#009270] px-4 sm:px-6 py-3 text-white font-extrabold text-sm sm:text-base tracking-wide uppercase">
                    Match Details & Tournament Information
                </div>
                <div class="p-4 sm:p-6 divide-y divide-slate-100 text-xs sm:text-sm">
                    <div class="py-2.5 flex justify-between"><span class="text-slate-500 font-medium">Match</span><span class="font-bold text-slate-800 text-right">{html_escape.escape(meta.match_title)}</span></div>
                    <div class="py-2.5 flex justify-between"><span class="text-slate-500 font-medium">Series / Tournament</span><span class="font-bold text-slate-800 text-right">{html_escape.escape(meta.series or 'Cricket Tournament')}</span></div>
                    <div class="py-2.5 flex justify-between"><span class="text-slate-500 font-medium">Venue</span><span class="font-bold text-slate-800 text-right">{html_escape.escape(meta.venue or 'Stadium')}</span></div>
                    <div class="py-2.5 flex justify-between"><span class="text-slate-500 font-medium">Toss</span><span class="font-bold text-slate-800 text-right">{html_escape.escape(meta.toss or 'N/A')}</span></div>
                    <div class="py-2.5 flex justify-between"><span class="text-slate-500 font-medium">Match Status</span><span class="font-bold text-emerald-700 text-right">{html_escape.escape(raw_status)}</span></div>
                </div>
            </div>
        </div>
        """

        # Build Tracked Matches Quick Switcher Bar
        current_mid = str(meta.match_id or "")
        json_pattern = os.path.join(output_dir, "match_*_full.json")
        sc_files = glob.glob(json_pattern)
        switcher_pills = ""
        for sf in sc_files:
            try:
                with open(sf, "r", encoding="utf-8") as fp:
                    m_json = json.load(fp)
                m_meta = m_json.get("metadata", {})
                mid = str(m_meta.get("match_id", "") or "")
                if not mid:
                    continue
                t_title = m_meta.get("match_title", f"Match {mid}")
                short_title = t_title.replace(" Women", "W").replace(" vs ", " v ")
                if len(short_title) > 28:
                    short_title = short_title[:26] + "..."
                is_curr = mid == current_mid
                is_l = m_meta.get("is_live", False)
                status_icon = '<span class="w-2 h-2 rounded-full bg-red-400 animate-pulse mr-1 inline-block"></span>' if is_l else '<span class="w-2 h-2 rounded-full bg-slate-400 mr-1 inline-block"></span>'
                if is_curr:
                    switcher_pills += f'<span class="inline-flex items-center px-2.5 py-1 rounded-lg text-xs font-black bg-[#009270] text-white border border-emerald-400 shadow-2xs whitespace-nowrap">{status_icon} {html_escape.escape(short_title)} (Current)</span>'
                else:
                    switcher_pills += f'<a href="/match/{mid}" class="inline-flex items-center px-2.5 py-1 rounded-lg text-xs font-semibold bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white transition border border-slate-700 whitespace-nowrap">{status_icon} {html_escape.escape(short_title)}</a>'
            except Exception:
                pass

        tracked_switcher_html = ""
        if switcher_pills:
            tracked_switcher_html = f"""
            <div class="mb-3.5 bg-[#124d38] border border-emerald-800 rounded-xl px-3 py-2 text-white flex items-center justify-between gap-3 overflow-x-auto no-scrollbar shadow-xs">
                <div class="flex items-center gap-2 shrink-0">
                    <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                    <span class="text-3xs uppercase font-black tracking-widest text-emerald-300">Tracked Matches:</span>
                </div>
                <div class="flex items-center gap-2 overflow-x-auto no-scrollbar text-xs">
                    {switcher_pills}
                </div>
            </div>
            """

        # Render Unified Shared Top Navigation
        global_header = PageTemplates.render_global_header("live-scores", matches_feed, series_feed)
        global_footer = PageTemplates.render_global_footer()

        # Full Complete Dashboard HTML
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta http-equiv="refresh" content="10">
    <title>{html_escape.escape(meta.match_title)} | Live Cricket Match Center</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Inter', sans-serif; background-color: #f1f5f9; -webkit-tap-highlight-color: transparent; }}
        .no-scrollbar::-webkit-scrollbar {{ display: none; }}
        .no-scrollbar {{ -ms-overflow-style: none; scrollbar-width: none; }}
        .tab-btn.active {{
            background-color: #009270 !important;
            color: #ffffff !important;
            border-bottom: 3px solid #fbbf24;
            font-weight: 800;
        }}
    </style>
</head>
<body class="text-slate-800 pb-16">

    {global_header}

    <main class="max-w-6xl mx-auto px-2.5 sm:px-4 mt-3 sm:mt-4">

        {tracked_switcher_html}

        <!-- CREX Hero Match Banner -->
        <div class="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden mb-3.5">
            <div class="p-3.5 sm:p-6 bg-gradient-to-r from-emerald-950 via-emerald-900 to-slate-900 text-white flex flex-col sm:flex-row sm:items-center justify-between gap-3 sm:gap-4">
                <div>
                    <span class="text-3xs sm:text-xs font-bold tracking-wider uppercase text-emerald-400">{html_escape.escape(meta.series or 'Cricket Tournament')}</span>
                    <h2 class="text-lg sm:text-2xl font-black mt-0.5 tracking-tight">{html_escape.escape(meta.match_title)}</h2>
                    <p class="text-2xs sm:text-xs text-slate-300 mt-0.5">Venue: {html_escape.escape(meta.venue or 'Match Venue')} {f'• Toss: {html_escape.escape(meta.toss)}' if meta.toss else ''}</p>
                </div>
                <div class="flex items-center gap-2 self-start sm:self-center">
                    <div class="bg-emerald-800/80 border border-emerald-600/50 rounded-xl px-3.5 sm:px-5 py-1.5 sm:py-2.5 text-center shadow-xs">
                        <div class="text-3xs uppercase text-emerald-300 font-bold">Total Impact Overs</div>
                        <div class="text-lg sm:text-2xl font-black text-amber-300 mt-0.5">{meta.match_impact_overs} Overs</div>
                    </div>
                </div>
            </div>

            <div class="p-3 sm:p-6 grid grid-cols-1 sm:grid-cols-2 gap-2.5 sm:gap-4 border-b border-slate-100 bg-slate-50/50">
                {score_boxes}
            </div>

            <div class="px-3.5 sm:px-6 py-2 sm:py-2.5 bg-emerald-50 border-t border-emerald-100 flex items-center justify-between text-2xs sm:text-sm font-semibold text-emerald-950">
                <span>{status_line_html}</span>
            </div>
        </div>

        <!-- STICKY SUB-MENU BAR (Includes 'Overs' and 'Points Table') -->
        <nav class="bg-[#124d38] border border-emerald-900 rounded-xl text-white shadow-sm mb-4 sticky top-12 z-40 overflow-hidden">
            <div class="flex items-center justify-between overflow-x-auto no-scrollbar px-1.5 sm:px-2 py-1.5">
                <div class="flex items-center space-x-1 sm:space-x-1.5 text-xs sm:text-sm font-bold shrink-0">
                    <button onclick="switchTab('live')" id="tabBtn-live" class="tab-btn px-3 py-1.5 rounded-lg transition active flex items-center gap-1">
                        <span>Live Hub</span>
                    </button>
                    <button onclick="switchTab('scorecard')" id="tabBtn-scorecard" class="tab-btn px-3 py-1.5 rounded-lg transition text-emerald-200 hover:text-white hover:bg-emerald-800/60 flex items-center gap-1">
                        <span>Scorecard</span>
                    </button>
                    <button onclick="switchTab('overs')" id="tabBtn-overs" class="tab-btn px-3 py-1.5 rounded-lg transition text-emerald-200 hover:text-white hover:bg-emerald-800/60 flex items-center gap-1">
                        <span>Overs</span>
                    </button>
                    <button onclick="switchTab('points')" id="tabBtn-points" class="tab-btn px-3 py-1.5 rounded-lg transition text-emerald-200 hover:text-white hover:bg-emerald-800/60 flex items-center gap-1">
                        <span>Points Table</span>
                    </button>
                    <button onclick="switchTab('partnerships')" id="tabBtn-partnerships" class="tab-btn px-3 py-1.5 rounded-lg transition text-emerald-200 hover:text-white hover:bg-emerald-800/60 flex items-center gap-1">
                        <span>Partnerships</span>
                    </button>
                    <button onclick="switchTab('impact')" id="tabBtn-impact" class="tab-btn px-3 py-1.5 rounded-lg transition text-emerald-200 hover:text-white hover:bg-emerald-800/60 flex items-center gap-1">
                        <span>Impact Overs</span>
                    </button>
                    <button onclick="switchTab('commentary')" id="tabBtn-commentary" class="tab-btn px-3 py-1.5 rounded-lg transition text-emerald-200 hover:text-white hover:bg-emerald-800/60 flex items-center gap-1">
                        <span>Commentary ({total_deliveries_count}b)</span>
                    </button>
                    <button onclick="switchTab('info')" id="tabBtn-info" class="tab-btn px-3 py-1.5 rounded-lg transition text-emerald-200 hover:text-white hover:bg-emerald-800/60 flex items-center gap-1">
                        <span>Info</span>
                    </button>
                </div>
                <button onclick="showAllTabs()" class="text-3xs sm:text-2xs font-semibold px-2.5 py-1 rounded bg-emerald-950/80 hover:bg-emerald-800 text-emerald-300 border border-emerald-700/60 shrink-0 ml-1.5">
                    View All
                </button>
            </div>
        </nav>

        <!-- SECTION 1: LIVE HUB -->
        {live_hub_section}

        <!-- SECTION 2: FULL SCORECARD (With Team Switcher & Extras) -->
        {full_scorecard_section}

        <!-- SECTION 3: NEW DEDICATED OVERS TAB -->
        {overs_section_html}

        <!-- SECTION 4: NEW POINTS TABLE TAB -->
        {points_table_section_html}

        <!-- SECTION 5: PARTNERSHIPS & BOUNDARIES -->
        {partnerships_section}

        <!-- SECTION 6: IMPACT OVERS -->
        {impact_overs_section}

        <!-- SECTION 7: DEDICATED COMMENTARY SECTION -->
        {commentary_tab_section}

        <!-- SECTION 8: MATCH INFO -->
        {match_info_section}

    </main>

    {global_footer}

    <script>
        const currentMatchId = "{safe_mid}";

        function switchTab(tabId) {{
            sessionStorage.setItem('cricket_active_tab', tabId);
            try {{ history.replaceState(null, null, '#' + tabId); }} catch(e) {{}}

            document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
            document.querySelectorAll('.tab-btn').forEach(el => {{
                el.classList.remove('active');
                el.classList.remove('bg-[#009270]', 'text-white', 'border-b-2', 'border-amber-400');
                el.classList.add('text-emerald-200');
            }});

            const target = document.getElementById('section-' + tabId);
            if (target) {{
                target.classList.remove('hidden');
            }}

            const btn = document.getElementById('tabBtn-' + tabId);
            if (btn) {{
                btn.classList.add('active');
                btn.classList.remove('text-emerald-200');
            }}
        }}

        function showAllTabs() {{
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('hidden'));
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
        }}

        function switchScorecardInn(innIdx) {{
            sessionStorage.setItem('cricket_scorecard_inn', innIdx);
            document.querySelectorAll('.sc-inn-container').forEach(el => el.classList.add('hidden'));
            document.querySelectorAll('.sc-inn-btn').forEach(btn => {{
                btn.classList.remove('bg-[#009270]', 'text-white', 'shadow-2xs', 'font-bold');
                btn.classList.add('bg-white', 'text-slate-700', 'border', 'border-slate-300', 'font-medium');
            }});

            const target = document.getElementById('sc-inn-' + innIdx);
            if (target) target.classList.remove('hidden');

            const btn = document.getElementById('scInnBtn-' + innIdx);
            if (btn) {{
                btn.classList.remove('bg-white', 'text-slate-700', 'border', 'border-slate-300', 'font-medium');
                btn.classList.add('bg-[#009270]', 'text-white', 'shadow-2xs', 'font-bold');
            }}
        }}

        function switchOversInn(innIdx) {{
            sessionStorage.setItem('cricket_overs_inn', innIdx);
            document.querySelectorAll('.ov-inn-container').forEach(el => el.classList.add('hidden'));
            document.querySelectorAll('.ov-inn-btn').forEach(btn => {{
                btn.classList.remove('bg-[#009270]', 'text-white', 'shadow-2xs', 'font-bold');
                btn.classList.add('bg-white', 'text-slate-700', 'border', 'border-slate-300', 'font-medium');
            }});

            const target = document.getElementById('ov-inn-' + innIdx);
            if (target) target.classList.remove('hidden');

            const btn = document.getElementById('ovInnBtn-' + innIdx);
            if (btn) {{
                btn.classList.remove('bg-white', 'text-slate-700', 'border', 'border-slate-300', 'font-medium');
                btn.classList.add('bg-[#009270]', 'text-white', 'shadow-2xs', 'font-bold');
            }}
        }}

        const hash = window.location.hash.replace('#', '');
        const savedTab = hash || sessionStorage.getItem('cricket_active_tab') || 'live';
        switchTab(savedTab);

        const savedInn = sessionStorage.getItem('cricket_scorecard_inn') || '{latest_inn_idx}';
        switchScorecardInn(savedInn);

        const savedOvInn = sessionStorage.getItem('cricket_overs_inn') || '{latest_inn_idx}';
        switchOversInn(savedOvInn);

        function filterLiveComm(tag) {{
            document.querySelectorAll('.live-pill').forEach(btn => {{
                btn.classList.remove('bg-[#009270]', 'text-white', 'shadow-2xs');
                btn.classList.add('bg-white', 'text-slate-700', 'border', 'border-slate-300');
            }});

            const activePill = document.getElementById('livePill-' + tag);
            if (activePill) {{
                activePill.classList.remove('bg-white', 'text-slate-700', 'border', 'border-slate-300');
                activePill.classList.add('bg-[#009270]', 'text-white', 'shadow-2xs');
            }}

            const items = document.querySelectorAll('.live-comm-item');
            items.forEach(el => {{
                const tags = (el.getAttribute('data-tags') || '').split(' ');
                if (tag === 'all' || tags.includes(tag)) {{
                    el.classList.remove('hidden');
                }} else {{
                    el.classList.add('hidden');
                }}
            }});
        }}
    </script>
</body>
</html>
"""

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        with open(match_html_path, "w", encoding="utf-8") as f:
            f.write(html)

        # Mirror to public directory for seamless Vercel / static CDN deployment
        pub_dir = os.path.join(os.path.dirname(os.path.abspath(output_dir)), "public")
        if os.path.isdir(pub_dir):
            try:
                with open(os.path.join(pub_dir, os.path.basename(html_path)), "w", encoding="utf-8") as pf:
                    pf.write(html)
                with open(os.path.join(pub_dir, os.path.basename(match_html_path)), "w", encoding="utf-8") as pf:
                    pf.write(html)
            except Exception:
                pass

        print(f"  [+] Clean Professional Match Center generated -> {html_path}")
        return html_path
