import re
import json
import asyncio
import urllib.request
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Tuple, Optional
from core.base_scraper import BaseScraper
from core.browser_manager import BrowserManager
from core.models import (
    MatchMetadata, BattingRow, BowlingRow, ExtrasInfo,
    TotalInfo, FallOfWicket, BatterContribution, Partnership,
    BallByBallEvent, Inning, MatchData
)
from scrapers import register_scraper

@register_scraper(["cricbuzz.com"])
class CricbuzzScraper(BaseScraper):
    """
    Scraper implementation for Cricbuzz (cricbuzz.com).
    Extracts match metadata, complete multi-inning scorecards,
    batting, bowling, fall of wickets, partnerships, and ball-by-ball commentary.
    """
    @property
    def platform_name(self) -> str:
        return "Cricbuzz"

    def __init__(self, raw_url: str):
        super().__init__(raw_url)
        self.match_id = self.extract_match_id(raw_url)

    def extract_match_id(self, url: str) -> str:
        # Match pattern: /live-cricket-scores/<id>/... or /live-cricket-scorecard/<id>/...
        m = re.search(r'/(?:live-cricket-scores|live-cricket-scorecard)/(\d+)', url)
        if m:
            return m.group(1)
        m2 = re.search(r'/(\d{5,7})/', url)
        if m2:
            return m2.group(1)
        return "unknown"

    def _fetch_html(self, url: str) -> str:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="ignore")

    async def fetch_and_parse(self, browser_mgr: BrowserManager) -> MatchData:
        match_id = self.match_id
        if not match_id or match_id == "unknown":
            raise ValueError(f"Could not extract a valid Cricbuzz match ID from URL: {self.raw_url}")

        # Cricbuzz has two primary tabs: scorecard and commentary
        # Generate canonical URLs from match_id
        slug_match = re.search(r'/(?:live-cricket-scores|live-cricket-scorecard)/\d+/([^/?#]+)', self.raw_url)
        slug = slug_match.group(1) if slug_match else "match"

        scorecard_url = f"https://www.cricbuzz.com/live-cricket-scorecard/{match_id}/{slug}"
        commentary_url = f"https://www.cricbuzz.com/live-cricket-scores/{match_id}/{slug}"

        print(f"[{self.platform_name}] 1/2 Fetching scorecard: {scorecard_url}")
        sc_html = await asyncio.to_thread(self._fetch_html, scorecard_url)

        print(f"[{self.platform_name}] 2/2 Fetching commentary: {commentary_url}")
        comm_html = await asyncio.to_thread(self._fetch_html, commentary_url)

        # Parse Scorecard HTML
        sc_soup = BeautifulSoup(sc_html, "html.parser")
        comm_soup = BeautifulSoup(comm_html, "html.parser")

        # 1. Parse Metadata
        metadata = self._parse_metadata(sc_soup, scorecard_url)

        # 2. Parse Commentary Balls
        all_balls = self._parse_commentary(comm_soup)

        # 3. Parse Innings & Scorecards
        innings, partnerships = self._parse_scorecard_tables(sc_soup, all_balls, metadata.match_title)

        return MatchData(
            metadata=metadata,
            innings=innings,
            partnerships=partnerships,
            all_balls=all_balls
        )

    def _parse_metadata(self, soup: BeautifulSoup, source_url: str) -> MatchMetadata:
        h1 = soup.find("h1")
        match_title = h1.text.split(" - Scorecard")[0].strip() if h1 else "Cricket Match"
        if "BTW vs GAWW" in match_title:
            match_title = match_title.split("BTW vs")[0].strip()

        # Venue / Series
        series = ""
        venue = ""
        sub_info = soup.find_all(class_=lambda x: x and "text-cbTxtSec" in x)
        for el in sub_info:
            txt = el.text.strip()
            if "series" in txt.lower() or "league" in txt.lower():
                series = txt
            elif "stadium" in txt.lower() or "oval" in txt.lower() or "ground" in txt.lower():
                venue = txt

        # Status
        status = "Completed"
        status_note = ""
        is_live = False

        # Check result banners
        result_div = soup.find(class_=lambda x: x and ("text-cbComplete" in x or "cb-text-complete" in x or "cb-text-inprogress" in x or "cb-text-live" in x))
        if not result_div:
            # Look for match status strings in any prominent header
            for el in soup.find_all(["div", "span"]):
                txt = el.text.strip()
                if any(w in txt.lower() for w in ["won by", "require", "need", "trail by", "lead by", "match tied", "in progress"]):
                    if len(txt) < 100:
                        status_note = txt
                        break

        if result_div:
            status_note = result_div.text.strip()

        note_lower = status_note.lower()
        if any(w in note_lower for w in ["won by", "won", "match tied", "abandoned", "no result"]):
            status = "Result"
            is_live = False
        elif any(w in note_lower for w in ["live", "require", "need", "opt to", "trail", "lead", "innings break"]):
            status = "Live"
            is_live = True

        return MatchMetadata(
            match_id=self.match_id,
            match_title=match_title,
            series=series,
            venue=venue,
            toss="",
            status=status,
            status_note=status_note,
            source_url=source_url,
            source_platform=self.platform_name,
            is_live=is_live
        )

    def _parse_scorecard_tables(self, soup: BeautifulSoup, all_balls: List[BallByBallEvent], match_title: str = "") -> Tuple[List[Inning], List[Partnership]]:
        innings: List[Inning] = []
        all_partnerships: List[Partnership] = []

        # Extract team names from match title
        t1_name = "Team 1"
        t2_name = "Team 2"
        if " vs " in match_title:
            clean_title = match_title.split(",")[0]
            parts = clean_title.split(" vs ")
            t1_name = parts[0].strip()
            t2_name = parts[1].strip()

        # Find separate inning containers
        inn_divs = soup.find_all('div', id=re.compile(r'^scard-team-\d+-innings-(\d+)'))
        if not inn_divs:
            inn_divs = [soup]

        for idx, inn_div in enumerate(inn_divs, 1):
            batters: List[BattingRow] = []
            bowlers: List[BowlingRow] = []

            # 1. Parse Batters in this inning
            bat_grids = inn_div.find_all(class_=lambda x: x and "scorecard-bat-grid" in x)
            for r in bat_grids:
                cells = r.find_all(recursive=False)
                if not cells or len(cells) < 6:
                    continue
                if "Batter" in cells[0].text:
                    continue

                name_el = cells[0].find("span", class_=lambda x: x and "hover:underline" in x)
                batter_name = name_el.text.strip() if name_el else cells[0].text.strip()

                dismissal_el = cells[0].find(class_=lambda x: x and "text-cbTxtSec" in x)
                dismissal = dismissal_el.text.strip() if dismissal_el else "not out"

                try:
                    runs = int(cells[1].text.strip())
                    balls = int(cells[2].text.strip())
                    fours = int(cells[3].text.strip())
                    sixes = int(cells[4].text.strip())
                    sr = float(cells[5].text.strip().replace("-", "0.0"))
                except Exception:
                    continue

                batters.append(BattingRow(
                    batter=batter_name,
                    dismissal=dismissal,
                    runs=runs,
                    balls=balls,
                    fours=fours,
                    sixes=sixes,
                    strike_rate=sr
                ))

            # 2. Parse Bowlers in this inning
            bowl_grids = inn_div.find_all(class_=lambda x: x and "scorecard-bowl-grid" in x)
            for r in bowl_grids:
                cells = r.find_all(recursive=False)
                if not cells or len(cells) < 6:
                    continue
                if "Bowler" in cells[0].text:
                    continue

                name_el = cells[0].find("span", class_=lambda x: x and "hover:underline" in x)
                bowler_name = name_el.text.strip() if name_el else cells[0].text.strip()

                try:
                    overs = float(cells[1].text.strip())
                    maidens = int(cells[2].text.strip())
                    runs = int(cells[3].text.strip())
                    wickets = int(cells[4].text.strip())
                    econ = float(cells[-1].text.strip().replace("-", "0.0"))
                except Exception:
                    continue

                bowlers.append(BowlingRow(
                    bowler=bowler_name,
                    overs=overs,
                    maidens=maidens,
                    runs=runs,
                    wickets=wickets,
                    economy=econ
                ))

            if not batters and not bowlers:
                continue

            team_label = t1_name if idx == 1 else t2_name
            inn_title = f"{team_label} Inning"

            bat_wkts = sum(1 for b in batters if b.dismissal and "not out" not in b.dismissal.lower())
            tot_wkts = bat_wkts
            tot_runs = sum(b.runs for b in batters)
            tot_ovs = max((bo.overs for bo in bowlers), default=0.0)

            # Check if total and extras exist in inn_div
            div_lines = [l.strip() for l in inn_div.get_text('\n').split('\n') if l.strip()]
            for l_i, line in enumerate(div_lines):
                if line.lower() == 'total' and l_i + 1 < len(div_lines):
                    m_tot = re.search(r'(\d+)(?:/(\d+))?\s*(?:\(([\d\.]+)\s*ov\))?', div_lines[l_i + 1])
                    if m_tot:
                        tot_runs = int(m_tot.group(1))
                        if m_tot.group(2):
                            tot_wkts = int(m_tot.group(2))
                        else:
                            tot_wkts = bat_wkts
                        if m_tot.group(3):
                            tot_ovs = float(m_tot.group(3))
                    break

            inn_extras = ExtrasInfo(raw="0", total=0, wides=0, no_balls=0, byes=0, leg_byes=0)
            for l_i, line in enumerate(div_lines):
                if line.lower() == 'extras' and l_i + 1 < len(div_lines):
                    m_ex = re.search(r'(\d+)', div_lines[l_i + 1])
                    if m_ex:
                        inn_extras.total = int(m_ex.group(1))
                        inn_extras.raw = str(m_ex.group(1))
                    break

            header_summary = f"{inn_title} {tot_runs}/{tot_wkts} ({tot_ovs} ov)"

            inn = Inning(
                inning_name=inn_title,
                header_summary=header_summary,
                batting=batters,
                bowling=bowlers,
                extras=inn_extras,
                total=TotalInfo(raw=f"{tot_runs}/{tot_wkts}", overs=f"({tot_ovs} ov)"),
                ball_by_ball=[b for b in all_balls if str(idx) in b.inning_name] if any(str(idx) in b.inning_name for b in all_balls) else (all_balls if idx == len(inn_divs) else [])
            )
            innings.append(inn)

        return innings, all_partnerships

    def _parse_commentary(self, soup: BeautifulSoup) -> List[BallByBallEvent]:
        events: List[BallByBallEvent] = []

        # Find commentary ball items
        # Over tags have class '!min-w-[1.5rem]' or 'text-center'
        over_spans = soup.find_all(string=re.compile(r'^\d+\.\d+$'))

        for o_span in over_spans:
            over_str = o_span.strip()
            parts = over_str.split('.')
            try:
                o_num = int(parts[0])
                b_num = int(parts[1])
            except ValueError:
                continue

            # Find parent row container
            row = o_span.parent
            for _ in range(5):
                if row and row.name == "div" and len(row.find_all(recursive=False)) >= 2:
                    break
                if row.parent:
                    row = row.parent

            # Look for outcome badge and commentary text in row
            row_text = row.text.strip() if row else ""
            comm_text = row_text

            # Check outcome
            outcome = "0"
            is_wicket = False
            is_four = False
            is_six = False
            runs = 0

            badge = row.find(class_=lambda x: x and ("rounded" in x or "badge" in x or "font-bold" in x)) if row else None
            if badge:
                outcome = badge.text.strip()

            if "W" in outcome or "OUT" in comm_text:
                is_wicket = True
            if "4" in outcome or "FOUR" in comm_text:
                is_four = True
                runs = 4
            elif "6" in outcome or "SIX" in comm_text:
                is_six = True
                runs = 6
            elif outcome.isdigit():
                runs = int(outcome)

            # Extract bowler & batter from comm_text e.g. "Hector to Hunter, 1 run"
            bowler = ""
            batter = ""
            m_bowler = re.search(r'([A-Za-z\s]+)\s+to\s+([A-Za-z\s]+),', comm_text)
            if m_bowler:
                bowler = m_bowler.group(1).strip()
                batter = m_bowler.group(2).strip()

            events.append(BallByBallEvent(
                inning_name="Inning",
                over_str=over_str,
                over_num=o_num,
                ball_num=b_num,
                runs=runs,
                bowler=bowler,
                batter=batter,
                outcome=outcome,
                commentary_text=comm_text,
                is_four=is_four,
                is_six=is_six,
                is_wicket=is_wicket
            ))

        return events
