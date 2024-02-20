import json
import sys
from opsMiles.ojira import list_jira_issues, get_jira

FIELDS = ["key", "type", "summary", "duedate", "customfield_10015", "Start date (migrated)",
           "Team", "component", "status"]

def fix_start_date(jira, project, user, pw):
    """ For all issues in  project copy start date from start date (migrated)  """
    issues = list_jira_issues(jira, pred2=" and project = " + project, fields=FIELDS)  # get all the issues

    for issue in issues:
        start_date = issue.fields.customfield_10059
        if start_date:
            update = {'customfield_10015': start_date}
            issue.fields.customfield_10015 = start_date
            issue.update(fields=update)
            message = f"Set start date to {start_date} from start date (migrated)"
            jira.add_comment(issue.key, message)
            print(f"Setting start date on {issue.key} to {start_date}")
        else:
            print(f"No start date on {issue.key}")


if __name__ == '__main__':
    """ Will  fix start date issues"""
    user = sys.argv[1]
    project = sys.argv[2]
    user, pw, jira = get_jira(user)

    r = fix_start_date(jira, project, user, pw)

    print(r)
