"""Tests for per-segment revenue extraction (axis disambiguation) + store."""
import pytest

from backend.facts import segments as seg
from backend.facts.models import FilingRef
from backend.facts.segments import segments_from_records, get_segments, upsert_segments


def _filing(form="10-K"):
    return FilingRef(filing_id="F1", cik="0000320193", ticker="AAPL", form_type=form,
                     filing_date="2025-11-01", period_of_report="2025-09-27",
                     fiscal_year=2025, fiscal_period="FY")


REV = "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"
ANNUAL = "duration_2024-09-29_2025-09-27"


def _rec(member, value, dimension, dim_cols, *, concept=REV, period=ANNUAL, dimensioned=True):
    base = {"concept": concept, "numeric_value": value, "period_key": period,
            "is_dimensioned": dimensioned, "dimension": dimension,
            "dimension_member_label": member,
            # all possible axis columns default to "nan"
            "dim_srt_ProductOrServiceAxis": "nan", "dim_srt_StatementGeographicalAxis": "nan",
            "dim_srt_ConsolidationItemsAxis": "nan", "dim_us-gaap_StatementBusinessSegmentsAxis": "nan"}
    base.update(dim_cols)
    return base


def test_single_axis_segments_grouped_and_multidim_skipped():
    records = [
        _rec("iPhone", 209.6e9, "srt:ProductOrServiceAxis",
             {"dim_srt_ProductOrServiceAxis": "aapl:IPhoneMember"}),
        _rec("Services", 109.2e9, "srt:ProductOrServiceAxis",
             {"dim_srt_ProductOrServiceAxis": "us-gaap:ServiceMember"}),
        _rec("U.S.", 151.8e9, "srt:StatementGeographicalAxis",
             {"dim_srt_StatementGeographicalAxis": "country:US"}),
        # multi-axis (operating segment × consolidation) → skipped
        _rec("Americas", 178.4e9, "srt:ConsolidationItemsAxis",
             {"dim_srt_ConsolidationItemsAxis": "us-gaap:OperatingSegmentsMember",
              "dim_us-gaap_StatementBusinessSegmentsAxis": "aapl:AmericasSegmentMember"}),
        # non-revenue concept → skipped
        _rec("Products", 5e9, "srt:ProductOrServiceAxis",
             {"dim_srt_ProductOrServiceAxis": "us-gaap:ProductMember"}, concept="us-gaap:GrossProfit"),
    ]
    facts = segments_from_records(records, _filing())
    by_axis = {}
    for f in facts:
        by_axis.setdefault(f.axis, []).append(f.member)
    assert set(by_axis["Product/Service"]) == {"iPhone", "Services"}
    assert by_axis["Geography"] == ["U.S."]
    assert "Operating Segment" not in by_axis and "Consolidation" not in by_axis  # multi-axis skipped
    assert all(f.member != "Products" or f.axis != "Product/Service" or f.value != 5e9 for f in facts)  # non-revenue skipped


def test_quarterly_rows_dropped_for_10k():
    rec = _rec("iPhone", 50e9, "srt:ProductOrServiceAxis",
               {"dim_srt_ProductOrServiceAxis": "aapl:IPhoneMember"},
               period="duration_2025-06-29_2025-09-27")
    assert segments_from_records([rec], _filing("10-K")) == []


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(seg.settings, "facts_db_path", str(tmp_path / "facts.db"))
    yield


def test_store_roundtrip_grouped(temp_db):
    facts = segments_from_records([
        _rec("iPhone", 209.6e9, "srt:ProductOrServiceAxis",
             {"dim_srt_ProductOrServiceAxis": "aapl:IPhoneMember"}),
        _rec("Services", 109.2e9, "srt:ProductOrServiceAxis",
             {"dim_srt_ProductOrServiceAxis": "us-gaap:ServiceMember"}),
        _rec("U.S.", 151.8e9, "srt:StatementGeographicalAxis",
             {"dim_srt_StatementGeographicalAxis": "country:US"}),
    ], _filing())
    assert upsert_segments(facts) == 3
    res = get_segments("AAPL")
    assert res["period_end"] == "2025-09-27"
    assert [m["member"] for m in res["axes"]["Product/Service"]] == ["iPhone", "Services"]  # value desc
    assert res["axes"]["Geography"][0]["member"] == "U.S."


def test_format_segments():
    from backend.valuation.summary import format_segments
    res = {"period_end": "2025-09-27", "axes": {
        "Geography": [{"member": "U.S.", "value": 151.8e9}, {"member": "China", "value": 64.4e9}]}}
    out = format_segments(res)
    assert "Revenue by segment" in out and "Geography" in out and "U.S. $151.8B" in out
    assert format_segments({"axes": {}}) == ""
