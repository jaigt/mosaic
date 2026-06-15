"""
Tests for the BeautifulSoup-based SEC-filing table HTML cleaner in
``backend.pipeline.ingest._clean_table_html``.

Covers the observable behavior contract: currency-cell merge, percent-cell
merge, empty-row removal, <thead> detection (numeric = 2+ consecutive digits),
plus robustness on <th> headers, colspans, nested tables, and malformed input.
"""
import re

import pytest
from bs4 import BeautifulSoup

from backend.pipeline.ingest import _clean_table_html


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def _cells(html: str, parent="tr"):
    """Flat list of cell texts for the FIRST matching parent element."""
    el = _soup(html).find(parent)
    return [c.get_text(strip=True) for c in el.find_all(["td", "th"])]


# ── Signature / contract ──────────────────────────────────────────────────────

def test_signature_is_str_to_str():
    out = _clean_table_html("<table><tr><td>Net</td><td>5000</td></tr></table>")
    assert isinstance(out, str)


def test_empty_and_whitespace_returned_as_is():
    assert _clean_table_html("") == ""
    assert _clean_table_html("   ") == "   "
    assert _clean_table_html("\n\t ") == "\n\t "


def test_no_table_returns_input_unchanged():
    html = "<div>no table here</div>"
    assert _clean_table_html(html) == html


# ── Currency-symbol merge ──────────────────────────────────────────────────────

def test_dollar_cell_merged_into_following_number():
    out = _clean_table_html("<table><tr><td>$</td><td>123</td></tr></table>")
    assert _cells(out) == ["$123"]


@pytest.mark.parametrize("sym", ["$", "€", "£", "¥"])
def test_all_currency_symbols_merge(sym):
    out = _clean_table_html(f"<table><tr><td>{sym}</td><td>4,200</td></tr></table>")
    assert _cells(out) == [f"{sym}4,200"]


def test_currency_with_no_following_cell_is_left_alone():
    out = _clean_table_html("<table><tr><td>$</td></tr></table>")
    # Lone $ has no number to merge into and is not empty → row survives.
    assert _cells(out) == ["$"]


# ── Percent merge ───────────────────────────────────────────────────────────────

def test_trailing_percent_cell_merged_into_preceding():
    out = _clean_table_html("<table><tr><td>Revenue</td><td>23</td><td>%</td></tr></table>")
    assert _cells(out) == ["Revenue", "23%"]


def test_percent_with_no_preceding_cell_is_left_alone():
    out = _clean_table_html("<table><tr><td>%</td><td>5</td></tr></table>")
    assert "%" in _cells(out)


# ── Empty-row removal ───────────────────────────────────────────────────────────

def test_fully_empty_row_dropped():
    out = _clean_table_html(
        "<table>"
        "<tr><td></td><td></td></tr>"
        "<tr><td>Net</td><td>5000</td></tr>"
        "</table>"
    )
    rows = _soup(out).find_all("tr")
    assert len(rows) == 1
    assert _cells(out) == ["Net", "5000"]


def test_self_closing_empty_cells_row_dropped():
    out = _clean_table_html(
        "<table><tr><td/><td/></tr><tr><td>A</td><td>1000</td></tr></table>"
    )
    assert len(_soup(out).find_all("tr")) == 1


# ── <thead> detection ───────────────────────────────────────────────────────────

def test_leading_non_numeric_rows_wrapped_in_thead():
    out = _clean_table_html(
        "<table>"
        "<tr><td>Name</td><td>Year</td></tr>"
        "<tr><td>Net</td><td>5000</td></tr>"
        "</table>"
    )
    soup = _soup(out)
    thead = soup.find("thead")
    tbody = soup.find("tbody")
    assert thead is not None and tbody is not None
    assert [c.get_text(strip=True) for c in thead.find_all(["td", "th"])] == ["Name", "Year"]
    assert [c.get_text(strip=True) for c in tbody.find_all(["td", "th"])] == ["Net", "5000"]


def test_single_digit_is_not_numeric_so_row_is_header():
    # "9" is a single digit (< 2 consecutive digits) → still treated as header.
    out = _clean_table_html(
        "<table><tr><td>Note</td><td>9</td></tr><tr><td>Net</td><td>5000</td></tr></table>"
    )
    soup = _soup(out)
    assert [c.get_text(strip=True) for c in soup.find("thead").find_all("td")] == ["Note", "9"]


def test_th_header_row_wrapped_in_thead():
    out = _clean_table_html(
        "<table>"
        "<tr><th>Name</th><th>Year</th></tr>"
        "<tr><td>Net</td><td>5000</td></tr>"
        "</table>"
    )
    soup = _soup(out)
    thead = soup.find("thead")
    assert thead is not None
    assert thead.find_all("th")  # <th> preserved as <th>, not coerced to <td>
    assert [c.get_text(strip=True) for c in thead.find_all("th")] == ["Name", "Year"]


# ── colspan robustness ──────────────────────────────────────────────────────────

def test_colspan_cell_does_not_crash_and_is_preserved():
    out = _clean_table_html(
        "<table>"
        '<tr><td colspan="2">Consolidated</td></tr>'
        "<tr><td>Net</td><td>5000</td></tr>"
        "</table>"
    )
    soup = _soup(out)
    header_cell = soup.find("thead").find("td")
    assert header_cell.get("colspan") == "2"
    assert header_cell.get_text(strip=True) == "Consolidated"


def test_colspan_with_currency_merge():
    out = _clean_table_html(
        "<table>"
        '<tr><td colspan="2">Header</td></tr>'
        "<tr><td>Cash</td><td>$</td><td>1234</td></tr>"
        "</table>"
    )
    # Currency merge still applies in the data row alongside a colspan header.
    assert _cells(out, parent="tbody") == ["Cash", "$1234"]


# ── Nested tables ───────────────────────────────────────────────────────────────

def test_nested_table_is_not_corrupted():
    html = (
        "<table>"
        "<tr><td>Outer"
        "<table><tr><td>$</td><td>9</td></tr></table>"
        "</td><td>123</td></tr>"
        "</table>"
    )
    out = _clean_table_html(html)
    soup = _soup(out)
    # Outer table preserved; the inner table still exists.
    inner = soup.find("table").find("table")
    assert inner is not None
    # Inner $ / 9 cells were NOT merged (we only operate on the outer table).
    inner_cells = [c.get_text(strip=True) for c in inner.find_all("td")]
    assert inner_cells == ["$", "9"]


def test_nested_table_outer_row_still_cleaned():
    # The outer row's own cells should still be subject to thead detection etc.
    html = (
        "<table>"
        "<tr><td>Label</td><td>Detail<table><tr><td>x</td></tr></table></td></tr>"
        "<tr><td>Net</td><td>5000</td></tr>"
        "</table>"
    )
    out = _clean_table_html(html)
    soup = _soup(out)
    # First (non-numeric) outer row is a header.
    assert soup.find("thead") is not None
    assert soup.find("tbody") is not None


# ── Malformed input fallback ────────────────────────────────────────────────────

def test_malformed_html_does_not_raise():
    # Severely broken markup must not throw — at worst return something sane.
    out = _clean_table_html("<table><tr><td>$<<<unbalanced")
    assert isinstance(out, str)


def test_parse_failure_falls_back_to_input(monkeypatch):
    """If parsing raises, the original input is returned unchanged (logged)."""
    import backend.pipeline.ingest as ingest_mod

    class _Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("boom")

    monkeypatch.setattr(ingest_mod, "BeautifulSoup", _Boom, raising=False)
    # Patch the name actually imported inside the function.
    monkeypatch.setattr("bs4.BeautifulSoup", _Boom)

    html = "<table><tr><td>Net</td><td>5000</td></tr></table>"
    assert _clean_table_html(html) == html
