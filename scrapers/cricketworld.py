import re
import asyncio
from typing import List, Dict, Any, Tuple
from bs4 import BeautifulSoup
from core.base_scraper import BaseScraper
from core.browser_manager import BrowserManager
from core.models import (
    MatchMetadata, BattingRow, BowlingRow, ExtrasInfo,
    TotalInfo, FallOfWicket, BatterContribution, Partnership,
    BallByBallEvent, Inning, MatchData
)
from scrapers import register_scraper

@register_scraper(["cricketworld.com", "www.cricketworld.com"])
class CricketWorldScraper(BaseScraper):
    """
    Scraper implementation for CricketWorld (cricketworld.com).
    Extracts full match metadata, multi-innings scorecards, extras, fall of wickets,
    DRS reviews, milestone partnerships, and complete ball-by-ball commentary streams.
    """
    @property
    def platform_name(self) -> str:
        return "CricketWorld"

    def extract_match_id(self, url: str) -> str:
        m = re.search(r'/(\d+)(?:[/?#]|$)', url)
        return m.group(1) if m else "unknown"

    def get_scorecard_url(self) -> str:
        url = self.raw_url
        if "/match/scorecard/" in url:
            return url
        for sub in ["/match/live/", "/match/commentary/", "/match/players/", "/match/stats/"]:
            if sub in url:
                return url.replace(sub, "/match/scorecard/")
        return url

    def get_commentary_url(self) -> str:
        url = self.raw_url
        if "/match/commentary/" in url:
            return url
        for sub in ["/match/live/", "/match/scorecard/", "/match/players/", "/match/stats/"]:
            if sub in url:
                return url.replace(sub, "/match/commentary/")
        return url

    async def fetch_and_parse(self, browser_mgr: BrowserManager) -> MatchData:
        scorecard_url = self.get_scorecard_url()
        commentary_url = self.get_commentary_url()

        print(f"[{self.platform_name}] 1/2 Fetching full scorecard: {scorecard_url}")
        scorecard_html = await browser_mgr.fetch_page_content(
            scorecard_url,
            wait_selector="table.battings, table.table1",
            delay_secs=3.0
        )

        await asyncio.sleep(2)

        print(f"[{self.platform_name}] 2/2 Fetching ball-by-ball commentary: {commentary_url}")
        commentary_html = await browser_mgr.fetch_page_content(
            commentary_url,
            wait_selector=".comment-ball",
            delay_secs=4.0
        )

        # Parse both DOMs
        metadata, innings, partnerships, day_events = self._parse_scorecard_html(scorecard_html)
        ball_by_ball_events = self._parse_commentary_html(commentary_html)

        # Merge ball-by-ball events into their corresponding innings
        for inn in innings:
            inn_clean = inn.inning_name.lower().replace("innings", "inning")
            inn_balls = [
                b for b in ball_by_ball_events
                if b.inning_name.lower().replace("innings", "inning") == inn_clean
            ]
            inn.ball_by_ball = inn_balls

        return MatchData(
            metadata=metadata,
            innings=innings,
            partnerships=partnerships,
            all_balls=ball_by_ball_events,
            day_by_day_events=day_events
        )

    def _parse_scorecard_html(self, html: str) -> Tuple[MatchMetadata, List[Inning], List[Partnership], List[Dict[str, Any]]]:
        soup = BeautifulSoup(html, "html.parser")

        # Scope metadata extraction to the match-center / content container to avoid global header navbar/tickers
        match_center = (
            soup.find(class_=lambda c: c and "match-center" in str(c).lower())
            or soup.find(id="content")
            or soup.find("main")
            or soup
        )

        # 1. Metadata
        title_tag = match_center.find("h1") or soup.find("h1")
        match_title = title_tag.get_text(strip=True) if title_tag else "Match"

        series_tag = match_center.find("a", href=lambda h: h and "/series/" in h) or soup.find("a", href=lambda h: h and "/series/" in h)
        series_name = series_tag.get_text(strip=True) if series_tag else ""

        venue_tag = match_center.find(class_=lambda c: c and "venue" in str(c).lower())
        venue = venue_tag.get_text(strip=True) if venue_tag else ""

        toss_tag = match_center.find(class_=lambda c: c and "toss" in str(c).lower())
        toss = toss_tag.get_text(strip=True) if toss_tag else ""

        status_tag = match_center.find(class_=lambda c: c and "status" in str(c).lower() and "status_note" not in str(c).lower())
        status = status_tag.get_text(strip=True) if status_tag else ""

        status_note_tag = match_center.find(class_=lambda c: c and "status_note" in str(c).lower())
        status_note = status_note_tag.get_text(strip=True) if status_note_tag else ""

        # Determine whether match is actively live or concluded
        status_clean = (status + " " + status_note).lower()
        ended_keywords = ["won by", "result", "completed", "match over", "abandoned", "no result", "cancelled", "concluded", "match tied"]
        if any(k in status_clean for k in ended_keywords):
            is_live = False
        else:
            is_live = any(k in status_clean for k in ["live", "need", "trail", "lead", "stumps", "break", "delay", "elected to", "in progress"])

        metadata = MatchMetadata(
            match_id=self.match_id,
            match_title=match_title,
            series=series_name,
            venue=venue,
            toss=toss,
            status=status,
            status_note=status_note,
            source_url=self.raw_url,
            source_platform=self.platform_name,
            is_live=is_live
        )

        innings = []
        partnerships = []
        day_events = []

        accordions = soup.find_all("div", class_=lambda c: c and "accordion" in str(c).split())
        for acc in accordions:
            btn = acc.find("div", class_=lambda c: c and "accordion-btn" in str(c).split())
            btn_text = btn.get_text(" ", strip=True) if btn else ""

            if "inning" in btn_text.lower():
                content = acc.find("div", class_=lambda c: c and "accordion-content" in str(c).split())
                if content:
                    inn = self._parse_single_inning(btn_text, content)
                    if inn.batting or inn.bowling or (inn.total and inn.total.raw):
                        innings.append(inn)
            elif "day-" in btn_text.lower():
                content = acc.find("div", class_=lambda c: c and "accordion-content" in str(c).split())
                if content:
                    day_data, day_parts = self._parse_day_events(btn_text, content)
                    day_events.append(day_data)
                    partnerships.extend(day_parts)

        return metadata, innings, partnerships, day_events

    def _parse_single_inning(self, header_text: str, content_div) -> Inning:
        score_match = re.search(r'(\d+/\d+)\s*\(([\d\.]+)\s*ov\)', header_text)
        total_score = score_match.group(1) if score_match else ""
        overs = score_match.group(2) if score_match else ""

        name_match = re.match(r'^(.*?)\s+[A-Z]{2,4}\s+\d', header_text)
        inning_name = name_match.group(1).strip() if name_match else header_text.split(" 133/")[0].strip()

        batting_table = content_div.find("table", class_=lambda c: c and "battings" in str(c).lower())
        bowling_table = content_div.find("table", class_=lambda c: c and "bowlings" in str(c).lower())

        batters = []
        extras_info = ExtrasInfo(raw="")
        total_info = TotalInfo(raw=total_score, overs=overs)

        if batting_table:
            for tr in batting_table.find_all("tr"):
                tds = tr.find_all(["th", "td"])
                row_text = [td.get_text(" ", strip=True) for td in tds]
                if not row_text or row_text[0].lower() in ["batters", "batter"]:
                    continue

                if row_text[0].lower() == "extra":
                    extra_str = row_text[1] if len(row_text) > 1 else ""
                    extras_info.raw = extra_str
                    tot_m = re.match(r'^(\d+)', extra_str)
                    if tot_m: extras_info.total = int(tot_m.group(1))
                    b_m = re.search(r'b\s*(\d+)', extra_str)
                    if b_m: extras_info.byes = int(b_m.group(1))
                    w_m = re.search(r'w\s*(\d+)', extra_str)
                    if w_m: extras_info.wides = int(w_m.group(1))
                    nb_m = re.search(r'nb\s*(\d+)', extra_str)
                    if nb_m: extras_info.no_balls = int(nb_m.group(1))
                    lb_m = re.search(r'lb\s*(\d+)', extra_str)
                    if lb_m: extras_info.leg_byes = int(lb_m.group(1))
                    p_m = re.search(r'p\s*(\d+)', extra_str)
                    if p_m: extras_info.penalty = int(p_m.group(1))
                    continue

                if row_text[0].lower() == "total":
                    total_info.raw = row_text[1] if len(row_text) > 1 else total_score
                    continue

                if len(tds) >= 6:
                    name = tds[0].get_text(" ", strip=True)
                    dismissal = tds[1].get_text(" ", strip=True)
                    if not dismissal:
                        how_out = tr.find(class_=lambda c: c and "how_out" in str(c))
                        if how_out:
                            dismissal = how_out.get_text(" ", strip=True)

                    runs = tds[2].get_text(strip=True) if len(tds) > 2 else "0"
                    balls = tds[3].get_text(strip=True) if len(tds) > 3 else "0"
                    fours = tds[4].get_text(strip=True) if len(tds) > 4 else "0"
                    sixes = tds[5].get_text(strip=True) if len(tds) > 5 else "0"
                    sr = tds[6].get_text(strip=True) if len(tds) > 6 else "0.00"

                    batters.append(BattingRow(
                        batter=name,
                        dismissal=dismissal if dismissal else "not out" if "not out" in name.lower() else "did not bat",
                        runs=int(runs) if runs.isdigit() else 0,
                        balls=int(balls) if balls.isdigit() else 0,
                        fours=int(fours) if fours.isdigit() else 0,
                        sixes=int(sixes) if sixes.isdigit() else 0,
                        strike_rate=float(sr) if sr.replace('.', '', 1).isdigit() else 0.0
                    ))

        bowlers = []
        if bowling_table:
            for tr in bowling_table.find_all("tr"):
                tds = tr.find_all(["th", "td"])
                row_text = [td.get_text(" ", strip=True) for td in tds]
                if not row_text or row_text[0].lower() in ["bowlers", "bowler"]:
                    continue
                if len(tds) >= 6:
                    b_name = tds[0].get_text(" ", strip=True)
                    overs_val = tds[1].get_text(strip=True)
                    maidens = tds[2].get_text(strip=True)
                    runs_conc = tds[3].get_text(strip=True)
                    wickets = tds[4].get_text(strip=True)
                    econ = tds[5].get_text(strip=True)

                    bowlers.append(BowlingRow(
                        bowler=b_name,
                        overs=float(overs_val) if overs_val.replace('.', '', 1).isdigit() else 0.0,
                        maidens=int(maidens) if maidens.isdigit() else 0,
                        runs=int(runs_conc) if runs_conc.isdigit() else 0,
                        wickets=int(wickets) if wickets.isdigit() else 0,
                        economy=float(econ) if econ.replace('.', '', 1).isdigit() else 0.0
                    ))

        fows = []
        fow_div = content_div.find("div", class_=lambda c: c and "fow" in str(c).lower())
        if fow_div:
            fow_text = fow_div.get_text(" ", strip=True)
            matches = re.findall(r'(\d+)-(\d+)\s*\(\s*([^-\)]+?)\s*-\s*([\d\.]+)\s*ov\s*\)', fow_text)
            for m in matches:
                fows.append(FallOfWicket(
                    wicket_num=int(m[0]),
                    team_score=int(m[1]),
                    batter_out=m[2].strip(),
                    over=float(m[3])
                ))

        reviews = {}
        rev_div = content_div.find(lambda t: t.name == "div" and "Batting Reviews" in t.get_text())
        if rev_div:
            txt = rev_div.get_text(" ", strip=True)
            tot = re.search(r'Total Reviews:\s*(\d+)', txt)
            suc = re.search(r'Review Success:\s*(\d+)', txt)
            reviews = {
                "total_reviews": int(tot.group(1)) if tot else None,
                "review_success": int(suc.group(1)) if suc else None
            }

        return Inning(
            inning_name=inning_name,
            header_summary=header_text,
            batting=batters,
            bowling=bowlers,
            extras=extras_info,
            total=total_info,
            fall_of_wickets=fows,
            reviews=reviews
        )

    def _parse_day_events(self, day_header: str, content_div) -> Tuple[Dict[str, Any], List[Partnership]]:
        events = []
        partnerships = []
        for child in content_div.find_all("div", recursive=False):
            txt = child.get_text(" ", strip=True)
            if not txt:
                continue
            events.append(txt)

            part_m = re.match(r'(\d+)\s+run partnership of\s+(\d+)\s+balls,\s*([^,]+?)\s+(\d+)\((\d+)\)\s*runs?,\s*([^,]+?)\s+(\d+)\((\d+)\)\s*runs?', txt, re.IGNORECASE)
            if part_m:
                partnerships.append(Partnership(
                    milestone_runs=int(part_m.group(1)),
                    balls=int(part_m.group(2)),
                    batter_1=BatterContribution(
                        name=part_m.group(3).strip(),
                        runs=int(part_m.group(4)),
                        balls=int(part_m.group(5))
                    ),
                    batter_2=BatterContribution(
                        name=part_m.group(6).strip(),
                        runs=int(part_m.group(7)),
                        balls=int(part_m.group(8))
                    ),
                    raw_text=txt,
                    source_day=day_header
                ))

        day_data = {"day": day_header, "events": events}
        return day_data, partnerships

    def _parse_commentary_html(self, html: str) -> List[BallByBallEvent]:
        soup = BeautifulSoup(html, "html.parser")
        events: List[BallByBallEvent] = []

        accordions = soup.find_all("div", class_=lambda c: c and "accordion" in str(c).split())
        if accordions:
            for acc in accordions:
                btn = acc.find("div", class_=lambda c: c and "accordion-btn" in str(c).split())
                btn_text = btn.get_text(" ", strip=True) if btn else ""

                name_match = re.match(r'^(.*?)\s+[A-Z]{2,4}\s+\d', btn_text)
                inning_name = name_match.group(1).strip() if name_match else btn_text.split(" 133/")[0].strip()
                if not inning_name:
                    inning_name = "Inning"

                content = acc.find("div", class_=lambda c: c and "accordion-content" in str(c).split())
                search_scope = content if content else acc
                balls = self._extract_balls_from_container(search_scope, inning_name)
                events.extend(balls)

        if not events:
            balls = self._extract_balls_from_container(soup, "Match Inning")
            events.extend(balls)

        return events

    def _extract_balls_from_container(self, container, inning_name: str) -> List[BallByBallEvent]:
        balls: List[BallByBallEvent] = []
        comment_balls = container.find_all(class_=lambda c: c and "comment-ball" in str(c).split())

        for cb in comment_balls:
            cls_list = cb.get("class", [])
            text_blocks = [s.strip() for s in cb.stripped_strings]
            raw_text = " ".join(text_blocks)

            runs = 0
            for cls in cls_list:
                if cls.startswith("run-"):
                    r_val = cls.replace("run-", "")
                    if r_val.isdigit():
                        runs = int(r_val)
                    elif r_val.lower() == "w":
                        runs = 0

            over_str = ""
            over_num = 0
            ball_num = 0
            over_match = re.search(r'\b(\d+)\.(\d+)\b', raw_text)
            if over_match:
                over_str = f"{over_match.group(1)}.{over_match.group(2)}"
                over_num = int(over_match.group(1))
                ball_num = int(over_match.group(2))

            bowler = ""
            batter = ""
            outcome = ""
            desc = raw_text

            bt_bw_match = re.search(r'(?:[\d\.]+\s+)?([A-Za-z\s\.\'-]+)\s+to\s+([A-Za-z\s\.\'-]+),\s*([^,]+),(.*)', raw_text)
            if bt_bw_match:
                bowler = bt_bw_match.group(1).strip()
                bowler = re.sub(r'^\d+\s*(\d+\.\d+)?\s*', '', bowler).strip()
                batter = bt_bw_match.group(2).strip()
                outcome = bt_bw_match.group(3).strip()
                desc = bt_bw_match.group(4).strip()
            else:
                parts = raw_text.split(",")
                if len(parts) >= 2:
                    outcome = parts[0]
                    desc = ", ".join(parts[1:])

            is_four = runs == 4 or "FOUR" in raw_text.upper() or "four" in outcome.lower()
            is_six = runs == 6 or "SIX" in raw_text.upper() or "six" in outcome.lower()
            is_wicket = "W" in cls_list or "OUT" in raw_text.upper() or "wicket" in outcome.lower() or "run out" in outcome.lower() or "caught" in outcome.lower()
            is_extra = any(k in raw_text.lower() for k in ["wide", "no ball", "leg bye", "bye"])
            extra_type = ""
            if "wide" in raw_text.lower(): extra_type = "wide"
            elif "no ball" in raw_text.lower(): extra_type = "no_ball"
            elif "leg bye" in raw_text.lower(): extra_type = "leg_bye"
            elif "bye" in raw_text.lower(): extra_type = "bye"

            balls.append(BallByBallEvent(
                inning_name=inning_name,
                over_str=over_str,
                over_num=over_num,
                ball_num=ball_num,
                runs=runs,
                bowler=bowler,
                batter=batter,
                outcome=outcome,
                commentary_text=desc,
                is_four=is_four,
                is_six=is_six,
                is_wicket=is_wicket,
                is_extra=is_extra,
                extra_type=extra_type,
                raw_event=raw_text
            ))

        return balls
