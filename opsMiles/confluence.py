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

from urllib.parse import quote
from atlassian import Confluence

def get_confluence_client(config: dict, admin_key: bool = False) -> Confluence:
    """Create a Confluence client from login config dict.
    config keys expected: url, user, password
    
    If admin_key=True, adds the Atl-Confluence-With-Admin-Key header to bypass
    page restrictions (requires Confluence Cloud Premium/Enterprise and site admin).
    """
    import requests
    
    url = config.get("url")
    username = config.get("user")
    password = config.get("password")
    
    if admin_key:
        # Create session with admin key header
        session = requests.Session()
        session.headers.update({
            'Atl-Confluence-With-Admin-Key': 'true'
        })
        print("Admin key mode enabled - bypassing page restrictions")
        confluence = Confluence(url=url, username=username, password=password, session=session)
    else:
        confluence = Confluence(url=url, username=username, password=password)
    
    return confluence


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
    page_id = extract_page_id_from_url(page_url)
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


def can_user_update_page(session, base_url, page_id, account_id):
    """
    True iff 'account_id' can UPDATE (edit) this page, considering
    site + space + content restrictions.
    Returns False on 404 (page not found or permission check not supported).
    """
    try:
        r = session.post(
            f"{base_url.rstrip('/')}/rest/api/content/{page_id}/permission/check",
            json={
                "subject": {"type": "user", "identifier": account_id},
                "operation": "update",
            },
            headers={"Accept": "application/json"},
        )
        if r.status_code == 404:
            # Page not found or permission check not supported
            return False
        r.raise_for_status()
        return bool(r.json().get("hasPermission"))
    except Exception:
        return False


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


def allow_edit(confluence, url, page_id, title, old_accountid,  new_accountid, dry_run ):
    """
    Check if old_account_id can edit the page - if so allow new account id to edit
    unless it already can.
    :param confluence:
    :param url:
    :param page_id:
    :param title:
    :param old_accountid:
    :param new_accountid:
    :param dry_run:
    :return:
    """
    if page_is_favourited(confluence,url,old_accountid,page_id):
        print(f"Adding favoroite {page_id}")
        add_page_favourite(confluence,url,new_accountid,page_id)
    try:
        if can_user_update_page(confluence.session, url, page_id, new_accountid):
            #print(f"SKIP (Can update {new_accountid}): {title} (id={page_id})")
            return False

        if can_user_update_page(confluence.session, url, page_id, old_accountid):
            # old account can edit so let the new one also
            print(f"FIX  (allow update {new_accountid}): {title} (id={page_id})")
            add_user_to_update_restriction(confluence, url, page_id, new_accountid, dry_run=dry_run)
            return True

    except Exception as e:
        print(f"FAILED: {title} (id={page_id}) -> {e}", file=sys.stderr)
    return False



def get_page_owner(confluence, page_id: str) -> str:
    """Get the owner ID of a Confluence page using REST API v2.
    
    Returns the owner account ID, or empty string if not found.
    """
    try:
        base_url = confluence.url.rstrip('/')
        if base_url.endswith('/wiki'):
            api_url = f"{base_url}/api/v2/pages/{page_id}"
        else:
            api_url = f"{base_url}/wiki/api/v2/pages/{page_id}"
        
        response = confluence._session.get(api_url)
        if response.status_code == 200:
            return response.json().get('ownerId', '')
    except Exception:
        pass
    return ''


def process_space(
    config,
    confluence,
    space_key,
    old_account_id,
    new_account_id,
    limit=50,
    dry_run=False,
):
    """Process a Confluence space to transfer edit permissions, watchers, and ownership.
    
    Returns tuple (edit_count, watch_count, owner_count) with number of pages modified.
    """
    start = 0
    count = 0
    wcount = 0
    ocount = 0
    pcount = 0
    while True:
        pages = confluence.get_all_pages_from_space(
            space=space_key,
            start=start,
            limit=limit,
            expand="history,version",
        )

        if not pages:
            break
        url = f'{config.get("url")}/wiki/'
        for page in pages:
            pcount += 1
            page_id = page["id"]
            title = page["title"]
            if (pcount % 100) == 0:
                print (f"Checked {pcount} pages")

            # Check ownership first
            owner_id = ""
            try:
                owner_id = get_page_owner(confluence, page_id)
            except Exception as e:
                print(f"  FAILED to get owner: {title} - {e}")

            if owner_id == old_account_id:
                # Old user owns the page - no need to check edit, just grant and change owner
                if not dry_run:
                    try:
                        add_user_to_update_restriction(confluence, url, page_id, new_account_id, dry_run=False)
                    except Exception as e:
                        print(f"  FAILED to add editor: {title} - {e}")
                
                if dry_run:
                    print(f"  Would change owner: {title}")
                    ocount += 1
                else:
                    try:
                        success, msg = set_page_owner(confluence, page_id, new_account_id)
                        if success and msg != "skipped":
                            print(f"  Changed owner: {title}")
                            ocount += 1
                        elif not success:
                            print(f"  FAILED to change owner: {title} - {msg}")
                    except Exception as e:
                        print(f"  FAILED to change owner: {title} - {e}")
            else:
                # Old user doesn't own - use normal allow_edit check
                try:
                    ok = allow_edit(
                        confluence=confluence,
                        url=url,
                        page_id=page_id,
                        title=title,
                        old_accountid=old_account_id,
                        new_accountid=new_account_id,
                        dry_run=dry_run,
                    )
                    if ok:
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
    print (f"Allowed edit on {count}, watch {wcount}, changed owner {ocount}")
    return count, wcount, ocount


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

def page_is_favourited(confluence, base_url, account_id, page_id):
    """
    True iff account_id has favourited page_id.

    base_url must include /wiki, e.g.
      https://your-domain.atlassian.net/wiki
    """
    path = (
        "/rest/api/relation/favourite/from/user/"
        f"{quote(str(account_id), safe='')}"
        f"/to/content/{quote(str(page_id), safe='')}"
    )
    resp = confluence_request(confluence.session, "GET", base_url, path)
    if resp.status_code == 200:
        return True
    if resp.status_code == 404:
        return False
    resp.raise_for_status()


def add_page_favourite(confluence, base_url, account_id, page_id, dry_run=False):
    """
    Add page_id to account_id's favourites.
    """
    if dry_run:
        print(f"DRY-RUN: would favourite page {page_id} for {account_id}")
        return None

    path = (
        "/rest/api/relation/favourite/from/user/"
        f"{quote(str(account_id), safe='')}"
        f"/to/content/{quote(str(page_id), safe='')}"
    )
    resp = confluence_request(confluence.session, "PUT", base_url, path)
    resp.raise_for_status()
    return resp.json()


def get_username_from_accountid(jira, account_id: str) -> str:
    """
    Look up username from accountId via Jira user API.
    Returns username or None if not found.
    """
    if jira is None:
        return None
    try:
        user = jira.user(account_id)
        # The 'name' field is the username
        username = getattr(user, 'emailAddress', None)
        if username:
            # Split on @, remove spaces, lowercase
            username = username.split('@')[0].replace(' ', '').lower()
            print(f"  Looked up user: {username} ({getattr(user, 'displayName', '')})")
            return username
    except Exception as e:
        print(f"  User lookup failed: {e}")
    return None


def get_personal_space(confluence, account_id: str, username: str = None, jira=None) -> dict:
    """
    Find a user's personal space by accountId or username.
    Personal space keys in Confluence Cloud:
    - ~username (older format like ~ykang)
    - ~accountid_without_colons_and_dashes (newer format)
      e.g., 712020:c1fcfc8a-1182-487b-8115-7478bfc2d6b8 → ~712020c1fcfc8a1182487b81157478bfc2d6b8
    Returns the space dict or None if not found.
    """
    # Transform: remove : and - from account ID (exact match only)
    clean_id = account_id.replace(':', '').replace('-', '')
    
    # Build list of possible keys to try
    possible_keys = [
        f"~{clean_id}",  # e.g., ~712020c1fcfc8a1182487b81157478bfc2d6b8
    ]
    
    # If username provided, try that
    if username:
        possible_keys.insert(0, f"~{username}")
    else:
        # Try to look up username from accountId via Jira
        looked_up_username = get_username_from_accountid(jira, account_id)
        if looked_up_username:
            possible_keys.insert(0, f"~{looked_up_username}")
    
    for space_key in possible_keys:
        try:
            space = confluence.get_space(space_key, expand='homepage')
            if space:
                print(f"  Found space with key: {space_key}")
                return space
        except Exception as e:
            print(f"  Tried {space_key}: not found")
    
    return None


def set_page_owner(confluence, page_id: str, owner_account_id: str) -> tuple:
    """
    Set the owner of a Confluence page using REST API v2.
    Requires fetching the page first to get body and version info.
    Returns (success: bool, message: str) - returns (True, "skipped") if owner already matches.
    """
    try:
        # Build base URL - handle cases where /wiki may or may not be in confluence.url
        base_url = confluence.url.rstrip('/')
        if base_url.endswith('/wiki'):
            api_base = f"{base_url}/api/v2/pages/{page_id}"
        else:
            api_base = f"{base_url}/wiki/api/v2/pages/{page_id}"
        
        # First get the current page with body and version
        get_url = f"{api_base}?body-format=storage"
        get_response = confluence._session.get(get_url)
        if get_response.status_code != 200:
            return False, f"Failed to get page: HTTP {get_response.status_code} - {get_url}"
        
        page_data = get_response.json()
        
        # Check if owner already matches
        current_owner = page_data.get('ownerId', '')
        if current_owner == owner_account_id:
            return True, "skipped"
        
        current_version = page_data.get('version', {}).get('number', 1)
        title = page_data.get('title', '')
        body_value = page_data.get('body', {}).get('storage', {}).get('value', '')
        
        # Update page with new owner using PUT
        update_payload = {
            "id": page_id,
            "status": "current",
            "title": title,
            "body": {
                "representation": "storage",
                "value": body_value
            },
            "version": {
                "number": current_version + 1,
                "message": "Updated page owner",
                "minorEdit": True
            },
            "ownerId": owner_account_id
        }
        
        response = confluence._session.put(api_base, json=update_payload)
        if response.status_code in (200, 204):
            return True, "Owner updated"
        else:
            return False, f"HTTP {response.status_code}: {response.text[:200]}"
    except Exception as e:
        return False, str(e)


def copy_page_to_space(confluence, page_id: str, dst_space_key: str, parent_id: str = None, 
                       dst_owner_id: str = None, dry_run: bool = False) -> tuple:
    """
    Copy a page to a different space.
    If dst_owner_id is provided, sets the owner of the new page to that account.
    Returns (success: bool, new_page_id or error_msg)
    """
    if dry_run:
        return True, "dry-run"
    
    try:
        # Get the source page
        page = confluence.get_page_by_id(page_id, expand='body.storage,version')
        title = page.get('title')
        body = page.get('body', {}).get('storage', {}).get('value', '')
        
        # Create in destination space
        new_page = confluence.create_page(
            space=dst_space_key,
            title=title,
            body=body,
            parent_id=parent_id,
            representation='storage'
        )
        new_page_id = new_page.get('id')
        
        # Set owner if specified
        if dst_owner_id and new_page_id:
            success, msg = set_page_owner(confluence, new_page_id, dst_owner_id)
            if not success:
                print(f"    Warning: Could not set owner: {msg}")
        
        return True, new_page_id
    except Exception as e:
        return False, str(e)


def create_personal_space(confluence, account_id: str, display_name: str = None) -> tuple:
    """
    Create a personal space for a user if it doesn't exist.
    
    Returns (success: bool, space_key: str or error_msg)
    """
    # Build the space key from account ID (remove : and -)
    clean_id = account_id.replace(':', '').replace('-', '')
    space_key = f"~{clean_id}"
    
    # Check if space already exists
    try:
        existing = confluence.get_space(space_key)
        if existing:
            return True, space_key
    except Exception:
        pass  # Space doesn't exist, create it
    
    # Create the space
    space_name = f"{display_name}'s Space" if display_name else f"Personal Space {space_key}"
    try:
        base_url = confluence.url.rstrip('/')
        if base_url.endswith('/wiki'):
            api_url = f"{base_url}/api/v2/spaces"
        else:
            api_url = f"{base_url}/wiki/api/v2/spaces"
        
        payload = {
            "key": space_key,
            "name": space_name,
            "type": "personal"
        }
        
        response = confluence._session.post(api_url, json=payload)
        if response.status_code in (200, 201):
            print(f"Created personal space: {space_key}")
            return True, space_key
        else:
            return False, f"Failed to create space: HTTP {response.status_code} - {response.text[:200]}"
    except Exception as e:
        return False, str(e)


def move_page_to_space(confluence, page_id: str, dst_space_key: str, dst_parent_id: str = None) -> tuple:
    """
    Move a page to a different space.
    
    Returns (success: bool, message: str)
    """
    try:
        base_url = confluence.url.rstrip('/')
        if base_url.endswith('/wiki'):
            api_url = f"{base_url}/api/v2/pages/{page_id}/move"
        else:
            api_url = f"{base_url}/wiki/api/v2/pages/{page_id}/move"
        
        payload = {
            "spaceId": None,  # Will be filled in
            "targetKey": dst_space_key
        }
        
        # Get the destination space ID
        try:
            dst_space = confluence.get_space(dst_space_key)
            if dst_space:
                space_id = dst_space.get('id')
                if space_id:
                    payload["spaceId"] = space_id
        except Exception:
            pass
        
        # If we have a parent, set it
        if dst_parent_id:
            payload["parentId"] = dst_parent_id
        
        # Try using the move endpoint (Confluence Cloud)
        response = confluence._session.post(api_url, json=payload)
        if response.status_code in (200, 201, 204):
            return True, "moved"
        
        # Fallback: Update page with new space using v1 API
        # Get the page first
        page = confluence.get_page_by_id(page_id, expand='body.storage,version,space')
        if not page:
            return False, "Page not found"
        
        title = page.get('title')
        body = page.get('body', {}).get('storage', {}).get('value', '')
        version = page.get('version', {}).get('number', 1)
        
        # Use the v1 API to update page with new space
        update_url = f"{confluence.url.rstrip('/')}/rest/api/content/{page_id}"
        if not confluence.url.rstrip('/').endswith('/wiki'):
            update_url = f"{confluence.url.rstrip('/')}/wiki/rest/api/content/{page_id}"
        
        update_payload = {
            "type": "page",
            "title": title,
            "space": {"key": dst_space_key},
            "body": {
                "storage": {
                    "value": body,
                    "representation": "storage"
                }
            },
            "version": {"number": version + 1}
        }
        
        if dst_parent_id:
            update_payload["ancestors"] = [{"id": dst_parent_id}]
        
        response = confluence._session.put(update_url, json=update_payload)
        if response.status_code in (200, 201):
            return True, "moved via update"
        else:
            error_text = response.text[:300]
            # Check if page already exists in destination
            if 'content with the name' in error_text.lower() or 'already exists' in error_text.lower():
                return True, "skipped - already exists in destination"
            return False, f"HTTP {response.status_code}: {error_text}"
            
    except Exception as e:
        error_str = str(e)
        # Check if page already exists in destination
        if 'content with the name' in error_str.lower() or 'already exists' in error_str.lower():
            return True, "skipped - already exists in destination"
        return False, error_str


def move_personal_space(confluence, src_account_id: str, dst_account_id: str,
                        src_username: str = None, dst_username: str = None,
                        jira=None, dry_run: bool = False) -> tuple:
    """
    Move all pages from src user's personal space to dst user's personal space.
    Creates the destination space if it doesn't exist.
    
    Returns (success: bool, message: str, moved_count: int)
    """
    # Find source space
    print(f"Looking for source user's personal space...")
    src_space = get_personal_space(confluence, src_account_id, src_username, jira=jira)
    if not src_space:
        return False, f"No personal space found for {src_account_id}", 0
    
    src_key = src_space.get('key')
    src_name = src_space.get('name', src_key)
    print(f"Found source personal space: {src_name} ({src_key})")
    
    # Find or create destination space
    print(f"Looking for destination user's personal space...")
    dst_space = get_personal_space(confluence, dst_account_id, dst_username, jira=jira)
    
    if not dst_space:
        print(f"Destination space not found, attempting to create...")
        # Try to get display name for the space name
        display_name = None
        if jira:
            try:
                user = jira.user(dst_account_id)
                display_name = user.displayName
            except Exception:
                pass
        
        success, result = create_personal_space(confluence, dst_account_id, display_name)
        if not success:
            return False, f"Could not create destination space: {result}", 0
        dst_key = result
        print(f"Created destination space: {dst_key}")
    else:
        dst_key = dst_space.get('key')
        print(f"Found destination personal space: {dst_space.get('name', dst_key)} ({dst_key})")
    
    # Get all pages from source space using get_all_pages_from_space with proper pagination
    all_pages = []
    start = 0
    limit = 50
    
    while True:
        pages = confluence.get_all_pages_from_space(space=src_key, start=start, limit=limit, expand='ancestors')
        print(f"  Fetched {len(pages) if pages else 0} pages at offset {start}")
        if not pages:
            break
        all_pages.extend(pages)
        start += limit
        # Safety check - if we got fewer than limit, we're done
        if len(pages) < limit:
            break
    
    if not all_pages:
        return True, "No pages found in source space", 0
    
    print(f"Found {len(all_pages)} total pages to move")
    
    # Build a map of old page IDs to track hierarchy
    # Sort pages by ancestor count (parents first, then children)
    def ancestor_count(page):
        return len(page.get('ancestors', []))
    
    all_pages.sort(key=ancestor_count)
    
    # Track mapping from old page ID to new page ID for parent references
    id_mapping = {}
    
    moved = 0
    skipped = 0
    failed = 0
    
    for page in all_pages:
        page_id = page.get('id')
        title = page.get('title')
        ancestors = page.get('ancestors', [])
        
        # Find the immediate parent (last in ancestors list)
        dst_parent_id = None
        if ancestors:
            old_parent_id = ancestors[-1].get('id')
            # Check if parent was already moved
            dst_parent_id = id_mapping.get(old_parent_id)
        
        if dry_run:
            print(f"  Would move: {title}")
            moved += 1
            id_mapping[page_id] = page_id  # Fake mapping for dry run
        else:
            success, msg = move_page_to_space(confluence, page_id, dst_key, dst_parent_id)
            if success:
                if 'skipped' in msg:
                    print(f"  Skipped (exists): {title}")
                    skipped += 1
                else:
                    print(f"  Moved: {title}")
                    moved += 1
                # The page keeps its ID after move
                id_mapping[page_id] = page_id
            else:
                print(f"  FAILED to move: {title} - {msg}")
                failed += 1
    
    return True, f"Moved {moved} pages, skipped {skipped} (already exist), failed {failed}", moved


def transfer_personal_space(config, confluence, src_account_id: str, dst_account_id: str,
                            src_username: str = None, dst_username: str = None,
                            jira=None, dry_run: bool = False) -> tuple:
    """
    Transfer ownership of all pages in src user's personal space to dst user,
    then move the pages to the destination user's personal space.
    Requires admin-key for restricted pages.
    
    Returns (success: bool, message: str, counts: tuple(edit, watch, owner, moved))
    """
    # Find source space
    print(f"Looking for source user's personal space...")
    src_space = get_personal_space(confluence, src_account_id, src_username, jira=jira)
    if not src_space:
        return False, f"No personal space found for {src_account_id}", (0, 0, 0, 0)
    
    src_key = src_space.get('key')
    src_name = src_space.get('name', src_key)
    print(f"Found personal space: {src_name} ({src_key})")
    
    # Process the space to transfer ownership
    print(f"Transferring ownership from {src_account_id} to {dst_account_id}...")
    edit_cnt, watch_cnt, owner_cnt = process_space(
        config, confluence, src_key, src_account_id, dst_account_id,
        limit=500, dry_run=dry_run
    )
    
    # Always move pages to destination user's personal space
    print(f"\nMoving pages to destination user's personal space...")
    success, msg, moved_cnt = move_personal_space(
        confluence, src_account_id, dst_account_id,
        src_username=src_username, dst_username=dst_username,
        jira=jira, dry_run=dry_run
    )
    print(f"Move result: {msg}")
    
    return True, f"Transferred {owner_cnt} page owners, {edit_cnt} edit perms, {watch_cnt} watchers, moved {moved_cnt} pages", (edit_cnt, watch_cnt, owner_cnt, moved_cnt)


def copy_personal_space(confluence, src_account_id: str, dst_account_id: str, 
                        src_username: str = None, dst_username: str = None,
                        jira=None, dry_run: bool = False) -> tuple:
    """
    Copy all pages from src user's personal space to dst user's personal space.
    Returns (success: bool, message: str)
    
    If usernames are not provided, will look up via Jira API.
    """
    # Find source space
    print(f"Looking for source personal space...")
    src_space = get_personal_space(confluence, src_account_id, src_username, jira=jira)
    if not src_space:
        return False, f"No personal space found for {src_account_id}"
    
    src_key = src_space.get('key')
    src_name = src_space.get('name', src_key)
    print(f"Found source personal space: {src_name} ({src_key})")
    
    # Find destination space
    print(f"Looking for destination personal space...")
    dst_space = get_personal_space(confluence, dst_account_id, dst_username, jira=jira)
    if not dst_space:
        return False, f"No personal space found for {dst_account_id}. User may need to create one first."
    
    dst_key = dst_space.get('key')
    dst_name = dst_space.get('name', dst_key)
    print(f"Found destination personal space: {dst_name} ({dst_key})")
    
    # Get all pages from source space
    pages = confluence.get_all_pages_from_space(src_key, expand='body.storage')
    if not pages:
        return True, f"No pages found in {src_key}"
    
    copied = 0
    failed = 0
    print(f"Found {len(pages)} pages to copy")
    
    for page in pages:
        page_id = page.get('id')
        title = page.get('title')
        
        if dry_run:
            print(f"  Would copy: {title}")
            copied += 1
        else:
            success, result = copy_page_to_space(confluence, page_id, dst_key, 
                                                  dst_owner_id=dst_account_id, dry_run=dry_run)
            if success:
                print(f"  Copied: {title} (owner set to {dst_account_id})")
                copied += 1
            else:
                print(f"  FAILED: {title} - {result}")
                failed += 1
    
    return True, f"Copied {copied} pages, failed {failed}"


def update_space_ownership(confluence, account_id: str,
                           username: str = None, jira=None, dry_run: bool = False) -> tuple:
    """
    Update ownership of all pages in a user's personal space to that user.
    This is useful when pages were copied into a space but have the wrong owner.
    
    Args:
        confluence: Confluence client
        account_id: Account ID of the user (used to find space and set as owner)
        username: Optional username to help find the space
        jira: Optional Jira client for username lookup
        dry_run: If True, only show what would be done
        
    Returns (success: bool, message: str)
    """
    # Find the personal space
    print(f"Looking for personal space for {account_id}...")
    space = get_personal_space(confluence, account_id, username, jira=jira)
    if not space:
        return False, f"No personal space found for {account_id}"
    
    space_key = space.get('key')
    space_name = space.get('name', space_key)
    print(f"Found personal space: {space_name} ({space_key})")
    
    # Get all pages from the space
    pages = confluence.get_all_pages_from_space(space_key)
    if not pages:
        return True, f"No pages found in {space_key}"
    
    updated = 0
    skipped = 0
    failed = 0
    print(f"Found {len(pages)} pages to check ownership for {account_id}")
    
    for page in pages:
        page_id = page.get('id')
        title = page.get('title')
        
        if dry_run:
            print(f"  Would check/update owner: {title}")
            updated += 1
        else:
            success, msg = set_page_owner(confluence, page_id, account_id)
            if success and msg == "skipped":
                print(f"  Skipped (already owned): {title}")
                skipped += 1
            elif success:
                print(f"  Updated owner: {title}")
                updated += 1
            else:
                print(f"  FAILED: {title} - {msg}")
                failed += 1
    
    return True, f"Updated {updated} pages, skipped {skipped} (already owned), failed {failed}"

