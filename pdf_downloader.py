#!/usr/bin/env python3
"""
Quarterly Report Download Module

Downloads quarterly report PDFs for Singapore REITs using the config.

Usage:
    uv run python pdf_downloader.py C38U.SI          # Single REIT (last 4 quarters)
    uv run python pdf_downloader.py --all            # All REITs (parallel)
    uv run python pdf_downloader.py C38U.SI --force  # Force re-download
    uv run python pdf_downloader.py C38U.SI -n 8     # Download last 8 quarters
"""

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs, unquote

import requests
from playwright.sync_api import sync_playwright


# Paths - shared data directory outside repo for persistence
CONFIG_PATH = Path(__file__).parent / "config" / "reit_ir_urls.json"
SHARED_DATA_DIR = Path.home() / "code" / "agents" / "reit-data"
CACHE_DIR = SHARED_DATA_DIR / "pdf_cache"


def load_config() -> dict:
    """Load the REIT IR URLs config."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config not found: {CONFIG_PATH}")

    with open(CONFIG_PATH) as f:
        return json.load(f)


def resolve_tracker_url(url: str) -> str:
    """
    Resolve tracker.pl redirect URLs to get the actual PDF URL.
    """
    if "tracker.pl" not in url:
        return url

    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        if "redirect" in params:
            redirect_url = unquote(params["redirect"][0])
            return redirect_url
    except Exception:
        pass

    return url


def extract_date_from_filename(filename: str) -> str:
    """
    Extract date from quarterly report filename.

    SGX-style filenames start with YYYYMMDD_HHMMSS.
    Keppel-style: kdcreit-1h-2025-results.pdf or kreit-3q-2025-presentation.pdf
    Returns date string like '20251028' for sorting, or empty string if not found.
    """
    # SGX-style: 20251028_070012_C38U_...
    match = re.match(r"^(\d{8})_\d{6}_", filename)
    if match:
        return match.group(1)

    # Fallback: look for any 8-digit date pattern
    match = re.search(r"(202[0-9][01]\d[0-3]\d)", filename)
    if match:
        return match.group(1)

    # Keppel-style: 1q-2025, 2q-2025, 1h-2025, 3q-2025, fy-2024
    # Convert to pseudo-date for sorting (YYYYMMDD format)
    match = re.search(r"(1q|2q|3q|4q|1h|2h|fy)-?(202\d)", filename, re.IGNORECASE)
    if match:
        quarter = match.group(1).lower()
        year = match.group(2)
        # Map quarters to approximate month for sorting
        quarter_month = {
            "1q": "03", "2q": "06", "3q": "09", "4q": "12",
            "1h": "06", "2h": "12", "fy": "12"
        }
        month = quarter_month.get(quarter, "12")
        return f"{year}{month}01"

    return ""


def discover_pdfs(quarterly_url: str, quarterly_pattern: str) -> list[dict]:
    """
    Visit the financial results page and discover all PDFs matching the pattern.

    Returns list of dicts with 'url', 'filename', 'date'.
    """
    pdfs = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(60000)

        try:
            print(f"  Loading: {quarterly_url}")
            page.goto(quarterly_url, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            # Find all PDF links
            links = page.query_selector_all("a[href]")

            for link in links:
                try:
                    href = link.get_attribute("href")
                    if not href:
                        continue

                    # Resolve full URL
                    full_url = urljoin(quarterly_url, href)

                    # Handle tracker.pl redirects
                    resolved_url = resolve_tracker_url(full_url)

                    # Check if it's a PDF
                    if ".pdf" not in resolved_url.lower():
                        continue

                    filename = urlparse(resolved_url).path.split("/")[-1]

                    # Check if it matches the pattern
                    if re.search(quarterly_pattern, filename, re.IGNORECASE):
                        date = extract_date_from_filename(filename)
                        pdfs.append({
                            "url": resolved_url,
                            "filename": filename,
                            "date": date,
                        })
                except Exception:
                    continue

        finally:
            browser.close()

    # Deduplicate by URL
    seen = set()
    unique_pdfs = []
    for pdf in pdfs:
        if pdf["url"] not in seen:
            seen.add(pdf["url"])
            unique_pdfs.append(pdf)

    # Sort by date descending (newest first)
    unique_pdfs.sort(key=lambda x: x["date"], reverse=True)

    return unique_pdfs


def download_pdf(url: str, dest_path: Path, force: bool = False, referer: str = None) -> bool:
    """
    Download a PDF to the destination path.

    Returns True if downloaded, False if skipped or failed.
    """
    if dest_path.exists() and not force:
        print(f"  Cached: {dest_path.name}")
        return False

    # Use browser-like headers to avoid 403 errors
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/pdf,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if referer:
        headers["Referer"] = referer

    try:
        print(f"  Downloading: {dest_path.name}")
        response = requests.get(url, timeout=120, stream=True, headers=headers)
        response.raise_for_status()

        # Ensure directory exists
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        print(f"  Saved: {dest_path.name} ({dest_path.stat().st_size // 1024} KB)")
        return True

    except Exception as e:
        print(f"  ERROR downloading {url}: {e}")
        return False


def download_quarterly_reports(
    ticker: str,
    force: bool = False,
    num_quarters: int = 4,
) -> list[Path]:
    """
    Download quarterly reports for a REIT.

    Args:
        ticker: REIT ticker (e.g., "C38U.SI")
        force: Force re-download even if cached
        num_quarters: Number of quarters to download (default: 4)

    Returns:
        List of paths to downloaded PDFs
    """
    print(f"\n=== {ticker} ===")

    # Load config
    config = load_config()

    if ticker not in config:
        print(f"ERROR: {ticker} not found in config")
        return []

    reit_config = config[ticker]
    quarterly_url = reit_config.get("quarterly_url")
    quarterly_pattern = reit_config.get("quarterly_pattern")

    if not quarterly_url or not quarterly_pattern:
        print(f"ERROR: {ticker} missing quarterly_url or quarterly_pattern in config")
        return []

    print(f"REIT: {reit_config['name']}")

    # Discover PDFs
    pdfs = discover_pdfs(quarterly_url, quarterly_pattern)
    print(f"  Found {len(pdfs)} matching PDFs")

    if not pdfs:
        print("  WARNING: No PDFs found matching pattern")
        return []

    # Group by date to get unique quarters (multiple PDFs per announcement)
    # Each quarterly announcement has .1.pdf, .2.pdf, .3.pdf etc.
    # We want to download the main presentation (.1.pdf or largest)
    quarters_seen = set()
    pdfs_to_download = []

    for pdf in pdfs:
        # Extract the base date (quarter identifier)
        date = pdf["date"]
        if date and date not in quarters_seen:
            quarters_seen.add(date)
            pdfs_to_download.append(pdf)
            if len(pdfs_to_download) >= num_quarters:
                break

    # Download
    cache_dir = CACHE_DIR / ticker
    downloaded = []

    for pdf in pdfs_to_download:
        dest_path = cache_dir / pdf["filename"]
        if download_pdf(pdf["url"], dest_path, force, referer=quarterly_url):
            downloaded.append(dest_path)
        elif dest_path.exists():
            downloaded.append(dest_path)

    return downloaded


def download_all_reits(force: bool = False, num_quarters: int = 4) -> dict[str, list[Path]]:
    """
    Download quarterly reports for all REITs in parallel.

    Returns dict mapping ticker to list of downloaded paths.
    """
    config = load_config()
    tickers = list(config.keys())

    print(f"Downloading quarterly reports for {len(tickers)} REITs...")

    results = {}

    # Use ThreadPoolExecutor for parallel downloads
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(download_quarterly_reports, ticker, force, num_quarters): ticker
            for ticker in tickers
        }

        for future in as_completed(futures):
            ticker = futures[future]
            try:
                paths = future.result()
                results[ticker] = paths
            except Exception as e:
                print(f"ERROR processing {ticker}: {e}")
                results[ticker] = []

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Download quarterly report PDFs for Singapore REITs"
    )
    parser.add_argument(
        "ticker",
        nargs="?",
        help="REIT ticker (e.g., C38U.SI). Omit to use --all.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Download reports for all REITs in config",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-download even if cached",
    )
    parser.add_argument(
        "-n", "--num-quarters",
        type=int,
        default=4,
        help="Number of quarters to download (default: 4)",
    )

    args = parser.parse_args()

    if not args.ticker and not args.all:
        parser.print_help()
        print("\nERROR: Provide a ticker or use --all")
        sys.exit(1)

    if args.all:
        results = download_all_reits(force=args.force, num_quarters=args.num_quarters)

        print("\n=== Summary ===")
        for ticker, paths in results.items():
            status = f"{len(paths)} quarterly reports" if paths else "FAILED"
            print(f"  {ticker}: {status}")
    else:
        paths = download_quarterly_reports(
            args.ticker,
            force=args.force,
            num_quarters=args.num_quarters,
        )

        if paths:
            print(f"\nDownloaded {len(paths)} quarterly reports to {CACHE_DIR / args.ticker}")
        else:
            print("\nNo PDFs downloaded")
            sys.exit(1)


if __name__ == "__main__":
    main()
