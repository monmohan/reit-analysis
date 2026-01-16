#!/usr/bin/env python3
"""
Quarterly Report Discovery Tool

Takes a REIT ticker as input, discovers its financial results page and quarterly PDF patterns,
and writes the result to config/reit_ir_urls.json.

Usage:
    uv run python tools/research_ir_urls.py C38U.SI
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs, unquote

import yfinance as yf
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


# Keywords to identify financial results / investor relations pages
IR_KEYWORDS = [
    "investor relations",
    "investor-relations",
    "investors",
    "/ir/",
    "/ir.",
    "financial results",
    "financial-results",
    "financials",
    "financial information",
    "quarterly",
    "results",
]

# Keywords to identify quarterly report PDFs
QUARTERLY_REPORT_KEYWORDS = [
    "business update",
    "business-update",
    "results",
    "financial results",
    "quarterly",
]

# Regex patterns for quarterly reports
# SGX-style: 20251028_070012_C38U_F3Q4RGWG1OAFZ3VC.1.pdf
QUARTERLY_REPORT_PATTERNS = [
    r"^\d{8}_\d{6}_[A-Z0-9]+_[A-Z0-9]+\.\d+\.pdf$",  # SGX announcement style
    r"^\d{8}_\d{6}_[A-Z0-9]+_[A-Z0-9]+\.pdf$",       # SGX without extension number
]

# Keywords to exclude (annual reports, circulars, etc.)
EXCLUDE_KEYWORDS = [
    "annual report",
    "annual-report",
    "annualreport",
    "circular",
    "notice",
    "agm",
    "egm",
    "sustainability",
    "proxy",
    "ar20",  # ar2024.pdf style annual reports
]


def get_company_info(ticker: str) -> dict:
    """Get company name and website from Yahoo Finance."""
    print(f"Fetching company info for {ticker}...")

    stock = yf.Ticker(ticker)
    info = stock.info

    company_name = info.get("longName") or info.get("shortName")
    website = info.get("website")

    if not company_name:
        raise ValueError(f"Could not find company name for ticker {ticker}")

    print(f"  Company: {company_name}")
    print(f"  Website: {website or 'Not found'}")

    return {
        "name": company_name,
        "website": website,
    }


def find_ir_links(page, base_url: str) -> list[str]:
    """Find links that look like investor relations pages."""
    ir_links = []

    # Get all links on the page
    links = page.query_selector_all("a[href]")

    for link in links:
        try:
            href = link.get_attribute("href")
            text = (link.inner_text() or "").lower()

            if not href:
                continue

            href_lower = href.lower()

            # Check if link text or URL contains IR keywords
            for keyword in IR_KEYWORDS:
                if keyword in text or keyword in href_lower:
                    # Convert relative URL to absolute
                    full_url = urljoin(base_url, href)
                    if full_url not in ir_links:
                        ir_links.append(full_url)
                    break
        except Exception:
            continue

    return ir_links


def resolve_tracker_url(url: str) -> str:
    """
    Resolve tracker.pl redirect URLs to get the actual PDF URL.

    Example input:
    https://ir.listedcompany.com/tracker.pl?...&redirect=https%3A%2F%2F...%2FFPL_Annual_Report_2025.pdf

    Returns the decoded redirect URL, or the original URL if not a tracker URL.
    """
    if "tracker.pl" not in url:
        return url

    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        if "redirect" in params:
            # URL-decode the redirect parameter
            redirect_url = unquote(params["redirect"][0])
            return redirect_url
    except Exception:
        pass

    return url


def find_pdf_links(page, base_url: str) -> list[dict]:
    """Find PDF links on the page."""
    pdf_links = []

    links = page.query_selector_all("a[href]")

    for link in links:
        try:
            href = link.get_attribute("href")
            text = (link.inner_text() or "").strip()

            if not href:
                continue

            # Check if it's a PDF link (direct or via tracker)
            full_url = urljoin(base_url, href)

            # Resolve tracker.pl redirects
            resolved_url = resolve_tracker_url(full_url)

            if ".pdf" in resolved_url.lower():
                pdf_links.append({
                    "url": resolved_url,
                    "text": text,
                    "filename": urlparse(resolved_url).path.split("/")[-1],
                })
        except Exception:
            continue

    return pdf_links


def is_quarterly_report(pdf_info: dict) -> bool:
    """Check if a PDF looks like a quarterly/half-yearly report."""
    filename = pdf_info["filename"].lower()
    text = pdf_info["text"].lower()

    # Check for exclusion keywords first (annual reports, circulars, etc.)
    for keyword in EXCLUDE_KEYWORDS:
        if keyword in filename or keyword in text:
            return False

    # Check for SGX-style quarterly report patterns
    # e.g., 20251028_070012_C38U_F3Q4RGWG1OAFZ3VC.1.pdf
    for pattern in QUARTERLY_REPORT_PATTERNS:
        if re.search(pattern, filename, re.IGNORECASE):
            return True

    # Check for quarterly report keywords in link text
    for keyword in QUARTERLY_REPORT_KEYWORDS:
        if keyword in text:
            return True

    # Check for quarter indicators in filename or text
    quarter_indicators = ["q1", "q2", "q3", "q4", "1q", "2q", "3q", "4q",
                          "half year", "half-year", "1h", "2h", "h1", "h2"]
    for indicator in quarter_indicators:
        if indicator in filename or indicator in text:
            return True

    return False


def extract_years_from_pdfs(pdfs: list[dict]) -> list[str]:
    """Extract year information from PDF filenames."""
    years = []
    for pdf in pdfs:
        matches = re.findall(r"20\d{2}", pdf["filename"])
        years.extend(matches)
    return sorted(set(years), reverse=True)


def generate_pdf_pattern(pdfs: list[dict]) -> str:
    """Generate a regex pattern that matches the quarterly report PDFs."""
    if not pdfs:
        return ""

    # Deduplicate PDFs by URL
    seen_urls = set()
    unique_pdfs = []
    for pdf in pdfs:
        if pdf["url"] not in seen_urls:
            seen_urls.add(pdf["url"])
            unique_pdfs.append(pdf)

    if not unique_pdfs:
        return ""

    # Get the first PDF filename as a template
    filename = unique_pdfs[0]["filename"].lower()

    # Check if this looks like an SGX announcement (random alphanumeric ID)
    # e.g., 20250627_071024_N2IU_A865ED2W965R9N0P.1.pdf
    if re.match(r"^\d{8}_\d{6}_[a-z0-9]+_[a-z0-9]+\.(\d+\.)?pdf$", filename, re.IGNORECASE):
        # For SGX-style filenames, use a generic pattern with ticker
        ticker_match = re.search(r"_([a-z0-9]{3,4})_", filename, re.IGNORECASE)
        if ticker_match:
            ticker = ticker_match.group(1)
            return f"(?i)\\d{{8}}_\\d{{6}}_{ticker}_[A-Z0-9]+\\.(\\d+\\.)?pdf"
        return "(?i)\\d{8}_\\d{6}_[A-Z0-9]+_[A-Z0-9]+\\.(\\d+\\.)?pdf"

    # For regular filenames, replace year with pattern
    pattern = re.sub(r"20\d{2}", r"20\\d{2}", filename)

    # Escape special regex characters except our year pattern
    pattern = re.sub(r"([.\-_])", r"\\\1", pattern)

    # Make it case insensitive
    pattern = f"(?i){pattern}"

    return pattern


# Known Frasers REIT subdomain mappings
FRASERS_REIT_SUBDOMAINS = {
    "BUOU.SI": "flct",  # Frasers Logistics & Commercial Trust
    "J69U.SI": "fct",   # Frasers Centrepoint Trust
}


def get_investor_subdomains(website: str, ticker: str = None) -> list[str]:
    """
    Get potential investor subdomain URLs to try.
    Returns a list of URLs to check.
    """
    subdomains = []
    parsed = urlparse(website)
    domain = parsed.netloc

    # Remove www. prefix if present
    if domain.startswith("www."):
        domain = domain[4:]

    # Standard investor subdomain
    subdomains.append(f"https://investor.{domain}")

    # For Frasers properties, try REIT-specific subdomains
    if "frasersproperty.com" in domain and ticker in FRASERS_REIT_SUBDOMAINS:
        reit_code = FRASERS_REIT_SUBDOMAINS[ticker]
        subdomains.insert(0, f"https://{reit_code}.frasersproperty.com")

    return subdomains


def discover_ir_page(browser, website: str, company_name: str, ticker: str = None) -> dict:
    """
    Discover the financial results page and quarterly report PDFs.

    Returns a dict with:
    - quarterly_url: The financial results page URL
    - quarterly_reports: List of quarterly report PDFs found
    - pdf_pattern: Regex pattern for matching quarterly reports
    - confidence: high/medium/low
    """
    result = {
        "quarterly_url": None,
        "quarterly_reports": [],
        "pdf_pattern": "",
        "confidence": "low",
        "notes": [],
    }

    page = browser.new_page()
    page.set_default_timeout(60000)  # 60 second timeout

    try:
        # Step 0: Try investor subdomains directly (common patterns)
        investor_subdomains = get_investor_subdomains(website, ticker)

        for investor_subdomain in investor_subdomains:
            print(f"Trying subdomain: {investor_subdomain}")
            try:
                page.goto(investor_subdomain, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)

                # Check if we landed on a valid page (not error page)
                title = page.title().lower()
                if page.url and "404" not in title and "error" not in title:
                    print(f"  Found valid subdomain: {page.url}")
                    website = page.url  # Use this as our starting point
                    break
            except Exception as e:
                print(f"  Subdomain not available: {e}")

        # Step 1: Load the homepage
        print(f"Loading homepage: {website}")
        page.goto(website, wait_until="domcontentloaded")
        # Give JS a moment to render
        page.wait_for_timeout(3000)

        # Step 1.5: Try common financial results paths directly
        common_paths = [
            "/financial_results.html",
            "/financial-results.html",
            "/financials.html",
            "/results.html",
            "/quarterly-results.html",
            "/newsroom.html",
        ]
        for path in common_paths:
            url = urljoin(website, path)
            print(f"Trying common path: {url}")
            try:
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)

                if page.url and "404" not in page.title().lower():
                    pdfs = find_pdf_links(page, url)
                    quarterly_pdfs = [p for p in pdfs if is_quarterly_report(p)]
                    if quarterly_pdfs:
                        print(f"  Found {len(quarterly_pdfs)} quarterly reports at {url}")
                        result["quarterly_url"] = url
                        result["quarterly_reports"] = quarterly_pdfs
                        result["pdf_pattern"] = generate_pdf_pattern(quarterly_pdfs)
                        result["confidence"] = "high" if len(quarterly_pdfs) >= 4 else "medium"
                        return result
            except Exception:
                pass

        # Step 2: Find IR links
        print("Searching for investor relations links...")
        ir_links = find_ir_links(page, website)
        print(f"  Found {len(ir_links)} potential IR links")

        if not ir_links:
            result["notes"].append("No IR links found on homepage")
            return result

        # Step 3: Visit each IR link and look for PDFs
        quarterly_reports = []
        best_url = None

        for ir_url in ir_links[:5]:  # Check top 5 IR links
            print(f"  Checking: {ir_url}")
            try:
                page.goto(ir_url, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)

                # Find PDF links
                pdfs = find_pdf_links(page, ir_url)
                print(f"    Found {len(pdfs)} PDF links")

                # Filter for quarterly reports
                q_pdfs = [p for p in pdfs if is_quarterly_report(p)]
                print(f"    Found {len(q_pdfs)} quarterly report PDFs")

                # Debug: show first 5 PDF filenames if no quarterly reports found
                if not q_pdfs and pdfs:
                    print(f"    Sample PDFs: {[p['filename'] for p in pdfs[:5]]}")

                if q_pdfs:
                    if len(q_pdfs) > len(quarterly_reports):
                        quarterly_reports = q_pdfs
                        best_url = ir_url

                    # If we found 4+ quarterly reports, we're confident
                    if len(q_pdfs) >= 4:
                        break

            except PlaywrightTimeout:
                print(f"    Timeout loading {ir_url}")
                result["notes"].append(f"Timeout: {ir_url}")
            except Exception as e:
                print(f"    Error: {e}")
                result["notes"].append(f"Error loading {ir_url}: {str(e)}")

        # Step 4: If no PDFs found on IR pages, look one level deeper
        if not quarterly_reports and ir_links:
            print("No quarterly reports found, checking sub-pages...")
            for ir_url in ir_links[:3]:
                try:
                    page.goto(ir_url, wait_until="domcontentloaded")
                    page.wait_for_timeout(2000)

                    # Look for links to financial results sections
                    sub_links = page.query_selector_all("a[href]")
                    for sub_link in sub_links:
                        href = sub_link.get_attribute("href")
                        text = (sub_link.inner_text() or "").lower()

                        if href and ("financial" in text or "results" in text or "quarterly" in text):
                            sub_url = urljoin(ir_url, href)
                            print(f"  Checking sub-page: {sub_url}")

                            try:
                                page.goto(sub_url, wait_until="domcontentloaded")
                                page.wait_for_timeout(2000)
                                pdfs = find_pdf_links(page, sub_url)
                                q_pdfs = [p for p in pdfs if is_quarterly_report(p)]

                                if q_pdfs:
                                    quarterly_reports = q_pdfs
                                    best_url = sub_url
                                    break
                            except Exception:
                                continue

                    if quarterly_reports:
                        break

                except Exception:
                    continue

        # Step 5: Compile results
        if best_url:
            result["quarterly_url"] = best_url

        if quarterly_reports:
            result["quarterly_reports"] = quarterly_reports[:10]  # Keep top 10
            result["pdf_pattern"] = generate_pdf_pattern(quarterly_reports)

            if len(quarterly_reports) >= 4:
                result["confidence"] = "high"
            elif len(quarterly_reports) >= 2:
                result["confidence"] = "medium"
            else:
                result["confidence"] = "low"

    except Exception as e:
        result["notes"].append(f"Error during discovery: {str(e)}")

    finally:
        page.close()

    return result


def save_to_config(ticker: str, data: dict, config_path: Path):
    """Save or update the config file with the new REIT data."""
    # Load existing config
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
    else:
        config = {}

    # Update with new data
    config[ticker] = data

    # Save
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    print(f"\nSaved to {config_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Discover investor relations URLs for a REIT"
    )
    parser.add_argument("ticker", help="REIT ticker (e.g., C38U.SI)")
    parser.add_argument(
        "--config",
        default="config/reit_ir_urls.json",
        help="Path to config file (default: config/reit_ir_urls.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print results without saving to config",
    )

    args = parser.parse_args()

    # Get the config path relative to the script location
    script_dir = Path(__file__).parent.parent
    config_path = script_dir / args.config

    print(f"=== IR Discovery Research Tool ===")
    print(f"Ticker: {args.ticker}")
    print()

    # Step 1: Get company info from Yahoo Finance
    try:
        company_info = get_company_info(args.ticker)
    except Exception as e:
        print(f"ERROR: Could not get company info: {e}")
        sys.exit(1)

    if not company_info["website"]:
        print("ERROR: No website found in Yahoo Finance. Manual research required.")
        sys.exit(1)

    # Step 2: Discover IR page and PDFs
    print()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        try:
            discovery = discover_ir_page(
                browser,
                company_info["website"],
                company_info["name"],
                ticker=args.ticker,
            )
        finally:
            browser.close()

    # Step 3: Compile results - deduplicate sample PDFs
    seen_urls = set()
    unique_sample_pdfs = []
    for p in discovery["quarterly_reports"]:
        if p["url"] not in seen_urls:
            seen_urls.add(p["url"])
            unique_sample_pdfs.append(p["url"])
            if len(unique_sample_pdfs) >= 5:
                break

    result = {
        "name": company_info["name"],
        "website": company_info["website"],
        "quarterly_url": discovery["quarterly_url"],
        "quarterly_pattern": discovery["pdf_pattern"],
        "sample_pdfs": unique_sample_pdfs,
        "confidence": discovery["confidence"],
        "last_researched": datetime.now().strftime("%Y-%m-%d"),
    }

    if discovery["notes"]:
        result["notes"] = discovery["notes"]

    # Print results
    print()
    print("=== Results ===")
    print(json.dumps(result, indent=2))

    # Step 4: Save to config
    if not args.dry_run:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        save_to_config(args.ticker, result, config_path)
    else:
        print("\n(Dry run - not saved)")

    # Report status
    print()
    if discovery["confidence"] == "high":
        print("SUCCESS: High confidence - found 4+ quarterly reports")
    elif discovery["confidence"] == "medium":
        print("PARTIAL: Medium confidence - found 2-3 quarterly reports")
    else:
        print("FAILED: Low confidence - could not find quarterly reports")
        print("Manual research may be required.")
        sys.exit(1)


if __name__ == "__main__":
    main()
