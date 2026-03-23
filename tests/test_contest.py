"""Tests for contest box score parsing."""

import unittest
from pathlib import Path

from bs4 import BeautifulSoup

from ncaa_wsoc.contest import extract_scoring_summary

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


class TestExtractScoringSummary(unittest.TestCase):
    def test_minimal_fixture_one_goal(self) -> None:
        html = (_FIXTURES / "box_score_minimal.html").read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "html.parser")
        data = extract_scoring_summary(soup)

        self.assertEqual(data["away_team_id"], "481517")
        self.assertEqual(data["home_team_id"], "481169")
        self.assertEqual(data["game_datetime"], "2019-08-30T14:00:00")
        self.assertEqual(len(data["goals"]), 1)
        g = data["goals"][0]
        self.assertEqual(g["period"], "2")
        self.assertEqual(g["clock"], "82:03")
        self.assertEqual(g["scoring_team_id"], "481517")
        self.assertIn("Emily Hill", g["play_text"])
        self.assertEqual(g["away_score_after"], "1")
        self.assertEqual(g["home_score_after"], "0")

    def test_full_sample_fixture(self) -> None:
        path = _FIXTURES / "box_score_sample.html"
        if not path.exists():
            self.skipTest("box_score_sample.html not present")
        html = path.read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "html.parser")
        data = extract_scoring_summary(soup)

        self.assertEqual(data["away_team_id"], "481517")
        self.assertEqual(data["home_team_id"], "481169")
        self.assertEqual(data["game_datetime"], "2019-08-30T14:00:00")
        self.assertEqual(len(data["goals"]), 1)
        self.assertEqual(data["goals"][0]["scoring_team_id"], "481517")

    def test_no_scoring_section_empty_goals(self) -> None:
        html = "<html><body><p>no scoring</p></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        data = extract_scoring_summary(soup)
        self.assertEqual(data["goals"], [])
        self.assertEqual(data["away_team_id"], "")

    def test_empty_tbody_zero_zero(self) -> None:
        html = (_FIXTURES / "box_score_empty_goals.html").read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "html.parser")
        data = extract_scoring_summary(soup)
        self.assertEqual(data["away_team_id"], "100")
        self.assertEqual(data["home_team_id"], "200")
        self.assertEqual(data["goals"], [])


if __name__ == "__main__":
    unittest.main()
