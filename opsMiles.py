
import argparse
import sys
from opsMiles.ojira import set_jira_due_date, get_jira, list_jira_issues
from opsMiles.ojira import list_milestones
from opsMiles.otable import outhead, complete_and_close_table, outputrow


def update_tickets_j(jira=None, report=False):
    """ Go through the milestones FROM Jira and for each
    look for a jira ticket with that label and update the due date"""

    # get the milestones with label and date.
    milestones = {}
    jmiles = list_milestones(jira)

    for m in jmiles:
        # Custom fileds come out a bit wird this is RO Milestone ID
        milestone_id = m.fields.customfield_16000
        due_date = m.fields.duedate
        if milestone_id and due_date:
            milestones[milestone_id] = due_date
            if report:
                print(f"{milestone_id} due {due_date}")
    update_tickets_m(jira, milestones, report)


def update_tickets_m(jira, milestones, report):
    """
    Given the milestones, look up the tickets and update them
    :param jira: Logged in Jira
    :param milestones: list of milestone, due date pairs
    :param report: boolean to just report not do
    """

    # get the tickets
    tickets = list_jira_issues(jira)

    for t in tickets:
        # for each ticket look at the labels if one of the labels is a
        # milestone (from list above) then update it
        # if the date is not correct.
        for l in t.fields.labels:
            if l in milestones:
                if not t.fields.duedate or (t.fields.duedate != milestones[l]):
                    # dates differ so should update
                    if report:
                        print(f"Should update {t} using {l} date "
                              f"{milestones[l]}")
                    else:
                        set_jira_due_date(jira=jira, issue=t,
                                          ms=l, due_date=milestones[l])

                else:
                    print(f"{t} due {t.fields.duedate} ok  {l} date "
                          f"{milestones[l]}")

    print(f"got {len(milestones)} milestones and {len(tickets)} tickets.")


def output(miles, mode, fname="milestones", caption=None):
    """
    Given list of milestones output them
    :param miles: list of milestones
    :param mode: one of OUPUT_MODES
    """

    cols = ["Milestone", "Jira ID", "Rubin ID", "Due Date", "Level", "Team"]
    tout = sys.stdout
    sep = "\t"
    if mode == "tex":
        print(f"Create tex table {fname}")
        tout = open(fname + '.tex', 'w')
        cap = "Milestones for Rubin Observatory Data Production " \
              "and System Performance  FY21"
        if caption:
            cap = caption
        form = r"|p{0.3\textwidth}  |r  |r  |r  |r  |p{0.1\textwidth} |"
        outhead(cols, tout=tout, cap=cap, name="miles", form=form)
        sep = "&"

    for m in miles:
        key = m.key
        sumry = m.fields.summary
        milestone_id = m.fields.customfield_16000
        due = m.fields.duedate
        lev = m.fields.customfield_11600
        team = m.fields.customfield_10502
        outputrow(tout, sep, sumry, key, milestone_id, due, lev, team, mode)

    if mode == "tex":
        complete_and_close_table(tout)
        

if __name__ == '__main__':
    pred="""and (component = "Data Production" or component = 
           "System Performance")"""
    OUTPUT_MODES = ["txt", "tex"]
    description = __doc__
    formatter = argparse.RawDescriptionHelpFormatter
    parser = argparse.ArgumentParser(description=description,
                                     formatter_class=formatter)
    parser.add_argument('-u', '--uname', help="""Username for Jira .""")
    parser.add_argument('-p', '--prompt', action='store_true',
                        help="""Prompt for Jira Password.""")
    parser.add_argument('-r', '--report', action='store_true',
                        help="""Just report dont update anything.""")
    parser.add_argument('-l', '--list', action='store_true',
                        help="""List milestones""")
    parser.add_argument('-q', '--query', default=pred,
                        help=""" Partial predicate for milestones like 
                        'component = Data Production' """)
    parser.add_argument('-c', '--caption', default=None,
                        help=""" Caption for the TeX tabel only with -t """)
    parser.add_argument("-m", "--mode", default="tex", choices=OUTPUT_MODES,
                        help="""Output mode for table.
                                verbose' displays all the information...""")

    args = parser.parse_args()
    user = args.uname

    user, pw, jira = get_jira(user, args.prompt)

    if args.list:
        output(list_milestones(jira,args.query), args.mode, caption=args.caption)
    else:
        update_tickets_j(jira, report=args.report)
