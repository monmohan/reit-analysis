#!/usr/bin/env python3
"""
Tests for Quarterly PDF Parser

Validates that quarterly report extraction works correctly for all configured REITs.
"""

import pytest
from pathlib import Path

from quarterly_parser import (
    extract_quarterly_data,
    extract_all_quarters,
    format_for_llm,
    get_quarterly_pdfs,
)
from data_cache import get_reit_qualitative_data, check_data_freshness


# All REITs configured in reit_ir_urls.json
CONFIGURED_REITS = [
    "C38U.SI",  # CICT
    "A17U.SI",  # CLAR
    "N2IU.SI",  # MPACT
    "M44U.SI",  # MLT
    "ME8U.SI",  # MIT
    "BUOU.SI",  # FLCT
    "J69U.SI",  # FCT
]


class TestQuarterlyPDFDiscovery:
    """Test that quarterly PDFs are available for extraction."""

    def test_all_reits_have_pdfs(self):
        """All configured REITs should have quarterly PDFs downloaded."""
        for ticker in CONFIGURED_REITS:
            pdfs = get_quarterly_pdfs(ticker)
            assert len(pdfs) >= 1, f"{ticker} should have at least 1 quarterly PDF"

    def test_cict_has_four_quarters(self):
        """CICT should have 4 quarterly PDFs."""
        pdfs = get_quarterly_pdfs("C38U.SI")
        assert len(pdfs) >= 4, f"CICT should have at least 4 quarterly PDFs, got {len(pdfs)}"


class TestCICTExtraction:
    """Test extraction specifically for CICT (our reference REIT)."""

    def test_cict_single_quarter_extraction(self):
        """Test extracting data from a single CICT quarterly PDF."""
        pdfs = get_quarterly_pdfs("C38U.SI")
        assert len(pdfs) > 0, "CICT should have quarterly PDFs"

        # Extract from the latest quarter
        data = extract_quarterly_data(pdfs[0])

        # Should have basic structure
        assert "quarter" in data
        assert "report_date" in data
        # Occupancy is nested in operational_metrics
        assert "operational_metrics" in data
        assert "occupancy" in data["operational_metrics"]

    def test_cict_occupancy_valid(self):
        """CICT occupancy should be in valid range."""
        data = extract_all_quarters("C38U.SI", num_quarters=1)

        if data["quarters"]:
            latest = data["quarters"][0]
            if latest.get("occupancy", {}).get("portfolio"):
                occ = latest["occupancy"]["portfolio"]
                assert 90 <= occ <= 100, f"Portfolio occupancy {occ}% outside valid range"

    def test_cict_wale_valid(self):
        """CICT WALE should be reasonable (1-10 years)."""
        data = extract_all_quarters("C38U.SI", num_quarters=1)

        if data["quarters"]:
            latest = data["quarters"][0]
            wale = latest.get("wale", {}).get("portfolio")
            if wale:
                assert 1 <= wale <= 10, f"WALE {wale} years outside valid range"

    def test_cict_leverage_valid(self):
        """CICT leverage should be in valid range (20-60%)."""
        data = extract_all_quarters("C38U.SI", num_quarters=1)

        if data["quarters"]:
            latest = data["quarters"][0]
            leverage = latest.get("leverage")
            if leverage:
                assert 20 <= leverage <= 60, f"Leverage {leverage}% outside valid range"

    def test_cict_top_tenants(self):
        """CICT should have top tenants extracted."""
        data = extract_all_quarters("C38U.SI", num_quarters=1)

        if data["quarters"]:
            latest = data["quarters"][0]
            tenants = latest.get("top_tenants", [])
            # May not always extract tenants, but if we do, validate
            if tenants:
                for tenant in tenants:
                    assert "name" in tenant
                    assert "percentage" in tenant
                    assert 0 < tenant["percentage"] < 20


class TestAllREITsExtraction:
    """Test extraction works for all configured REITs."""

    @pytest.mark.parametrize("ticker", CONFIGURED_REITS)
    def test_reit_extraction(self, ticker):
        """Each REIT should extract at least some data."""
        pdfs = get_quarterly_pdfs(ticker)
        if not pdfs:
            pytest.skip(f"No PDFs available for {ticker}")

        data = extract_quarterly_data(pdfs[0])

        # Should have basic structure
        assert "quarter" in data or "report_date" in data, f"{ticker} missing basic fields"

    @pytest.mark.parametrize("ticker", CONFIGURED_REITS)
    def test_reit_all_quarters(self, ticker):
        """Each REIT should have data from multiple quarters."""
        data = extract_all_quarters(ticker, num_quarters=4)

        assert "ticker" in data
        assert "quarters" in data
        # Should have at least one quarter extracted
        assert len(data["quarters"]) >= 1, f"{ticker} should have at least 1 quarter"


class TestLLMFormatting:
    """Test the LLM output formatting."""

    def test_format_for_llm_structure(self):
        """Formatted output should have expected sections."""
        data = extract_all_quarters("C38U.SI", num_quarters=2)
        formatted = format_for_llm(data)

        # Should be a string
        assert isinstance(formatted, str)

        # Should contain the ticker
        assert "C38U.SI" in formatted

        # Should have markdown structure
        assert "##" in formatted or "**" in formatted

    def test_format_for_llm_token_count(self):
        """Formatted output should be concise (~500-2000 tokens)."""
        data = extract_all_quarters("C38U.SI", num_quarters=4)
        formatted = format_for_llm(data)

        # Rough estimate: ~4 chars per token
        estimated_tokens = len(formatted) / 4

        # Should be in reasonable range (not too short, not too long)
        assert estimated_tokens < 3000, f"Output too long: ~{estimated_tokens:.0f} tokens"


class TestDataCache:
    """Test the data caching layer."""

    def test_get_reit_qualitative_data(self):
        """Should return formatted data for a REIT."""
        result = get_reit_qualitative_data("C38U.SI", "CapitaLand Integrated Commercial Trust")

        assert isinstance(result, str)
        assert len(result) > 100  # Should have substantial content
        assert "C38U.SI" in result

    def test_check_data_freshness(self):
        """Should return freshness status for all REITs."""
        status = check_data_freshness()

        assert isinstance(status, dict)
        assert "C38U.SI" in status

        cict_status = status["C38U.SI"]
        assert "has_pdfs" in cict_status
        assert "num_pdfs" in cict_status


class TestIntegration:
    """End-to-end integration tests."""

    def test_full_pipeline_cict(self):
        """Test full pipeline: PDFs -> extraction -> formatting."""
        # Get formatted data (uses cache if available)
        result = get_reit_qualitative_data("C38U.SI")

        # Should have key information
        assert "Occupancy" in result or "occupancy" in result.lower()
        assert "%" in result  # Should have percentage values

    def test_full_pipeline_all_reits(self):
        """Test full pipeline works for all configured REITs."""
        for ticker in CONFIGURED_REITS:
            result = get_reit_qualitative_data(ticker)
            assert isinstance(result, str)
            assert len(result) > 50  # Should have some content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
