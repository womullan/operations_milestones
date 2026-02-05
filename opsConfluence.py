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
from opsMiles.confluence import replace_pages, update_single_page, process_space, list_spaces, get_confluence_client, \
    allow_edit, extract_page_id_from_url

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Confluence utility")
    parser.add_argument('-a', '--ask', action='store_true',
                        help="Ask for Atlassian Password/API token for user.")
    parser.add_argument('-u', '--uname', help="Username for Confluence/Jira keyring lookup.")
    parser.add_argument('-p', '--passwd', help="Password/API token (optional, keyring used otherwise).")

    parser.add_argument('--replace', action='store_true',
                       help="Search Confluence pages and replace text")
    parser.add_argument('--page-url', default=None,
                       help="If set, update only the single Confluence page at this URL")

    parser.add_argument('--search-string', default=None,
                        help="String to search for in Confluence pages ")
    parser.add_argument('--replace-string', default=None,
                        help="String to replace the search string with in Confluence pages NOT WORKING")
    parser.add_argument('--space', default=None,
                        help="Optional Confluence space key to restrict search")
    parser.add_argument('--dry-run', action='store_true',
                        help="If set, only report pages that would be changed")
    parser.add_argument('--confirm', action='store_true',
                        help="If set, prompt per page for confirmation before updating")
    parser.add_argument('--reassign', nargs=2, metavar=('SRC','DST'),
                        help='Allow edit for owned pages add watcher of all pages from SRC to DST accountId')
    parser.add_argument('--listspaces', action='store_true',
                       help="List conflunce space ids")
    parser.add_argument( "--limit", type=int, default=100, help="Page batch size (default: 100)", )
    parser.add_argument('--pageid', default=None,
                        help="If set, update only the single Confluence page at this ID")

    args = parser.parse_args()

    # Reuse the repo's credential helper (get_login_config expects args with uname and ask)
    config = get_login_config(args)
    confluence = get_confluence_client(config)

    if args.listspaces:
        for space in list_spaces(confluence, limit=args.limit):
            key = space.get("key")
            name = space.get("name")
            space_type = space.get("type")
            if not space_type.startswith('personal'):
                print(f"{key}\t{space_type}\t{name}")
        sys.exit(0)

    if args.reassign:
        old_accountid, new_accountid = args.reassign
        pageid = None
        if args.pageid:
            pageid = args.pageid
        if args.page_url:
            pageid = extract_page_id_from_url(args.page_url)

        if pageid:
            allow_edit(confluence, f"{config.get('url')}/wiki/", pageid, "",
                       old_accountid, new_accountid, args.dry_run)

        else:
            process_space(
                config=config,
                confluence=confluence,
                space_key=args.space,
                old_account_id=old_accountid,
                new_account_id=new_accountid,
                limit=args.limit,
                dry_run=args.dry_run,
            )
        sys.exit(0)

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
