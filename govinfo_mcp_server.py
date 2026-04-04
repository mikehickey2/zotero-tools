#!/usr/bin/env python3
"""
govinfo_mcp_server.py

Local MCP server that wraps the GovInfo REST API.
Reads GOVINFO_API_KEY from .env (python-dotenv) so the key
never appears in .mcp.json.

Exposes two tools:
  - searchGovInfo: Full-text search across GovInfo collections
  - describePackage: Get full metadata + download links for a package

Usage (stdio, called by Claude Code):
    python govinfo_mcp_server.py

Configuration in ~/.mcp.json:
    "govinfo": {
      "command": "/Users/mikehickey2/projects/zotero-tools/venv/bin/python",
      "args": ["/Users/mikehickey2/projects/zotero-tools/govinfo_mcp_server.py"],
      "env": {}
    }
"""

import os
import sys

import requests
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

API_BASE = "https://api.govinfo.gov"
API_KEY = os.getenv("GOVINFO_API_KEY", "")

if not API_KEY:
    print("ERROR: GOVINFO_API_KEY not found in environment or .env", file=sys.stderr)

mcp = FastMCP(
    "govinfo",
    instructions=(
        "GovInfo API server for U.S. government publications. "
        "Search GAO reports, Congressional documents, Federal Register entries, "
        "and 40+ other government collections. Use searchGovInfo to find documents "
        "and describePackage to get full metadata with PDF download links."
    ),
)


@mcp.tool()
def searchGovInfo(
    query: str,
    collection: str = "",
    page_size: int = 5,
) -> str:
    """Search GovInfo for U.S. government publications.

    Args:
        query: Search terms. Supports boolean (AND, OR), phrases ("exact match"),
               and wildcards (*). Examples: "unmanned aircraft", "GAO-24-106833"
        collection: Optional collection filter. Common values:
                    GAOREPORTS (GAO), FR (Federal Register), CFR (regulations),
                    CRPT (Congressional Reports), CHRG (hearings), BILLS, PLAW.
                    Leave empty to search all collections.
        page_size: Number of results to return (1-100, default 5).
    """
    search_query = query
    if collection:
        search_query = f"collection:{collection} AND {query}"

    payload = {
        "query": search_query,
        "pageSize": min(page_size, 100),
        "offsetMark": "*",
        "sorts": [{"field": "publishdate", "sortOrder": "DESC"}],
    }

    resp = requests.post(
        f"{API_BASE}/search",
        json=payload,
        headers={"X-Api-Key": API_KEY, "Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    count = data.get("count", 0)
    results = data.get("results", [])

    lines = [f"Found {count} results (showing {len(results)}):\n"]
    for r in results:
        pkg_id = r.get("packageId", "N/A")
        title = r.get("title", "N/A")
        date = r.get("dateIssued", "N/A")
        authors = r.get("governmentAuthor", [])
        author_str = ", ".join(authors) if authors else "N/A"
        pdf = r.get("download", {}).get("pdfLink", "")

        lines.append(f"### {title}")
        lines.append(f"- **Package ID:** {pkg_id}")
        lines.append(f"- **Date:** {date}")
        lines.append(f"- **Author:** {author_str}")
        lines.append(f"- **Collection:** {r.get('collectionCode', 'N/A')}")
        if pdf:
            lines.append(f"- **PDF:** {pdf}?api_key=REDACTED")
        lines.append(f"- **Details:** {r.get('resultLink', 'N/A')}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def describePackage(package_id: str) -> str:
    """Get full metadata and download links for a GovInfo package.

    Args:
        package_id: The GovInfo package ID (e.g., "GAOREPORTS-GAO-24-106833").
                    Get this from searchGovInfo results.
    """
    resp = requests.get(
        f"{API_BASE}/packages/{package_id}/summary",
        params={"api_key": API_KEY},
        timeout=30,
    )
    if resp.status_code == 404:
        return f"Package not found: {package_id}"
    resp.raise_for_status()
    pkg = resp.json()

    title = pkg.get("title", "N/A")
    date = pkg.get("dateIssued", "N/A")
    author = pkg.get("governmentAuthor1", "N/A")
    doc_type = pkg.get("documentType", "N/A")
    pages = pkg.get("pages", "N/A")
    collection = pkg.get("collectionName", "N/A")
    details = pkg.get("detailsLink", "N/A")
    sudoc = pkg.get("suDocClassNumber", "")

    download = pkg.get("download", {})
    pdf = download.get("pdfLink", "")
    txt = download.get("txtLink", "")
    xml = download.get("xmlLink", "")

    lines = [
        f"# {title}\n",
        f"- **Package ID:** {package_id}",
        f"- **Date Issued:** {date}",
        f"- **Government Author:** {author}",
        f"- **Document Type:** {doc_type}",
        f"- **Pages:** {pages}",
        f"- **Collection:** {collection}",
        f"- **Details Page:** {details}",
    ]

    if sudoc:
        lines.append(f"- **SuDoc Class:** {sudoc}")

    # Report number extraction
    if "GAO-" in package_id:
        report_num = package_id.replace("GAOREPORTS-", "")
        lines.append(f"- **Report Number:** {report_num}")

    lines.append("\n## Downloads")
    if pdf:
        lines.append(f"- **PDF:** {pdf}?api_key=REDACTED")
    if txt:
        lines.append(f"- **Text/HTML:** {txt}?api_key=REDACTED")
    if xml:
        lines.append(f"- **XML:** {xml}?api_key=REDACTED")

    # Cross-references
    refs = pkg.get("references", [])
    if refs:
        lines.append("\n## References")
        for ref in refs[:10]:
            lines.append(f"- {ref}")

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="stdio")
