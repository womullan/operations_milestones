#!/usr/bin/env python3
"""
Small admin utility to find potential duplicate Atlassian users (same display name,
multiple email addresses).

Usage examples:
  python3 opsAdmin.py --dups
  python3 opsAdmin.py --dups --output duplicates.csv

This script reuses the existing credential helper `get_login_config` from
`opsMiles.ojira` to obtain url/user/password (email + API token for Atlassian Cloud).
"""

import argparse
import json
import sys
from typing import Dict, List

import re
import requests
from jira import JIRA, JIRAError
from requests.auth import HTTPBasicAuth

from opsMiles.ojira import (
    get_login_config, list_jira_issues, get_jira_from_config,
    get_all_atlassian_users, get_account_ids_by_display_prefix,
    list_user_groups, add_user_to_group, copy_groups,
    get_issues_assigned, get_issues_watched, get_issues_reported,
    add_watcher, copy_watcher, assign_issue_quiet,
    change_reporter_quiet, copy_reporter, copy_reviewer, reassign,
    get_user_filters, share_filter, share_all_filters,
    get_user_dashboards, transfer_dashboard, transfer_user_dashboards,
    list_user_fields
)
from opsMiles.confluence import (
    process_space, process_spaces, process_single_page, get_confluence_client, update_space_ownership,
    extract_page_id_from_url, extract_space_key_from_url, get_page_owner, set_page_owner, add_user_to_update_restriction,
    transfer_personal_space, list_spaces, list_pages_in_space, replace_pages, update_single_page,
    replace_user_in_page, replace_user_in_space, print_space_pages, get_personal_space
)


def find_duplicate_displayname_users(users: List[Dict]):
    """Simple duplicate finder that uses only displayName and 'startswith' matching.

    For each user's displayName (base), it finds other users whose displayName
    starts with that base (case-insensitive). If matches are found, the function
    returns a dict keyed by the base displayName with aggregated emails and the
    collected user dicts. This keeps the output shape compatible with existing callers.
    """
    # Build a mapping from displayName to list of users with that exact displayName
    dups = {}
    skip = ["Peter", "Product Requirements Guide", "Work Organizer", "Brand Voice Crafter"
            "Lucidchart Diagrams Connector for Jira", "Opsgenie Incident Timeline",
            "migrate-jira-34f7173f-c7ca-4a05-82c6-d7f88d2266ec", "Jira Workflow Toolbox Cloud",
            "Lucidchart Diagrams Connector"]
    for u in users:
        dn = u.get('displayName')
        if not dn or dn in dups:
            continue
        # find other names that start with base (case-insensitive), excluding exact match
        for trymatch in users:
            if trymatch != u :
                odn = trymatch.get('displayName')
                if dn.startswith(odn):  # got a dup
                    if odn != "Peter" and dn not in skip:
                        if not dn in dups:
                            dups[dn]=[u]
                        dups[dn].append(trymatch)

    return dups


# Helper: print groups for an account id (no-frills)
def print_groups_for_account(config: Dict, account_id: str) -> None:
    groups = list_user_groups(config, account_id)
    if not groups:
        print(f'No groups found for accountId {account_id}')
        return
    print(f'Groups for {account_id}:')
    for g in groups:
        name = g.get('name') if isinstance(g, dict) else str(g)
        print(f' - {name}')


# New helper: print duplicates in the same format the main loop used
def print_duplicates(dups: Dict) -> None:
    if not dups:
        print('No potential duplicates found (exact or similar).')
        return
    for name, info in dups.items():
        print(f" {name}")
        for u in info:
            if isinstance(u, dict):
                display = u.get('displayName') or ''
                aid = u.get('accountId') or ''
                email = u.get('emailAddress') or ''
                print(f"  - {display} | {aid} | {email}")


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    p = argparse.ArgumentParser(description='Atlassian admin helpers')
    p.add_argument('--dups', action='store_true', help='Find duplicate users by displayName and similar-name pairs')
    p.add_argument('-a', '--ask', action='store_true', help='Prompt for password / API token')
    p.add_argument('-u', '--uname', help='Username for keyring lookup (email)')
    p.add_argument('-p', '--passwd', help='Password / API token (optional)')
    p.add_argument('--listGroups', nargs='+', help='Print groups for one or more user accountIds (space-separated)')
    p.add_argument('--copyGroups', nargs=2, metavar=('SRC','DST'), help='Copy all groups from SRC accountId to DST accountId')
    p.add_argument('--dry-run', action='store_true', help='Show what would be done for --copyGroups without making changes')
    p.add_argument('--findAccount', help='Find account ids for users whose displayName starts with the given prefix')
    p.add_argument('--countAssigned', nargs='+', help='Print the number of issues assigned to the given accountId(s)')
    p.add_argument('--listWatched', nargs='+', help=' issues watched by the given accountId(s)')
    p.add_argument('--reassign', nargs=2, metavar=('SRC','DST'), help='Change assignee of all tickets assigned to SRC to DST accountId')
    p.add_argument('--copyWatcher', nargs=2, metavar=('SRC','DST'), help=' Make  DST accountId watch all tickets  watched by SRC accountId')
    p.add_argument('--copyReporter', nargs=2, metavar=('SRC','DST'), help='Change reporter from SRC to DST on all issues reported by SRC')
    p.add_argument('--assignReviewer', nargs=2, metavar=('SRC','DST'), help='Change reviewer from SRC to DST on all issues where SRC is reviewer')
    p.add_argument('--reviewerField', default='Reviewer', help='Name of the reviewer field in Jira (default: Reviewer)')
    p.add_argument('--listUserFields', action='store_true', help='List all user-type fields in Jira')
    p.add_argument('--transferFilters', nargs=2, metavar=('SRC','DST'), help='Transfer all Jira filters owned by SRC to DST accountId')
    p.add_argument('--transferDashboards', nargs=2, metavar=('SRC','DST'), help='Transfer all Jira dashboards from SRC to DST accountId')
    p.add_argument('--transferSpace', nargs=2, metavar=('SRC','DST'), help='Transfer ownership and move pages from SRC\'s personal space to DST')
    p.add_argument('--updateSpaceOwnership', metavar='ACCOUNT_ID', help='Update ownership of all pages in user\'s personal space to that user')
    p.add_argument('--processConfluence', nargs=2, metavar=('SRC','DST'), help='Process Confluence spaces: transfer edit perms, watchers, and ownership from SRC to DST')
    p.add_argument('--srcUsername', help='Username for SRC personal space lookup (e.g., ykang)')
    p.add_argument('--dstUsername', help='Username for DST personal space lookup')
    p.add_argument('--moveuser', nargs=2, metavar=('SRC','DST'), help=' Copy groups, reassign tickets and copy watcher from  DST accountId to SRC accountId')
    p.add_argument('--predicate', help=' partial predicate to pass to jira  like "and project=SE"')
    p.add_argument('--spaces', nargs='+', help='Space names for --processConfluence or --moveuser (e.g., DM EPO LSSTOps). Omit to scan all spaces.')
    p.add_argument('--pageid', help='Process a single Confluence page by ID (use with --processConfluence)')
    p.add_argument('--page-url', help='Process a single Confluence page by URL (use with --processConfluence)')

    p.add_argument('--list-personal-pages', metavar='ACCOUNT', help='List all pages in a personal space (account ID, username, or space URL)')
    p.add_argument('--list-space', metavar='SPACE', help='List all pages in a space (space key like "LSSTOps" or space URL)')
    p.add_argument('--list-spaces', action='store_true', help='List all Confluence spaces (excludes personal spaces)')
    p.add_argument('--replace-text', action='store_true', help='Search and replace text in Confluence pages (requires --search-string and --replace-string)')
    p.add_argument('--search-string', help='String to search for in Confluence pages')
    p.add_argument('--replace-string', help='String to replace the search string with')
    p.add_argument('--replace-user', nargs=2, metavar=('SRC', 'DST'), help='Replace user mentions/assignments from SRC account ID to DST account ID')
    p.add_argument('--confirm', action='store_true', help='Prompt for confirmation before each page update')

    args = p.parse_args(argv)
    # reuse existing helper to build login config
    config = get_login_config(args)

    ok = False
    acct = args.listGroups
    pred = args.predicate
    # if an account id was requested, list groups and exit
    if acct:
        # acct may be a list of account ids; iterate and print groups for each
        for aid in acct:
            print_groups_for_account(config, aid)
        ok = True

    # find account(s) by display-name prefix
    if getattr(args, 'findAccount', None):
        prefix = args.findAccount
        matches = get_account_ids_by_display_prefix(config, prefix)
        if not matches:
            print(f'No accounts starting with "{prefix}" found')
        for m in matches:
            print(f"{m['accountId']} | {m['displayName']} | {m.get('email','')}")
        ok = True

    # copy groups operation
    if getattr(args, 'copyGroups', None):
        src, dst = args.copyGroups
        copy_groups(config, src, dst, dry_run=bool(getattr(args, 'dry_run', False)))
        ok = True

    # print counts of issues assigned to account(s)
    if getattr(args, 'countAssigned', None):
        jira = get_jira_from_config(config)
        for aid in args.countAssigned:
            n = get_issues_assigned(jira, aid, pred)
            print(f'{aid}: {len(n)}')
        ok = True

    if getattr(args, 'listWatched', None):
        jira = get_jira_from_config(config)
        for aid in args.listWatched:
            issues = get_issues_watched(jira, aid, pred)
            print(f'{aid}: {len(issues)}')
            for i in issues:
               print(f'{aid}: {i.key}')
        ok = True

    if getattr(args, 'moveuser', None):
        src, dst = args.moveuser
        dry_run = getattr(args, 'dry_run', False)
        jira = get_jira_from_config(config)
        
        # Track counts for summary
        summary = {
            'reassigned': 0,
            'watched': 0,
            'reporter_changed': 0,
            'reviewer_changed': 0,
            'filters_shared': 0,
            'dashboards_copied': 0,
            'confluence_edit': 0,
            'confluence_watch': 0,
            'confluence_owner': 0,
            'confluence_moved': 0,
        }
        
        copy_groups(config, src, dst, dry_run=dry_run)
        summary['filters_shared'] = share_all_filters(jira, src, dst, dry_run=dry_run)
        copied, _ = transfer_user_dashboards(jira, src, dst, dry_run=dry_run)
        summary['dashboards_copied'] = copied
        summary['watched'] = copy_watcher(config, src, dst, pred)
        summary['reporter_changed'] = copy_reporter(config, src, dst, dry_run, pred)
        summary['reviewer_changed'] = copy_reviewer(config, src, dst, dry_run, pred, getattr(args, 'reviewerField', 'Reviewer'))
        summary['reassigned'] = reassign(config, src, dst, dry_run, pred)
        confluence = get_confluence_client(config)
        # Transfer personal space ownership and move pages
        success, msg, ps_counts = transfer_personal_space(
            config, confluence, src, dst,
            src_username=getattr(args, 'srcUsername', None),
            dst_username=getattr(args, 'dstUsername', None),
            jira=jira,
            dry_run=dry_run
        )
        print(f"Personal space: {msg}")
        # Add personal space counts to totals (edit, watch, owner, moved)
        summary['confluence_edit'] += ps_counts[0]
        summary['confluence_watch'] += ps_counts[1]
        summary['confluence_owner'] += ps_counts[2]
        summary['confluence_moved'] = ps_counts[3]
        
        totals = process_spaces(config, confluence, args.spaces, src, dst, limit=500, dry_run=dry_run)
        summary['confluence_edit'] += totals['edit']
        summary['confluence_watch'] += totals['watch']
        summary['confluence_owner'] += totals['owner']
        
        # Print summary
        print("\n" + "=" * 50)
        print("MOVE USER SUMMARY")
        print("=" * 50)
        print(f"Jira tickets reassigned:      {summary['reassigned']}")
        print(f"Jira tickets watched:         {summary['watched']}")
        print(f"Jira reporter changed:        {summary['reporter_changed']}")
        print(f"Jira reviewer changed:        {summary['reviewer_changed']}")
        print(f"Jira filters shared:          {summary['filters_shared']}")
        print(f"Jira dashboards copied:       {summary['dashboards_copied']}")
        print(f"Confluence pages edit access: {summary['confluence_edit']}")
        print(f"Confluence pages watched:     {summary['confluence_watch']}")
        print(f"Confluence pages owner changed: {summary['confluence_owner']}")
        print(f"Confluence pages moved:       {summary['confluence_moved']}")
        print("=" * 50)
        
        ok = True

    if getattr(args, 'reassign', None):
        src, dst = args.reassign
        reassign(config, src, dst, (getattr(args, 'dry_run', False)), pred)
        ok = True

    # copy watcher operation
    if getattr(args, 'copyWatcher', None):
        src, dst = args.copyWatcher
        copy_watcher(config, src, dst, pred)
        ok = True

    # copy reporter operation
    if getattr(args, 'copyReporter', None):
        src, dst = args.copyReporter
        copy_reporter(config, src, dst, getattr(args, 'dry_run', False), pred)
        ok = True

    # list user fields
    if getattr(args, 'listUserFields', False):
        jira = get_jira_from_config(config)
        fields = list_user_fields(jira)
        print(f"Found {len(fields)} user-type fields:")
        for f in fields:
            custom = " (custom)" if f['custom'] else ""
            print(f"  {f['name']}: {f['id']}{custom}")
        ok = True

    # copy reviewer operation
    if getattr(args, 'assignReviewer', None):
        src, dst = args.assignReviewer
        field_name = getattr(args, 'reviewerField', 'Reviewer')
        copy_reviewer(config, src, dst, getattr(args, 'dry_run', False), pred, field_name)
        ok = True

    if getattr(args, 'transferFilters', None):
        src, dst = args.transferFilters
        jira = get_jira_from_config(config)
        share_all_filters(jira, src, dst, dry_run=getattr(args, 'dry_run', False))
        ok = True

    if getattr(args, 'transferDashboards', None):
        src, dst = args.transferDashboards
        jira = get_jira_from_config(config)
        transfer_user_dashboards(jira, src, dst, dry_run=getattr(args, 'dry_run', False))
        ok = True

    if getattr(args, 'transferSpace', None):
        src, dst = args.transferSpace
        confluence = get_confluence_client(config)
        jira = get_jira_from_config(config)
        success, msg, counts = transfer_personal_space(
            config, confluence, src, dst,
            src_username=getattr(args, 'srcUsername', None),
            dst_username=getattr(args, 'dstUsername', None),
            jira=jira,
            dry_run=getattr(args, 'dry_run', False)
        )
        print(msg)
        ok = True

    if getattr(args, 'updateSpaceOwnership', None):
        account_id = args.updateSpaceOwnership
        confluence = get_confluence_client(config)
        jira = get_jira_from_config(config)
        success, msg = update_space_ownership(
            confluence, account_id,
            username=getattr(args, 'srcUsername', None),
            jira=jira,
            dry_run=getattr(args, 'dry_run', False)
        )
        print(msg)
        ok = True

    if getattr(args, 'list_personal_pages', None):
        account = args.list_personal_pages
        confluence = get_confluence_client(config)
        base_url = config.get("url")
        jira = get_jira_from_config(config)
        
        # Check if it's a URL, space key, or account ID/username
        if account.startswith('http'):
            space_key = extract_space_key_from_url(account)
            if not space_key:
                print(f"Could not extract space key from URL: {account}")
                sys.exit(1)
            print(f"Extracted space key from URL: {space_key}")
        elif account.startswith('~'):
            space_key = account
        else:
            # Look up personal space by account ID or username
            space = get_personal_space(confluence, account, account, jira=jira)
            if not space:
                print(f"Could not find personal space for: {account}")
                sys.exit(1)
            space_key = space.get("key")
            print(f"Found personal space: {space.get('name')} ({space_key})")
        
        print_space_pages(confluence, space_key, base_url)
        ok = True

    if getattr(args, 'list_space', None):
        space_arg = args.list_space
        confluence = get_confluence_client(config)
        base_url = config.get("url")
        
        # Check if it's a URL or space key
        if space_arg.startswith('http'):
            space_key = extract_space_key_from_url(space_arg)
            if not space_key:
                print(f"Could not extract space key from URL: {space_arg}")
                sys.exit(1)
            print(f"Extracted space key from URL: {space_key}")
        else:
            space_key = space_arg
        
        print_space_pages(confluence, space_key, base_url, debug=True)
        ok = True

    if getattr(args, 'list_spaces', None):
        confluence = get_confluence_client(config)
        print("Listing all Confluence spaces (excluding personal spaces):\n")
        print(f"{'Key':<20} {'Type':<15} {'Name'}")
        print("-" * 60)
        for space in list_spaces(confluence):
            key = space.get("key")
            name = space.get("name")
            space_type = space.get("type")
            if not space_type.startswith('personal'):
                print(f"{key:<20} {space_type:<15} {name}")
        ok = True

    if getattr(args, 'replace_text', None):
        if not args.search_string:
            print("Error: --replace-text requires --search-string")
            sys.exit(1)
        if not args.replace_string:
            print("Error: --replace-text requires --replace-string")
            sys.exit(1)
        
        confluence = get_confluence_client(config)
        dry_run = getattr(args, 'dry_run', False)
        confirm = getattr(args, 'confirm', False)
        space = getattr(args, 'spaces', None)
        space_key = space[0] if space else None
        
        # Check if single page mode
        page_url = getattr(args, 'page_url', None)
        if page_url:
            print(f"Updating single page: {page_url}")
            modified = update_single_page(config, page_url, args.search_string, args.replace_string,
                                          dry_run=dry_run, confirm=confirm)
            print(f"Pages matched/modified: {len(modified)}")
        else:
            print(f"Searching for '{args.search_string}' in Confluence pages...")
            if space_key:
                print(f"  (restricted to space: {space_key})")
            modified = replace_pages(config, args.search_string, args.replace_string,
                                     space=space_key,
                                     dry_run=dry_run,
                                     confirm_per_page=confirm)
            print(f"Pages matched/modified: {len(modified)}")
        ok = True

    if getattr(args, 'replace_user', None):
        src_id, dst_id = args.replace_user
        confluence = get_confluence_client(config)
        dry_run = getattr(args, 'dry_run', False)
        confirm = getattr(args, 'confirm', False)
        space = getattr(args, 'spaces', None)
        space_key = space[0] if space else None
        page_url = getattr(args, 'page_url', None)
        
        print(f"Replacing user mentions from {src_id} to {dst_id}...")
        if dry_run:
            print("  (dry-run mode)")
        
        if page_url:
            # Single page mode
            page_id = extract_page_id_from_url(page_url)
            if page_id:
                if replace_user_in_page(confluence, page_id, src_id, dst_id, dry_run=dry_run):
                    print("Pages with user mentions replaced: 1")
                else:
                    print("Pages with user mentions replaced: 0")
        else:
            # Space mode
            if not space_key:
                print("Error: --replace-user requires --spaces or --page-url")
                sys.exit(1)
            
            modified = replace_user_in_space(confluence, space_key, src_id, dst_id, 
                                              dry_run=dry_run, confirm=confirm)
            print(f"Pages with user mentions replaced: {len(modified)}")
        ok = True

    if getattr(args, 'processConfluence', None):
        src, dst = args.processConfluence
        confluence = get_confluence_client(config)
        dry_run = getattr(args, 'dry_run', False)
        url = f'{config.get("url")}/wiki/'
        
        # Check for single page processing
        page_id = getattr(args, 'pageid', None)
        if not page_id and getattr(args, 'page_url', None):
            page_id = extract_page_id_from_url(args.page_url)
        
        if page_id:
            # Process single page
            process_single_page(config, confluence, page_id, src, dst, dry_run=dry_run)
        else:
            # Process spaces
            process_spaces(config, confluence, args.spaces, src, dst, limit=500, dry_run=dry_run)
        ok = True

    if getattr(args, 'dups', None):
        print('Fetching users from Atlassian...')
        users = get_all_atlassian_users(config)
        print(f'Got {len(users)} users')
        dups = find_duplicate_displayname_users(users)
        # print duplicates via helper and exit
        print_duplicates(dups)
        ok = True

    # if no action ran, show help (preserve old style)
    if not ok:
        p.print_help()
        return 2

    return 0


if __name__ == '__main__':
    sys.exit(main())
