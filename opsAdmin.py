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
    get_user_dashboards, copy_dashboard, copy_user_dashboards,
    list_user_fields
)
from opsMiles.confluence import (
    process_space, get_confluence_client, copy_personal_space, update_space_ownership,
    extract_page_id_from_url, get_page_owner, set_page_owner, add_user_to_update_restriction,
    transfer_personal_space, move_personal_space
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


def get_account_ids_by_display_prefix(config: Dict, prefix: str) -> List[Dict]:
    """Return list of user info for accounts whose displayName starts with prefix.

    No-frills, case-insensitive startswith. Each result is a dict with keys:
      - accountId: the Atlassian account id (or fallback key/name)
      - displayName: the user's displayName
      - email: the preferred email field if present

    Uses the existing get_all_atlassian_users to fetch users.
    """
    if not prefix:
        return []
    users = get_all_atlassian_users(config)
    p = prefix.lower()
    out = []
    for u in users:
        dn = (u.get('displayName') or '')
        if not dn:
            continue
        if dn.lower().startswith(p):
            aid = u.get('accountId') or u.get('key') or u.get('name') or ''
            email = u.get('emailAddress') or u.get('email') or u.get('accountEmail') or ''
            out.append({'accountId': aid, 'displayName': dn, 'email': email})
    return out


def get_issues_assigned(jira: JIRA, account_id: str, pred:str) -> list:
    """Return the issues assigned to account_id.
    """
    issues = list_jira_issues(jira, query=f'project != PREOPS and assignee={account_id}', pred2=pred)
    return issues


def get_issues_watched(jira: JIRA, account_id: str, pred) -> list:
    """Return the issues assigned to account_id.
    """
    issues = list_jira_issues(jira, query=f'project != PREOPS and watcher={account_id} and '
                                          f'status NOT IN (Closed, Done, Resolved, Cancelled, Deprecated, "Journal Submitted") ', pred2=pred)
    return issues


def get_issues_reported(jira: JIRA, account_id: str, pred) -> list:
    """Return the issues reported by account_id."""
    issues = list_jira_issues(jira, query=f'project != PREOPS and reporter={account_id} '
                                          , pred2=pred)
    return issues


def add_watcher(j:JIRA, config: Dict, account_id: str, issue: str) -> str:
    base = config.get('url')
    if not base:
        raise ValueError('Missing url in config')
    url = base.rstrip('/') + f'/rest/api/3/issue/{issue}/watchers?notifyUsers=false'
    headers = {
        "Content-Type": "application/json"
    }
    data = json.dumps(account_id)  # this produces: '"5b10a2844c20165700ede21g"'
    try:
        r= j._session.post(url, headers=headers, data=data)
        r.raise_for_status()  # Raises an HTTPError if status is 4xx/5xx
    except JIRAError as err:
        return(err.text)
    if r and r.status_code == 204:
        return 'added'
    return f'error:{r.status_code} {r.text}'


def copy_watcher(config: Dict, src:str, dst:str, pred:str) -> int:
    """For tickets watched by accountIDsrc add dst as a wtacher also"""
    jira = get_jira_from_config(config)
    issues = get_issues_watched(jira, src, pred)
    tot = len(issues)
    print (f"Got {tot} watched by {src}")
    problem = []
    count = 0
    for i in issues:
        s = add_watcher(jira, config, dst, i.key)
        print(f'{i.key} ({count}/{tot}) {s}')
        if s.startswith('added'):
            count += 1
        else:
            problem.append(i.key)
    print (f"Of {len(issues)} watched {count} PROBLEMS with :{problem}")
    print (f"PREOPS is ignored")
    return count


def change_reporter_quiet(jira: JIRA, issue_key: str, account_id: str) -> tuple:
    """Change reporter on issue without sending notification.
    
    Returns (success: bool, error_msg: str or None)
    """
    # Try using jira library's update method first (may send notification)
    try:
        issue = jira.issue(issue_key)
        issue.update(fields={'reporter': {'accountId': account_id}}, notify=False)
        return True, None
    except JIRAError as e:
        pass  # Fall through to try direct API
    except Exception as e:
        pass
    
    # Try direct REST API with notifyUsers=false
    url = f'{jira.server_url}/rest/api/3/issue/{issue_key}?notifyUsers=false'
    payload = {
        'fields': {
            'reporter': {'accountId': account_id}
        }
    }
    try:
        r = jira._session.put(url, json=payload)
        if r.status_code in (200, 204):
            return True, None
        try:
            err = r.json().get('errorMessages', [r.text])
            errors = r.json().get('errors', {})
            if errors:
                err_msg = str(errors)
            elif err:
                err_msg = '; '.join(err) if isinstance(err, list) else str(err)
            else:
                err_msg = f'{r.status_code}: {r.text}'
        except Exception:
            err_msg = f'{r.status_code}: {r.text}'
        return False, err_msg
    except JIRAError as e:
        return False, e.text
    except Exception as e:
        return False, str(e)


def copy_reporter(config: Dict, src: str, dst: str, dry_run: bool, pred: str) -> int:
    """Change reporter from src to dst on all issues reported by src."""
    jira = get_jira_from_config(config)
    # Verify destination user exists
    try:
        dst_user = jira.user(dst)
        print(f"Destination user: {dst_user.displayName} ({dst})")
    except Exception as e:
        print(f"WARNING: Could not verify destination user {dst}: {e}")
    issues = get_issues_reported(jira, src, pred)
    tot = len(issues)
    print(f"Got {tot} reported by {src}")
    count = 0
    problem = []
    if dry_run:
        print("NO changes - dry run only")
    for i in issues:
        if dry_run:
            print(f"  Would change reporter on {i.key}")
        else:
            success, err = change_reporter_quiet(jira, i.key, dst)
            if success:
                print(f"Changed reporter ({count}/{tot}) {i.key}")
                count += 1
            else:
                print(f"FAILED to change reporter on {i.key}: {err}")
                problem.append(i.key)
    if not dry_run and problem:
        print(f"Of {tot} issues, changed {count}. PROBLEMS with: {problem}")
    print("PREOPS is ignored")
    return count


def add_user_to_group(config: Dict, account_id: str, group_name: str) -> str:
    base = config.get('url')
    if not base:
        raise ValueError('Missing url in config')
    url = base.rstrip('/') + '/rest/api/3/group/user'
    auth = HTTPBasicAuth(config.get('user'), config.get('password'))
    params = {'groupname': group_name}
    payload = {'accountId': account_id}
    r = requests.post(url, auth=auth, params=params, json=payload)
    # 201 Created -> added, 409 Conflict -> already a member
    if r.status_code == 201:
        return 'added'
    if r.status_code == 409:
        return 'exists'
    return f'error:{r.status_code} {r.text}'

def copy_groups(config: Dict, src_account: str, dst_account: str, dry_run: bool = False) -> None:
    """Copy all groups where src_account is a member to dst_account.

    Minimal: list groups for src_account, then POST dst_account into each group's members.
    Prints per-group status and a small summary.
    """
    groups = list_user_groups(config, src_account)
    if not groups:
        print(f'No groups found for source account {src_account}')
        return
    if dry_run:
        # Compare source groups to destination membership and report what would change
        dst_groups = list_user_groups(config, dst_account)
        dst_names = {g.get('name') for g in dst_groups if isinstance(g, dict) and g.get('name')}
        would_add = 0
        already = 0
        skipped = 0
        print(f'DRY-RUN: comparing groups from {src_account} to {dst_account}...')
        for g in groups:
            name = g.get('name') if isinstance(g, dict) else None
            if not name:
                print('  - skipping group with no name field')
                skipped += 1
                continue
            if name in dst_names:
                print(f'  - {name}: already a member (would skip)')
                already += 1
            else:
                print(f'  - {name}: would add')
                would_add += 1
        print(f'DRY-RUN summary: would_add={would_add} already={already} skipped={skipped}')
        return

    added = 0
    exists = 0
    errors = 0
    print(f'Copying groups from {src_account} to {dst_account}...')
    for g in groups:
        name = g.get('name') if isinstance(g, dict) else None
        if not name:
            print('  - skipping group with no name field')
            continue
        res = add_user_to_group(config, dst_account, name)
        if res == 'added':
            print(f"  - {name}: added")
            added += 1
        elif res == 'exists':
            print(f"  - {name}: already a member")
            exists += 1
        else:
            print(f"  - {name}: {res}")
            errors += 1
    print(f'Finished: added={added} exists={exists} errors={errors}')

def assign_issue_quiet(jira: JIRA, issue_key: str, account_id: str) -> bool:
    """Assign issue without sending notification.
    
    Uses the general issue update endpoint with notifyUsers=false which is
    more reliable for suppressing notifications than the assignee endpoint.
    """
    url = f'{jira.server_url}/rest/api/3/issue/{issue_key}?notifyUsers=false'
    payload = {
        'fields': {
            'assignee': {'accountId': account_id}
        }
    }
    r = jira._session.put(url, json=payload)
    return r.status_code == 204


def get_user_filters(jira: JIRA, account_id: str) -> list:
    """Get all filters owned by an account."""
    url = f'{jira.server_url}/rest/api/3/filter/search'
    params = {'accountId': account_id, 'maxResults': 100}
    r = jira._session.get(url, params=params)
    if r.status_code == 200:
        return r.json().get('values', [])
    return []


def share_filter(jira: JIRA, filter_id: int, account_id: str) -> tuple:
    """Grant view permission on a filter to a user.
    
    Returns (success: bool, error_msg: str or None)
    """
    url = f'{jira.server_url}/rest/api/3/filter/{filter_id}/permission'
    payload = {
        'type': 'user',
        'accountId': account_id
    }
    try:
        r = jira._session.post(url, json=payload)
        if r.status_code in (200, 201):
            return True, None
        try:
            err = r.json().get('errorMessages', [r.text])
            err_msg = '; '.join(err) if isinstance(err, list) else str(err)
        except Exception:
            err_msg = r.text
        return False, err_msg
    except JIRAError as e:
        return False, e.text
    except Exception as e:
        return False, str(e)


def share_all_filters(jira: JIRA, src: str, dst: str, dry_run: bool = False) -> int:
    """Share all filters owned by src user with dst user (grants edit permission)."""
    filters = get_user_filters(jira, src)
    shared = 0
    failed = 0
    print(f"Found {len(filters)} filters owned by {src}")
    for f in filters:
        fid = f['id']
        fname = f['name']
        if dry_run:
            print(f"  Would share filter {fid}: {fname}")
        else:
            success, err = share_filter(jira, fid, dst)
            if success:
                print(f"  Shared filter {fid}: {fname}")
                shared += 1
            else:
                print(f"  FAILED filter {fid}: {fname} - {err}")
                failed += 1
    print(f"Filters: shared={shared} failed={failed}")
    return shared


def get_user_dashboards(jira: JIRA, account_id: str) -> list:
    """Get all dashboards owned by an account."""
    url = f'{jira.server_url}/rest/api/3/dashboard/search'
    params = {'accountId': account_id, 'maxResults': 100}
    r = jira._session.get(url, params=params)
    if r.status_code == 200:
        return r.json().get('values', [])
    return []


def copy_dashboard(jira: JIRA, dashboard_id: str, new_owner_id: str, new_name: str = None) -> tuple:
    """Copy a dashboard and set the owner to the new user.
    
    Returns (success: bool, new_dashboard_id or error_msg)
    """
    # First copy the dashboard
    copy_url = f'{jira.server_url}/rest/api/3/dashboard/{dashboard_id}/copy'
    copy_payload = {}
    if new_name:
        copy_payload['name'] = new_name
    
    try:
        r = jira._session.post(copy_url, json=copy_payload)
        if r.status_code not in (200, 201):
            return False, f"Copy failed: HTTP {r.status_code} - {r.text[:200]}"
        
        new_dashboard = r.json()
        new_dashboard_id = new_dashboard.get('id')
        
        # Now change the owner using bulk edit
        edit_url = f'{jira.server_url}/rest/api/3/dashboard/bulk/edit'
        edit_payload = {
            'action': 'changeOwner',
            'entityIds': [int(new_dashboard_id)],
            'newOwner': new_owner_id,
            'extendAdminPermissions': True
        }
        
        r2 = jira._session.put(edit_url, json=edit_payload)
        if r2.status_code not in (200, 204):
            return True, f"{new_dashboard_id} (warning: owner change failed: {r2.text[:100]})"
        
        return True, new_dashboard_id
    except Exception as e:
        return False, str(e)


def copy_user_dashboards(jira: JIRA, src_account: str, dst_account: str, dry_run: bool = False) -> tuple:
    """Copy all dashboards from src user to dst user.
    
    Returns (copied_count, failed_count)
    """
    dashboards = get_user_dashboards(jira, src_account)
    copied = 0
    failed = 0
    print(f"Found {len(dashboards)} dashboards owned by {src_account}")
    
    for dash in dashboards:
        dash_id = dash.get('id')
        dash_name = dash.get('name', 'Unknown')
        
        if dry_run:
            print(f"  Would copy dashboard {dash_id}: {dash_name}")
            copied += 1
        else:
            success, result = copy_dashboard(jira, dash_id, dst_account)
            if success:
                print(f"  Copied dashboard {dash_id}: {dash_name} -> new id: {result}")
                copied += 1
            else:
                print(f"  FAILED dashboard {dash_id}: {dash_name} - {result}")
                failed += 1
    
    print(f"Dashboards: copied={copied} failed={failed}")
    return copied, failed


def reassign(config:dict, src:str, dst:str, dry_run:bool, pred:str) -> int:
    """Reassign tickets from accoutn id src to accountid dst - return the count"""
    jira = get_jira_from_config(config)
    issues = get_issues_assigned(jira, src, pred)
    tot = len(issues)
    print (f"Got {tot} for {src}")
    count = 0
    problem = []
    if dry_run:
        print("NO changes - dry run only ")
    for i in issues:
        v = False
        if  not dry_run:
            try:
                #v = jira.assign_issue(i.key, dst)
                v = assign_issue_quiet(jira, i.key, dst)
                print(f"Assign ({count}/{tot}) {i.key} to {dst}: {v}")
            except JIRAError as err:
                print(f'{i.key} {err.text}')
        if v:
           count += 1
        else:
            problem.append(i.key)

    if dry_run:
        print("NO changes - dry run only ")
    else:
        if len(problem) > 0:
            print (f'Of {len(issues)} assigned {count}.  THERE WERE PROBLEMS ASSIGNING :{problem}')
    return count


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
    p.add_argument('--copyDashboards', nargs=2, metavar=('SRC','DST'), help='Copy all Jira dashboards from SRC to DST accountId')
    p.add_argument('--copyPersonalSpace', nargs=2, metavar=('SRC','DST'), help='Copy pages from SRC\'s Confluence personal space to DST\'s')
    p.add_argument('--transferSpace', nargs=2, metavar=('SRC','DST'), help='Transfer ownership and move pages from SRC\'s personal space to DST (requires --admin-key)')
    p.add_argument('--movePersonalSpace', nargs=2, metavar=('SRC','DST'), help='Move pages from SRC\'s personal space to DST\'s personal space (creates DST space if needed, does NOT transfer ownership)')
    p.add_argument('--updateSpaceOwnership', metavar='ACCOUNT_ID', help='Update ownership of all pages in user\'s personal space to that user')
    p.add_argument('--processConfluence', nargs=2, metavar=('SRC','DST'), help='Process Confluence spaces: transfer edit perms, watchers, and ownership from SRC to DST')
    p.add_argument('--srcUsername', help='Username for SRC personal space lookup (e.g., ykang)')
    p.add_argument('--dstUsername', help='Username for DST personal space lookup')
    p.add_argument('--moveuser', nargs=2, metavar=('SRC','DST'), help=' Copy groups, reassign tickets and copy watcher from  DST accountId to SRC accountId')
    p.add_argument('--predicate', help=' partial predicate to pass to jira  like "and project=SE"')
    p.add_argument('--spaces', nargs='+', help='Space names for --processConfluence or --moveuser (e.g., DM EPO LSSTOps). Omit to scan all spaces.')
    p.add_argument('--pageid', help='Process a single Confluence page by ID (use with --processConfluence)')
    p.add_argument('--page-url', help='Process a single Confluence page by URL (use with --processConfluence)')
    p.add_argument('--admin-key', action='store_true', help='Use Confluence admin key to bypass page restrictions (requires Premium/Enterprise and site admin)')

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
        copied, _ = copy_user_dashboards(jira, src, dst, dry_run=dry_run)
        summary['dashboards_copied'] = copied
        summary['watched'] = copy_watcher(config, src, dst, pred)
        summary['reporter_changed'] = copy_reporter(config, src, dst, dry_run, pred)
        summary['reviewer_changed'] = copy_reviewer(config, src, dst, dry_run, pred, getattr(args, 'reviewerField', 'Reviewer'))
        summary['reassigned'] = reassign(config, src, dst, dry_run, pred)
        confluence = get_confluence_client(config, admin_key=getattr(args, 'admin_key', False))
        # Transfer personal space ownership and move pages
        if not getattr(args, 'admin_key', False):
            print("WARNING: Personal space transfer works best with --admin-key for restricted pages")
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
        
        if args.spaces:
            for s in args.spaces:
                edit_cnt, watch_cnt, owner_cnt = process_space(config, confluence, s, src, dst, limit=500, dry_run=dry_run)
                summary['confluence_edit'] += edit_cnt
                summary['confluence_watch'] += watch_cnt
                summary['confluence_owner'] += owner_cnt
        else:
            print ("This will take a long time since it will scan all spaces")
            edit_cnt, watch_cnt, owner_cnt = process_space(config, confluence, "", src, dst, limit=500, dry_run=dry_run)
            summary['confluence_edit'] += edit_cnt
            summary['confluence_watch'] += watch_cnt
            summary['confluence_owner'] += owner_cnt
        
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

    if getattr(args, 'copyDashboards', None):
        src, dst = args.copyDashboards
        jira = get_jira_from_config(config)
        copy_user_dashboards(jira, src, dst, dry_run=getattr(args, 'dry_run', False))
        ok = True

    if getattr(args, 'copyPersonalSpace', None):
        src, dst = args.copyPersonalSpace
        confluence = get_confluence_client(config, admin_key=getattr(args, 'admin_key', False))
        jira = get_jira_from_config(config)
        success, msg = copy_personal_space(
            confluence, src, dst,
            src_username=getattr(args, 'srcUsername', None),
            dst_username=getattr(args, 'dstUsername', None),
            jira=jira,
            dry_run=getattr(args, 'dry_run', False)
        )
        print(msg)
        ok = True

    if getattr(args, 'transferSpace', None):
        if not getattr(args, 'admin_key', False):
            print("WARNING: --transferSpace requires --admin-key to work on restricted pages")
            print("         Without admin-key, many pages may fail to transfer")
        src, dst = args.transferSpace
        confluence = get_confluence_client(config, admin_key=getattr(args, 'admin_key', False))
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

    if getattr(args, 'movePersonalSpace', None):
        src, dst = args.movePersonalSpace
        confluence = get_confluence_client(config, admin_key=getattr(args, 'admin_key', False))
        jira = get_jira_from_config(config)
        success, msg, moved = move_personal_space(
            confluence, src, dst,
            src_username=getattr(args, 'srcUsername', None),
            dst_username=getattr(args, 'dstUsername', None),
            jira=jira,
            dry_run=getattr(args, 'dry_run', False)
        )
        print(msg)
        ok = True

    if getattr(args, 'updateSpaceOwnership', None):
        account_id = args.updateSpaceOwnership
        confluence = get_confluence_client(config, admin_key=getattr(args, 'admin_key', False))
        jira = get_jira_from_config(config)
        success, msg = update_space_ownership(
            confluence, account_id,
            username=getattr(args, 'srcUsername', None),
            jira=jira,
            dry_run=getattr(args, 'dry_run', False)
        )
        print(msg)
        ok = True

    if getattr(args, 'processConfluence', None):
        src, dst = args.processConfluence
        confluence = get_confluence_client(config, admin_key=getattr(args, 'admin_key', False))
        dry_run = getattr(args, 'dry_run', False)
        url = f'{config.get("url")}/wiki/'
        
        # Check for single page processing
        page_id = getattr(args, 'pageid', None)
        if not page_id and getattr(args, 'page_url', None):
            page_id = extract_page_id_from_url(args.page_url)
        
        if page_id:
            # Process single page
            print(f"Processing single page: {page_id}")
            owner_id = get_page_owner(confluence, page_id)
            print(f"  Current owner: {owner_id}")
            
            if owner_id == src:
                # Old user owns - grant edit and change owner
                if not dry_run:
                    try:
                        add_user_to_update_restriction(confluence, url, page_id, dst, dry_run=False)
                        print(f"  Granted edit to {dst}")
                    except Exception as e:
                        print(f"  FAILED to add editor: {e}")
                
                if dry_run:
                    print(f"  Would change owner to {dst}")
                else:
                    success, msg = set_page_owner(confluence, page_id, dst)
                    if success:
                        print(f"  Changed owner to {dst}")
                    else:
                        print(f"  FAILED to change owner: {msg}")
            else:
                print(f"  Page not owned by {src}, skipping owner change")
        else:
            # Process spaces
            total_edit = 0
            total_watch = 0
            total_owner = 0
            
            if args.spaces:
                for s in args.spaces:
                    print(f"\nProcessing space: {s}")
                    edit_cnt, watch_cnt, owner_cnt = process_space(config, confluence, s, src, dst, limit=500, dry_run=dry_run)
                    total_edit += edit_cnt
                    total_watch += watch_cnt
                    total_owner += owner_cnt
            else:
                print("Processing all spaces (this may take a long time)...")
                edit_cnt, watch_cnt, owner_cnt = process_space(config, confluence, "", src, dst, limit=500, dry_run=dry_run)
                total_edit = edit_cnt
                total_watch = watch_cnt
                total_owner = owner_cnt
            
            print("\n" + "=" * 50)
            print("CONFLUENCE PROCESSING SUMMARY")
            print("=" * 50)
            print(f"Pages with edit access granted: {total_edit}")
            print(f"Pages with watcher added:       {total_watch}")
            print(f"Pages with owner changed:       {total_owner}")
            print("=" * 50)
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
