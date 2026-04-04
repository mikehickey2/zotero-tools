#!/usr/bin/env python3
"""
zotero_govinfo_import.py

Search GovInfo API for U.S. government publications (GAO reports, Congressional
documents, Federal Register entries) and produce Zotero-ready JSON for import
via zotero_import_items.py.

Supports:
  - GAO reports by report number (e.g., GAO-24-106833)
  - Full-text search across all GovInfo collections
  - CRS reports via EveryCRSReport.com fallback
  - Direct package lookup by packageId

Requirements:
    pip install requests python-dotenv

Usage:
    python zotero_govinfo_import.py --gao GAO-24-106833
    python zotero_govinfo_import.py --search "unmanned aircraft" --collection GAOREPORTS
    python zotero_govinfo_import.py --crs IF11550
    python zotero_govinfo_import.py --package GAOREPORTS-GAO-24-106833
    python zotero_govinfo_import.py --gao GAO-24-106833 --output /tmp/import.json
"""

import argparse
import json
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
import os

API_BASE = "https://api.govinfo.gov"
EVERYCRS_BASE = "https://www.everycrsreport.com"


def load_api_key() -> str:
    """Load GovInfo API key from environment."""
    load_dotenv()
    key = os.getenv("GOVINFO_API_KEY")
    if not key:
        print("ERROR: GOVINFO_API_KEY not found in environment or .env file.")
        print("Register at https://www.govinfo.gov/api-signup")
        sys.exit(1)
    return key


def search_govinfo(query: str, collection: str | None, limit: int, api_key: str) -> list[dict]:
    """Search GovInfo across collections."""
    search_query = query
    if collection:
        search_query = f'collection:{collection} AND {query}'

    payload = {
        "query": search_query,
        "pageSize": limit,
        "offsetMark": "*",
        "sorts": [{"field": "publishdate", "sortOrder": "DESC"}],
    }

    resp = requests.post(
        f"{API_BASE}/search",
        json=payload,
        headers={"X-Api-Key": api_key, "Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    print(f"Found {data.get('count', 0)} results")
    return data.get("results", [])


def lookup_gao(report_number: str, api_key: str) -> dict | None:
    """Look up a GAO report by report number."""
    # Normalize: strip "GAO-" prefix if present for package ID construction
    clean = report_number.strip()

    # Try direct package lookup first
    package_id = f"GAOREPORTS-{clean}"
    result = get_package_summary(package_id, api_key)
    if result:
        return result

    # Fall back to search
    print(f"  Direct lookup failed, searching for '{clean}'...")
    results = search_govinfo(f'"{clean}"', "GAOREPORTS", 3, api_key)
    if results:
        # Get full summary for first match
        pkg_id = results[0].get("packageId")
        if pkg_id:
            return get_package_summary(pkg_id, api_key)

    return None


def get_package_summary(package_id: str, api_key: str) -> dict | None:
    """Get full metadata for a GovInfo package."""
    resp = requests.get(
        f"{API_BASE}/packages/{package_id}/summary",
        params={"api_key": api_key},
        timeout=30,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def lookup_crs(report_number: str) -> dict | None:
    """Look up a CRS report via EveryCRSReport.com."""
    clean = report_number.strip().upper()
    url = f"{EVERYCRS_BASE}/reports/{clean}.html"

    resp = requests.get(url, timeout=30)
    if resp.status_code == 404:
        print(f"  CRS {clean} not found on EveryCRSReport.com")
        return None
    resp.raise_for_status()

    # Parse basic metadata from the HTML page
    html = resp.text

    title = ""
    title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
    if title_match:
        title = title_match.group(1).strip()

    date = ""
    date_match = re.search(r'<div class="report-date"[^>]*>([^<]+)</div>', html)
    if date_match:
        date = date_match.group(1).strip()

    authors = []
    author_matches = re.findall(r'<a href="/authors/[^"]*">([^<]+)</a>', html)
    for name in author_matches:
        parts = name.strip().split()
        if len(parts) >= 2:
            authors.append({
                "creatorType": "author",
                "firstName": " ".join(parts[:-1]),
                "lastName": parts[-1],
            })
        elif len(parts) == 1:
            authors.append({"creatorType": "author", "name": parts[0]})

    # Determine CRS series from report number prefix
    series = ""
    if clean.startswith("IF"):
        series = "CRS In Focus"
    elif clean.startswith("R4") or clean.startswith("R3") or clean.startswith("RL"):
        series = "CRS Report"
    elif clean.startswith("RS"):
        series = "CRS Report for Congress"

    return {
        "title": title,
        "date": date,
        "authors": authors,
        "reportNumber": clean,
        "series": series,
        "url": f"https://crsreports.congress.gov/product/pdf/{clean[:2]}/{clean}",
        "source": "EveryCRSReport.com",
    }


def govinfo_to_zotero(pkg: dict) -> dict:
    """Convert a GovInfo package summary to Zotero import format."""
    title = pkg.get("title", "")

    # APA7: sentence case for title
    title_lower = title_to_sentence_case(title)

    # Determine institution from governmentAuthor1
    institution = pkg.get("governmentAuthor1", "")
    if not institution:
        authors = pkg.get("governmentAuthor", [])
        institution = authors[0] if authors else ""

    # Build creator
    creators = []
    if institution:
        creators.append({"creatorType": "author", "name": institution})
    else:
        creators.append({"creatorType": "author", "name": "United States Government"})

    # Extract report number from package ID
    package_id = pkg.get("packageId", "")
    report_number = ""
    if "GAO-" in package_id:
        report_number = package_id.replace("GAOREPORTS-", "")

    # Date
    date = pkg.get("dateIssued", "")

    # URL: prefer govinfo details page
    url = pkg.get("detailsLink", "")
    if not url:
        url = f"https://www.govinfo.gov/app/details/{package_id}"

    # PDF link
    pdf_link = ""
    download = pkg.get("download", {})
    if download.get("pdfLink"):
        pdf_link = download["pdfLink"]

    item = {
        "itemType": "report",
        "title": title_lower,
        "creators": creators,
        "date": date,
        "institution": institution,
        "place": "Washington, DC",
        "url": url,
    }

    if report_number:
        item["reportNumber"] = report_number
    if pdf_link:
        item["extra"] = f"PDF: {pdf_link}"

    pages = pkg.get("pages")
    if pages:
        item["numPages"] = str(pages)

    return item


def crs_to_zotero(crs: dict) -> dict:
    """Convert CRS lookup result to Zotero import format."""
    title = title_to_sentence_case(crs.get("title", ""))

    creators = crs.get("authors", [])
    if not creators:
        creators = [{"creatorType": "author", "name": "Congressional Research Service"}]

    item = {
        "itemType": "report",
        "title": title,
        "creators": creators,
        "date": crs.get("date", ""),
        "reportNumber": crs.get("reportNumber", ""),
        "institution": "Congressional Research Service",
        "place": "Washington, DC",
        "url": crs.get("url", ""),
    }

    series = crs.get("series", "")
    if series:
        item["seriesTitle"] = series

    return item


def title_to_sentence_case(title: str) -> str:
    """Convert title to APA7 sentence case, preserving acronyms and proper nouns."""
    if not title:
        return title

    # Split on colon for subtitle handling
    parts = title.split(": ", 1)

    def convert_part(text: str, is_first: bool) -> str:
        words = text.split()
        result = []
        for i, word in enumerate(words):
            # Preserve all-caps acronyms (2+ letters)
            if len(word) >= 2 and word.isupper() and word.isalpha():
                result.append(word)
            # Preserve mixed case (CamelCase, abbreviations with periods)
            elif any(c.isupper() for c in word[1:]):
                result.append(word)
            # First word of part: capitalize
            elif i == 0:
                result.append(word.capitalize())
            # Everything else: lowercase
            else:
                result.append(word.lower())
        return " ".join(result)

    converted = convert_part(parts[0], True)
    if len(parts) > 1:
        converted += ": " + convert_part(parts[1], False)

    return converted


def format_preview(item: dict) -> str:
    """Format a Zotero item dict for human-readable preview."""
    lines = [f"  Title: {item.get('title', 'N/A')}"]
    if item.get("reportNumber"):
        lines.append(f"  Report #: {item['reportNumber']}")
    lines.append(f"  Date: {item.get('date', 'N/A')}")
    if item.get("institution"):
        lines.append(f"  Institution: {item['institution']}")
    if item.get("url"):
        lines.append(f"  URL: {item['url']}")
    if item.get("extra"):
        lines.append(f"  {item['extra']}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Search GovInfo for government publications and produce Zotero-ready JSON.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python zotero_govinfo_import.py --gao GAO-24-106833
  python zotero_govinfo_import.py --search "drone collision" --collection GAOREPORTS
  python zotero_govinfo_import.py --crs IF11550
  python zotero_govinfo_import.py --gao GAO-24-106833 --output /tmp/gao_import.json
        """,
    )
    parser.add_argument("--gao", help="Look up a GAO report by number (e.g., GAO-24-106833)")
    parser.add_argument("--crs", help="Look up a CRS report by number (e.g., IF11550)")
    parser.add_argument("--package", help="Look up a GovInfo package by ID")
    parser.add_argument("--search", help="Full-text search query")
    parser.add_argument("--collection", help="Limit search to collection (e.g., GAOREPORTS, FR, CRPT)")
    parser.add_argument("--limit", type=int, default=5, help="Max search results (default: 5)")
    parser.add_argument("--output", "-o", help="Output JSON file path (default: stdout preview)")

    args = parser.parse_args()

    if not any([args.gao, args.crs, args.package, args.search]):
        parser.print_help()
        sys.exit(1)

    zotero_items = []

    # GAO lookup
    if args.gao:
        api_key = load_api_key()
        print(f"Looking up GAO report: {args.gao}")
        pkg = lookup_gao(args.gao, api_key)
        if pkg:
            item = govinfo_to_zotero(pkg)
            zotero_items.append(item)
            print(f"  Found:\n{format_preview(item)}")
        else:
            print(f"  NOT FOUND: {args.gao}")
            print("  Try searching: --search '\"GAO report number\"'")

    # CRS lookup
    if args.crs:
        print(f"Looking up CRS report: {args.crs}")
        crs = lookup_crs(args.crs)
        if crs:
            item = crs_to_zotero(crs)
            zotero_items.append(item)
            print(f"  Found:\n{format_preview(item)}")
        else:
            print(f"  NOT FOUND: {args.crs}")

    # Direct package lookup
    if args.package:
        api_key = load_api_key()
        print(f"Looking up package: {args.package}")
        pkg = get_package_summary(args.package, api_key)
        if pkg:
            item = govinfo_to_zotero(pkg)
            zotero_items.append(item)
            print(f"  Found:\n{format_preview(item)}")
        else:
            print(f"  NOT FOUND: {args.package}")

    # Search
    if args.search:
        api_key = load_api_key()
        print(f"Searching GovInfo: {args.search}")
        if args.collection:
            print(f"  Collection: {args.collection}")
        results = search_govinfo(args.search, args.collection, args.limit, api_key)
        for r in results:
            pkg_id = r.get("packageId")
            pkg = get_package_summary(pkg_id, api_key) if pkg_id else None
            if pkg:
                item = govinfo_to_zotero(pkg)
                zotero_items.append(item)
                print(f"\n{format_preview(item)}")
            else:
                # Use search result directly
                print(f"\n  {r.get('title', 'N/A')} ({r.get('dateIssued', '')})")
                print(f"  Package: {pkg_id}")

    # Output
    if not zotero_items:
        print("\nNo items to export.")
        sys.exit(0)

    if args.output:
        output_path = Path(args.output)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(zotero_items, f, indent=2, ensure_ascii=False)
        print(f"\nWrote {len(zotero_items)} item(s) to {args.output}")
        print(f"Import with: python zotero_import_items.py --input {args.output} --collection 00-Inbox --dry-run")
    else:
        print(f"\n{'='*60}")
        print(f"Preview: {len(zotero_items)} item(s)")
        print(json.dumps(zotero_items, indent=2, ensure_ascii=False))
        print(f"\nTo save: add --output /tmp/govinfo_import.json")


if __name__ == "__main__":
    main()
