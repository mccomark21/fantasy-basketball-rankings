import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from draft_board import filter_bar  # noqa: E402

DF = pd.DataFrame({
    "team": ["NYK", "BOS", "—", "BOS"],
    "pos": ["C", "SF/PF", "—", "PG/SG"],
})


def test_position_buttons_use_the_yahoo_order():
    html = filter_bar(DF)
    assert re.findall(r'data-pos="(\w+)"', html) == ["PG", "SG", "SF", "PF", "C"]


def test_team_options_are_sorted_with_no_team_last():
    html = filter_bar(DF)
    assert re.findall(r'<option value="([^"]*)"', html) == ["", "BOS", "NYK", "—"]
