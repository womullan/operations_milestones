#ahoc to load fromexle tojira
import argparse
import sys
import xlrd
from opsMiles.ojira import set_jira_due_date, get_jira, list_jira_issues

FIELDS = ['type', 'Epic Name', 'description', 'asignee']


def create_tickets(jira):
    workbook = xlrd.open_workbook("mis.xls", logfile=sys.stderr)
    sheet = workbook.sheets()[0]

    header = sheet[0]
    print(header)  #  header
    c = 0
    skip = 41
    for r in sheet:
        c = c + 1
        if c > skip and r[0].value != '':
            p = 0
            id = str(int(r[p].value))
            p = 2
            name = str(r[p].value)
            description = "ID:"+id+ " Management Prio:" + str(r[13].value)+ "\n"
            p = 15
            assingee = str(r[p].value)
            p = 3
            description = description + " \n Notes: " +str(r[p].value) + "\n" + str(r[4].value) + "\n " + str(r[11].value)
            p = p + 1
            description = description+ "\n " + header[p].value + ":" + str(r[p].value)
            p = p + 1
            description = description+ "\n " + header[p].value + ":" + str(r[p].value)
            p = p + 1
            description = description+ "\n " + header[p].value + ":" + str(r[p].value)
            p = p + 1
            description = description+ "\n " + header[p].value + ":" + str(r[p].value)
            p = p + 1
            description = description+ "\n " + header[p].value + ":" + str(r[p].value)
            p = p + 1
            description = description+ "\n " + header[p].value + ":" + str(r[p].value)

            #print (name)
            #rint (assingee)
            #rint (description)
            issue_dict = {
                'project' : {'id': 14701},
                'summary' : name,
                'description' : description,
                'issuetype': {'name': 'Epic'},
                'customfield_10207': name,
                'components' : [{'name': 'SIT-Com Organizational Support'}],
            }
            tic = jira.create_issue(issue_dict)
            print (f"added {tic}")
            try:
               jira.assign_issue(tic, assingee)
            except BaseException:
                print (f"Failed to assing {tic} to {assingee}")
    #jira.create_issue()


if __name__ == '__main__':
    pred = """and (component = "Data Management" or component = 
           "System Performance")"""
    OUTPUT_MODES = ["txt", "tex"]
    description = __doc__
    formatter = argparse.RawDescriptionHelpFormatter
    parser = argparse.ArgumentParser(description=description,
                                     formatter_class=formatter)
    parser.add_argument('-u', '--uname', help="""Username for Jira .""")
    parser.add_argument('-p', '--prompt', action='store_true',
                        help="""Prompt for Jira Password.""")

    args = parser.parse_args()
    user = args.uname

    user, pw, jira = get_jira(user, args.prompt)

    create_tickets(jira)
