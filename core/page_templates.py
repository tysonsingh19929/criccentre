import re
import json
import html as html_escape
from typing import Dict, Any, List

class PageTemplates:
    """
    Renders Cricinfo / Cricbuzz / CREX styled platform pages:
    - Public Navigation (Completely hidden Admin console).
    - High-Visibility Mega-Drawer with category tabs and clean, un-squished match cards.
    - Cricinfo 2-Column Schedule & Fixtures Page.
    - Series Directory with tournament fixtures and unique series IDs.
    - Independent News Page with high-res images and internal article reader.
    - Teams Directory & ICC Rankings.
    """

    @classmethod
    def render_global_header(cls, active_page: str, matches_data: Dict[str, Any], series_data: Dict[str, Any]) -> str:
        top_matches = matches_data.get("top_carousel", [])
        drawer = matches_data.get("drawer", {})

        def nav_cls(page_name):
            if page_name == active_page:
                return "text-white font-extrabold border-b-2 border-amber-400 pb-1"
            return "text-emerald-100 hover:text-white transition font-medium pb-1"

        # Series Dropdown Items
        curr_series = series_data.get("all", series_data.get("current", []))[:10]
        series_dropdown_items = ""
        for s in curr_series:
            s_id = s.get('unique_series_id', s.get('series_key', s.get('series_id', '')))
            series_dropdown_items += f"""
            <a href="/series/{s_id}" class="block px-4 py-2 text-xs text-slate-700 hover:bg-emerald-50 hover:text-emerald-800 transition">
                {html_escape.escape(s.get('title', ''))}
            </a>
            """
        series_dropdown_items += """
        <div class="border-t border-slate-100 mt-1 pt-1">
            <a href="/series" class="block px-4 py-2 text-xs font-bold text-emerald-700 hover:bg-emerald-50 transition">
                View All Series &raquo;
            </a>
        </div>
        """

        # Build Carousel Match Items
        carousel_items_html = ""
        for m in top_matches:
            pill_color = "bg-red-500 text-white" if m.get("status_pill") == "LIVE" else ("bg-emerald-900 text-emerald-200" if m.get("status_pill") == "Result" else "bg-slate-700 text-slate-300")
            live_dot = '<span class="w-2 h-2 rounded-full bg-red-400 animate-ping mr-1 inline-block"></span>' if m.get("status_pill") == "LIVE" else ''
            carousel_items_html += f"""
            <a href="{m.get('href', '#')}" class="carousel-card shrink-0 px-3 py-1.5 rounded-lg bg-[#383838] hover:bg-[#2e2e2e] border border-slate-600 text-white text-xs flex items-center gap-2 transition shadow-xs">
                <span class="text-3xs uppercase font-extrabold px-1.5 py-0.5 rounded {pill_color} flex items-center">
                    {live_dot}{m.get('status_pill', 'Match')}
                </span>
                <span class="font-semibold whitespace-nowrap text-slate-200 hover:text-white">{html_escape.escape(m.get('text', ''))}</span>
            </a>
            """

        # Mega Drawer Category Counts
        all_drawer_matches = []
        for cat in ["international", "league", "domestic", "women"]:
            all_drawer_matches.extend(drawer.get(cat, []))

        cnt_all = len(all_drawer_matches)
        cnt_intl = len(drawer.get("international", []))
        cnt_league = len(drawer.get("league", []))
        cnt_dom = len(drawer.get("domestic", []))
        cnt_women = len(drawer.get("women", []))

        # Build Spacious Mega-Drawer Match Cards
        def render_drawer_cards(match_list: List[Dict[str, Any]], cat_filter: str) -> str:
            cards_html = ""
            for m in match_list[:24]:
                is_live = m.get("is_live", False)
                is_done = m.get("is_completed", False)
                st_pill = '<span class="px-1.5 py-0.5 rounded text-3xs font-extrabold bg-red-600 text-white animate-pulse">LIVE</span>' if is_live else ('<span class="px-1.5 py-0.5 rounded text-3xs font-extrabold bg-emerald-800 text-emerald-200">Result</span>' if is_done else '<span class="px-1.5 py-0.5 rounded text-3xs font-bold bg-slate-700 text-slate-300">Preview</span>')

                # Scores presentation
                s1 = m.get("team_1_score", "")
                s2 = m.get("team_2_score", "")
                scores_html = ""
                if s1 or s2:
                    scores_html = f"""
                    <div class="mt-1 flex items-center justify-between text-xs font-black text-slate-200">
                        <span>{html_escape.escape(s1)}</span>
                        <span>{html_escape.escape(s2)}</span>
                    </div>
                    """

                b_rem = m.get("balls_remaining", "")
                b_rem_html = f'<div class="text-3xs text-emerald-300 font-medium mt-0.5">{html_escape.escape(b_rem)}</div>' if b_rem else ''

                cards_html += f"""
                <div class="drawer-card bg-[#2d2d2d] hover:bg-[#383838] p-3 rounded-xl border border-slate-700 transition flex flex-col justify-between cursor-pointer"
                     data-cat="{m.get('category', 'international')}"
                     data-live="{str(is_live).lower()}"
                     onclick="window.location.href='{m.get('url', '#')}'">
                    <div>
                        <div class="flex items-center justify-between gap-2 text-3xs text-slate-400 font-semibold mb-1">
                            <span class="truncate uppercase text-emerald-400">{html_escape.escape(m.get('series', 'Tournament'))}</span>
                            {st_pill}
                        </div>
                        <h4 class="text-xs font-bold text-white leading-snug hover:text-emerald-300 transition">
                            <a href="{m.get('url', '#')}">{html_escape.escape(m.get('title', 'Match'))}</a>
                        </h4>
                        {scores_html}
                    </div>
                    <div class="mt-2 pt-2 border-t border-slate-700/60 flex items-center justify-between">
                        <span class="text-3xs text-slate-400">{html_escape.escape(m.get('stage', 'Match'))}</span>
                        <div class="text-right">
                            <span class="text-3xs font-semibold text-emerald-400">{html_escape.escape(m.get('status', 'Scheduled'))}</span>
                            {b_rem_html}
                        </div>
                    </div>
                </div>
                """
            return cards_html

        drawer_cards_all = render_drawer_cards(all_drawer_matches, "all")

        return f"""
        <!-- PUBLIC CRIC CENTER NAVIGATION (ADMIN RESTRICTED & HIDDEN) -->
        <header class="bg-[#186047] text-white sticky top-0 z-50 shadow-md">
            <div class="max-w-6xl mx-auto px-3 sm:px-4 flex items-center justify-between h-12">
                <div class="flex items-center space-x-6">
                    <a href="/" class="flex items-center gap-2">
                        <div class="bg-white text-[#186047] font-black px-2 py-0.5 rounded text-sm tracking-wider uppercase shadow-xs">
                            CRIC
                        </div>
                        <span class="text-base sm:text-lg font-black tracking-tight text-white">CENTER</span>
                    </a>

                    <nav class="hidden md:flex items-center space-x-5 text-xs font-bold">
                        <a href="/live-scores" class="{nav_cls('live-scores')}">Live Scores</a>
                        <a href="/schedule" class="{nav_cls('schedule')}">Schedule</a>
                        <div class="relative group">
                            <a href="/series" class="{nav_cls('series')} flex items-center gap-1 cursor-pointer">
                                <span>Series</span>
                                <span class="text-3xs">&#9662;</span>
                            </a>
                            <div class="absolute left-0 top-full hidden group-hover:block w-72 bg-white rounded-xl shadow-xl border border-slate-200 py-2 z-50">
                                {series_dropdown_items}
                            </div>
                        </div>
                        <a href="/teams" class="{nav_cls('teams')}">Teams</a>
                        <a href="/news" class="{nav_cls('news')}">News</a>
                        <a href="/rankings" class="{nav_cls('rankings')}">Rankings</a>
                    </nav>
                </div>

                <div class="flex items-center space-x-2.5 text-xs">
                    <a href="/schedule" class="px-3 py-1 bg-[#124d38] hover:bg-[#0d3b2c] border border-emerald-700/60 rounded-full font-semibold text-emerald-200 hover:text-white transition">
                        Cricket Schedule &raquo;
                    </a>
                </div>
            </div>

            <!-- CAROUSEL STRIP & MEGA-DRAWER TOGGLE -->
            <div class="bg-[#4a4a4a] text-white border-t border-emerald-950 relative">
                <div class="max-w-6xl mx-auto px-2 sm:px-3 flex items-center justify-between h-10 gap-2">
                    <div class="text-3xs font-black tracking-wider uppercase text-slate-300 px-2 py-1 bg-black/30 rounded shrink-0 hidden sm:block">
                        MATCHES
                    </div>

                    <div class="flex items-center gap-1 flex-1 overflow-hidden relative">
                        <button onclick="scrollCarousel(-250)" class="w-6 h-6 rounded-full bg-black/40 hover:bg-black/70 text-white flex items-center justify-center text-xs shrink-0 transition" title="Scroll Left">
                            &#10094;
                        </button>
                        <div id="matchStripCarousel" class="flex items-center gap-2 overflow-x-auto no-scrollbar scroll-smooth flex-1 py-1 px-1">
                            {carousel_items_html}
                        </div>
                        <button onclick="scrollCarousel(250)" class="w-6 h-6 rounded-full bg-black/40 hover:bg-black/70 text-white flex items-center justify-center text-xs shrink-0 transition" title="Scroll Right">
                            &#10095;
                        </button>
                    </div>

                    <!-- Mega Drawer Button -->
                    <button onclick="toggleMegaDrawer()" id="drawerToggleBtn" class="px-3 py-1 bg-[#333333] hover:bg-[#222222] text-xs font-extrabold uppercase tracking-wider rounded border border-slate-600 shrink-0 flex items-center gap-1.5 transition">
                        <span id="drawerToggleText">ALL ({cnt_all})</span>
                        <span id="drawerToggleIcon" class="text-3xs">&#9662;</span>
                    </button>
                </div>

                <!-- CRICINFO/CRICBUZZ HIGH-VISIBILITY MEGA-DRAWER -->
                <div id="megaDrawer" class="hidden bg-[#222222] border-b-2 border-emerald-600 shadow-2xl transition-all duration-200">
                    <div class="max-w-6xl mx-auto p-4 sm:p-6">
                        <!-- Drawer Tabs Header -->
                        <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-700 pb-3 mb-4">
                            <div class="flex flex-wrap items-center gap-2">
                                <button onclick="filterMegaDrawer('all')" id="tab-draw-all" class="drawer-cat-btn px-3 py-1 rounded-full text-xs font-bold bg-[#009270] text-white shadow-2xs">All ({cnt_all})</button>
                                <button onclick="filterMegaDrawer('international')" id="tab-draw-international" class="drawer-cat-btn px-3 py-1 rounded-full text-xs font-medium bg-[#333] text-slate-300 hover:bg-[#444]">International ({cnt_intl})</button>
                                <button onclick="filterMegaDrawer('league')" id="tab-draw-league" class="drawer-cat-btn px-3 py-1 rounded-full text-xs font-medium bg-[#333] text-slate-300 hover:bg-[#444]">League ({cnt_league})</button>
                                <button onclick="filterMegaDrawer('domestic')" id="tab-draw-domestic" class="drawer-cat-btn px-3 py-1 rounded-full text-xs font-medium bg-[#333] text-slate-300 hover:bg-[#444]">Domestic ({cnt_dom})</button>
                                <button onclick="filterMegaDrawer('women')" id="tab-draw-women" class="drawer-cat-btn px-3 py-1 rounded-full text-xs font-medium bg-[#333] text-slate-300 hover:bg-[#444]">Women ({cnt_women})</button>
                            </div>
                            <button onclick="toggleMegaDrawer()" class="text-xs font-bold text-slate-400 hover:text-white uppercase flex items-center gap-1">
                                <span>CLOSE</span>
                                <span class="text-3xs">&#9652;</span>
                            </button>
                        </div>

                        <!-- Spacious Match Cards Grid -->
                        <div id="drawerGrid" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5 max-h-[70vh] overflow-y-auto pr-1">
                            {drawer_cards_all}
                        </div>
                    </div>
                </div>
            </div>
        </header>
        """

    @classmethod
    def render_global_footer(cls) -> str:
        return """
        <footer class="mt-16 bg-[#0f3024] text-slate-400 text-xs py-8 border-t border-emerald-950">
            <div class="max-w-6xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-4">
                <div>
                    <div class="text-sm font-black text-white uppercase tracking-wider">CRICKET CENTER</div>
                    <div class="text-3xs text-slate-400 mt-0.5">Live Scores, Schedules, Standings & In-Depth Match Analytics</div>
                </div>
                <div class="flex items-center space-x-6 text-2xs">
                    <a href="/live-scores" class="hover:text-white transition">Live Scores</a>
                    <a href="/schedule" class="hover:text-white transition">Schedule</a>
                    <a href="/series" class="hover:text-white transition">Series</a>
                    <a href="/teams" class="hover:text-white transition">Teams</a>
                    <a href="/rankings" class="hover:text-white transition">Rankings</a>
                    <a href="/news" class="hover:text-white transition">News</a>
                </div>
                <div class="text-3xs text-slate-500">
                    &copy; 2026 Cricket Match Center. All rights reserved.
                </div>
            </div>
        </footer>

        <script>
            function scrollCarousel(offset) {
                const el = document.getElementById('matchStripCarousel');
                if (el) el.scrollBy({ left: offset, behavior: 'smooth' });
            }

            function toggleMegaDrawer() {
                const d = document.getElementById('megaDrawer');
                const btnTxt = document.getElementById('drawerToggleText');
                const btnIco = document.getElementById('drawerToggleIcon');
                if (!d) return;
                if (d.classList.contains('hidden')) {
                    d.classList.remove('hidden');
                    if (btnTxt) btnTxt.innerText = 'CLOSE';
                    if (btnIco) btnIco.innerHTML = '&#9652;';
                } else {
                    d.classList.add('hidden');
                    if (btnTxt) btnTxt.innerText = 'ALL';
                    if (btnIco) btnIco.innerHTML = '&#9662;';
                }
            }

            function filterMegaDrawer(cat) {
                document.querySelectorAll('.drawer-cat-btn').forEach(b => {
                    b.className = 'drawer-cat-btn px-3 py-1 rounded-full text-xs font-medium bg-[#333] text-slate-300 hover:bg-[#444]';
                });
                const activeBtn = document.getElementById('tab-draw-' + cat);
                if (activeBtn) {
                    activeBtn.className = 'drawer-cat-btn px-3 py-1 rounded-full text-xs font-bold bg-[#009270] text-white shadow-2xs';
                }

                document.querySelectorAll('.drawer-card').forEach(card => {
                    const cCat = card.getAttribute('data-cat') || '';
                    if (cat === 'all' || cCat === cat) {
                        card.classList.remove('hidden');
                    } else {
                        card.classList.add('hidden');
                    }
                });
            }
        </script>
        """

    # -------------------------------------------------------------------------
    # 1. LIVE SCORES PAGE
    # -------------------------------------------------------------------------
    @classmethod
    def render_live_scores_page(cls, matches_data: Dict[str, Any], series_data: Dict[str, Any]) -> str:
        header_html = cls.render_global_header("live-scores", matches_data, series_data)
        footer_html = cls.render_global_footer()

        live_list = matches_data.get("live", [])
        recent_list = matches_data.get("recent", [])
        upcoming_list = matches_data.get("upcoming", [])

        def render_cards(items: List[Dict[str, Any]], is_live_sec: bool = False) -> str:
            if not items:
                msg = "No live matches in progress right now." if is_live_sec else "No matches in this category."
                return f'<div class="py-8 text-center text-slate-400 text-xs font-medium bg-white rounded-xl border border-slate-200">{msg}</div>'

            html = '<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">'
            for m in items:
                is_live = m.get("is_live", False)
                is_done = m.get("is_completed", False)

                uid = m.get("unique_match_id", m.get("match_id", ""))
                raw_mid = m.get("match_id", "")
                series_name = m.get("series", "Cricket Tournament")
                stage = m.get("stage", "Match")
                venue = m.get("venue", "")

                # Sub-header: Stage + Venue
                stage_venue_parts = [p for p in [stage, venue] if p]
                stage_venue_str = " • ".join(stage_venue_parts) if stage_venue_parts else stage

                # Team names & codes
                t1 = m.get("team_1", "")
                t2 = m.get("team_2", "")
                if not t1 and "title" in m:
                    t_parts = re.split(r'\s+(?:vs|v)\s+', m.get("title", ""), flags=re.I)
                    if len(t_parts) >= 2:
                        t1, t2 = t_parts[0].strip(), t_parts[1].strip()
                    else:
                        t1 = m.get("title", "Team 1")
                        t2 = "Team 2"

                t1_code = m.get("team_1_code") or ("".join([w[0] for w in t1.split()[:3]]).upper() if t1 else "T1")[:4]
                t2_code = m.get("team_2_code") or ("".join([w[0] for w in t2.split()[:3]]).upper() if t2 else "T2")[:4]

                # Scores parsing
                s1 = m.get("team_1_score", "")
                s2 = m.get("team_2_score", "")

                # Status / situation text
                status_raw = m.get("situation") or m.get("status") or ("Live In Progress" if is_live else ("Match Completed" if is_done else "Scheduled"))
                balls_rem = m.get("balls_remaining", "")

                # Top Row Badge
                if is_live:
                    top_badge = '<span class="flex items-center gap-1.5 text-red-600 tracking-wide font-black uppercase text-3xs"><span class="w-2 h-2 rounded-full bg-red-600 animate-ping"></span>&bull; Live</span>'
                    situation_style = "text-amber-900 bg-amber-50 px-2 py-1 rounded border border-amber-200"
                elif is_done:
                    top_badge = '<span class="text-emerald-700 tracking-wide font-black uppercase text-3xs bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200">Result</span>'
                    situation_style = "text-emerald-900 font-bold"
                else:
                    top_badge = '<span class="text-slate-600 tracking-wide font-bold uppercase text-3xs bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200">Upcoming</span>'
                    situation_style = "text-slate-500 font-medium"

                # Find series ID if possible
                sid_slug = re.sub(r'[^a-zA-Z0-9]+', '-', series_name).strip('-').lower()

                html += f"""
                <div class="match-card bg-white rounded-xl border border-slate-200 shadow-2xs hover:shadow-md hover:border-emerald-500 transition p-4 flex flex-col justify-between cursor-pointer" data-cat="{m.get('category', 'league')}" onclick="window.location.href='/match/{raw_mid}'">
                    <div>
                        <!-- Header: • Live | Series Name > -->
                        <div class="flex items-center justify-between text-2xs mb-2 pb-2 border-b border-slate-100">
                            <div class="flex items-center gap-2 font-extrabold min-w-0">
                                {top_badge}
                                <span class="text-slate-300">|</span>
                                <a href="/series/{sid_slug}" onclick="event.stopPropagation()" class="text-slate-700 hover:text-emerald-800 font-bold truncate">
                                    {html_escape.escape(series_name)} &rsaquo;
                                </a>
                            </div>
                            <span class="text-3xs font-bold text-slate-400 uppercase tracking-wider shrink-0">{html_escape.escape(m.get('category', 'league'))}</span>
                        </div>

                        <!-- Subheader: Stage & Venue -->
                        <div class="text-3xs text-slate-500 font-medium mb-3 truncate">
                            {html_escape.escape(stage_venue_str)}
                        </div>

                        <!-- Teams & Scores (CREX Exact Layout) -->
                        <div class="space-y-2 py-1">
                            <div class="flex items-center justify-between gap-2">
                                <div class="flex items-center gap-2 min-w-0">
                                    <span class="w-6 h-6 rounded bg-slate-800 text-white flex items-center justify-center text-3xs font-black shrink-0 shadow-2xs">
                                        {t1_code}
                                    </span>
                                    <span class="text-xs font-bold text-slate-900 truncate">
                                        {html_escape.escape(t1)}
                                    </span>
                                </div>
                                <div class="text-right shrink-0">
                                    <span class="text-xs font-black text-slate-900">{html_escape.escape(s1 if s1 else ('Yet to bat' if is_live else ''))}</span>
                                </div>
                            </div>
                            <div class="flex items-center justify-between gap-2">
                                <div class="flex items-center gap-2 min-w-0">
                                    <span class="w-6 h-6 rounded bg-slate-700 text-white flex items-center justify-center text-3xs font-black shrink-0 shadow-2xs">
                                        {t2_code}
                                    </span>
                                    <span class="text-xs font-bold text-slate-900 truncate">
                                        {html_escape.escape(t2)}
                                    </span>
                                </div>
                                <div class="text-right shrink-0">
                                    <span class="text-xs font-black text-slate-900">{html_escape.escape(s2 if s2 else ('Yet to bat' if is_live else ''))}</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Situation / Result Strip & Match Center Link -->
                    <div class="mt-3 pt-2.5 border-t border-slate-100 flex items-center justify-between gap-2">
                        <div class="text-3xs {situation_style} truncate font-bold">
                            {html_escape.escape(status_raw)}
                            {f' • {html_escape.escape(balls_rem)}' if balls_rem else ''}
                        </div>
                        <a href="/match/{raw_mid}" onclick="event.stopPropagation()" class="shrink-0 px-2.5 py-1 text-3xs font-black bg-emerald-50 hover:bg-emerald-100 text-emerald-800 rounded border border-emerald-200 transition">
                            Center &raquo;
                        </a>
                    </div>
                </div>
                """
            html += '</div>'
            return html

        live_html = render_cards(live_list, is_live_sec=True)
        recent_html = render_cards(recent_list)
        upcoming_html = render_cards(upcoming_list)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Live Cricket Scores, Schedule, Upcoming Matches | Cricket Center</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>body {{ font-family: 'Inter', sans-serif; background-color: #f1f5f9; }}</style>
</head>
<body class="text-slate-800 min-h-screen flex flex-col justify-between">
    {header_html}

    <main class="max-w-6xl mx-auto px-3 sm:px-4 mt-6 flex-1 w-full space-y-8">
        <!-- Live Matches Section -->
        <div>
            <div class="flex items-center justify-between border-b-2 border-red-600 pb-2 mb-4">
                <h2 class="text-sm sm:text-base font-black uppercase tracking-wider text-slate-900 flex items-center gap-2">
                    <span class="w-2.5 h-2.5 rounded-full bg-red-500 animate-ping"></span>
                    Live Matches ({len(live_list)})
                </h2>
            </div>
            {live_html}
        </div>

        <!-- Recent Completed Matches -->
        <div>
            <div class="flex items-center justify-between border-b-2 border-[#186047] pb-2 mb-4">
                <h2 class="text-sm sm:text-base font-black uppercase tracking-wider text-slate-900">
                    Recent Matches & Results ({len(recent_list)})
                </h2>
            </div>
            {recent_html}
        </div>

        <!-- Upcoming Schedule Matches -->
        <div>
            <div class="flex items-center justify-between border-b-2 border-slate-400 pb-2 mb-4">
                <h2 class="text-sm sm:text-base font-black uppercase tracking-wider text-slate-900">
                    Upcoming Fixtures ({len(upcoming_list)})
                </h2>
            </div>
            {upcoming_html}
        </div>
    </main>

    {footer_html}
</body>
</html>"""

    # -------------------------------------------------------------------------
    # 2. SCHEDULE & FIXTURES PAGE (Cricinfo 2-Column Standard)
    # -------------------------------------------------------------------------
    @classmethod
    def render_schedule_page(cls, schedule_data: List[Dict[str, Any]], matches_data: Dict[str, Any], series_data: Dict[str, Any]) -> str:
        header_html = cls.render_global_header("schedule", matches_data, series_data)
        footer_html = cls.render_global_footer()

        # Build dynamic series rows from CREX ingested schedule & series
        all_series = series_data.get("all", [])
        if not all_series:
            # Fallback to schedule_data
            all_series = [{"title": s.get("series_name", "Tournament"), "category": s.get("category", "international").lower(), "dates": s.get("dates", "2026 Season"), "unique_series_id": s.get("unique_series_id", "S-2026")} for s in schedule_data]

        def render_fixtures_rows(cat_filter: str) -> str:
            rows = ""
            for s in all_series:
                c = s.get("category", "international").lower()
                if cat_filter != "all" and c != cat_filter:
                    continue

                title = s.get("title", "Cricket Series")
                sid = s.get("unique_series_id", s.get("series_key", "S-2026"))

                # Format classification (T20 / ODI / TEST)
                low_title = title.lower()
                if any(w in low_title for w in ["odi", "one day", "world cup", "champions trophy"]):
                    fmt = "ODI"
                    fmt_color = "bg-blue-50 text-blue-800 border-blue-200"
                elif any(w in low_title for w in ["test", "shield", "ranji", "championship"]):
                    fmt = "TEST"
                    fmt_color = "bg-rose-50 text-rose-800 border-rose-200"
                elif "t10" in low_title:
                    fmt = "T10"
                    fmt_color = "bg-amber-50 text-amber-800 border-amber-200"
                else:
                    fmt = "T20"
                    fmt_color = "bg-purple-50 text-purple-800 border-purple-200"

                cat_color = "bg-emerald-50 text-emerald-800 border-emerald-200" if c == "league" else ("bg-amber-50 text-amber-800 border-amber-200" if c == "women" else "bg-slate-100 text-slate-700 border-slate-200")

                rows += f"""
                <div class="py-3.5 px-4 sm:px-6 border-b border-slate-100 hover:bg-slate-50 transition flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div class="flex items-start sm:items-center gap-3 min-w-0">
                        <!-- Clean Format Badge Pill (NO overlapping circle avatars) -->
                        <div class="shrink-0 flex items-center justify-center w-11 h-9 rounded-lg {fmt_color} border text-center font-black">
                            <span class="text-3xs uppercase tracking-wider">{fmt}</span>
                        </div>
                        <div class="min-w-0">
                            <div class="flex items-center gap-2">
                                <span class="font-mono text-3xs font-black text-slate-700 bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200">
                                    {html_escape.escape(sid)}
                                </span>
                                <span class="text-3xs uppercase font-extrabold px-1.5 py-0.5 rounded border {cat_color}">{html_escape.escape(c)}</span>
                            </div>
                            <h3 class="text-xs sm:text-sm font-bold text-slate-900 truncate hover:text-emerald-800 transition cursor-pointer mt-0.5">
                                <a href="/series/{sid}">{html_escape.escape(title)}</a>
                            </h3>
                            <div class="text-3xs text-slate-500 mt-0.5 flex items-center gap-2">
                                <span>{html_escape.escape(s.get('dates', '2026 Season'))}</span>
                                <span class="text-slate-300">&bull;</span>
                                <span class="text-slate-400 font-medium">Global Tour</span>
                            </div>
                        </div>
                    </div>
                    <div class="flex items-center gap-2 shrink-0 self-end sm:self-center">
                        <a href="/series/{sid}" class="px-3 py-1.5 text-2xs font-bold text-slate-700 hover:text-emerald-800 hover:bg-emerald-50 rounded-lg border border-slate-200 transition">
                            Fixtures & Results
                        </a>
                        <a href="/teams" class="px-3 py-1.5 text-2xs font-bold text-slate-700 hover:text-emerald-800 hover:bg-emerald-50 rounded-lg border border-slate-200 transition">
                            Squads
                        </a>
                    </div>
                </div>
                """
            return rows

        current_rows = render_fixtures_rows("all")
        intl_rows = render_fixtures_rows("international")
        league_rows = render_fixtures_rows("league")
        women_rows = render_fixtures_rows("women")

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cricket Fixtures - Domestic & International Cricket Series | Match Center</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>body {{ font-family: 'Inter', sans-serif; background-color: #f8fafc; }}</style>
</head>
<body class="text-slate-800 min-h-screen flex flex-col justify-between">
    {header_html}

    <main class="max-w-6xl mx-auto px-3 sm:px-4 mt-4 sm:mt-6 flex-1 w-full">
        <!-- Breadcrumbs -->
        <nav class="text-3xs text-slate-500 font-medium mb-3 flex items-center gap-1.5">
            <a href="/" class="hover:text-emerald-700">Home</a>
            <span>&rsaquo;</span>
            <span class="text-slate-800 font-semibold">Series Fixtures</span>
        </nav>

        <div class="mb-5">
            <h1 class="text-xl sm:text-2xl font-black tracking-tight text-slate-900">
                Cricket Fixtures - Domestic & International Cricket Series
            </h1>
            <p class="text-xs text-slate-500 mt-0.5">Complete global tour dates, tournament schedules, and venues</p>
        </div>

        <!-- 2-COLUMN CRICINFO FIXTURES LAYOUT -->
        <div class="grid grid-cols-1 lg:grid-cols-12 gap-5 sm:gap-6 items-start">
            
            <!-- LEFT SIDEBAR: FILTERS -->
            <div class="lg:col-span-3 space-y-5">
                <div class="bg-white rounded-xl border border-slate-200 shadow-2xs overflow-hidden">
                    <div class="px-4 py-3 bg-slate-50 border-b border-slate-200 font-bold text-xs uppercase tracking-wider text-slate-700">
                        Category Filter
                    </div>
                    <div class="p-2 space-y-1">
                        <button onclick="switchFixturesTab('all')" id="btn-fix-all" class="w-full text-left px-3 py-2 rounded-lg text-xs font-bold bg-[#186047] text-white shadow-2xs transition">
                            All Cricket Series ({len(all_series)})
                        </button>
                        <button onclick="switchFixturesTab('intl')" id="btn-fix-intl" class="w-full text-left px-3 py-2 rounded-lg text-xs font-semibold text-slate-700 hover:bg-slate-100 transition">
                            International Tours
                        </button>
                        <button onclick="switchFixturesTab('league')" id="btn-fix-league" class="w-full text-left px-3 py-2 rounded-lg text-xs font-semibold text-slate-700 hover:bg-slate-100 transition">
                            Premier T20 Leagues
                        </button>
                        <button onclick="switchFixturesTab('women')" id="btn-fix-women" class="w-full text-left px-3 py-2 rounded-lg text-xs font-semibold text-slate-700 hover:bg-slate-100 transition">
                            Women's Cricket
                        </button>
                    </div>
                </div>

                <div class="bg-white rounded-xl border border-slate-200 shadow-2xs overflow-hidden">
                    <div class="px-4 py-3 bg-slate-50 border-b border-slate-200 font-bold text-3xs uppercase tracking-wider text-slate-600">
                        Download Schedule
                    </div>
                    <div class="p-4 space-y-3 text-xs">
                        <a href="#" class="block text-emerald-800 hover:text-emerald-950 font-medium hover:underline flex items-center justify-between">
                            <span>Download ICC's Future tours programme (Men)</span>
                            <span>&rsaquo;</span>
                        </a>
                        <div class="border-t border-slate-100"></div>
                        <a href="#" class="block text-emerald-800 hover:text-emerald-950 font-medium hover:underline flex items-center justify-between">
                            <span>Download ICC's Future tours programme (Women)</span>
                            <span>&rsaquo;</span>
                        </a>
                    </div>
                </div>
            </div>

            <!-- RIGHT COLUMN: FIXTURES LISTINGS -->
            <div class="lg:col-span-9 bg-white rounded-xl border border-slate-200 shadow-2xs overflow-hidden">
                <div class="px-4 sm:px-6 py-3 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
                    <h2 class="font-bold text-xs sm:text-sm uppercase tracking-wider text-slate-800" id="fixtures-column-title">
                        International Tours & Domestic Series
                    </h2>
                    <span class="text-3xs font-semibold text-emerald-700 bg-emerald-50 px-2.5 py-0.5 rounded-full border border-emerald-200">
                        2026 Season
                    </span>
                </div>

                <div id="panel-fix-all" class="divide-y divide-slate-100">
                    {current_rows}
                </div>

                <div id="panel-fix-intl" class="divide-y divide-slate-100 hidden">
                    {intl_rows}
                </div>

                <div id="panel-fix-league" class="divide-y divide-slate-100 hidden">
                    {league_rows}
                </div>

                <div id="panel-fix-women" class="divide-y divide-slate-100 hidden">
                    {women_rows}
                </div>
            </div>
        </div>
    </main>

    {footer_html}

    <script>
        function switchFixturesTab(tab) {{
            const tabs = ['all', 'intl', 'league', 'women'];
            tabs.forEach(t => {{
                const btn = document.getElementById('btn-fix-' + t);
                const panel = document.getElementById('panel-fix-' + t);
                if (btn && panel) {{
                    if (t === tab) {{
                        btn.className = 'w-full text-left px-3 py-2 rounded-lg text-xs font-bold bg-[#186047] text-white shadow-2xs transition';
                        panel.classList.remove('hidden');
                    }} else {{
                        btn.className = 'w-full text-left px-3 py-2 rounded-lg text-xs font-semibold text-slate-700 hover:bg-slate-100 transition';
                        panel.classList.add('hidden');
                    }}
                }}
            }});
        }}
    </script>
</body>
</html>"""

    # -------------------------------------------------------------------------
    # 3. SERIES DIRECTORY PAGE
    # -------------------------------------------------------------------------
    @classmethod
    def render_series_page(cls, series_data: Dict[str, Any], matches_data: Dict[str, Any]) -> str:
        header_html = cls.render_global_header("series", matches_data, series_data)
        footer_html = cls.render_global_footer()

        series_list = series_data.get("all", series_data.get("current", []))

        def render_cards(items: List[Dict[str, Any]]) -> str:
            if not items:
                return '<div class="py-8 text-center text-slate-400 text-xs font-medium">No series in this category.</div>'
            html = '<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">'
            for s in items:
                sid = s.get("unique_series_id", s.get("series_key", "S-2026"))
                html += f"""
                <div class="bg-white rounded-xl border border-slate-200 shadow-2xs p-4 hover:shadow-md transition flex flex-col justify-between">
                    <div>
                        <div class="flex items-center justify-between text-3xs font-semibold text-slate-400 mb-1.5">
                            <span class="font-mono font-black text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">{html_escape.escape(sid)}</span>
                            <span class="uppercase">{html_escape.escape(s.get('category', 'international'))}</span>
                        </div>
                        <h3 class="text-sm font-black text-slate-900 hover:text-emerald-800 transition">
                            <a href="/series/{sid}">{html_escape.escape(s.get('title', ''))}</a>
                        </h3>
                        <p class="text-3xs text-slate-500 mt-1">{html_escape.escape(s.get('dates', '2026 Season'))}</p>
                    </div>
                    <div class="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between">
                        <a href="/schedule" class="text-3xs font-bold text-emerald-800 hover:underline">
                            View Full Schedule &raquo;
                        </a>
                    </div>
                </div>
                """
            html += '</div>'
            return html

        all_html = render_cards(series_list)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cricket Series Directory | All Tournaments Worldwide</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>body {{ font-family: 'Inter', sans-serif; background-color: #f1f5f9; }}</style>
</head>
<body class="text-slate-800 min-h-screen flex flex-col justify-between">
    {header_html}

    <main class="max-w-6xl mx-auto px-3 sm:px-4 mt-6 flex-1 w-full space-y-6">
        <div>
            <h1 class="text-2xl font-black text-slate-900 uppercase tracking-tight">Cricket Series Directory</h1>
            <p class="text-xs text-slate-500 mt-1">All current, upcoming, international, and franchise cricket tournaments ({len(series_list)} Active)</p>
        </div>
        {all_html}
    </main>

    {footer_html}
</body>
</html>"""

    # -------------------------------------------------------------------------
    # 4. TEAMS DIRECTORY PAGE
    # -------------------------------------------------------------------------
    @classmethod
    def render_teams_page(cls, teams_data: Dict[str, Any], matches_data: Dict[str, Any], series_data: Dict[str, Any]) -> str:
        header_html = cls.render_global_header("teams", matches_data, series_data)
        footer_html = cls.render_global_footer()

        def render_team_chips(items: List[Dict[str, Any]]) -> str:
            chips = ""
            for t in items:
                chips += f"""
                <div class="p-3 bg-white rounded-xl border border-slate-200 shadow-2xs hover:shadow-md transition flex items-center justify-between">
                    <div class="flex items-center gap-2.5">
                        <div class="w-8 h-8 rounded-full bg-emerald-800 text-white flex items-center justify-center font-black text-xs">
                            {html_escape.escape(t.get('code', t.get('name', 'T'))[:3])}
                        </div>
                        <span class="text-xs font-bold text-slate-800">{html_escape.escape(t.get('name', ''))}</span>
                    </div>
                    <span class="text-3xs font-mono font-bold text-slate-400 uppercase">{html_escape.escape(t.get('code', ''))}</span>
                </div>
                """
            return f'<div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">{chips}</div>'

        men_html = render_team_chips(teams_data.get("international_men", []))
        women_html = render_team_chips(teams_data.get("international_women", []))
        league_html = render_team_chips(teams_data.get("leagues", []))

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cricket Teams Directory | International & League Clubs</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>body {{ font-family: 'Inter', sans-serif; background-color: #f1f5f9; }}</style>
</head>
<body class="text-slate-800 min-h-screen flex flex-col justify-between">
    {header_html}

    <main class="max-w-6xl mx-auto px-3 sm:px-4 mt-6 flex-1 w-full space-y-8">
        <div>
            <h1 class="text-2xl font-black tracking-tight text-slate-900 uppercase">Cricket Teams Directory</h1>
            <p class="text-xs text-slate-500 mt-1">Official national squads, women's teams, and world franchise clubs</p>
        </div>

        <div>
            <h2 class="text-sm font-black uppercase tracking-wider text-slate-800 border-b-2 border-[#186047] pb-1.5 mb-3.5">International Men</h2>
            {men_html}
        </div>
        <div>
            <h2 class="text-sm font-black uppercase tracking-wider text-slate-800 border-b-2 border-[#186047] pb-1.5 mb-3.5">International Women</h2>
            {women_html}
        </div>
        <div>
            <h2 class="text-sm font-black uppercase tracking-wider text-slate-800 border-b-2 border-[#186047] pb-1.5 mb-3.5">Premier T20 Leagues & Clubs</h2>
            {league_html}
        </div>
    </main>

    {footer_html}
</body>
</html>"""

    # -------------------------------------------------------------------------
    # 5. RANKINGS PAGE
    # -------------------------------------------------------------------------
    @classmethod
    def render_rankings_page(cls, rankings_data: Dict[str, Any], matches_data: Dict[str, Any], series_data: Dict[str, Any]) -> str:
        header_html = cls.render_global_header("rankings", matches_data, series_data)
        footer_html = cls.render_global_footer()

        def render_team_rank_table(items: List[Dict[str, Any]]) -> str:
            rows = ""
            for it in items:
                rows += f"""
                <tr class="hover:bg-slate-50 transition border-b border-slate-100 last:border-0">
                    <td class="py-2.5 px-3 font-black text-slate-800 text-center w-12">{it.get('rank')}</td>
                    <td class="py-2.5 px-3 font-bold text-slate-900">{html_escape.escape(it.get('team', ''))}</td>
                    <td class="py-2.5 px-3 text-right font-black text-emerald-800">{it.get('rating')}</td>
                    <td class="py-2.5 px-3 text-right text-slate-600 font-medium">{it.get('points')}</td>
                </tr>
                """
            return f"""
            <div class="overflow-x-auto bg-white rounded-xl border border-slate-200 shadow-2xs">
                <table class="w-full text-left text-xs sm:text-sm">
                    <thead class="bg-slate-100 text-slate-600 uppercase font-semibold text-3xs tracking-wider border-b border-slate-200">
                        <tr>
                            <th class="py-2 px-3 text-center">Pos</th>
                            <th class="py-2 px-3">Team</th>
                            <th class="py-2 px-3 text-right">Rating</th>
                            <th class="py-2 px-3 text-right">Points</th>
                        </tr>
                    </thead>
                    <tbody>{rows}</tbody>
                </table>
            </div>
            """

        test_teams = render_team_rank_table(rankings_data.get("teams", {}).get("test", []))
        odi_teams = render_team_rank_table(rankings_data.get("teams", {}).get("odi", []))
        t20i_teams = render_team_rank_table(rankings_data.get("teams", {}).get("t20i", []))

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ICC Cricket Rankings | Official Men's & Women's Standings</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>body {{ font-family: 'Inter', sans-serif; background-color: #f1f5f9; }}</style>
</head>
<body class="text-slate-800 min-h-screen flex flex-col justify-between">
    {header_html}

    <main class="max-w-6xl mx-auto px-3 sm:px-4 mt-6 flex-1 w-full space-y-6">
        <div>
            <h1 class="text-2xl font-black tracking-tight text-slate-900 uppercase">ICC Team Rankings</h1>
            <p class="text-xs text-slate-500 mt-1">Official International Cricket Council rankings across Test, ODI, and T20I formats</p>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div>
                <div class="bg-[#186047] text-white px-4 py-2 rounded-t-xl font-extrabold text-xs uppercase tracking-wider">
                    ICC Men's Test Rankings
                </div>
                {test_teams}
            </div>
            <div>
                <div class="bg-[#186047] text-white px-4 py-2 rounded-t-xl font-extrabold text-xs uppercase tracking-wider">
                    ICC Men's ODI Rankings
                </div>
                {odi_teams}
            </div>
            <div>
                <div class="bg-[#186047] text-white px-4 py-2 rounded-t-xl font-extrabold text-xs uppercase tracking-wider">
                    ICC Men's T20I Rankings
                </div>
                {t20i_teams}
            </div>
        </div>
    </main>

    {footer_html}
</body>
</html>"""

    # -------------------------------------------------------------------------
    # 6. NEWS PAGE & INTERNAL ARTICLE READER (INDEPENDENT ATTRIBUTION)
    # -------------------------------------------------------------------------
    @classmethod
    def render_news_page(cls, news_data: List[Dict[str, Any]], matches_data: Dict[str, Any], series_data: Dict[str, Any]) -> str:
        header_html = cls.render_global_header("news", matches_data, series_data)
        footer_html = cls.render_global_footer()

        cards = ""
        for n in news_data:
            nid = str(n.get("news_id", "1"))
            img_html = ""
            if n.get("image"):
                img_html = f"""
                <div class="relative h-48 w-full bg-slate-200 overflow-hidden shrink-0">
                    <img src="{n['image']}" alt="{html_escape.escape(n.get('title', 'News'))}" class="w-full h-full object-cover hover:scale-105 transition duration-300" loading="lazy" onerror="this.parentElement.style.display='none'">
                    <span class="absolute bottom-2 left-2 px-2 py-0.5 rounded bg-black/70 backdrop-blur-xs text-white text-3xs font-extrabold tracking-wider uppercase">
                        CRIC CENTER
                    </span>
                </div>
                """

            cards += f"""
            <article class="bg-white rounded-xl border border-slate-200 shadow-2xs hover:shadow-md transition flex flex-col justify-between overflow-hidden">
                {img_html}
                <div class="p-4 sm:p-5 flex-1 flex flex-col justify-between">
                    <div>
                        <div class="flex items-center justify-between text-3xs text-slate-500 font-semibold mb-1.5">
                            <span class="text-emerald-700 font-bold uppercase tracking-wider">Tournament Report</span>
                            <span>{html_escape.escape(n.get('time', 'Recent'))}</span>
                        </div>
                        <h2 class="text-sm sm:text-base font-black text-slate-900 leading-snug hover:text-emerald-800 transition">
                            <a href="/news/{nid}">{html_escape.escape(n.get('title', ''))}</a>
                        </h2>
                        <p class="text-xs text-slate-600 mt-2 leading-relaxed line-clamp-3">
                            {html_escape.escape(n.get('intro', ''))}
                        </p>
                    </div>
                    <div class="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between">
                        <span class="text-3xs font-semibold text-slate-400">Match Insights</span>
                        <a href="/news/{nid}" class="text-xs font-bold text-emerald-700 hover:text-emerald-950 flex items-center gap-1">
                            Read Full Story &raquo;
                        </a>
                    </div>
                </div>
            </article>
            """

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cricket News | Match Reports, Press Conferences & Player Updates</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>body {{ font-family: 'Inter', sans-serif; background-color: #f1f5f9; }}</style>
</head>
<body class="text-slate-800 min-h-screen flex flex-col justify-between">
    {header_html}

    <main class="max-w-6xl mx-auto px-3 sm:px-4 mt-6 flex-1 w-full">
        <div class="mb-6">
            <h1 class="text-2xl font-black tracking-tight text-slate-900 uppercase">Latest Cricket News</h1>
            <p class="text-xs text-slate-500 mt-1">Live match reports, tournament analysis, and breaking stories</p>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-6">
            {cards}
        </div>
    </main>

    {footer_html}
</body>
</html>"""

    # -------------------------------------------------------------------------
    # 7. INTERNAL NEWS DETAIL ARTICLE READER
    # -------------------------------------------------------------------------
    @classmethod
    def render_news_detail_page(cls, article: Dict[str, Any], matches_data: Dict[str, Any], series_data: Dict[str, Any]) -> str:
        header_html = cls.render_global_header("news", matches_data, series_data)
        footer_html = cls.render_global_footer()

        img_tag = f'<div class="rounded-2xl overflow-hidden mb-6 shadow-sm border border-slate-200"><img src="{article.get("image")}" class="w-full max-h-[480px] object-cover" alt="Article Image"></div>' if article.get("image") else ''

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html_escape.escape(article.get('title', 'Article'))} | Cricket Center</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>body {{ font-family: 'Inter', sans-serif; background-color: #f8fafc; }}</style>
</head>
<body class="text-slate-800 min-h-screen flex flex-col justify-between">
    {header_html}

    <main class="max-w-4xl mx-auto px-4 py-8 flex-1 w-full">
        <nav class="text-3xs text-slate-500 font-medium mb-4 flex items-center gap-1.5">
            <a href="/" class="hover:text-emerald-700">Home</a>
            <span>&rsaquo;</span>
            <a href="/news" class="hover:text-emerald-700">News</a>
            <span>&rsaquo;</span>
            <span class="text-slate-800 font-semibold truncate">Article</span>
        </nav>

        <article class="bg-white rounded-2xl border border-slate-200 p-6 sm:p-10 shadow-2xs">
            <div class="flex items-center gap-2 text-3xs font-black uppercase text-emerald-800 tracking-wider mb-2">
                <span>CRICKET CENTER EXCLUSIVE</span>
                <span>&bull;</span>
                <span class="text-slate-500">{html_escape.escape(article.get('time', 'Recently'))}</span>
            </div>

            <h1 class="text-2xl sm:text-3xl font-black text-slate-900 tracking-tight leading-tight mb-4">
                {html_escape.escape(article.get('title', ''))}
            </h1>

            {img_tag}

            <div class="prose prose-slate max-w-none text-sm leading-relaxed space-y-4 text-slate-700 font-normal">
                <p class="text-base font-semibold text-slate-900 leading-snug">
                    {html_escape.escape(article.get('intro', ''))}
                </p>
                <p>
                    Full match analysis and tactical debrief from our on-ground correspondents covering all the momentum shifts, critical impact overs, and bowler dot-ball figures throughout the tournament.
                </p>
                <p>
                    Stay tuned for post-match reactions, updated points tables, and upcoming fixtures across all international and domestic leagues.
                </p>
            </div>

            <div class="mt-8 pt-6 border-t border-slate-100 flex items-center justify-between">
                <a href="/news" class="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-bold transition">
                    &larr; Back to News
                </a>
                <a href="/live-scores" class="px-4 py-2 bg-[#186047] hover:bg-[#0d3b2c] text-white rounded-lg text-xs font-bold transition shadow-xs">
                    View Live Scores &raquo;
                </a>
            </div>
        </article>
    </main>

    {footer_html}
</body>
</html>"""

    @classmethod
    def render_match_hub_page(cls, match_info: Dict[str, Any], matches_data: Dict[str, Any] = None, series_data: Dict[str, Any] = None) -> str:
        matches_data = matches_data or {}
        series_data = series_data or {}
        header_html = cls.render_global_header("live-scores", matches_data, series_data)
        footer_html = cls.render_global_footer()

        m_id = str(match_info.get("match_id", "")).strip()
        title = match_info.get("title", f"Match #{m_id}")
        series_name = match_info.get("series", "Cricket Tournament")
        stage = match_info.get("stage", "Match")
        venue = match_info.get("venue", "International Stadium")
        cat = match_info.get("category", "international").upper()
        status_text = match_info.get("situation") or match_info.get("status") or "Match in Progress"
        is_live = match_info.get("is_live", False)
        is_done = match_info.get("is_completed", False)

        t1 = match_info.get("team_1", "")
        t2 = match_info.get("team_2", "")
        if not t1 and "title" in match_info:
            parts = re.split(r'\s+(?:vs|v)\s+', match_info.get("title", ""), flags=re.I)
            if len(parts) >= 2:
                t1, t2 = parts[0].strip(), parts[1].strip()
            else:
                t1, t2 = match_info.get("title", "Team 1"), "Team 2"

        t1_code = match_info.get("team_1_code") or ("".join([w[0] for w in t1.split()[:3]]).upper() if t1 else "T1")[:4]
        t2_code = match_info.get("team_2_code") or ("".join([w[0] for w in t2.split()[:3]]).upper() if t2 else "T2")[:4]

        s1 = match_info.get("team_1_score", "") or ("Yet to bat" if is_live else "")
        s2 = match_info.get("team_2_score", "") or ("Yet to bat" if is_live else "")

        if is_live:
            status_badge = '<span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-black bg-red-600 text-white shadow-xs uppercase tracking-wider"><span class="w-2 h-2 rounded-full bg-white animate-ping"></span>LIVE</span>'
            status_style = "text-amber-900 bg-amber-50 border-amber-200"
        elif is_done:
            status_badge = '<span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-black bg-emerald-700 text-white uppercase tracking-wider">RESULT</span>'
            status_style = "text-emerald-900 bg-emerald-50 border-emerald-200"
        else:
            status_badge = '<span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-slate-700 text-slate-200 uppercase tracking-wider">UPCOMING</span>'
            status_style = "text-slate-800 bg-slate-100 border-slate-200"

        sid_slug = re.sub(r'[^a-zA-Z0-9]+', '-', series_name).strip('-').lower()

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html_escape.escape(title)} | Match Center | CricCenter</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>body {{ font-family: 'Inter', sans-serif; background-color: #f8fafc; }}</style>
</head>
<body class="text-slate-800 min-h-screen flex flex-col justify-between">
    {header_html}

    <main class="max-w-5xl mx-auto px-3 sm:px-4 py-6 flex-1 w-full space-y-6">
        <!-- Breadcrumbs -->
        <nav class="text-3xs text-slate-500 font-medium flex items-center gap-1.5">
            <a href="/" class="hover:text-emerald-700 font-bold">Home</a>
            <span>&rsaquo;</span>
            <a href="/series/{sid_slug}" class="hover:text-emerald-700 font-bold">{html_escape.escape(series_name)}</a>
            <span>&rsaquo;</span>
            <span class="text-slate-800 font-extrabold truncate">{html_escape.escape(title)}</span>
        </nav>

        <!-- HERO MATCH CENTER CARD -->
        <div class="bg-white rounded-2xl border border-slate-200 shadow-xs overflow-hidden">
            <!-- Top Strip -->
            <div class="bg-slate-900 text-white px-4 sm:px-6 py-3 flex flex-wrap items-center justify-between gap-2 border-b border-slate-800">
                <div class="flex items-center gap-2 text-xs font-bold min-w-0">
                    {status_badge}
                    <a href="/series/{sid_slug}" class="text-emerald-400 hover:underline truncate uppercase tracking-wider text-2xs">{html_escape.escape(series_name)}</a>
                    <span class="text-slate-500">&bull;</span>
                    <span class="text-slate-300 text-2xs font-semibold">{html_escape.escape(stage)}</span>
                </div>
                <div class="flex items-center gap-2 text-3xs font-mono text-slate-400">
                    <span class="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 font-bold uppercase">{html_escape.escape(cat)}</span>
                    <span>ID: {html_escape.escape(m_id)}</span>
                </div>
            </div>

            <!-- Main Scoreboard Hero -->
            <div class="p-5 sm:p-8">
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-6 items-center">
                    <!-- Team 1 -->
                    <div class="flex items-center justify-between sm:justify-start gap-4 p-4 rounded-xl bg-slate-50 border border-slate-100">
                        <div class="flex items-center gap-3 min-w-0">
                            <span class="w-12 h-12 rounded-xl bg-slate-800 text-white flex items-center justify-center text-sm font-black shrink-0 shadow-xs">
                                {html_escape.escape(t1_code)}
                            </span>
                            <div class="min-w-0">
                                <h2 class="text-sm sm:text-base font-extrabold text-slate-900 truncate">{html_escape.escape(t1)}</h2>
                                <span class="text-3xs text-slate-500 font-semibold uppercase">Innings</span>
                            </div>
                        </div>
                        <div class="text-right sm:ml-auto">
                            <div class="text-lg sm:text-xl font-black text-slate-900">{html_escape.escape(s1)}</div>
                        </div>
                    </div>

                    <!-- Team 2 -->
                    <div class="flex items-center justify-between sm:justify-start gap-4 p-4 rounded-xl bg-slate-50 border border-slate-100">
                        <div class="flex items-center gap-3 min-w-0">
                            <span class="w-12 h-12 rounded-xl bg-slate-700 text-white flex items-center justify-center text-sm font-black shrink-0 shadow-xs">
                                {html_escape.escape(t2_code)}
                            </span>
                            <div class="min-w-0">
                                <h2 class="text-sm sm:text-base font-extrabold text-slate-900 truncate">{html_escape.escape(t2)}</h2>
                                <span class="text-3xs text-slate-500 font-semibold uppercase">Innings</span>
                            </div>
                        </div>
                        <div class="text-right sm:ml-auto">
                            <div class="text-lg sm:text-xl font-black text-slate-900">{html_escape.escape(s2)}</div>
                        </div>
                    </div>
                </div>

                <!-- Match Situation Banner -->
                <div class="mt-6 p-3.5 rounded-xl border {status_style} flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div class="flex items-center gap-2">
                        <span class="w-2 h-2 rounded-full bg-amber-500 shrink-0"></span>
                        <span class="text-xs sm:text-sm font-black tracking-tight">{html_escape.escape(status_text)}</span>
                    </div>
                    <div class="text-3xs font-semibold text-slate-600 flex items-center gap-1.5">
                        <span>Venue:</span>
                        <span class="font-bold text-slate-800">{html_escape.escape(venue)}</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- DETAILS & ACTIONS SECTION -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <!-- Left 2 Cols: Match Information & Live Tracking -->
            <div class="lg:col-span-2 space-y-6">
                <!-- Match Information Card -->
                <div class="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs">
                    <h3 class="text-sm font-black uppercase tracking-wider text-slate-900 mb-4 pb-2 border-b border-slate-100 flex items-center gap-2">
                        <span class="w-2 h-2 rounded-full bg-emerald-600"></span>
                        Match Information
                    </h3>
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
                        <div class="p-3 bg-slate-50 rounded-xl border border-slate-100">
                            <span class="text-3xs text-slate-400 font-bold uppercase block mb-0.5">Series</span>
                            <span class="font-bold text-slate-800">{html_escape.escape(series_name)}</span>
                        </div>
                        <div class="p-3 bg-slate-50 rounded-xl border border-slate-100">
                            <span class="text-3xs text-slate-400 font-bold uppercase block mb-0.5">Match Stage</span>
                            <span class="font-bold text-slate-800">{html_escape.escape(stage)}</span>
                        </div>
                        <div class="p-3 bg-slate-50 rounded-xl border border-slate-100">
                            <span class="text-3xs text-slate-400 font-bold uppercase block mb-0.5">Venue</span>
                            <span class="font-bold text-slate-800">{html_escape.escape(venue)}</span>
                        </div>
                        <div class="p-3 bg-slate-50 rounded-xl border border-slate-100">
                            <span class="text-3xs text-slate-400 font-bold uppercase block mb-0.5">Category</span>
                            <span class="font-bold text-slate-800 uppercase">{html_escape.escape(cat)}</span>
                        </div>
                    </div>
                </div>

                <!-- Live Stream & Scorecard Stream Card -->
                <div class="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs">
                    <h3 class="text-sm font-black uppercase tracking-wider text-slate-900 mb-4 pb-2 border-b border-slate-100 flex items-center gap-2">
                        <span class="w-2 h-2 rounded-full bg-red-600 animate-pulse"></span>
                        Live Ball Feed & Status
                    </h3>
                    <div id="liveStreamStatus" class="p-4 bg-emerald-50 rounded-xl border border-emerald-100 text-xs text-emerald-950 flex items-center justify-between gap-3">
                        <div>
                            <p class="font-extrabold mb-0.5">Real-Time Data Feed Active</p>
                            <p class="text-3xs text-emerald-800">Tracking live score updates, boundary momentum, and ball-by-ball developments.</p>
                        </div>
                        <span class="shrink-0 px-2.5 py-1 rounded bg-emerald-600 text-white font-black text-3xs uppercase tracking-wider">Connected</span>
                    </div>
                </div>
            </div>

            <!-- Right 1 Col: Quick Actions & Navigation -->
            <div class="space-y-6">
                <!-- Navigation Card -->
                <div class="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs">
                    <h3 class="text-xs font-black uppercase tracking-wider text-slate-900 mb-4 pb-2 border-b border-slate-100">
                        Quick Navigation
                    </h3>
                    <div class="space-y-2">
                        <a href="/live-scores" class="w-full flex items-center justify-between p-3 rounded-xl bg-slate-50 hover:bg-emerald-50 text-slate-700 hover:text-emerald-900 border border-slate-100 transition font-bold text-xs">
                            <span>&larr; All Live Scores</span>
                            <span>&rsaquo;</span>
                        </a>
                        <a href="/schedule" class="w-full flex items-center justify-between p-3 rounded-xl bg-slate-50 hover:bg-emerald-50 text-slate-700 hover:text-emerald-900 border border-slate-100 transition font-bold text-xs">
                            <span>Full Match Schedule</span>
                            <span>&rsaquo;</span>
                        </a>
                        <a href="/series" class="w-full flex items-center justify-between p-3 rounded-xl bg-slate-50 hover:bg-emerald-50 text-slate-700 hover:text-emerald-900 border border-slate-100 transition font-bold text-xs">
                            <span>Browse All Series</span>
                            <span>&rsaquo;</span>
                        </a>
                    </div>
                </div>

                <!-- Admin Mapping Helper -->
                <div class="bg-gradient-to-br from-slate-900 to-[#186047] text-white rounded-2xl p-6 shadow-md">
                    <div class="text-xs font-black uppercase tracking-wider text-emerald-300 mb-1">CricCenter Admin</div>
                    <h4 class="text-sm font-bold mb-2">Deep Scorecard Mapping</h4>
                    <p class="text-3xs text-slate-300 leading-relaxed mb-4">
                        Connect this match to an official CREX or Cricinfo URL for full ball-by-ball commentary and partnership wagon wheels.
                    </p>
                    <a href="/admin" class="inline-block w-full text-center py-2.5 px-4 bg-amber-400 hover:bg-amber-300 text-slate-900 font-extrabold text-xs rounded-xl shadow-xs transition">
                        Open Admin Panel &rarr;
                    </a>
                </div>
            </div>
        </div>
    </main>

    {footer_html}

    <script>
        // Auto refresh match state every 15 seconds
        setInterval(async () => {{
            try {{
                const res = await fetch('/api/matches');
                if (res.ok) {{
                    const data = await res.json();
                    const allMatches = [...(data.live || []), ...(data.recent || []), ...(data.upcoming || [])];
                    const currentMatch = allMatches.find(m => String(m.match_id) === '{m_id}');
                    if (currentMatch) {{
                        console.log('[*] Live match sync:', currentMatch.status);
                    }}
                }}
            }} catch(e) {{}}
        }}, 15000);
    </script>
</body>
</html>"""

