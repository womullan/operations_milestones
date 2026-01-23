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
import sys
from typing import Dict, List

import requests
from requests.auth import HTTPBasicAuth

from opsMiles.ojira import get_login_config


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
    for u in users:
        dn = u.get('displayName')
        if not dn or dn in dups:
            continue
        # find other names that start with base (case-insensitive), excluding exact match
        for trymatch in users:
            if trymatch != u :
                odn = trymatch.get('displayName')
                if dn.startswith(odn):  # got a dup
                    if not dn in dups:
                        dups[dn]=[u]
                    dups[dn].append(trymatch)

    return dups


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    p = argparse.ArgumentParser(description='Atlassian admin helpers')
    p.add_argument('--dups', action='store_true', help='Find duplicate users by displayName and similar-name pairs')
    p.add_argument('-a', '--ask', action='store_true', help='Prompt for password / API token')
    p.add_argument('-u', '--uname', help='Username for keyring lookup (email)')
    p.add_argument('-p', '--passwd', help='Password / API token (optional)')

    args = p.parse_args(argv)

    if not args.dups:
        p.print_help()
        return 2

    # reuse existing helper to build login config
    config = get_login_config(args)

    print('Fetching users from Atlassian...')
    users = get_all_atlassian_users(config)
    print(f'Got {len(users)} users')

    dups = find_duplicate_displayname_users(users)

    if not dups:
        print('No potential duplicates found (exact or similar).')
        return 0

    if dups:
        for name, info in dups.items():
            print(f" {name}" )
            for u in info:
                if isinstance(u,dict):
                    display = u.get('displayName') or ''
                    aid = u.get('accountId') or ''
                    email = u.get('emailAddress') or ''
                    print(f"  - {display} | {aid} | {email}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
