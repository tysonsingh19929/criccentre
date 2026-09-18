import os
import re
import glob
import json
import socket
import threading
import time
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Optional, Tuple, Dict, Any

from core.page_templates import PageTemplates
from core.admin_panel import AdminPanel
from core.hermes_brain import HermesBrain
from scrapers.feed_scraper import CricketFeedEngine
from scrapers.crex_feed import CrexFeedEngine

class DashboardHTTPHandler(SimpleHTTPRequestHandler):
    """
    Custom HTTP request handler serving the Cricbuzz/CREX multi-page platform
    and REST API endpoints for real-time match data, schedules, series, teams,
    rankings, news, match center dashboards, and Hermes Brain Admin Panel.
    """
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, directory=None, **kwargs):
        self.output_dir = directory or os.path.abspath("output")
        super().__init__(*args, directory=self.output_dir, **kwargs)

    def log_message(self, format, *args):
        # Silence default HTTP server access logs so terminal output remains clean
        pass

    def _load_json(self, file_path: str, default: Any = None) -> Any:
        if default is None:
            default = {}
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return default
        return default

    def _get_data(self, name: str, default: Any = None) -> Any:
        p = os.path.join(self.output_dir, "data", f"{name}.json")
        return self._load_json(p, default)

    def _get_merged_matches_data(self) -> Dict[str, Any]:
        """Delegates state aggregation and lifecycle resolution to Hermes Brain."""
        return HermesBrain.get_platform_matches_data(self.output_dir)

    def _send_html(self, html_str: str, status_code: int = 200):
        encoded = html_str.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, data: Any, status_code: int = 200):
        encoded = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        clean_path = parsed.path.rstrip("/")
        if not clean_path:
            clean_path = "/"

        # 1. Match Specific Routes: /match/<id> or /match/<id>.html
        # 1. Match Specific Routes: /match/<id> or /match/<id>.html
        if clean_path.startswith("/match/"):
            raw_id = clean_path.split("/match/")[1].split("?")[0].replace(".html", "").strip("/")
            m_id = HermesBrain.resolve_match_id(raw_id, self.output_dir)
            m_file = os.path.join(self.output_dir, f"dashboard_{m_id}.html")
            if os.path.exists(m_file):
                try:
                    with open(m_file, "r", encoding="utf-8") as f:
                        return self._send_html(f.read())
                except Exception:
                    pass

            # Check if match full json exists to regenerate dashboard on-demand
            json_file = os.path.join(self.output_dir, f"match_{m_id}_full.json")
            if not os.path.exists(json_file):
                json_file = os.path.join(self.output_dir, f"match_{m_id}.json")
            if os.path.exists(json_file):
                try:
                    from core.dashboard_generator import DashboardGenerator
                    from core.models import MatchData
                    with open(json_file, "r", encoding="utf-8") as f:
                        d_dict = json.load(f)
                    m_data = MatchData.from_dict(d_dict)
                    DashboardGenerator.generate(m_data, output_dir=self.output_dir)
                    if os.path.exists(m_file):
                        with open(m_file, "r", encoding="utf-8") as f:
                            return self._send_html(f.read())
                except Exception as ex:
                    print(f"On-demand dashboard generation error for {m_id}: {ex}")

            # Check if match URL exists in crex_catalog, mappings, or urls.txt to scrape on-demand
            target_url = None
            catalog_file = os.path.join(self.output_dir, "data", "crex_catalog.json")
            if os.path.exists(catalog_file):
                try:
                    with open(catalog_file, "r", encoding="utf-8") as f:
                        cat_list = json.load(f)
                    for item in cat_list:
                        if str(item.get("match_id")) == str(m_id) or str(item.get("unique_match_id")) == str(m_id):
                            target_url = item.get("crex_url")
                            break
                except Exception:
                    pass

            if not target_url:
                mappings = HermesBrain.load_mappings(os.path.join(self.output_dir, "data"))
                if m_id in mappings:
                    target_url = mappings[m_id].get("crex_url") or mappings[m_id].get("cricinfo_url") or mappings[m_id].get("cricbuzz_url")

            if target_url and "crex.com" in target_url:
                try:
                    import asyncio
                    from scrapers.crex import CrexScraper
                    from core.dashboard_generator import DashboardGenerator
                    scraper = CrexScraper(target_url, None)
                    m_data = asyncio.run(scraper.fetch_and_parse(None))
                    # Save json and generate dashboard
                    out_json = os.path.join(self.output_dir, f"match_{m_id}_full.json")
                    with open(out_json, "w", encoding="utf-8") as f:
                        json.dump(m_data.to_dict(), f, indent=2, ensure_ascii=False)
                    DashboardGenerator.generate(m_data, output_dir=self.output_dir)
                    if os.path.exists(m_file):
                        with open(m_file, "r", encoding="utf-8") as f:
                            return self._send_html(f.read())
                except Exception as ex:
                    print(f"On-demand CREX scrape error for {m_id}: {ex}")

            # Look up metadata from matches.json or catalog for dedicated match preview
            matches_data = self._get_merged_matches_data()
            series_data = self._get_data("series", {})

            match_info = None
            for m in matches_data.get("live", []) + matches_data.get("upcoming", []) + matches_data.get("recent", []):
                if str(m.get("match_id")) == str(m_id):
                    match_info = m
                    break

            if not match_info:
                drawer = matches_data.get("drawer", {})
                for cat_list in drawer.values():
                    if isinstance(cat_list, list):
                        for m in cat_list:
                            if str(m.get("match_id")) == str(m_id):
                                match_info = m
                                break
                    if match_info:
                        break

            match_info = match_info or {"match_id": m_id, "title": f"Match #{m_id}"}
            return self._send_html(PageTemplates.render_match_hub_page(match_info, matches_data, series_data))

        # 2. Dedicated Article Reader: /news/<id>
        if clean_path.startswith("/news/"):
            nid = clean_path.split("/news/")[1].split("?")[0].strip("/")
            news_list = self._get_data("news", [])
            article = next((n for n in news_list if str(n.get("news_id")) == nid), None)
            if not article and news_list:
                article = news_list[0]
            if article:
                matches_data = self._get_merged_matches_data()
                series_data = self._get_data("series", {})
                return self._send_html(PageTemplates.render_news_detail_page(article, matches_data, series_data))

        # 3. Query param ?match=<id>
        if "match=" in self.path:
            qs = urllib.parse.parse_qs(parsed.query)
            if "match" in qs and qs["match"]:
                raw_id = qs["match"][0].strip()
                self.send_response(302)
                self.send_header("Location", f"/match/{raw_id}")
                self.send_header("Connection", "close")
                self.end_headers()
                return

        # 4. Dedicated Match Center: /dashboard
        if clean_path in ["/dashboard", "/dashboard.html"]:
            dash_path = os.path.join(self.output_dir, "dashboard.html")
            if os.path.exists(dash_path):
                try:
                    with open(dash_path, "r", encoding="utf-8") as f:
                        return self._send_html(f.read())
                except Exception:
                    pass
            self.send_response(302)
            self.send_header("Location", "/live-scores")
            self.send_header("Connection", "close")
            self.end_headers()
            return

        # 5. Multi-Page Navigation Routes
        # 5.1 Live Scores Page
        if clean_path in ["/", "/live-scores", "/live-scores.html", "/scores", "/live"]:
            matches_data = self._get_merged_matches_data()
            series_data = self._get_data("series", {})
            html = PageTemplates.render_live_scores_page(matches_data, series_data)
            return self._send_html(html)

        # 5.2 Cricket Schedule Page (Cricinfo 2-column layout)
        elif clean_path in ["/schedule", "/schedule.html"]:
            schedule_data = self._get_data("schedule", [])
            matches_data = self._get_merged_matches_data()
            series_data = self._get_data("series", {})
            html = PageTemplates.render_schedule_page(schedule_data, matches_data, series_data)
            return self._send_html(html)

        # 5.3 Series Directory Page
        elif clean_path in ["/series", "/series.html"]:
            series_data = self._get_data("series", {})
            matches_data = self._get_merged_matches_data()
            html = PageTemplates.render_series_page(series_data, matches_data)
            return self._send_html(html)

        # 5.4 Teams Directory Page
        elif clean_path in ["/teams", "/teams.html"]:
            teams_data = self._get_data("teams", {})
            matches_data = self._get_merged_matches_data()
            series_data = self._get_data("series", {})
            html = PageTemplates.render_teams_page(teams_data, matches_data, series_data)
            return self._send_html(html)

        # 5.5 ICC Rankings Page
        elif clean_path in ["/rankings", "/rankings.html"]:
            rankings_data = self._get_data("rankings", {})
            matches_data = self._get_merged_matches_data()
            series_data = self._get_data("series", {})
            html = PageTemplates.render_rankings_page(rankings_data, matches_data, series_data)
            return self._send_html(html)

        # 5.6 Cricket News Page
        elif clean_path in ["/news", "/news.html"]:
            news_data = self._get_data("news", [])
            matches_data = self._get_merged_matches_data()
            series_data = self._get_data("series", {})
            html = PageTemplates.render_news_page(news_data, matches_data, series_data)
            return self._send_html(html)

        # 5.7 Hermes Brain Admin Panel (Restricted route)
        elif clean_path in ["/admin", "/admin.html"]:
            data_dir = os.path.join(self.output_dir, "data")
            mappings = HermesBrain.load_mappings(data_dir)
            matches_data = self._get_merged_matches_data()
            series_data = self._get_data("series", {})
            catalog_data = self._get_data("crex_catalog", {"events": [], "series": []})
            html = AdminPanel.render(mappings, matches_data, series_data, catalog_data)
            return self._send_html(html)

        # 6. REST APIs
        elif clean_path == "/api/matches":
            return self._send_json(self._get_merged_matches_data())

        elif clean_path == "/api/schedule":
            return self._send_json(self._get_data("schedule", []))

        elif clean_path == "/api/series":
            return self._send_json(self._get_data("series", {}))

        elif clean_path == "/api/teams":
            return self._send_json(self._get_data("teams", {}))

        elif clean_path == "/api/rankings":
            return self._send_json(self._get_data("rankings", {}))

        elif clean_path == "/api/news":
            return self._send_json(self._get_data("news", []))

        elif clean_path in ["/api/points-table", "/api/standings"]:
            return self._send_json(self._get_data("points_table", {}))

        elif clean_path == "/api/admin/mappings":
            data_dir = os.path.join(self.output_dir, "data")
            return self._send_json(HermesBrain.load_mappings(data_dir))

        elif clean_path in ["/api/live", "/live.json"]:
            json_files = [os.path.join(self.output_dir, f) for f in os.listdir(self.output_dir) if f.endswith("_full.json")]
            if json_files:
                latest_file = max(json_files, key=os.path.getmtime)
                try:
                    with open(latest_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    return self._send_json(data)
                except Exception as e:
                    return self._send_json({"error": str(e)}, status_code=500)
            else:
                return self._send_json({"status": "waiting", "message": "No match data currently available"}, status_code=404)

        elif clean_path in ["/api/admin/sync", "/api/sync"]:
            def _sync_all():
                CrexFeedEngine.sync_catalog(self.output_dir)
                HermesBrain.sync_all_feeds(self.output_dir)
            threading.Thread(target=_sync_all, daemon=True).start()
            return self._send_json({"status": "syncing", "timestamp": time.time()})

        # 7. Fallback to standard static file serving
        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        clean_path = parsed.path.rstrip("/")
        content_length = int(self.headers.get("Content-Length", 0))
        body_data = {}
        if content_length > 0:
            raw_body = self.rfile.read(content_length).decode("utf-8", errors="ignore")
            try:
                body_data = json.loads(raw_body)
            except Exception:
                body_data = {}

        if clean_path == "/api/admin/map":
            match_id = str(body_data.get("match_id", "")).strip()
            url = str(body_data.get("url", "")).strip()
            title = str(body_data.get("title", "")).strip()
            cat = str(body_data.get("category", "international")).strip()

            if not match_id or not url:
                return self._send_json({"status": "error", "error": "match_id and url are required"}, status_code=400)

            data_dir = os.path.join(self.output_dir, "data")
            urls_file = os.path.join(os.path.dirname(self.output_dir), "urls.txt")
            if not os.path.exists(urls_file):
                urls_file = os.path.join(os.getcwd(), "urls.txt")

            try:
                mapping = HermesBrain.save_mapping(
                    match_id=match_id,
                    url=url,
                    title=title,
                    category=cat,
                    data_dir=data_dir,
                    urls_file=urls_file
                )
                # Trigger immediate background ingestion
                HermesBrain.trigger_match_ingestion(url, output_dir=self.output_dir, port=DashboardServer._actual_port)
                return self._send_json({"status": "ok", "mapping": mapping})
            except Exception as e:
                return self._send_json({"status": "error", "error": str(e)}, status_code=500)

        elif clean_path == "/api/admin/unmap":
            match_id = str(body_data.get("match_id", "")).strip()
            if not match_id:
                return self._send_json({"status": "error", "error": "match_id is required"}, status_code=400)

            data_dir = os.path.join(self.output_dir, "data")
            urls_file = os.path.join(os.path.dirname(self.output_dir), "urls.txt")
            if not os.path.exists(urls_file):
                urls_file = os.path.join(os.getcwd(), "urls.txt")

            ok = HermesBrain.delete_mapping(match_id=match_id, data_dir=data_dir, urls_file=urls_file)
            return self._send_json({"status": "ok" if ok else "not_found"})

        elif clean_path in ["/api/admin/sync", "/api/sync"]:
            def _sync_all():
                CrexFeedEngine.sync_catalog(self.output_dir)
                HermesBrain.sync_all_feeds(self.output_dir)
            threading.Thread(target=_sync_all, daemon=True).start()
            return self._send_json({"status": "ok", "message": "CREX catalog and all cricket feeds synchronized successfully in background", "timestamp": time.time()})

        return self._send_json({"status": "error", "error": "Unknown endpoint"}, status_code=404)


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Multi-threaded HTTPServer that handles every request concurrently."""
    daemon_threads = True
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE") and os.name == "nt":
            try:
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            except Exception:
                pass
        super().server_bind()


class DashboardServer:
    """
    Manages the background HTTP web server instance for the Live Dashboard.
    Automatically finds an empty available port and starts the Hermes Brain Autonomous Scheduler.
    """
    _server: Optional[ThreadedHTTPServer] = None
    _thread: Optional[threading.Thread] = None
    _actual_port: int = 8080

    @classmethod
    def is_port_free(cls, port: int) -> bool:
        """Check whether a given port is available and free to bind."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.15)
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    return False
        except Exception:
            pass

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if hasattr(socket, "SO_EXCLUSIVEADDRUSE") and os.name == "nt":
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                s.bind(("0.0.0.0", port))
                return True
        except OSError:
            return False

    @classmethod
    def find_free_port(cls, preferred_port: int = 8080) -> int:
        if cls.is_port_free(preferred_port):
            return preferred_port

        candidate_ports = [8085, 8090, 8000, 8888, 5000, 5050, 9000, 9090, 7070]
        for p in candidate_ports:
            if cls.is_port_free(p):
                return p

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    @classmethod
    def start(cls, port: int = 8080, output_dir: str = "output", clear_previous: bool = False) -> Tuple[str, int]:
        if cls._server is not None:
            return f"http://localhost:{cls._actual_port}", cls._actual_port

        os.makedirs(output_dir, exist_ok=True)
        abs_output_dir = os.path.abspath(output_dir)

        # 1. Start Hermes Brain Autonomous Background Scheduler
        HermesBrain.start_autonomous_scheduler(abs_output_dir)

        def handler_factory(*args, **kwargs):
            return DashboardHTTPHandler(*args, directory=abs_output_dir, **kwargs)

        candidate_ports = [port]
        for p in [8085, 8090, 8000, 8888, 5000, 5050, 9000, 9090, 7070]:
            if p not in candidate_ports:
                candidate_ports.append(p)

        actual_server = None
        actual_port = port

        for p in candidate_ports:
            if not cls.is_port_free(p):
                continue
            try:
                actual_server = ThreadedHTTPServer(("0.0.0.0", p), handler_factory)
                actual_port = p
                break
            except OSError:
                continue

        if actual_server is None:
            actual_server = ThreadedHTTPServer(("0.0.0.0", 0), handler_factory)
            actual_port = actual_server.server_address[1]

        cls._server = actual_server
        cls._actual_port = actual_port

        cls._thread = threading.Thread(target=cls._server.serve_forever, daemon=True)
        cls._thread.start()

        cls.pre_render_all_pages(abs_output_dir)

        dashboard_url = f"http://localhost:{actual_port}"
        print("=" * 75, flush=True)
        print(f"[*] LIVE CRICKET PLATFORM WEB SERVER INITIALIZED", flush=True)
        print(f"[*] Live Platform URL : {dashboard_url} (Port {actual_port} verified empty)", flush=True)
        print(f"[*] Routes Active     : /, /live-scores, /schedule, /series, /teams, /rankings, /news, /admin, /match/<id>", flush=True)
        print(f"[*] Open in Browser   : {dashboard_url}", flush=True)
        print("=" * 75, flush=True)

        return dashboard_url, actual_port

    @staticmethod
    def _load_static_json(file_path: str, default: Any = None) -> Any:
        if default is None:
            default = {}
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return default
        return default

    @classmethod
    def pre_render_all_pages(cls, output_dir: str = "output"):
        """Pre-renders all HTML pages into output_dir and public/ for static hosting & Vercel deployment."""
        try:
            os.makedirs(output_dir, exist_ok=True)
            pub_dir = os.path.join(os.path.dirname(os.path.abspath(output_dir)), "public")
            os.makedirs(pub_dir, exist_ok=True)

            matches_data = HermesBrain.get_platform_matches_data(output_dir)
            series_data = cls._load_static_json(os.path.join(output_dir, "data", "series.json"), {})
            schedule_data = cls._load_static_json(os.path.join(output_dir, "data", "schedule.json"), [])
            teams_data = cls._load_static_json(os.path.join(output_dir, "data", "teams.json"), {})
            rankings_data = cls._load_static_json(os.path.join(output_dir, "data", "rankings.json"), {})
            news_data = cls._load_static_json(os.path.join(output_dir, "data", "news.json"), [])
            data_dir = os.path.join(output_dir, "data")
            mappings = HermesBrain.load_mappings(data_dir)
            catalog_data = cls._load_static_json(os.path.join(data_dir, "crex_catalog.json"), {"events": [], "series": []})

            pages = {
                "index.html": PageTemplates.render_live_scores_page(matches_data, series_data),
                "live-scores.html": PageTemplates.render_live_scores_page(matches_data, series_data),
                "schedule.html": PageTemplates.render_schedule_page(schedule_data, matches_data, series_data),
                "series.html": PageTemplates.render_series_page(series_data, matches_data),
                "teams.html": PageTemplates.render_teams_page(teams_data, matches_data, series_data),
                "rankings.html": PageTemplates.render_rankings_page(rankings_data, matches_data, series_data),
                "news.html": PageTemplates.render_news_page(news_data, matches_data, series_data),
                "admin.html": AdminPanel.render(mappings, matches_data, series_data, catalog_data),
            }

            for filename, content in pages.items():
                for target_dir in [output_dir, pub_dir]:
                    path = os.path.join(target_dir, filename)
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(content)

            # Pre-render Match Hub dashboards for all active feed matches (Live, Recent, Upcoming, Drawer)
            all_feed_matches = list(matches_data.get("live", [])) + list(matches_data.get("recent", [])) + list(matches_data.get("upcoming", []))
            drawer = matches_data.get("drawer", {})
            for cat_list in drawer.values():
                if isinstance(cat_list, list):
                    all_feed_matches.extend(cat_list)

            seen_ids = set()
            for m in all_feed_matches:
                m_id = str(m.get("match_id", "")).strip()
                if not m_id or m_id in seen_ids:
                    continue
                seen_ids.add(m_id)

                hub_html = PageTemplates.render_match_hub_page(m, matches_data, series_data)
                for target_dir in [output_dir, pub_dir]:
                    m_file = os.path.join(target_dir, f"dashboard_{m_id}.html")
                    # If file exists and is already a full scorecard (> 50KB), do NOT overwrite
                    if os.path.exists(m_file) and os.path.getsize(m_file) > 50000:
                        continue
                    with open(m_file, "w", encoding="utf-8") as f:
                        f.write(hub_html)

            # Sync data directory to public/data
            src_data = os.path.join(output_dir, "data")
            dst_data = os.path.join(pub_dir, "data")
            if os.path.isdir(src_data):
                os.makedirs(dst_data, exist_ok=True)
                import shutil
                for item in os.listdir(src_data):
                    s_item = os.path.join(src_data, item)
                    d_item = os.path.join(dst_data, item)
                    if os.path.isfile(s_item):
                        shutil.copy2(s_item, d_item)
        except Exception as e:
            print(f"[!] Pre-render warning: {e}")

    @classmethod
    def stop(cls):
        if cls._server:
            cls._server.shutdown()
            cls._server.server_close()
            cls._server = None
