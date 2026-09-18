import os
import json
import html as html_escape
from typing import Dict, Any, List

class AdminPanel:
    """
    Renders the Hermes Brain Master Event Mapping Console:
    - Lists all events and series ingested from CREX.
    - Unique Match IDs (M-<CAT>-<KEY>) and Unique Series IDs (S-<CAT>-<KEY>).
    - Inline 1-click URL mapping for any match to Cricinfo, Cricbuzz, or CREX.
    - Autonomous Live Promotion: Shifts matches to Live as soon as ball feeds arrive.
    - Completely isolated from public user site.
    """

    @classmethod
    def render(cls, mappings: Dict[str, Any], matches_data: Dict[str, Any], series_data: Dict[str, Any], catalog_data: Dict[str, Any] = None) -> str:
        if catalog_data is None:
            catalog_file = os.path.join("output", "data", "crex_catalog.json")
            if os.path.exists(catalog_file):
                try:
                    with open(catalog_file, "r", encoding="utf-8") as f:
                        catalog_data = json.load(f)
                except Exception:
                    catalog_data = {"events": [], "series": []}
            else:
                catalog_data = {"events": [], "series": []}

        events = catalog_data.get("events", [])
        total_events_count = len(events)
        mapped_count = len(mappings)
        unmapped_count = max(0, total_events_count - mapped_count)

        # Build Mapped Rows
        mapped_rows = ""
        for mid, m in mappings.items():
            plat = m.get("platform", "Unknown")
            plat_badge = "bg-blue-100 text-blue-800 border-blue-300" if "cricinfo" in plat.lower() else ("bg-emerald-100 text-emerald-800 border-emerald-300" if "cricbuzz" in plat.lower() else "bg-amber-100 text-amber-900 border-amber-300")
            mapped_rows += f"""
            <tr class="hover:bg-slate-50 transition border-b border-slate-100">
                <td class="py-3 px-3 sm:px-4 font-mono font-bold text-slate-800">
                    <span class="px-2 py-0.5 bg-slate-100 text-slate-700 rounded border border-slate-200">{html_escape.escape(mid)}</span>
                </td>
                <td class="py-3 px-3 sm:px-4">
                    <div class="font-bold text-slate-900">{html_escape.escape(m.get('title', f'Match {mid}'))}</div>
                    <div class="text-3xs uppercase text-slate-400 font-semibold">{html_escape.escape(m.get('category', 'international'))}</div>
                </td>
                <td class="py-3 px-3 sm:px-4">
                    <span class="px-2 py-0.5 rounded text-3xs font-extrabold border {plat_badge}">
                        {html_escape.escape(plat)}
                    </span>
                </td>
                <td class="py-3 px-3 sm:px-4 max-w-xs truncate font-mono text-2xs text-slate-600">
                    <a href="{html_escape.escape(m.get('url', ''))}" target="_blank" class="hover:underline text-emerald-700 font-medium">
                        {html_escape.escape(m.get('url', ''))}
                    </a>
                </td>
                <td class="py-3 px-3 sm:px-4 text-right">
                    <div class="flex items-center justify-end gap-2">
                        <a href="/match/{mid}" target="_blank" class="px-3 py-1 bg-emerald-700 hover:bg-emerald-800 text-white rounded text-2xs font-bold transition shadow-2xs">
                            View Center &raquo;
                        </a>
                        <button onclick="unmapMatch('{mid}')" class="px-2.5 py-1 bg-rose-600 hover:bg-rose-700 text-white rounded text-2xs font-bold transition shadow-2xs">
                            Unmap
                        </button>
                    </div>
                </td>
            </tr>
            """

        # Build CREX Events Master Directory Rows
        crex_event_cards = ""
        for ev in events:
            ev_mid = str(ev.get("match_id", ""))
            ev_unique = ev.get("unique_match_id", f"M-{ev_mid}")
            is_mapped = ev_mid in mappings or ev_unique in mappings
            mapped_info = mappings.get(ev_mid) or mappings.get(ev_unique)

            st_color = "text-emerald-700 bg-emerald-50 border-emerald-200" if ev.get("status") == "Live" else ("text-slate-700 bg-slate-100 border-slate-200" if "result" in ev.get("status", "").lower() else "text-blue-700 bg-blue-50 border-blue-200")
            map_status_badge = f'<span class="px-2 py-0.5 rounded text-3xs font-black bg-emerald-100 text-emerald-800 border border-emerald-300">Mapped ({mapped_info.get("platform", "Feed")})</span>' if is_mapped else '<span class="px-2 py-0.5 rounded text-3xs font-bold bg-amber-50 text-amber-800 border border-amber-200">Ready to Map</span>'

            crex_event_cards += f"""
            <div class="event-row bg-white rounded-xl border border-slate-200 shadow-2xs p-4 hover:border-emerald-500/50 transition flex flex-col justify-between"
                 data-title="{html_escape.escape(ev.get('title', '').lower())}"
                 data-series="{html_escape.escape(ev.get('series', '').lower())}"
                 data-mapped="{str(is_mapped).lower()}"
                 data-live="{str(ev.get('is_live', False)).lower()}">
                <div>
                    <div class="flex items-center justify-between gap-2 mb-1.5">
                        <span class="font-mono text-3xs font-black text-emerald-900 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                            {html_escape.escape(ev_unique)}
                        </span>
                        <div class="flex items-center gap-1.5">
                            <span class="text-3xs font-bold px-2 py-0.5 rounded border {st_color}">
                                {html_escape.escape(ev.get('status', 'Scheduled'))}
                            </span>
                            {map_status_badge}
                        </div>
                    </div>

                    <h3 class="text-xs sm:text-sm font-bold text-slate-900 leading-snug">
                        {html_escape.escape(ev.get('title', 'Cricket Match'))}
                    </h3>
                    <div class="text-3xs text-emerald-800 font-bold mt-1.5 truncate">
                        {html_escape.escape(ev.get('series', 'Tournament'))} &bull; <span class="text-slate-600 font-medium">{html_escape.escape(ev.get('stage', 'Match'))}</span>
                    </div>
                    <div class="text-3xs text-slate-400 font-medium mt-1 flex items-center justify-between">
                        <span>Date: <strong class="text-slate-700">{html_escape.escape(ev.get('date_str', 'Today'))}</strong></span>
                        <span class="text-3xs uppercase font-extrabold px-1.5 py-0.2 bg-slate-100 text-slate-600 rounded border border-slate-200">{html_escape.escape(ev.get('category', 'league'))}</span>
                    </div>
                </div>

                <div class="mt-3 pt-3 border-t border-slate-100">
                    {
                    f'''
                    <div class="flex items-center justify-between">
                        <span class="text-3xs text-slate-500 truncate max-w-[200px] font-mono">{html_escape.escape(mapped_info.get("url", ""))}</span>
                        <div class="flex items-center gap-1.5">
                            <a href="/match/{ev_mid}" target="_blank" class="px-2 py-1 bg-emerald-700 hover:bg-emerald-800 text-white rounded text-3xs font-bold transition">View</a>
                            <button onclick="unmapMatch('{ev_mid}')" class="px-2 py-1 bg-rose-600 hover:bg-rose-700 text-white rounded text-3xs font-bold transition">Unmap</button>
                        </div>
                    </div>
                    ''' if is_mapped else f'''
                    <div class="flex items-center gap-2">
                        <input type="url" id="input-{ev_mid}" placeholder="Paste Cricinfo, Cricbuzz, or CREX URL..." class="flex-1 px-2.5 py-1 text-3xs border border-slate-300 rounded font-mono focus:ring-1 focus:ring-emerald-500 focus:outline-hidden">
                        <button onclick="quickMapMatch('{ev_mid}', '{html_escape.escape(ev.get('title', ''))}', '{html_escape.escape(ev.get('category', 'international'))}')" class="px-3 py-1 bg-[#186047] hover:bg-[#0d3b2c] text-white text-3xs font-bold rounded transition whitespace-nowrap shadow-2xs">
                            Map & Track Live &raquo;
                        </button>
                    </div>
                    '''
                    }
                </div>
            </div>
            """

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hermes Brain Admin | Match & Series Master Mapping Console</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>body {{ font-family: 'Inter', sans-serif; background-color: #f1f5f9; }}</style>
</head>
<body class="text-slate-800 min-h-screen flex flex-col justify-between">
    <!-- RESTRICTED ADMIN NAVIGATION (NOT LINKED ON PUBLIC SITE) -->
    <header class="bg-slate-900 text-white shadow-md border-b border-slate-800">
        <div class="max-w-6xl mx-auto px-4 h-12 flex items-center justify-between">
            <div class="flex items-center gap-3">
                <div class="bg-emerald-600 text-white font-black px-2 py-0.5 rounded text-xs tracking-wider uppercase">
                    ADMIN
                </div>
                <span class="text-sm font-black text-white tracking-tight">HERMES BRAIN MATCH MAPPER</span>
            </div>
            <div class="flex items-center gap-3">
                <a href="/" target="_blank" class="text-xs font-semibold text-slate-300 hover:text-white transition">
                    &larr; Open Public Portal
                </a>
                <button onclick="triggerSync()" class="px-3 py-1 bg-emerald-700 hover:bg-emerald-800 text-white rounded text-xs font-bold transition shadow-xs">
                    Sync CREX Feeds
                </button>
            </div>
        </div>
    </header>

    <main class="max-w-6xl mx-auto px-3 sm:px-4 mt-6 flex-1 w-full space-y-6">
        <!-- Control Banner -->
        <div class="bg-gradient-to-r from-emerald-950 via-slate-900 to-emerald-900 text-white p-6 rounded-2xl shadow-sm border border-emerald-800">
            <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                    <span class="text-3xs font-black uppercase tracking-widest text-emerald-400">ENGINE CONTROL CONSOLE</span>
                    <h1 class="text-xl sm:text-2xl font-black tracking-tight mt-0.5">CREX Master Event Directory & URL Router</h1>
                    <p class="text-xs text-emerald-200/80 mt-1">
                        All events and series worldwide ingested from CREX. Input any Cricinfo, Cricbuzz, or CREX match link to begin live ball-by-ball scraping and automatically promote matches to Live.
                    </p>
                </div>
                <div class="flex items-center gap-3 shrink-0">
                    <div class="text-right">
                        <div class="text-2xl font-black text-white">{total_events_count}</div>
                        <div class="text-3xs uppercase font-bold text-emerald-300">Total CREX Events</div>
                    </div>
                    <div class="h-8 w-px bg-emerald-800"></div>
                    <div class="text-right">
                        <div class="text-2xl font-black text-amber-400">{mapped_count}</div>
                        <div class="text-3xs uppercase font-bold text-emerald-300">Actively Mapped</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Custom URL Mapper Box -->
        <div class="bg-white rounded-2xl border border-slate-200 shadow-2xs p-5 sm:p-6">
            <h2 class="text-sm sm:text-base font-black text-slate-900 uppercase tracking-wide mb-1">
                Custom Match Mapping (Any URL)
            </h2>
            <p class="text-xs text-slate-500 mb-4">Paste any match URL from ESPNcricinfo, Cricbuzz, or CREX. Hermes Brain will auto-bind the match ID, sync urls.txt, and start live scraping.</p>
            
            <form onsubmit="handleCustomMapSubmit(event)" class="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
                <div class="md:col-span-3">
                    <label class="block text-3xs font-extrabold uppercase text-slate-600 mb-1">Match ID / Key</label>
                    <input type="text" id="customMatchId" required placeholder="e.g. 1534214 or 11UV" class="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:outline-hidden font-mono">
                </div>
                <div class="md:col-span-4">
                    <label class="block text-3xs font-extrabold uppercase text-slate-600 mb-1">Match Title</label>
                    <input type="text" id="customTitle" required placeholder="e.g. Barbados Tridents vs Jamaica Kingsmen" class="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:outline-hidden">
                </div>
                <div class="md:col-span-2">
                    <label class="block text-3xs font-extrabold uppercase text-slate-600 mb-1">Category</label>
                    <select id="customCategory" class="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:outline-hidden font-semibold">
                        <option value="international">International</option>
                        <option value="league">League</option>
                        <option value="women">Women</option>
                        <option value="domestic">Domestic</option>
                    </select>
                </div>
                <div class="md:col-span-12 lg:col-span-9">
                    <label class="block text-3xs font-extrabold uppercase text-slate-600 mb-1">Source Match URL (Cricinfo, Cricbuzz, or CREX)</label>
                    <input type="url" id="customUrl" required placeholder="https://www.cricinfo.com/... or https://www.cricbuzz.com/... or https://crex.com/..." class="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:outline-hidden font-mono">
                </div>
                <div class="md:col-span-12 lg:col-span-3">
                    <button type="submit" class="w-full py-2 bg-[#186047] hover:bg-[#124d38] text-white text-xs font-black uppercase tracking-wider rounded-lg transition shadow-xs">
                        Save & Scrape Now &raquo;
                    </button>
                </div>
            </form>
            <div id="mapStatusMsg" class="mt-3 text-xs font-bold hidden"></div>
        </div>

        <!-- Active Mappings Table -->
        <div class="bg-white rounded-2xl border border-slate-200 shadow-2xs overflow-hidden">
            <div class="px-5 py-3.5 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
                <h3 class="text-xs sm:text-sm font-black text-slate-900 uppercase tracking-wide">
                    Actively Mapped & Ingested Matches ({mapped_count})
                </h3>
                <span class="text-3xs text-emerald-800 bg-emerald-100 font-bold px-2.5 py-0.5 rounded-full border border-emerald-300">
                    Live Engine Synced
                </span>
            </div>
            <div class="overflow-x-auto">
                <table class="w-full text-left text-xs whitespace-nowrap">
                    <thead class="bg-slate-100 text-slate-600 font-extrabold uppercase text-3xs tracking-wider border-b border-slate-200">
                        <tr>
                            <th class="py-2.5 px-3 sm:px-4">Match ID</th>
                            <th class="py-2.5 px-3 sm:px-4">Match Title</th>
                            <th class="py-2.5 px-3 sm:px-4">Platform</th>
                            <th class="py-2.5 px-3 sm:px-4">Mapped Source URL</th>
                            <th class="py-2.5 px-3 sm:px-4 text-right">Actions</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100">
                        {mapped_rows if mapped_rows else '<tr><td colspan="5" class="py-6 text-center text-slate-400 font-medium">No matches mapped yet.</td></tr>'}
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Ingested CREX Directory (Filterable & Searchable) -->
        <div class="bg-slate-50 border border-slate-200 rounded-2xl p-5 sm:p-6">
            <div class="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-4">
                <div>
                    <h3 class="text-xs sm:text-sm font-black text-slate-900 uppercase tracking-wide">
                        CREX World Events Directory ({total_events_count} Ingested)
                    </h3>
                    <p class="text-3xs text-slate-500 mt-0.5">Quickly map any event by pasting a Cricinfo, Cricbuzz, or CREX link directly into its card.</p>
                </div>
                <div class="flex flex-wrap items-center gap-2">
                    <input type="text" id="eventSearch" oninput="filterEvents()" placeholder="Search team or series..." class="px-3 py-1.5 text-xs bg-white border border-slate-300 rounded-lg focus:ring-1 focus:ring-emerald-500 focus:outline-hidden font-medium">
                    <button onclick="setFilterTab('all')" id="tab-all" class="admin-tab-btn px-3 py-1.5 rounded-lg text-xs font-black bg-slate-900 text-white shadow-2xs">All ({total_events_count})</button>
                    <button onclick="setFilterTab('unmapped')" id="tab-unmapped" class="admin-tab-btn px-3 py-1.5 rounded-lg text-xs font-bold bg-white text-slate-700 border border-slate-300 hover:bg-slate-100">Unmapped ({unmapped_count})</button>
                    <button onclick="setFilterTab('mapped')" id="tab-mapped" class="admin-tab-btn px-3 py-1.5 rounded-lg text-xs font-bold bg-white text-slate-700 border border-slate-300 hover:bg-slate-100">Mapped ({mapped_count})</button>
                </div>
            </div>

            <div id="eventsGrid" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {crex_event_cards}
            </div>
        </div>
    </main>

    <footer class="mt-12 py-6 bg-slate-900 text-slate-500 text-3xs text-center border-t border-slate-800">
        Hermes Brain v2.0 Admin Engine &bull; Restricted Access
    </footer>

    <script>
        let currentFilter = 'all';

        function setFilterTab(f) {{
            currentFilter = f;
            document.querySelectorAll('.admin-tab-btn').forEach(b => {{
                b.className = 'admin-tab-btn px-3 py-1.5 rounded-lg text-xs font-bold bg-white text-slate-700 border border-slate-300 hover:bg-slate-100';
            }});
            const activeBtn = document.getElementById('tab-' + f);
            if (activeBtn) {{
                activeBtn.className = 'admin-tab-btn px-3 py-1.5 rounded-lg text-xs font-black bg-slate-900 text-white shadow-2xs';
            }}
            filterEvents();
        }}

        function filterEvents() {{
            const q = (document.getElementById('eventSearch').value || '').toLowerCase().trim();
            document.querySelectorAll('.event-row').forEach(row => {{
                const title = row.getAttribute('data-title') || '';
                const series = row.getAttribute('data-series') || '';
                const isMapped = row.getAttribute('data-mapped') === 'true';

                let matchesTab = true;
                if (currentFilter === 'unmapped') matchesTab = !isMapped;
                if (currentFilter === 'mapped') matchesTab = isMapped;

                let matchesQuery = !q || title.includes(q) || series.includes(q);

                if (matchesTab && matchesQuery) {{
                    row.classList.remove('hidden');
                }} else {{
                    row.classList.add('hidden');
                }}
            }});
        }}

        async function quickMapMatch(mid, title, cat) {{
            const input = document.getElementById('input-' + mid);
            if (!input) return;
            const url = input.value.trim();
            if (!url) {{
                alert('Please paste a match URL first.');
                input.focus();
                return;
            }}

            try {{
                const res = await fetch('/api/admin/map', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ match_id: mid, title: title, category: cat, url: url }})
                }});
                const data = await res.json();
                if (data.status === 'ok' || data.status === 'received') {{
                    alert('Match ' + mid + ' mapped successfully! Ingestion initiated.');
                    window.location.reload();
                }} else {{
                    alert('Error: ' + (data.error || 'Failed to map'));
                }}
            }} catch (err) {{
                alert('Network error: ' + err.message);
            }}
        }}

        async function handleCustomMapSubmit(e) {{
            e.preventDefault();
            const mid = document.getElementById('customMatchId').value.trim();
            const title = document.getElementById('customTitle').value.trim();
            const cat = document.getElementById('customCategory').value;
            const url = document.getElementById('customUrl').value.trim();

            const msg = document.getElementById('mapStatusMsg');
            msg.className = 'mt-3 text-xs font-bold text-blue-600 block';
            msg.innerText = 'Saving mapping and syncing urls.txt...';

            try {{
                const res = await fetch('/api/admin/map', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ match_id: mid, title: title, category: cat, url: url }})
                }});
                const data = await res.json();
                if (data.status === 'ok' || data.status === 'received') {{
                    msg.className = 'mt-3 text-xs font-bold text-emerald-600 block';
                    msg.innerText = 'Mapping saved successfully! Live scraping initiated.';
                    setTimeout(() => window.location.reload(), 1200);
                }} else {{
                    msg.className = 'mt-3 text-xs font-bold text-rose-600 block';
                    msg.innerText = 'Error: ' + (data.error || 'Failed to save');
                }}
            }} catch (err) {{
                msg.className = 'mt-3 text-xs font-bold text-rose-600 block';
                msg.innerText = 'Network error: ' + err.message;
            }}
        }}

        async function unmapMatch(mid) {{
            if (!confirm('Are you sure you want to unmap match ' + mid + '?')) return;
            try {{
                const res = await fetch('/api/admin/unmap', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ match_id: mid }})
                }});
                const data = await res.json();
                if (data.status === 'ok') {{
                    window.location.reload();
                }} else {{
                    alert('Error: ' + (data.error || 'Failed to unmap'));
                }}
            }} catch (err) {{
                alert('Error: ' + err.message);
            }}
        }}

        async function triggerSync() {{
            try {{
                const res = await fetch('/api/admin/sync', {{ method: 'POST' }});
                const data = await res.json();
                alert('Feed sync triggered: ' + (data.message || 'Syncing'));
                window.location.reload();
            }} catch (err) {{
                alert('Sync failed: ' + err.message);
            }}
        }}
    </script>
</body>
</html>"""
