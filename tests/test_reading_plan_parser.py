"""Tests for the master reading plan markdown parser."""
import os
import pytest
from zotero_seed_paper_role import parse_reading_plan

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample_reading_plan.md")


def test_must_read_items_get_must_read_role():
    mapping, _ = parse_reading_plan(FIXTURE)
    assert mapping["KCNG6EMD"] == "must-read"  # Abraham
    assert mapping["DYLS7ZDJ"] == "must-read"  # Tikayat Ray


def test_should_read_items_get_should_read_role():
    mapping, _ = parse_reading_plan(FIXTURE)
    assert mapping["VRYD8YIR"] == "should-read"  # SafeAeroBERT
    assert mapping["U9ZSB48D"] == "should-read"  # Brown


def test_cornerstone_marker_in_role_text_wins_over_tier():
    mapping, _ = parse_reading_plan(FIXTURE)
    assert mapping["NN435K2K"] == "cornerstone"  # Pitcher
    assert mapping["FVZJ44CJ"] == "cornerstone"  # Das


def test_tier1_default_is_supporting():
    mapping, _ = parse_reading_plan(FIXTURE)
    assert mapping["USXDG9JH"] == "supporting"  # Howard (no cornerstone marker in fixture)


def test_statistical_foundations_get_methodological():
    mapping, _ = parse_reading_plan(FIXTURE)
    assert mapping["UXL9VUYL"] == "methodological"  # Gwet
    assert mapping["VBYBXJRW"] == "methodological"  # Sim & Wright


def test_archived_items_get_archived_role():
    mapping, _ = parse_reading_plan(FIXTURE)
    assert mapping["9GRB2BE7"] == "archived"  # Wallace 2023


def test_news_and_web_items_get_reference_only_role():
    mapping, _ = parse_reading_plan(FIXTURE)
    assert mapping["R3AJH6CB"] == "reference-only"


def test_needs_deeper_read_marker_returns_separate_list():
    _, needs_deeper = parse_reading_plan(FIXTURE)
    assert "PRYQIYIH" in needs_deeper  # Ahmadi


def test_parser_handles_empty_file(tmp_path):
    empty = tmp_path / "empty.md"
    empty.write_text("# Empty\n")
    mapping, needs_deeper = parse_reading_plan(str(empty))
    assert mapping == {}
    assert needs_deeper == []
