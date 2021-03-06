import sys

from jira import JIRA

from opsMiles.uname import get_login_cli

API_ENDPOINT = "https://jira.lsstcorp.org/rest/api/latest/"


def list_milestones(jira=None, pred2="""and (component = "Data Production" or
                    component = "System Performance")"""):
    """
    Get the milestone issues from Jira for PRE-OPS.
    Defaults to Data Produciton and System Performance
    set pred2="" to get all
    """

    fields = ["key", "RO Milestone ID", "type", "summary", "duedate",
              "Team", "component", "Milestone Level", "status"]
    query = "project = PREOPS AND type = Milestone " + pred2
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
    issue.update(duedate=due_date)
    jira.add_comment(issue_id, message)

    # requests.put(API_ENDPOINT + "issue/" + issue_id, auth=(user, pw), json=data)


def list_jira_issues(jira, pred2=None, query=None):
    """
    :JIRA jira: setup up JIRA object
    :String query: Query string "
    :String pred2: If you use the defualt query string but want to
                    add more predicate or sort order start with AND or OR
    """
    fields = ["key", "labels", "type", "assignee", "summary", "duedate", "status"]
    if query is None:
        query = """project = PREOPS AND resolution = Unresolved AND
                   (type = epic or type= story) AND labels is not EMPTY """

    if (pred2 is not None):
        query = query + " " + pred2
    r = jira.search_issues(jql_str=query, fields=fields, maxResults=500)
    return r


def get_jira(username=None, prompt=False):
    """ Setup up the JIRA object endpoint - prompt
        for username and passwd as needed.
        Password will be looked up from key chain.
    :String username: Optionally pass the username (prompted othereise)
    """

    user, pw = get_login_cli(username=username,prompt=prompt)
    print("Jira user:" + user)
    ep = "https://jira.lsstcorp.org"
    return (user, pw, JIRA(server=ep, basic_auth=(user, pw)))


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


if __name__ == '__main__':
    """ Will list PREOPS issues"""
    user = sys.argv[1]
    user, pw, jira = get_jira(user)

    r = list_jira_issues(jira)
    print(r)
