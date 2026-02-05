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

import requests
from jira import JIRA, JIRAError
from requests.auth import HTTPBasicAuth

from opsMiles.ojira import get_login_config, list_jira_issues, get_jira_from_config
from opsMiles.confluence import process_space, get_confluence_client


def get_all_atlassian_users(config: Dict, page_size: int = 1000) -> List[Dict]:
    """Fetch all users from Atlassian REST /rest/api/3/users/search (paged).

    Returns list of user dicts as returned by the API.
    """
    base = config.get('url')
    if not base:
        raise ValueError('Missing url in config')
    url = base.rstrip('/') + '/rest/api/3/users/search'
    auth = HTTPBasicAuth(config.get('user'), config.get('password'))

    users = []
    start_at = 0
    while True:
        params = {'startAt': start_at, 'maxResults': page_size}
        r = requests.get(url, auth=auth, params=params)
        if r.status_code >= 400:
            raise RuntimeError(f'Failed to fetch users: {r.status_code} {r.text}')
        page = r.json()
        if not isinstance(page, list):
            # Some instances may return an object; handle gracefully
            raise RuntimeError(f'unexpected users response: {page}')
        for u in page:
            if isinstance(u, dict) and u.get('active'):
               users.append(u)

        if len(page) < page_size:
            break
        start_at += page_size
    return users


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


def list_user_groups(config: Dict, account_id: str) -> List[Dict]:
    """Minimal routine: return groups for an Atlassian accountId.

    Calls /rest/api/3/user/groups?accountId=... and returns the list (handles
    either list or paged dict with 'values'). No extras, no debug.
    """
    base = config.get('url')
    if not base:
        raise ValueError('Missing url in config')
    url = base.rstrip('/') + '/rest/api/3/user/groups'
    auth = HTTPBasicAuth(config.get('user'), config.get('password'))

    params = {'accountId': account_id, 'maxResults': 100}
    r = requests.get(url, auth=auth, params=params)
    if r.status_code >= 400:
        raise RuntimeError(f'Failed to fetch groups for {account_id}: {r.status_code} {r.text}')
    page = r.json()
    if isinstance(page, list):
        return page
    if isinstance(page, dict):
        return page.get('values') or page.get('groups') or []
    return []


# New helper: print groups for an account id (no-frills)
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
    issues = list_jira_issues(jira, query=f'project != PREOPS and watcher={account_id}', pred2=pred)
    return issues


def add_watcher(j:JIRA, config: Dict, account_id: str, issue: str) -> str:
    base = config.get('url')
    if not base:
        raise ValueError('Missing url in config')
    url = base.rstrip('/') + f'/rest/api/3/issue/{issue}/watchers'
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
                v = jira.assign_issue(i.key, dst)
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
    p.add_argument('--moveuser', nargs=2, metavar=('SRC','DST'), help=' Copy groups, reassign tickets and copy watcher from  DST accountId to SRC accountId')
    p.add_argument('--predicate', help=' partial predicate to pass to jira  like "and project=SE"')
    p.add_argument('--spaces', nargs='+', help=' for move user:one or more space names for confluence reasignment like DM EPO LSSTOps')

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
        copy_groups(config, src, dst, dry_run=dry_run)
        copy_watcher(config, src, dst, pred)
        reassign(config, src, dst, dry_run, pred)
        confluence = get_confluence_client(config)
        if args.spaces:
            for s in args.spaces:
                process_space(config,confluence, s, src, dst, limit=500, dry_run=dry_run)
        else:
            print ("This will take a long time since it will scan all spaces")
            process_space(config, confluence, "", src, dst, limit=500, dry_run=dry_run)
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
