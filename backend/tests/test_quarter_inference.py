"""Tests for SEC filing quarter inference (edgar_fetcher)."""
import datetime

from backend.ingestion.edgar_fetcher import _calendar_quarter, _infer_quarter


class TestCalendarQuarter:
    def test_q1_months(self):
        assert _calendar_quarter(1) == "Q1"
        assert _calendar_quarter(2) == "Q1"
        assert _calendar_quarter(3) == "Q1"

    def test_q2_months(self):
        assert _calendar_quarter(4) == "Q2"
        assert _calendar_quarter(5) == "Q2"
        assert _calendar_quarter(6) == "Q2"

    def test_q3_months(self):
        assert _calendar_quarter(7) == "Q3"
        assert _calendar_quarter(8) == "Q3"
        assert _calendar_quarter(9) == "Q3"

    def test_q4_months(self):
        assert _calendar_quarter(10) == "Q4"
        assert _calendar_quarter(11) == "Q4"
        assert _calendar_quarter(12) == "Q4"

    def test_boundary_months_are_unambiguous(self):
        # Regression: the old overlapping-range heuristic mislabeled month 4 as
        # Q1 and month 7 as Q2. Non-overlapping calendar quarters must not.
        assert _calendar_quarter(4) == "Q2"
        assert _calendar_quarter(7) == "Q3"


class TestInferQuarter:
    def test_10k_is_always_fy(self):
        assert _infer_quarter("10-K", datetime.date(2024, 3, 28)) == "FY"

    def test_10q_uses_period_end_quarter(self):
        # A 10-Q for a period ending late March -> calendar Q1, regardless of
        # the (later) filing date.
        assert _infer_quarter("10-Q", datetime.date(2026, 3, 28)) == "Q1"
        assert _infer_quarter("10-Q", datetime.date(2025, 6, 30)) == "Q2"
        assert _infer_quarter("10-Q", datetime.date(2025, 9, 27)) == "Q3"

    def test_10q_accepts_isoformat_string(self):
        assert _infer_quarter("10-Q", "2026-03-28") == "Q1"

    def test_10q_missing_period_falls_back_to_unknown(self):
        assert _infer_quarter("10-Q", None) == "Q?"
