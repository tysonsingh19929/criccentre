---
name: cricket-ui-engine
description: Expert cricket domain rules, Cricbuzz and CREX live match scorecard layouts, ball-by-ball commentary streaming, and match center UI design principles.
---

# Cricket UI Engine & Domain Knowledge Skill

## Core Principles
1. **Match Center Isolation**:
   - Never serve or fallback to an unrelated match's scorecard.
   - When a match ID is requested, fetch and render only that specific event.

2. **Cricbuzz & CREX Visual Standards**:
   - **CREX Hero Ball Outcome**: Top prominent badge displaying the last ball outcome (0, 1, 4, 6, W), current over (e.g. 19.3 Ov), current over ball dot progression, CRR, and toss info.
   - **Active On-Crease Batters**: Two batters on crease with asterisk (*) on not-out batters, runs, balls, 4s, 6s, and Strike Rate.
   - **Current Bowler**: Overs, maidens, runs, wickets, dot balls, and economy.
   - **Recent Overs Strip**: Over-by-over cards with numerical ball tokens and bowler figure.
   - **Cricbuzz Over End Cards**: Clean divider cards every 6 balls with cumulative team score, batters on crease, and bowler figures.

3. **Match Lifecycle & Mega-Drawer Rules**:
   - Concluded matches (containing 'won by', 'result', 'tied', 'concluded') must display 'Result' pill and never 'LIVE'.
   - Stumps / break in multi-day matches must never blink 'LIVE'.
   - Live pill is strictly reserved for active in-progress matches.

4. **Scraping Priority**:
   - CREX: getSV3 (live real-time socket state), getSC4 (11-player scorecard), getBallFeeds (all deliveries), getWD (dismissals).
   - Cricinfo: Detailed ball-by-ball commentary, wagon wheels, wagon extras.
   - Cricbuzz: Clean mobile over breakdowns and commentary.
