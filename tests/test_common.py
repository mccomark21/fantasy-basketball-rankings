import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from common import name_key, weeks  # noqa: E402


def test_weeks_returns_names_in_order():
    cfg = {"playoffs": {"weeks": [{"name": "wk19"}, {"name": "wk20"}, {"name": "wk21"}]}}
    assert weeks(cfg) == ["wk19", "wk20", "wk21"]


def test_name_key_removes_accents_and_case():
    assert name_key("Nikola Jokić") == "nikola jokic"


def test_name_key_removes_suffixes_and_punctuation():
    assert name_key("Jaren Jackson Jr.") == "jaren jackson"
    assert name_key("Gary Trent III") == "gary trent"
    assert name_key("De'Aaron Fox") == "deaaron fox"


def test_name_key_turns_hyphen_into_space():
    assert name_key("Shai Gilgeous-Alexander") == "shai gilgeous alexander"
