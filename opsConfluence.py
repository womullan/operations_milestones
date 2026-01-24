#!/usr/bin/env python3
"""
Command-line wrapper for Confluence operations extracted from opsMiles.py.
Provides options to search-and-replace across pages or update a single page by URL.

Usage examples:
  python opsConfluence.py --replace --search-string "OLD" --replace-string "NEW" --dry-run
  python opsConfluence.py --page-url "https://...pageId=123" --search-string "OLD" --replace-string "NEW" --confirm

This script reuses the credential helper get_login_config from opsMiles.ojira.
"""

import argparse
import sys

from opsMiles.ojira import get_login_config
from opsMiles.confluence import replace_pages, update_single_page


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Confluence search-and-replace utility")
    parser.add_argument('-a', '--ask', action='store_true',
                        help="Ask for Atlassian Password/API token for user.")
    parser.add_argument('-u', '--uname', help="Username for Confluence/Jira keyring lookup.")
    parser.add_argument('-p', '--passwd', help="Password/API token (optional, keyring used otherwise).")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--replace', action='store_true',
                       help="Search Confluence pages and replace text")
    group.add_argument('--page-url', default=None,
                       help="If set, update only the single Confluence page at this URL")

    parser.add_argument('--search-string', default=None,
                        help="String to search for in Confluence pages")
    parser.add_argument('--replace-string', default=None,
                        help="String to replace the search string with in Confluence pages")
    parser.add_argument('--space', default=None,
                        help="Optional Confluence space key to restrict search")
    parser.add_argument('--dry-run', action='store_true',
                        help="If set, only report pages that would be changed")
    parser.add_argument('--confirm', action='store_true',
                        help="If set, prompt per page for confirmation before updating")

    args = parser.parse_args()

    # Validate search/replace inputs for both modes
    if not args.search_string or args.replace_string is None:
        print("--search-string and --replace-string are required")
        sys.exit(2)

    # Reuse the repo's credential helper (get_login_config expects args with uname and ask)
    config = get_login_config(args)

    if args.page_url:
        modified = update_single_page(config, args.page_url, args.search_string, args.replace_string,
                                      dry_run=args.dry_run, confirm=args.confirm)
        print(f"Confluence single page matched/modified: {len(modified)}")
        sys.exit(0)

    if args.replace:
        modified = replace_pages(config, args.search_string, args.replace_string,
                                 space=args.space,
                                 dry_run=args.dry_run,
                                 confirm_per_page=args.confirm)
        print(f"Confluence pages matched/modified: {len(modified)}")
        sys.exit(0)
