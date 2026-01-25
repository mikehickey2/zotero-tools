"""
Shared utilities for Zotero Tools scripts.

This module provides common functionality used across all Zotero Tools scripts,
including credential loading and API connection helpers.
"""

import os
import sys
from dotenv import load_dotenv


def load_credentials() -> tuple[str, str, str]:
    """
    Load Zotero credentials from environment variables or .env file.

    Returns:
        Tuple of (library_id, library_type, api_key)

    Raises:
        SystemExit: If required credentials are missing
    """
    load_dotenv()

    library_id = os.getenv('ZOTERO_LIBRARY_ID')
    library_type = os.getenv('ZOTERO_LIBRARY_TYPE', 'group')
    api_key = os.getenv('ZOTERO_API_KEY')

    missing = []
    if not library_id:
        missing.append('ZOTERO_LIBRARY_ID')
    if not api_key:
        missing.append('ZOTERO_API_KEY')

    if missing:
        print("ERROR: Missing required environment variables:")
        for var in missing:
            print(f"  - {var}")
        print("\nPlease set these in your environment or create a .env file.")
        print("See .env.example for the expected format.")
        sys.exit(1)

    return library_id, library_type, api_key
