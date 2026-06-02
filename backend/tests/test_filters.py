"""Tests for LanceDB filter validation/escaping (injection hardening)."""
import pytest

from backend.retrieval.filters import (
    build_where_clause,
    sql_quote,
    validate_doc_type,
    validate_quarter,
    validate_ticker,
)


class TestValidateTicker:
    def test_uppercases(self):
        assert validate_ticker("aapl") == "AAPL"

    def test_allows_dot_and_dash(self):
        assert validate_ticker("BRK.B") == "BRK.B"
        assert validate_ticker("RDS-A") == "RDS-A"

    def test_rejects_injection(self):
        with pytest.raises(ValueError):
            validate_ticker("A' OR '1'='1")

    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            validate_ticker("")


class TestValidateDocType:
    def test_allows_known(self):
        assert validate_doc_type("10-K") == "10-K"
        assert validate_doc_type("10-Q") == "10-Q"

    def test_rejects_unknown(self):
        with pytest.raises(ValueError):
            validate_doc_type("'; DROP")


class TestValidateQuarter:
    def test_allows_known(self):
        assert validate_quarter("Q1") == "Q1"
        assert validate_quarter("FY") == "FY"

    def test_rejects_unknown(self):
        with pytest.raises(ValueError):
            validate_quarter("Q9")


class TestSqlQuote:
    def test_wraps_in_single_quotes(self):
        assert sql_quote("AAPL") == "'AAPL'"

    def test_doubles_embedded_quotes(self):
        assert sql_quote("O'Brien") == "'O''Brien'"


class TestBuildWhereClause:
    def test_all_filters(self):
        clause = build_where_clause(ticker="aapl", year=2023, document_type="10-K")
        assert clause == "ticker = 'AAPL' AND filing_year = 2023 AND document_type = '10-K'"

    def test_single_filter(self):
        assert build_where_clause(ticker="AAPL") == "ticker = 'AAPL'"

    def test_no_filters_returns_none(self):
        assert build_where_clause() is None

    def test_year_coerced_to_int(self):
        assert build_where_clause(year="2023") == "filing_year = 2023"

    def test_injection_in_ticker_raises(self):
        with pytest.raises(ValueError):
            build_where_clause(ticker="A' OR '1'='1")
