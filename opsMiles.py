
import argparse
import opsMiles
from opsMiles.google import get_sheet
from opsMiles.ojira import set_jira_due_date, get_jira, list_jira_issues
from opsMiles.uname import get_login_cli


def update_tickets(user,pw,jira=None, report=False):
    """ Go through the milestones and for each look for a jira ticket with
    that label and update the due date"""

    # grab the milesons from google
    sheet = "1RCXFwnVfXgR-WxFO4dfYRZuMX8egz35nABODKANEAUo"
    tab = "ImpMiles!A2:L"
    data = get_sheet(sheet, tab)['values']

    # get the milestones with label and date.
    milestones={}
    for m in data:
        # if anyone changes the columns we have a problem
        milestone_id = m[0]
        due_date = m[1]
        if milestone_id and milestone_id != "#N/A":
            if due_date:
                milestones[milestone_id]=due_date

    #get the tickets
    tickets = list_jira_issues(jira )

    for t in tickets:
        # for each ticket look at the labels if one of the labels is a
        # milestone (from google list above) then update it
        # if the date is not correct.
        for l in t.fields.labels:
            if l in milestones:
                if not t.fields.duedate or (t.fields.duedate != milestones[l]):
                    #dates differ so should update
                    if report:
                        print (f"Should update {t} using {l} date {milestones[l]}")
                    else:
                         set_jira_due_date(jira=jira,user=user,pw=pw,
                                           issue=t,
                                           ms=l, due_date=milestones[l])

                else:
                    print (f"{t} due {t.fields.duedate} ok  {l} date {milestones[l]}")

    print (f"got {len(milestones)} milestones and {len(tickets)} tickets.")

if __name__ == '__main__':
    description = __doc__
    formatter = argparse.RawDescriptionHelpFormatter
    parser = argparse.ArgumentParser(description=description,
                                     formatter_class=formatter)
    parser.add_argument('-u', '--uname', help="""Username for Jira .""")
    parser.add_argument('-r', '--report', action='store_true',
                        help="""Just report dont update anything.""")

    args = parser.parse_args()
    user = args.uname

    user, pw, jira = get_jira(user)

    #update_tickets(user,pw,jira,report=args.report)
    update_tickets(user,pw,jira,report=None)

