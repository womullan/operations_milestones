"""
Minimal Confluence search-and-replace helper using the atlassian Python package.
Uses the existing `get_login_config` from `opsMiles.ojira` to retrieve login info.

Functions:
- replace_pages(config, search_string, replace_string, space=None, dry_run=True, confirm_per_page=False)

Notes:
- This expects the `atlassian` package to be installed (pip install atlassian-python-api).
- For Atlassian Cloud, the password should be an API token.
"""

from typing import Optional
import re
import html
import sys

from atlassian import Confluence

def get_confluence_client(config: dict) -> Confluence:
    """Create a Confluence client from login config dict.
    config keys expected: url, user, password
    """
    url = config.get("url")
    username = config.get("user")
    password = config.get("password")
    # atlassian.Confluence accepts cloud if using Atlassian Cloud; leave defaults.
    return Confluence(url=url, username=username, password=password)


def _paginate_cql(confluence: Confluence, cql: str):
    """Yield result dicts for CQL query, handling paging."""
    start = 0
    limit = 50
    while True:
        r = confluence.cql(cql, start=start, limit=limit)
        results = r.get("results", [])
        if not results:
            break
        for item in results:
            yield item
        start += limit
        if start >= r.get("size", 0):
            break


# Shared helper used by both replace_pages and update_single_page
def _update_page_by_id(confluence_client, page_id, candidates, replace_s, dry_run_flag, confirm_flag):
    """Return tuple (matched, updated, apply_all_selected).
    matched: pattern found in page storage
    updated: change was applied (False if dry_run or skipped)
    apply_all_selected: user chose 'a' to apply to all remaining pages
    """
    # 'candidates' is a list of literal search strings to try on this page
    # they should be ordered from preferred (exact) to fallback (escaped/inner)
    # Always use the storage representation (body.storage)
    page = confluence_client.get_page_by_id(page_id, expand='body.storage,version')
    title = page.get('title')
    storage = page.get('body', {}).get('storage', {}).get('value', '') or ''
    representation = 'storage'

    matched = False
    new_storage = storage

    # Try each candidate string for this page; replace the first candidate that appears.
    # If a candidate is an escaped form (contains '&lt;' or '&gt;') we should replace with escaped replacement.
    for cand in candidates:
        if not cand:
            continue
        if cand in storage:
            matched = True
            # decide replacement form: if candidate looks escaped, escape the replacement
            if '&lt;' in cand or '&gt;' in cand or '&amp;' in cand:
                rep = html.escape(replace_s)
            else:
                rep = replace_s
            new_storage = storage.replace(cand, rep)
            break

    if not matched:
        # final fallback: case-insensitive search on raw/unescaped storage
        try:
            for cand in candidates:
                if not cand:
                    continue
                ci_pat = re.compile(re.escape(cand), flags=re.IGNORECASE)
                if ci_pat.search(storage):
                    matched = True
                    new_storage = ci_pat.sub(replace_s, storage)
                    break
            if not matched:
                # try unescaped storage
                unescaped = html.unescape(storage)
                for cand in candidates:
                    if not cand:
                        continue
                    ci_pat = re.compile(re.escape(cand), flags=re.IGNORECASE)
                    if ci_pat.search(unescaped):
                        matched = True
                        new_unescaped = ci_pat.sub(replace_s, unescaped)
                        new_storage = html.escape(new_unescaped)
                        break
        except re.error:
            pass
    if not matched:
        return (False, False, False)

    if new_storage == storage:
        return (True, False, False)

    print(f"Page id={page_id} title='{title}' : will replace occurrences")

    if dry_run_flag:
        return (True, False, False)

    if confirm_flag:
        try:
            choice = input(f"Apply replacement on page '{title}' (id={page_id})? [y/N/a]: ").strip().lower()
        except EOFError:
            choice = 'n'
        if choice == 'a':
            confluence_client.update_page(page_id, title, new_storage, representation='storage')
            print(f"Updated page id={page_id} title='{title}'")
            return (True, True, True)
        if choice != 'y':
            print(f"Skipped page id={page_id} title='{title}'")
            return (True, False, False)

    confluence_client.update_page(page_id, title, new_storage, representation='storage')
    print(f"Updated page id={page_id} title='{title}'")
    return (True, True, False)


def replace_pages(config: dict, search_string: str, replace_string: str,
                  space: Optional[str] = None, dry_run: bool = True, confirm_per_page: bool = False):
    """Search Confluence pages containing `search_string` and replace with `replace_string`.

    Args:
      config: login config (url, user, password) — use get_login_config from ojira.py
      search_string: literal string to find
      replace_string: literal replacement
      space: optional Confluence space key to restrict search
      dry_run: if True, only print what would be changed
      confirm_per_page: if True and not dry_run, prompt before updating each matched page

    Returns: list of page ids modified (or that would be modified).
    """
    confluence = get_confluence_client(config)

    # Build CQL query. Use text ~ for text search. Escape double quotes.
    esc = search_string.replace('"', '\\"')
    # Also search for inner email if search_string is angle-wrapped or if pages store it without brackets
    inner = search_string
    if search_string.startswith('<') and search_string.endswith('>'):
        inner = search_string[1:-1]
    esc_inner = inner.replace('"', '\\"')
    # Build a CQL that matches either the exact string or the inner form
    cql = f'type=page and (text ~ "{esc}" or text ~ "{esc_inner}")'
    if space:
        cql = f'space = "{space}" and {cql}'

    modified = []
    apply_all = False

    # use literal substring matching
    # Build candidate forms to try per-page: exact, inner (if <...>), and escaped versions
    inner = inner if 'inner' in locals() else (search_string[1:-1] if search_string.startswith('<') and search_string.endswith('>') else search_string)
    candidates = [search_string]
    if inner and inner != search_string:
        candidates.append(inner)
    # escaped variants
    candidates.append(html.escape(search_string))
    if inner and inner != search_string:
        candidates.append(html.escape(inner))

    for res in _paginate_cql(confluence, cql):
        page_id = res.get("id")
        # decide whether to prompt: if confirm_per_page True and not apply_all
        confirm_flag = (confirm_per_page and not apply_all)
        # call helper with candidate list for this page
        matched, updated, apply_all_sel = _update_page_by_id(confluence, page_id, candidates, replace_string, dry_run, confirm_flag)
        if apply_all_sel:
            apply_all = True
        if matched:
            # if dry_run, consider matched as listing
            if dry_run:
                modified.append(page_id)
            elif updated:
                modified.append(page_id)

    return modified


def extract_page_id_from_url(url: str) -> Optional[str]:
    """Try to extract a Confluence page id from common URL patterns.
    Returns the page id string or None if not found.
    Patterns handled:
      - ...pageId=12345 (query param)
      - /pages/12345/...
      - .../12345
    """
    # pageId=12345
    m = re.search(r"[?&]pageId=(\d+)", url)
    if m:
        return m.group(1)
    # /pages/12345 or /pages/12345/
    m = re.search(r"/pages/(\d+)(?:/|$)", url)
    if m:
        return m.group(1)
    # trailing numeric id at end of path
    m = re.search(r"/(\d+)(?:/|$)(?:\?|$)", url)
    if m:
        return m.group(1)
    return None


def update_single_page(config: dict, page_url: str, search_string: str, replace_string: str,
                       dry_run: bool = True, confirm: bool = False):
    """Update a single Confluence page specified by URL.

    Args:
      config: login config (url, user, password)
      page_url: full URL of the Confluence page
      search_string: literal string to find
      replace_string: literal replacement
      dry_run: if True, only report (no changes)
      confirm: if True and not dry_run, prompt before applying the change

    Returns list with the page id if updated (or would be updated on dry run), else empty list.
    """
    confluence = get_confluence_client(config)
    page_id = _extract_page_id_from_url(page_url)
    if not page_id or page_id=='None':
        raise ValueError(f"Could not extract page id from URL: {page_url}")

    # Build candidates for single-page update
    single_inner = search_string[1:-1] if search_string.startswith('<') and search_string.endswith('>') else search_string
    single_candidates = [search_string]
    if single_inner and single_inner != search_string:
        single_candidates.append(single_inner)
    single_candidates.append(html.escape(search_string))
    if single_inner and single_inner != search_string:
        single_candidates.append(html.escape(single_inner))
    # Reuse the shared helper with candidates
    matched, updated, _ = _update_page_by_id(confluence, page_id, single_candidates, replace_string, dry_run, confirm)
    if not matched:
        print(f"Search string not found on page id={page_id}")
        return []
    if dry_run and not updated:
        return [page_id]
    if updated:
        return [page_id]
    return []

def page_has_watcher(confluence, page_id, account_id):
    """
    Return True if account_id is a watcher of page_id.
    Best-effort: returns False if watcher API is restricted.
    """
    try:
        watchers = confluence.get_page_watchers(page_id)
        return any(w["accountId"] == account_id for w in watchers)
    except Exception:
        return False


def add_watcher(confluence, page_id, account_id, dry_run=False):
    """
    Add account_id as watcher to page_id.
    """
    if dry_run:
        print(f"  DRY-RUN: would add watcher {account_id}")
        return

    confluence.add_watcher_to_page(page_id, account_id)
    print(f"  added watcher {account_id}")




def confluence_request(session, method, base_url, path, *, params=None, json=None):
    """
    Confluence Cloud REST v1 helper.
    base_url should include /wiki, e.g. https://rubinobs.atlassian.net/wiki
    path should start with /rest/api/...
    """
    url = base_url.rstrip("/") + path
    r = session.request(method=method, url=url, params=params, json=json)
    return r


def page_has_update_restrictions(session, base_url, page_id):
    """
    Returns True if the page already has any 'update' restrictions (user or group).
    Uses: GET /rest/api/content/{id}/restriction/byOperation/update
    """
    r = confluence_request(
        session,
        "GET",
        base_url,
        f"/rest/api/content/{page_id}/restriction/byOperation/update",
        params={"expand": "restrictions.user,restrictions.group"},
    )

    if r.status_code == 404:
        # No restrictions object found (treat as unrestricted)
        return False

    r.raise_for_status()
    data = r.json()
    restrictions = data.get("restrictions", {})
    users = restrictions.get("user", {}).get("results", []) or []
    groups = restrictions.get("group", {}).get("results", []) or []
    return (len(users) + len(groups)) > 0


def can_user_update_page(session, base_url, page_id, account_id):
    """
    True iff 'account_id' can UPDATE (edit) this page, considering
    site + space + content restrictions.
    """
    r = session.post(
        f"{base_url.rstrip('/')}/rest/api/content/{page_id}/permission/check",
        json={
            "subject": {"type": "user", "identifier": account_id},
            "operation": "update",
        },
        headers={"Accept": "application/json"},
    )
    r.raise_for_status()
    return bool(r.json().get("hasPermission"))


def _put_update_editor(confluence, page_id: str, account_id: str):
    """
    Confluence Cloud: add user to 'update' (edit) restriction.
    PUT /rest/api/content/{id}/restriction/byOperation/update/user?accountId=...
    """
    path = f"/rest/api/content/{page_id}/restriction/byOperation/update/user"
    resp = confluence.request(
        method="PUT",
        path=path,
        params={"accountId": account_id},
    )
    return resp


def add_user_to_update_restriction(confluence, base_url, page_id, accountid, dry_run=False):
    """
    Adds user to existing update restriction:
    PUT /rest/api/content/{id}/restriction/byOperation/update/user?accountId=...
    """
    if dry_run:
        print(f"  DRY-RUN: would add accountId={accountid} to UPDATE restriction")
        return

    try:
        resp = _put_update_editor(confluence, page_id, accountid)
        if resp.status_code == 200:
            return
    except Exception as ex:
        # If Confluence says we'd evict ourselves, add ourselves first then retry.
        # This is the exact error class you hit. :contentReference[oaicite:3]{index=3}
        if "evicts current user" in str(ex):
            me = _get_current_account_id(confluence)

            r2 = _put_update_editor(confluence, page_id, me)
            r2.raise_for_status()

            r3 = _put_update_editor(confluence, page_id, accountid)
            r3.raise_for_status()
            return

    # Anything else: raise with full context
    resp.raise_for_status()



def _get_current_account_id(confluence) -> str:
    """
    Confluence Cloud: get the current user accountId
    GET /rest/api/user/current
    """
    resp = confluence.request(method="GET", path="/rest/api/user/current")
    resp.raise_for_status()
    return resp.json()["accountId"]


def allow_edit(confluence, url, page_id, title, new_accountid, dry_run ):
    try:
        #if not page_has_update_restrictions(session, url, page_id):
        if can_user_update_page(confluence.session, url, page_id, new_accountid):
            # Important safety: do NOT create new restrictions.
            print(f"SKIP ({new_accountid}Can update ): {title} (id={page_id})")
        else:
            print(f"FIX  (restricted update): {title} (id={page_id})")
            add_user_to_update_restriction(confluence, url, page_id, new_accountid, dry_run=dry_run)
            return True

    except Exception as e:
        print(f"FAILED: {title} (id={page_id}) -> {e}", file=sys.stderr)
    return False



def process_space(
    config,
    confluence,
    space_key,
    old_account_id,
    new_account_id,
    limit=50,
    dry_run=False,
):
    start = 0
    count = 0
    wcount = 0
    while True:
        pages = confluence.get_all_pages_from_space(
            space=space_key,
            start=start,
            limit=limit,
            expand="history,version",
        )

        if not pages:
            break

        for page in pages:
            page_id = page["id"]
            title = page["title"]
            creator_id = page["history"]["createdBy"]["accountId"]

            #print(f"Checking: {title} (id={page_id})")

            # Cannot Transfer ownership - cna make sure editable
            url = f'{config.get("url")}/wiki/'
            if creator_id == old_account_id:
                try:
                    print(f"Check/allow edit: {title} (id={page_id})")
                    ok = allow_edit(
                        confluence=confluence,
                        url=url,
                        page_id=page_id,
                        title=title,
                        new_accountid=new_account_id,
                        dry_run=dry_run,
                    )
                    if ok :
                        count += 1
                except Exception as e:
                    print(f"  FAILED to add editor: {e}")

            # Transfer watcher
            if page_has_watcher(confluence, page_id, old_account_id):
                try:
                    print(f"Trying to watch : {title} (id={page_id})")
                    add_watcher(
                        confluence,
                        page_id,
                        new_account_id,
                        dry_run=dry_run,
                    )
                    wcount += 1
                except Exception as e:
                    print(f"  FAILED to add watcher: {e}")

        start += limit
    print (f"Allowed edit on  {count}, watch {wcount}")


def list_spaces(confluence, limit=50):
    """
    Yield all spaces visible to the authenticated user.
    """
    start = 0

    while True:
        result = confluence.get_all_spaces(start=start, limit=limit)

        spaces = result.get("results", [])
        if not spaces:
            break

        for space in spaces:
            yield space

        start += limit
