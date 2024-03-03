import argparse
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


def filters(jira):
    """ For all filters for user pull them down  """
    filters = {jira.filter(11342), jira.filter(11340)}


    for f in filters:
        print(f" {f}")

if __name__ == '__main__':

    description = """Fix cloud issues"""
    formatter = argparse.RawDescriptionHelpFormatter
    parser = argparse.ArgumentParser(description=description,
                                     formatter_class=formatter)
    parser.add_argument('-u', '--uname', help="""Username for Jira .""")
    parser.add_argument('-p', '--passwd', help="""Jira Password for user.""")
    parser.add_argument('-a', '--ask', action='store_true',
                        help="""Ask for Jira Password for user.""")
    parser.add_argument('-f', '--filter', action='store_true',
                        help="""Do filter thing.""")
    parser.add_argument('--project', help="""Project to fix start dates on.""")
    args = parser.parse_args()
    user = args.uname

    user, pw, jira = get_jira(user, args.passwd, args.ask)

    if args.filter:
        filters(jira)
    else:
        """ Will  fix start date issues"""
        project = args.project
        fix_start_date(jira, project, user, pw)

