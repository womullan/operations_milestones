
import argparse
import io
import sys
from opsMiles.ojira import set_jira_due_date, get_jira, list_jira_issues
from opsMiles.ojira import list_milestones, get_last_comment
from opsMiles.otable import outhead, complete_and_close_table, outputrow
from opsMiles.gantt import gantt


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
        for label in t.fields.labels:
            if label in milestones:
                if not t.fields.duedate or \
                        (t.fields.duedate != milestones[label]):
                    # dates differ so should update
                    if report:
                        print(f"Should update {t} using {label} date "
                              f"{milestones[label]}")
                    else:
                        set_jira_due_date(jira=jira, issue=t,
                                          ms=label, due_date=milestones[label])

                else:
                    print(f"{t} due {t.fields.duedate} ok  {label} date "
                          f"{milestones[label]}")

    print(f"got {len(milestones)} milestones and {len(tickets)} tickets.")


def splitMiles(miles):
    """
    Given list of milestones split them in done and pending lists
    :param miles: list of milestones
    :return: done and pending lists
    """
    omiles = []
    dmiles = []

    for m in miles:
        if str(m.fields.status) == "Done" or str(m.fields.status) == "Won't Fix" :
            dmiles.append(m)
        else:
            omiles.append(m)

    return [omiles, dmiles]

def output(miles, mode, fname="milestones", caption=None, split=False):
    """
    Given list of milestones output them
    :param miles: list of milestones
    :param mode: one of OUPUT_MODES
    :param split: deived into two tables done, not done
    """

    if split:
        openMiles,doneMiles = splitMiles(miles)
        output(openMiles,mode, "openMilestones", caption=caption, split=False)
        output(doneMiles,mode, "doneMilestones", caption=caption, split=False)
        return

    cols = ["Milestone", "Jira ID", "Rubin ID", "Due Date", "Level", "Status", "Team"]
    tout = sys.stdout
    sep = "\t"
    if mode == "tex":
        print(f"Create tex table {fname}")
        tout = open(fname + '.tex', 'w')
        cap = "Milestones for Rubin Observatory Data Production " \
              "and System Performance "
        if caption:
            cap = caption
        form = r"|p{0.3\textwidth}  |r  |r  |r  |r |l |p{0.1\textwidth} |"
        outhead(cols, tout=tout, cap=cap, name=fname, form=form)
        sep = "&"

    for m in miles:
        key = m.key
        sumry = m.fields.summary
        milestone_id = m.fields.customfield_16000
        if milestone_id is None:
            milestone_id = "not set"
        due = m.fields.duedate
        lev = m.fields.customfield_11600
        team = m.fields.customfield_10502
        status = m.fields.status
        outputrow(tout, sep, sumry, key, milestone_id, due, lev, team, status, mode)

    if mode == "tex":
        complete_and_close_table(tout)



def jor(outfile):
    """ Create a JOR report from the issues"""
    tout = open(outfile, 'w')
    # names for the csv
    cols = ["Issue key","Rec#","Summary","Report date","Due Date","Implementation Status",
            "Description","Response","Implementation Status Description"]
    # names in jira
    fields = ["key", "RR Item ID", "summary", "labels", "due", "Implementation Status",
            "description", "Review Response"]
    issues = list_jira_issues(jira, args.query, "project = PREOPS ", order="", fields=fields)
    print (f"Create {outfile} with {len(issues)} issues")
    header = ",".join(cols)
    print(header, file=tout)

    for i in issues:
        key = i.key
        recnum= i.fields.customfield_14813
        summary = i.fields.summary.strip()
        repdate = i.fields.labels[0]
        due = i.fields.duedate
        status = i.fields.customfield_17207
        description = i.fields.description.strip()
        reposnse = i.fields.customfield_12104
        isd = get_last_comment(jira, i.key).strip()
        tmp: io.StringIO = io.StringIO()
        print(f'{key},{recnum},"{summary}",{repdate},{due},"{status}","{description}",'
              f'"{reposnse}","{isd}"', file=tmp)
        print(tmp.getvalue().replace("\r", ""), file=tout)

    tout.close()


if __name__ == '__main__':
    pred = """and (component = "Data Production" or component = 
           "System Performance")"""
    OUTPUT_MODES = ["txt", "tex"]
    description = __doc__
    formatter = argparse.RawDescriptionHelpFormatter
    parser = argparse.ArgumentParser(description=description,
                                     formatter_class=formatter)
    parser.add_argument('-u', '--uname', help="""Username for Jira .""")
    parser.add_argument('-p', '--passwd', help="""Jira Password for user.""")
    parser.add_argument('-a', '--ask', action='store_true',
                        help="""Ask for Jira Password for user.""")
    parser.add_argument('-r', '--report', action='store_true',
                        help="""Just report dont update anything.""")
    parser.add_argument('-l', '--list', action='store_true',
                        help="""List milestones""")
    parser.add_argument('-s', '--split', action='store_true',
                        help=""" Split milestones in two lists done and not done""")
    parser.add_argument('-q', '--query', default=pred,
                        help=""" Partial predicate for milestones like 
                        'component = Data Production' """)
    parser.add_argument('-c', '--caption', default=None,
                        help=""" Caption for the TeX tabel only with -t """)
    parser.add_argument("-m", "--mode", default="tex", choices=OUTPUT_MODES,
                        help="""Output mode for table.
                                verbose' displays all the information...""")
    parser.add_argument("-g", "--gantt",action='store_true',
                        help="""For specfied tickets plot a chart """)
    parser.add_argument("-j", "--jor",action='store_true',
                        help="""Joint Operations Review actions report""")

    args = parser.parse_args()
    user = args.uname

    user, pw, jira = get_jira(user, args.ask, args.passwd)

    if args.gantt:
        gantt("USDFplan.tex", list_jira_issues(jira, args.query, "project = PREOPS "))
        exit(0)

    if args.jor:
        jor("jor.csv")
        exit(0)

    if args.list:
        output(list_milestones(jira, args.query), args.mode,
               caption=args.caption, split=args.split)
    else:
        update_tickets_j(jira, report=args.report)
