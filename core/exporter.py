import os
import csv
import json
from typing import Dict
from core.models import MatchData

class DataExporter:
    """
    Exports MatchData into complete structured JSON dataset.
    """
    @staticmethod
    def export(match_data: MatchData, output_dir: str = "output") -> Dict[str, str]:
        os.makedirs(output_dir, exist_ok=True)
        m_id = match_data.metadata.match_id
        exported = {}

        # Full Hierarchical JSON Export
        json_file = os.path.join(output_dir, f"match_{m_id}_full.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(match_data.to_dict(), f, indent=2, ensure_ascii=False)
        exported["json"] = json_file

        return exported
