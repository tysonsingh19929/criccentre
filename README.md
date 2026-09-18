# CricCenter — Live Cricket Platform & Real-Time Match Center

A high-performance live cricket scoring platform and scraper framework featuring an 80% Cricbuzz / 20% CREX professional aesthetic, real-time ball-by-ball commentary feeds, tournament standings, global schedules, series, teams, ICC rankings, news reader, and the Hermes Brain event mapping console.

---

## 🚀 Instant Vercel Deployment (Mobile & Web)

CricCenter is configured out-of-the-box for **Vercel Serverless & Static Deployment**:

1. Fork or import this repository (criccentre) into [Vercel](https://vercel.com).
2. Set the framework preset to **Other** (Root directory: ./).
3. Click **Deploy**!
4. Access https://your-project.vercel.app on desktop or mobile:
   - **Live Scores**: /live-scores or /
   - **Match Center**: /match/<id> (e.g. /match/13Q2)
   - **Full Schedule**: /schedule
   - **Series Directory**: /series
   - **Teams**: /teams
   - **ICC Rankings**: /rankings
   - **Cricket News**: /news
   - **Admin Console**: /admin

---

## ⚡ Local & VPS Live Scraping Daemon

Run the scraping daemon locally or on a VPS (Linux/Windows) to stream live ball-by-ball updates and sync scorecards:

### 1. Install Dependencies
`ash
pip install -r requirements-scraper.txt
playwright install chromium
`

### 2. Start the Master Engine
`ash
python main.py --file urls.txt --interval 10
`
- List any match URLs from **Cricinfo**, **Cricbuzz**, or **CREX** in urls.txt.
- Hermes Brain will self-heal all scorecard extras, strike rates, fall-of-wickets, and stream live ball updates.
- Web server starts locally at http://localhost:8080.

---

## 🌟 Key Features

1. **Cricbuzz & CREX Match Center UI**:
   - **CREX Hero Ball Outcome**: Prominent last-ball outcome bubble, current over progress, ball dots trail, CRR, and toss.
   - **On-Crease Batters & Bowler Figures**: Active not-out batters with runs, balls, 4s, 6s, and SR.
   - **Cricbuzz Over End Cards**: Clean divider cards every 6 deliveries with cumulative scores and bowler figures.
   - **Recent Overs Strip**: Over-by-over breakdown with numerical tokens.

2. **Unified Navigation & Mega-Drawer**:
   - Filter matches across International, League, Domestic, and Women categories.
   - Intelligent lifecycle automation: Concluded matches show **Result** (no stale LIVE badges).

3. **Hermes Brain Admin Console**:
   - Ingests events and series catalog from CREX.
   - 1-click cross-platform mapping for Cricinfo, Cricbuzz, and CREX URLs.

4. **Dedicated Sections**:
   - Full Multi-Innings Scorecards with extras breakdown.
   - Over-by-Over tab with team switcher.
   - Tournament Points Table.
   - Key Partnerships with numerical boundary counts.
   - Impact Overs tracking.
