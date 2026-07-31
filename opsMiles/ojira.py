import sys

from atlassian import Confluence
from jira import JIRA

from opsMiles.uname import get_from_keyring

#API_ENDPOINT = "https://jira.lsstcorp.org/rest/api/latest/"
EP = "https://rubinobs.atlassian.net"
API_ENDPOINT = f"{EP}/rest/api/3/"

MFIELDS = ["key", "RO Milestone ID", "type", "summary", "duedate", "startdate",
          "RubinTeam", "component", "Milestone Level", "status"]

FIELDS = ["key", "type", "summary", "duedate", "Start date",
           "RubinTeam", "component", "status"]

def list(jira=None, fields=FIELDS, pred2=""):
    """
    Get the  issues from Jira .
    set pred2="" to restric like "and labels=USDF"
    """

    query = "project = RDO " + pred2
    query = query  +  " order by duedate asc"

    r = jira.search_issues(jql_str=query, fields=fields,  maxResults=500)
    return r

def list_milestones(jira=None, pred2='and (component in ("Data Management", '
                                     '"System Performance", "RDO")'):
    """
    Get the milestone issues from Jira.
    Defaults to Data Management and System Performance
    set pred2="" to get all
    """

    fields = MFIELDS
    query = 'type in ("L1 Milestone", "L2 Milestone", "L3 Milestone") ' + pred2
    query = query  +  " order by duedate asc"

    r = jira.search_issues(jql_str=query, fields=fields,  maxResults=500)
    return r


def set_jira_due_date(ms, due_date, jira=None, issue=None):
    """
    Update the duedate of the issue in jira - add a comment also
    if jira is passed. If the issue_id is not passed then it will be looked up
    based on a label with the milestone in it.
    Could not get the issue,update to work so need to still do rest call for
    that - but add comment used JIRA class.

    :param ms: Milesonte ID
    :param due_date: date
    :param jira: optional JIRA object do not pass for no comments
    :issue issue: optiona issue - will look up on ms
    :return:
    """

    if issue is None:
        p2 = " and labels = " + ms
        issues = list_jira_issues(jira, pred2=p2)[0]
        if issues:
            issue = issues[0]
        else:
            raise Exception("There is no issue tagged " + ms)

    issue_id: str = issue.key
    message = "Setting Milestone " + ms + " due date on " + issue_id + " to " + due_date
    print(message)
    issue.update(duedate=due_date, notifyUsers=False)
    jira.add_comment(issue_id, message)

    # requests.put(API_ENDPOINT + "issue/" + issue_id, auth=(user, pw), json=data)


def list_jira_issues(jira, pred2=None, query=None, order="order by duedate asc", fields=FIELDS):
    """
    :JIRA jira: setup up JIRA object
    :String query: Query string "
    :String pred2: If you use the defualt query string but want to
                    add more predicate or sort order start with AND or OR
    """
    if query is None:
        query = """resolution = Unresolved AND
                   (type = epic or type= story) AND labels is not EMPTY """

    if (pred2 is not None):
        query = query + " " + pred2
    query = query + " " + order
    print(f"Query:{query}")
    r = jira.search_issues(jql_str=query, fields=fields, maxResults=False)
    return r


def get_jira_from_config(config:dict):
    return get_jira(username=config['user'], prompt=False, password=config['password'])[2]

def get_jira(username=None, prompt=False, password=None):
    """ Setup up the JIRA object endpoint - prompt
        for username and passwd as needed.
        Password will be looked up from key chain if not passed.
    :String username: Optionally pass the username (prompted othereise)
    """

    user = username
    pw = password
    if password is None:
        user, pw = get_from_keyring(username=username, prompt=prompt)
    print(f"Jira user: {user} end point: {EP}")
    jira = JIRA(server=EP, basic_auth=(user, pw))
    try:
        jira.myself()
    except Exception as e:
        raise Exception(f"Authentication failed for user '{user}': {e}")
    return (user, pw, jira)

def get_login_config(args):
    username = args.uname
    user, pw = get_from_keyring(username=username, prompt=args.ask)
    print(f"Jira user: {user} end point: {EP}")
    return ({"user": f"{username}",
            "password": f"{pw}",
            "url": f"{EP}"})

def update_one(jira, user, pw):
    """ update due date on specific milestone as a test"""
    ms = "DO-DI-M14"
    p2 = " and labels = " + ms
    r = list_jira_issues(jira, pred2=p2)
    key = r[0].key
    print(key)
    issue = jira.issue(key)
    ddate = "2020-09-10"
    set_jira_due_date(jira, user, pw, ms, r, ddate)
    # issue.update(duedate=ddate)


def get_last_comment(jira, key):
    """ Get the last comment on the issue
    :param jira:
    :param key:
    :return: String
    """
    issue = jira.issue(key)
    comments = issue.fields.comment.comments
    if comments:
        return comments[-1].body
    return ""




# ============================================================================
# User and Group Management Functions
# ============================================================================

def get_all_atlassian_users(config: dict, page_size: int = 1000) -> list:
    """Fetch all users from Atlassian REST /rest/api/3/users/search (paged).

    Returns list of user dicts as returned by the API.
    """
    import requests
    from requests.auth import HTTPBasicAuth
    
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
            raise RuntimeError(f'unexpected users response: {page}')
        for u in page:
            if isinstance(u, dict) and u.get('active'):
               users.append(u)

        if len(page) < page_size:
            break
        start_at += page_size
    return users


def get_account_ids_by_display_prefix(config: dict, prefix: str) -> list:
    """Return list of user info for accounts whose displayName starts with prefix."""
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


def list_user_groups(config: dict, account_id: str) -> list:
    """Return groups for an Atlassian accountId."""
    import requests
    from requests.auth import HTTPBasicAuth
    
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


def add_user_to_group(config: dict, account_id: str, group_name: str) -> str:
    """Add a user to a group. Returns 'added', 'exists', or error string."""
    import requests
    from requests.auth import HTTPBasicAuth
    
    base = config.get('url')
    if not base:
        raise ValueError('Missing url in config')
    url = base.rstrip('/') + '/rest/api/3/group/user'
    auth = HTTPBasicAuth(config.get('user'), config.get('password'))
    params = {'groupname': group_name}
    payload = {'accountId': account_id}
    r = requests.post(url, auth=auth, params=params, json=payload)
    if r.status_code == 201:
        return 'added'
    if r.status_code == 409:
        return 'exists'
    return f'error:{r.status_code} {r.text}'


def copy_groups(config: dict, src_account: str, dst_account: str, dry_run: bool = False) -> None:
    """Copy all groups where src_account is a member to dst_account."""
    groups = list_user_groups(config, src_account)
    if not groups:
        print(f'No groups found for source account {src_account}')
        return
    if dry_run:
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


# ============================================================================
# Issue Operations (watcher, reporter, assignee)
# ============================================================================

def get_issues_assigned(jira: JIRA, account_id: str, pred: str) -> list:
    """Return the issues assigned to account_id."""
    issues = list_jira_issues(jira, query=f'project != PREOPS and assignee={account_id}', pred2=pred)
    return issues


def get_issues_watched(jira: JIRA, account_id: str, pred: str) -> list:
    """Return the issues watched by account_id."""
    issues = list_jira_issues(jira, query=f'project != PREOPS and watcher={account_id} and '
                                          f'status NOT IN (Closed, Done, Resolved, Cancelled, Deprecated, "Journal Submitted") ', pred2=pred)
    return issues


def get_issues_reported(jira: JIRA, account_id: str, pred: str) -> list:
    """Return the issues reported by account_id."""
    issues = list_jira_issues(jira, query=f'project != PREOPS and reporter={account_id}', pred2=pred)
    return issues


def add_watcher(jira: JIRA, config: dict, account_id: str, issue: str) -> str:
    """Add a watcher to an issue."""
    import json
    from jira import JIRAError
    
    base = config.get('url')
    if not base:
        raise ValueError('Missing url in config')
    url = base.rstrip('/') + f'/rest/api/3/issue/{issue}/watchers?notifyUsers=false'
    headers = {"Content-Type": "application/json"}
    data = json.dumps(account_id)
    try:
        r = jira._session.post(url, headers=headers, data=data)
        r.raise_for_status()
    except JIRAError as err:
        return err.text
    if r and r.status_code == 204:
        return 'added'
    return f'error:{r.status_code} {r.text}'


def copy_watcher(config: dict, src: str, dst: str, pred: str) -> int:
    """For tickets watched by src, add dst as a watcher also."""
    jira = get_jira_from_config(config)
    issues = get_issues_watched(jira, src, pred)
    tot = len(issues)
    print(f"Got {tot} watched by {src}")
    problem = []
    count = 0
    for i in issues:
        s = add_watcher(jira, config, dst, i.key)
        print(f'{i.key} ({count}/{tot}) {s}')
        if s.startswith('added'):
            count += 1
        else:
            problem.append(i.key)
    print(f"Of {len(issues)} watched {count} PROBLEMS with :{problem}")
    print(f"PREOPS is ignored")
    return count


def assign_issue_quiet(jira: JIRA, issue_key: str, account_id: str) -> bool:
    """Assign issue without sending notification."""
    url = f'{jira.server_url}/rest/api/3/issue/{issue_key}?notifyUsers=false'
    payload = {'fields': {'assignee': {'accountId': account_id}}}
    r = jira._session.put(url, json=payload)
    return r.status_code == 204


def change_reporter_quiet(jira: JIRA, issue_key: str, account_id: str) -> tuple:
    """Change reporter on issue without sending notification.
    
    Returns (success: bool, error_msg: str or None)
    """
    from jira import JIRAError
    
    try:
        issue = jira.issue(issue_key)
        issue.update(fields={'reporter': {'accountId': account_id}}, notify=False)
        return True, None
    except JIRAError:
        pass
    except Exception:
        pass
    
    url = f'{jira.server_url}/rest/api/3/issue/{issue_key}?notifyUsers=false'
    payload = {'fields': {'reporter': {'accountId': account_id}}}
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


def copy_reporter(config: dict, src: str, dst: str, dry_run: bool, pred: str) -> int:
    """Change reporter from src to dst on all issues reported by src."""
    jira = get_jira_from_config(config)
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


def reassign(config: dict, src: str, dst: str, dry_run: bool, pred: str) -> int:
    """Reassign tickets from src to dst account. Returns the count."""
    from jira import JIRAError
    
    jira = get_jira_from_config(config)
    issues = get_issues_assigned(jira, src, pred)
    tot = len(issues)
    print(f"Got {tot} for {src}")
    count = 0
    problem = []
    if dry_run:
        print("NO changes - dry run only ")
    for i in issues:
        v = False
        if not dry_run:
            try:
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
            print(f'Of {len(issues)} assigned {count}.  THERE WERE PROBLEMS ASSIGNING :{problem}')
    return count


# ============================================================================
# Filter Operations
# ============================================================================

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
    from jira import JIRAError
    
    url = f'{jira.server_url}/rest/api/3/filter/{filter_id}/permission'
    payload = {'type': 'user', 'accountId': account_id}
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
    """Share all filters owned by src user with dst user."""
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


# ============================================================================
# Dashboard Operations
# ============================================================================

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


if __name__ == '__main__':
    """ Will list issues"""
    user = sys.argv[1]
    user, pw, jira = get_jira(user)

    r = list_jira_issues(jira)
    print(r)
