import sys
import os
import time
import argparse
import asyncio
from typing import List

# Fix Windows console UTF-8 output encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Add local path to sys.path so core and scrapers are discoverable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.browser_manager import BrowserManager
from core.exporter import DataExporter
from core.hermes_brain import HermesBrain
from core.dashboard_generator import DashboardGenerator
from core.dashboard_server import DashboardServer
from scrapers import get_scraper_for_url

async def process_single_event(url: str, browser_mgr: BrowserManager, output_dir: str, port: int = 8080):
    print("\n" + "=" * 75, flush=True)
    print(f"[*] Processing Event: {url}", flush=True)
    print("=" * 75, flush=True)
    
    try:
        scraper = get_scraper_for_url(url)
    except Exception as e:
        print(f"[!] Router Error: {e}", flush=True)
        return None

    start_time = time.time()
    try:
        match_data = await scraper.fetch_and_parse(browser_mgr)
    except Exception as e:
        print(f"[!] Extraction Error on {url}: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return None

    elapsed = time.time() - start_time
    
    # Process through Hermes Brain Engine (computes dot balls, partnership boundaries, impact overs)
    match_data = HermesBrain.analyze(match_data)

    # Export all structured formats
    exported = DataExporter.export(match_data, output_dir=output_dir)
    
    # Generate Live Dashboard (CREX card layout + Cricbuzz color styling)
    try:
        import importlib
        import core.dashboard_generator
        importlib.reload(core.dashboard_generator)
        from core.dashboard_generator import DashboardGenerator
        dash_path = DashboardGenerator.generate(match_data, output_dir=output_dir, port=port)
        exported['dashboard'] = dash_path
    except Exception as e:
        print(f"[!] Dashboard generation error: {e}", flush=True)

    # Render Console Summary
    meta = match_data.metadata
    status_prefix = "[🔴 LIVE]" if meta.is_live else "[🏁 COMPLETED]"
    print("\n" + "-" * 75, flush=True)
    print(f"MATCH:     {meta.match_title}", flush=True)
    print(f"SERIES:    {meta.series} | VENUE: {meta.venue}", flush=True)
    print(f"TOSS:      {meta.toss}", flush=True)
    print(f"STATUS:    {status_prefix} {meta.status} ({meta.status_note})", flush=True)
    print(f"DASHBOARD: http://localhost:{port}", flush=True)
    print(f"HERMES:    ⚡ {meta.match_impact_overs} Impact Overs (≥10R) | BALLS EXTRACTED: {len(match_data.all_balls)}", flush=True)
    print(f"TIME:      Completed in {elapsed:.2f}s", flush=True)
    print("-" * 75, flush=True)

    for inn in match_data.innings:
        print(f"\n>>> {inn.header_summary}", flush=True)
        print(f"{'BATTER':<24} {'DISMISSAL':<30} {'R':>4} {'B':>4} {'4s':>3} {'6s':>3} {'SR':>6}", flush=True)
        print("-" * 75, flush=True)
        for b in inn.batting:
            print(f"{b.batter:<24} {b.dismissal[:28]:<30} {b.runs:>4} {b.balls:>4} {b.fours:>3} {b.sixes:>3} {b.strike_rate:>6}", flush=True)
        
        if inn.extras:
            print(f"Extras: {inn.extras.raw}", flush=True)
        if inn.total:
            print(f"Total:  {inn.total.raw}", flush=True)

        print("\n" + "." * 75, flush=True)
        print(f"{'BOWLER':<24} {'O':>6} {'M':>4} {'R':>5} {'W':>3} {'DOTS':>5} {'ECON':>6}", flush=True)
        print("." * 75, flush=True)
        for bo in inn.bowling:
            print(f"{bo.bowler:<24} {bo.overs:>6} {bo.maidens:>4} {bo.runs:>5} {bo.wickets:>3} {bo.dot_balls:>5} {bo.economy:>6}", flush=True)

        if inn.fall_of_wickets:
            fow_str = " | ".join([f"{w.wicket_num}-{w.team_score} ({w.batter_out} {w.over} ov)" for w in inn.fall_of_wickets])
            print(f"\nFall of Wickets:\n  {fow_str}", flush=True)

        if inn.impact_overs_list:
            io_str = " | ".join([f"{io['over_label']}: {io['runs']}R ({io['bowler']})" for io in inn.impact_overs_list])
            print(f"\n⚡ Inning Impact Overs (≥10R): {io_str}", flush=True)

        if inn.ball_by_ball:
            print(f"\nBall-by-Ball Commentary Sample (Total in inning: {len(inn.ball_by_ball)} deliveries):", flush=True)
            for b in inn.ball_by_ball[:3]:
                print(f"  * Over {b.over_str:<5} [{b.runs} runs] {b.bowler} -> {b.batter} | {b.outcome}: {b.commentary_text[:80]}...", flush=True)

    if match_data.partnerships:
        print("\n" + "-" * 75, flush=True)
        print("KEY PARTNERSHIPS & BOUNDARIES:", flush=True)
        for p in match_data.partnerships:
            b1 = p.batter_1
            b2 = p.batter_2
            b_str = p.boundary_str or f"{p.fours}x4, {p.sixes}x6"
            print(f"  * {p.milestone_runs} runs ({p.balls}b) [{b_str:<10}] | {b1.name}: {b1.runs}({b1.balls}) & {b2.name}: {b2.runs}({b2.balls}) [{p.source_day}]", flush=True)

    print("\n" + "-" * 75, flush=True)
    print("SAVED DATASET ARTIFACTS:", flush=True)
    for k, path in exported.items():
        print(f"  [+] {k.upper():<18}: {path}", flush=True)
    print("-" * 75, flush=True)

    return match_data

def read_file_shared_text(file_path: str, max_retries: int = 6, retry_delay: float = 0.05) -> str:
    """
    Reads file content with non-locking sharing mode (FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE).
    Guarantees Windows File Explorer, Notepad, VS Code, and any other program
    can edit, save, rename, or delete the file at any time without locking conflicts.
    """
    if not os.path.exists(file_path):
        return ""

    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        GENERIC_READ = 0x80000000
        FILE_SHARE_READ = 0x00000001
        FILE_SHARE_WRITE = 0x00000002
        FILE_SHARE_DELETE = 0x00000004
        OPEN_EXISTING = 3
        FILE_ATTRIBUTE_NORMAL = 0x00000080
        INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

        kernel32.CreateFileW.restype = wintypes.HANDLE
        kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE
        ]
        kernel32.ReadFile.restype = wintypes.BOOL
        kernel32.ReadFile.argtypes = [
            wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID
        ]
        kernel32.GetFileSizeEx.restype = wintypes.BOOL
        kernel32.GetFileSizeEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_int64)]
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

        for attempt in range(max_retries):
            h = kernel32.CreateFileW(
                os.path.abspath(file_path),
                GENERIC_READ,
                FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                None,
                OPEN_EXISTING,
                FILE_ATTRIBUTE_NORMAL,
                None
            )
            if h != INVALID_HANDLE_VALUE and h is not None:
                try:
                    size = ctypes.c_int64(0)
                    if kernel32.GetFileSizeEx(h, ctypes.byref(size)) and size.value > 0:
                        buf = ctypes.create_string_buffer(size.value)
                        bytes_read = wintypes.DWORD(0)
                        if kernel32.ReadFile(h, buf, size.value, ctypes.byref(bytes_read), None):
                            return buf.raw[:bytes_read.value].decode("utf-8", errors="replace")
                finally:
                    kernel32.CloseHandle(h)
            time.sleep(retry_delay)

    for attempt in range(max_retries):
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except (PermissionError, OSError):
            time.sleep(retry_delay)
    return ""

def get_file_fingerprint(file_path: str) -> tuple:
    """
    Returns (st_mtime_ns, st_size) using filesystem directory metadata.
    Does NOT open any file handle on Windows, guaranteeing zero lock overhead.
    """
    try:
        st = os.stat(file_path)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return (0, 0)

def read_urls_from_file(file_path: str) -> List[str]:
    """Read and deduplicate active cricket URLs from a file safely without locking."""
    text = read_file_shared_text(file_path)
    if not text:
        return []
    urls = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#"):
            clean_u = line.strip("'\"")
            if clean_u.startswith("http"):
                urls.append(clean_u)
    # Deduplicate preserving order
    seen = set()
    deduped = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped

async def run_file_watcher_mode(file_path: str, browser_mgr: BrowserManager, output_dir: str, interval: int = 10, once: bool = False, port: int = 8080):
    """
    Continuously monitors a URLs file in real-time with zero file locks.
    Dynamically detects added, updated, or deleted URLs, keeps live-fetching active matches,
    and wakes up instantly (<0.5s) when the user edits or saves the file.
    """
    file_name = os.path.basename(file_path)
    print("=" * 75, flush=True)
    print("LIVE FILE WATCHER MODE ACTIVE (ZERO-LOCK EDITING ENABLED)", flush=True)
    print("=" * 75, flush=True)
    print(f"Monitoring File   : {file_path}", flush=True)
    print(f"Output Directory  : {output_dir}", flush=True)
    print(f"Live Dashboard    : http://localhost:{port}", flush=True)
    print(f"Polling Interval  : {interval}s cycle (real-time 0.5s edit detection)", flush=True)
    print(f"Live Auto-Sync    : {'Enabled (press Ctrl+C to stop)' if not once else 'Disabled (--once single run)'}", flush=True)
    print("=" * 75, flush=True)
    print("[*] LIVE matches will update continuously until they conclude.", flush=True)
    print("[*] 'urls.txt' is always unlocked for editing - add/update URLs anytime!\n", flush=True)

    previous_urls: set = set()
    concluded_urls: set = set()
    last_fingerprint = get_file_fingerprint(file_path)
    cycle_num = 0

    while True:
        cycle_num += 1
        current_urls = read_urls_from_file(file_path)
        last_fingerprint = get_file_fingerprint(file_path)
        current_set = set(current_urls)

        # Detect additions & deletions
        added = [u for u in current_urls if u not in previous_urls]
        removed = [u for u in previous_urls if u not in current_set]

        # If a URL was removed, remove it from concluded list so if re-added it can scrape fresh
        for u in removed:
            concluded_urls.discard(u)

        if added and cycle_num > 1:
            print("\n" + "#" * 75, flush=True)
            print(f"[+] DETECTED {len(added)} NEW/UPDATED MATCH URL(S) IN '{file_name}':", flush=True)
            for u in added:
                print(f"    --> {u}", flush=True)
                concluded_urls.discard(u)  # Ensure newly added URLs are processed immediately
            print("#" * 75, flush=True)

        if removed and cycle_num > 1:
            print("\n" + "#" * 75, flush=True)
            print(f"[-] DETECTED {len(removed)} MATCH URL(S) REMOVED FROM '{file_name}':", flush=True)
            for u in removed:
                print(f"    <-- {u}", flush=True)
            print("#" * 75, flush=True)

        previous_urls = current_set

        if not current_urls:
            print(f"\n[*] '{file_name}' currently contains 0 active URLs.", flush=True)
            print(f"[*] Waiting for match URLs to be added... (instant auto-detection active)", flush=True)
        else:
            # Filter active (live or not-yet-fetched) URLs
            urls_to_process = [u for u in current_urls if u not in concluded_urls or cycle_num == 1]
            if not urls_to_process:
                print(f"\n[*] All {len(current_urls)} match(es) in '{file_name}' have concluded.", flush=True)
                print(f"[*] Engine is STANDBY & monitoring '{file_name}' for edits/new URLs... (Ctrl+C to stop)", flush=True)
            else:
                print(f"\n{'=' * 25} [LIVE CYCLE #{cycle_num} | {len(urls_to_process)} MATCH(ES) TO FETCH] {'=' * 25}", flush=True)
                for url in urls_to_process:
                    # Check if file was modified during processing
                    curr_fp = get_file_fingerprint(file_path)
                    if curr_fp != last_fingerprint:
                        last_fingerprint = curr_fp
                        fresh_urls = set(read_urls_from_file(file_path))
                        if url not in fresh_urls:
                            print(f"[-] Skipping {url} (removed from {file_name} during cycle)", flush=True)
                            continue

                    m_data = await process_single_event(url, browser_mgr, output_dir, port=port)
                    if m_data and not m_data.metadata.is_live:
                        concluded_urls.add(url)
                        print(f"\n[🏁 MATCH CONCLUDED] {m_data.metadata.match_title} has officially ended. Final results saved!", flush=True)

        if once:
            break

        # Re-check file state immediately in case the user edited urls.txt during the scraping cycle
        current_urls = read_urls_from_file(file_path)
        last_fingerprint = get_file_fingerprint(file_path)
        unprocessed = [u for u in current_urls if u not in concluded_urls]
        if unprocessed:
            continue

        # Check if any matches in file are still live
        has_live_matches = any(u not in concluded_urls for u in current_urls)

        if has_live_matches:
            print(f"\n[Live Sync] Polling live match in {interval}s... (or instantly if '{file_name}' is edited)", flush=True)

        # Standby sleep loop with ultra-fast 0.5s change detection
        # If all matches are concluded, sleeps indefinitely waiting for edits without flooding terminal
        sleep_elapsed = 0.0
        max_wait = interval if has_live_matches else 86400

        while sleep_elapsed < max_wait:
            await asyncio.sleep(0.5)
            sleep_elapsed += 0.5
            current_fp = get_file_fingerprint(file_path)
            if current_fp != last_fingerprint:
                # Wait 100ms for editor to finish file write buffer
                await asyncio.sleep(0.1)
                last_fingerprint = get_file_fingerprint(file_path)
                fresh_urls = read_urls_from_file(file_path)
                fresh_set = set(fresh_urls)
                if fresh_set != previous_urls:
                    print(f"\n[*] Instant edit detected in '{file_name}'! Starting fetch cycle immediately...", flush=True)
                    break
                else:
                    # File was modified/saved even if URLs are unchanged (e.g. user forced re-save)
                    print(f"\n[*] File modification detected in '{file_name}'! Re-checking matches...", flush=True)
                    concluded_urls.clear()
                    break

async def main_async(
    urls: List[str] = None,
    watch_file: str = None,
    output_dir: str = "output",
    live_mode: bool = False,
    interval: int = 10,
    headless: bool = True,
    once: bool = False,
    port: int = 8080
):
    async with BrowserManager(headless=headless) as browser_mgr:
        if watch_file:
            await run_file_watcher_mode(
                file_path=watch_file,
                browser_mgr=browser_mgr,
                output_dir=output_dir,
                interval=interval,
                once=once,
                port=port
            )
        elif urls:
            print("=" * 75, flush=True)
            print("MODULAR CRICKET DATA & BALL-BY-BALL SCRAPING ENGINE", flush=True)
            print("=" * 75, flush=True)
            print(f"Total Target Events : {len(urls)}", flush=True)
            print(f"Output Directory    : {output_dir}", flush=True)
            print(f"Live Dashboard      : http://localhost:{port}", flush=True)
            print(f"Polling Interval    : {interval}s", flush=True)
            print("=" * 75, flush=True)

            active_urls = list(urls)
            concluded_urls = set()
            cycle_num = 0

            while active_urls:
                cycle_num += 1
                still_active = []
                for url in active_urls:
                    match_data = await process_single_event(url, browser_mgr, output_dir, port=port)
                    if match_data:
                        if match_data.metadata.is_live and not once:
                            still_active.append(url)
                        else:
                            concluded_urls.add(url)
                            if not match_data.metadata.is_live:
                                print(f"\n[🏁 MATCH CONCLUDED] {match_data.metadata.match_title} has officially ended. Final results saved!", flush=True)
                    else:
                        if not once:
                            still_active.append(url)

                if once or not still_active:
                    break

                active_urls = still_active
                print(f"\n[🔴 LIVE TRACKING] {len(active_urls)} active match(es) still in progress. Next live update in {interval}s... (Ctrl+C to stop)", flush=True)
                await asyncio.sleep(interval)

            print(f"\n[🏁 All target matches have finished. Final JSON datasets saved in '{output_dir}/'.]\n", flush=True)

def main():
    parser = argparse.ArgumentParser(
        description="Unified Multi-Site Cricket Match & Ball-by-Ball Data Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 1. Interactive menu mode (default: live auto-sync from urls.txt)
  python main.py

  # 2. Live auto-sync watcher on urls.txt directly
  python main.py --file urls.txt

  # 3. Single-pass run from file without continuous live watching
  python main.py --file urls.txt --once

  # 4. Scrape single match event URL directly
  python main.py "https://www.cricketworld.com/cricket/england-vs-pakistan/match/live/95255"

  # 5. Continuous live tracking of a specific URL
  python main.py "https://www.cricketworld.com/.../95255" --live --interval 10
        """
    )
    parser.add_argument("urls", nargs="*", help="One or more cricket match event URLs")
    parser.add_argument("-f", "--file", help="Path to text file containing match URLs (one per line)")
    parser.add_argument("-o", "--output-dir", default="output", help="Directory to save JSON & CSV exports")
    parser.add_argument("--live", action="store_true", help="Enable continuous live polling mode")
    parser.add_argument("--once", action="store_true", help="Run once without continuous live watching")
    parser.add_argument("--interval", type=int, default=10, help="Polling interval in seconds for live mode (default: 10)")
    parser.add_argument("--headed", action="store_true", help="Launch visible browser window for debugging")
    parser.add_argument("--port", type=int, default=8080, help="Port for live HTTP dashboard (default: 8080; auto-finds free port if occupied)")
    parser.add_argument("--no-dashboard", action="store_true", help="Disable live HTTP dashboard server")

    args = parser.parse_args()

    # Dynamic Port & Live Dashboard Server Startup
    actual_port = args.port
    if not args.no_dashboard:
        try:
            dash_url, actual_port = DashboardServer.start(
                port=args.port,
                output_dir=args.output_dir,
                clear_previous=False
            )
            # Background sync for global cricket categories if needed
            try:
                import threading
                from scrapers.feed_scraper import CricketFeedEngine
                data_dir = os.path.join(args.output_dir, "data")
                matches_file = os.path.join(data_dir, "matches.json")
                if not os.path.exists(matches_file) or (time.time() - os.path.getmtime(matches_file) > 1800):
                    threading.Thread(target=CricketFeedEngine.sync_all, args=(args.output_dir,), daemon=True).start()
            except Exception as e:
                pass
        except Exception as e:
            print(f"[!] Warning: Could not initialize dashboard server: {e}", flush=True)

    watch_file_path = None
    target_urls = []

    # If --file was explicitly specified via CLI
    if args.file:
        watch_file_path = os.path.abspath(args.file)
    elif args.urls:
        target_urls.extend(args.urls)

    # Interactive Menu Mode if no URLs or file provided via CLI arguments
    if not watch_file_path and not target_urls:
        urls_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "urls.txt")
        if not os.path.exists(urls_file_path):
            with open(urls_file_path, "w", encoding="utf-8") as f:
                f.write("# Add cricket match URLs below (one per line)\n")

        file_urls_found = read_urls_from_file(urls_file_path)

        print("=" * 75, flush=True)
        print("CRICKET MATCH SCRAPING ENGINE - SELECT INPUT SOURCE", flush=True)
        print("=" * 75, flush=True)
        print("Choose how you want to provide match URLs:", flush=True)
        print("  [1] Enter Match Event URL(s) manually", flush=True)
        print(f"  [2] Live auto-sync from 'urls.txt' in folder ({len(file_urls_found)} URLs found) [DEFAULT]", flush=True)
        print("-" * 75, flush=True)

        default_choice = "2"
        try:
            choice = input(f"Select option [1/2, default: {default_choice}]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.", flush=True)
            DashboardServer.stop()
            sys.exit(0)

        if not choice:
            choice = default_choice

        if choice == "2":
            watch_file_path = urls_file_path
            if file_urls_found:
                print(f"\n[*] Starting Live Watcher with {len(file_urls_found)} initial URL(s) from 'urls.txt':", flush=True)
                for u in file_urls_found:
                    print(f"  [+] {u}", flush=True)
            else:
                print(f"\n[*] 'urls.txt' is currently empty. The engine will watch 'urls.txt' in real-time.", flush=True)
                print(f"[*] Simply add match URLs into 'urls.txt' and save; it will automatically begin scraping.", flush=True)

        if choice == "1":
            print("\nEnter cricket match event URL (or multiple URLs separated by space):", flush=True)
            print("-" * 75, flush=True)

            while True:
                try:
                    user_input = input("Enter Match Event URL: ").strip()
                except (KeyboardInterrupt, EOFError):
                    print("\nAborted.", flush=True)
                    DashboardServer.stop()
                    sys.exit(0)

                if not user_input:
                    if target_urls:
                        break
                    print("  [!] Please enter a valid URL.", flush=True)
                    continue

                urls_in_line = [u.strip() for u in user_input.replace(",", " ").split() if u.strip().startswith("http")]
                if urls_in_line:
                    for u in urls_in_line:
                        if u not in target_urls:
                            target_urls.append(u)
                            print(f"  [+] Added: {u}", flush=True)
                    break
                elif user_input.startswith("http"):
                    if user_input not in target_urls:
                        target_urls.append(user_input)
                        print(f"  [+] Added: {user_input}", flush=True)
                    break
                else:
                    print("  [!] Please enter a valid URL starting with http:// or https://", flush=True)

    try:
        asyncio.run(main_async(
            urls=target_urls,
            watch_file=watch_file_path,
            output_dir=args.output_dir,
            live_mode=args.live,
            interval=args.interval,
            headless=not args.headed,
            once=args.once,
            port=actual_port
        ))
    except KeyboardInterrupt:
        print("\n\n[!] Live Scraping stopped by user. Exiting cleanly.\n", flush=True)
    finally:
        DashboardServer.stop()

if __name__ == "__main__":
    main()
