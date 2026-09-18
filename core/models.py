from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any

@dataclass
class MatchMetadata:
    match_id: str
    match_title: str
    series: str
    venue: str
    toss: str
    status: str
    status_note: str
    source_url: str
    source_platform: str
    is_live: bool = True
    match_impact_overs: int = 0

@dataclass
class BattingRow:
    batter: str
    dismissal: str
    runs: int
    balls: int
    fours: int
    sixes: int
    strike_rate: float

@dataclass
class BowlingRow:
    bowler: str
    overs: float
    maidens: int
    runs: int
    wickets: int
    economy: float
    dot_balls: int = 0

@dataclass
class ExtrasInfo:
    raw: str
    byes: int = 0
    wides: int = 0
    no_balls: int = 0
    leg_byes: int = 0
    penalty: int = 0
    total: int = 0

@dataclass
class TotalInfo:
    raw: str
    overs: str
    run_rate: str = ""

@dataclass
class FallOfWicket:
    wicket_num: int
    team_score: int
    batter_out: str
    over: float

@dataclass
class BatterContribution:
    name: str
    runs: int
    balls: int

@dataclass
class Partnership:
    milestone_runs: int
    balls: int
    batter_1: BatterContribution
    batter_2: BatterContribution
    raw_text: str
    source_day: str = ""
    fours: int = 0
    sixes: int = 0
    boundary_runs: int = 0
    boundary_str: str = ""

@dataclass
class BallByBallEvent:
    inning_name: str
    over_str: str              # e.g. "33.4"
    over_num: int              # 33
    ball_num: int              # 4
    runs: int                  # 0, 1, 2, 4, 6...
    bowler: str
    batter: str
    outcome: str               # "no run", "1 run", "FOUR", "SIX", "OUT", etc.
    commentary_text: str
    is_four: bool = False
    is_six: bool = False
    is_wicket: bool = False
    is_extra: bool = False
    extra_type: str = ""       # "wide", "no_ball", "bye", "leg_bye"
    raw_event: str = ""

@dataclass
class Inning:
    inning_name: str
    header_summary: str
    batting: List[BattingRow] = field(default_factory=list)
    bowling: List[BowlingRow] = field(default_factory=list)
    extras: Optional[ExtrasInfo] = None
    total: Optional[TotalInfo] = None
    fall_of_wickets: List[FallOfWicket] = field(default_factory=list)
    reviews: Dict[str, Any] = field(default_factory=dict)
    ball_by_ball: List[BallByBallEvent] = field(default_factory=list)
    impact_overs_count: int = 0
    impact_overs_list: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class MatchData:
    metadata: MatchMetadata
    innings: List[Inning] = field(default_factory=list)
    partnerships: List[Partnership] = field(default_factory=list)
    all_balls: List[BallByBallEvent] = field(default_factory=list)
    day_by_day_events: List[Dict[str, Any]] = field(default_factory=list)
    hermes_analysis: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'MatchData':
        meta_d = d.get("metadata", {})
        meta = MatchMetadata(
            match_id=str(meta_d.get("match_id", "")),
            match_title=meta_d.get("match_title", ""),
            series=meta_d.get("series", ""),
            venue=meta_d.get("venue", ""),
            toss=meta_d.get("toss", ""),
            status=meta_d.get("status", ""),
            status_note=meta_d.get("status_note", ""),
            source_url=meta_d.get("source_url", ""),
            source_platform=meta_d.get("source_platform", ""),
            is_live=meta_d.get("is_live", False),
            match_impact_overs=meta_d.get("match_impact_overs", 0)
        )

        innings = []
        for inn_d in d.get("innings", []):
            batting = [BattingRow(**b) for b in inn_d.get("batting", [])]
            bowling = [BowlingRow(**bo) for bo in inn_d.get("bowling", [])]
            extras = ExtrasInfo(**inn_d["extras"]) if inn_d.get("extras") else None
            total = TotalInfo(**inn_d["total"]) if inn_d.get("total") else None
            fow = [FallOfWicket(**f) for f in inn_d.get("fall_of_wickets", [])]
            bball = [BallByBallEvent(**bb) for bb in inn_d.get("ball_by_ball", [])]
            innings.append(Inning(
                inning_name=inn_d.get("inning_name", ""),
                header_summary=inn_d.get("header_summary", ""),
                batting=batting,
                bowling=bowling,
                extras=extras,
                total=total,
                fall_of_wickets=fow,
                reviews=inn_d.get("reviews", {}),
                ball_by_ball=bball,
                impact_overs_count=inn_d.get("impact_overs_count", 0),
                impact_overs_list=inn_d.get("impact_overs_list", [])
            ))

        partnerships = []
        for p_d in d.get("partnerships", []):
            b1 = BatterContribution(**p_d.get("batter_1", {"name": "", "runs": 0, "balls": 0}))
            b2 = BatterContribution(**p_d.get("batter_2", {"name": "", "runs": 0, "balls": 0}))
            partnerships.append(Partnership(
                milestone_runs=p_d.get("milestone_runs", 0),
                balls=p_d.get("balls", 0),
                batter_1=b1,
                batter_2=b2,
                raw_text=p_d.get("raw_text", ""),
                source_day=p_d.get("source_day", ""),
                fours=p_d.get("fours", 0),
                sixes=p_d.get("sixes", 0),
                boundary_runs=p_d.get("boundary_runs", 0),
                boundary_str=p_d.get("boundary_str", "")
            ))

        all_balls = [BallByBallEvent(**bb) for bb in d.get("all_balls", [])]

        return cls(
            metadata=meta,
            innings=innings,
            partnerships=partnerships,
            all_balls=all_balls,
            day_by_day_events=d.get("day_by_day_events", []),
            hermes_analysis=d.get("hermes_analysis", {})
        )
