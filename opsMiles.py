
import argparse
import io
import sys
from datetime import datetime

from opsMiles.ojira import set_jira_due_date, get_jira, list_jira_issues
from opsMiles.ojira import list_milestones, get_last_comment, get_login_config
from opsMiles.orst import jordoc
from opsMiles.orpop import popdoc
from opsMiles.otable import outhead, complete_and_close_table, outputrow
from opsMiles.gantt import gantt
from jiraone import issue_export, LOGIN

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

    cols = ["Milestone", "Jira ID", "Rubin ID", "Due Date", "Level", "Status", "RubinTeam"]
    tout = sys.stdout
    sep = "\t"
    if mode == "tex":
        print(f"Create tex table {fname}")
        tout = open(fname + '.tex', 'w')
        cap = "Milestones for Rubin Observatory Data Management " \
              "and System Performance "
        if caption:
            cap = caption
        form = r"|p{0.3\textwidth}  |r  |r  |r  |r |l |p{0.1\textwidth} |"
        outhead(cols, tout=tout, cap=cap, name=fname, form=form)
        sep = "&"

    for m in miles:
        key = m.key
        sumry = m.fields.summary
        milestone_id = m.fields.customfield_10105
        if milestone_id is None:
            milestone_id = "not set"
        due = m.fields.duedate
        lev = m.fields.customfield_10037
        team = m.fields.customfield_10056
        status = m.fields.status
        outputrow(tout, sep, sumry, key, milestone_id, due, lev, team, status, mode)

    if mode == "tex":
        complete_and_close_table(tout)


def getComponentsStr(components):
    componentlist = []
    for c in components:
        componentlist.append(c.name)

    return ",".join(componentlist)

def pop(outfile):
    """ Create a POP report from the issues"""
    tout = open(outfile, 'w')
    # names for the csv
    cols = ["Issue key","Summary","Assignee","BL End Date","Component","Status", "Implementation Status Description"]
    # names in jira - baseline start date is customfield_10063
    # baseline end date is "customfield_10064
    fields = ["key", "summary", "assignee", "customfield_10064", "components", "status"]
    issues = list_jira_issues(jira, args.query, "project = PREOPS ", order="", fields=fields)
    print (f"Create {outfile} with {len(issues)} issues")
    header = ",".join(cols)
    print(header, file=tout)
    rows = []

    for i in issues:
        key = i.key
        summary = i.fields.summary.strip()
        due = i.fields.customfield_10064
        assignee = i.fields.assignee
        components = getComponentsStr(i.fields.components)
        status = i.fields.status
        isd = get_last_comment(jira, i.key).strip()
        tmp: io.StringIO = io.StringIO()
        print(f'{key},"{summary}",{assignee},{due},"{components}","{status}", "{isd}"', file=tmp)
        keylink = f"`{key} <https://ls.st/{key}>`_ "
        # isd out of this fow now
        row = [keylink, summary, assignee, due, components, status]
        rows.append(row)
        print(tmp.getvalue().replace("\r", ""), file=tout)
    tout.close()
    popdoc(cols,rows)

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
    rows = []

    for i in issues:
        key = i.key
        recnum= i.fields.customfield_10148
        summary = i.fields.summary.strip()
        repdate = i.fields.labels[0]
        due = i.fields.duedate
        status = i.fields.customfield_10195
        description = i.fields.description.strip()
        reposnse = i.fields.customfield_10147
        isd = get_last_comment(jira, i.key).strip()
        tmp: io.StringIO = io.StringIO()
        print(f'{key},{recnum},"{summary}",{repdate},{due},"{status}","{description}",'
              f'"{reposnse}","{isd}"', file=tmp)
        keylink = f"`{key} <https://ls.st/{key}>`_"
        row = [keylink, recnum, summary, repdate, due, status, description, reposnse, isd]
        rows.append(row)
        print(tmp.getvalue().replace("\r", ""), file=tout)
    tout.close()
    jordoc(cols,rows)

def dump(outfile, args):
    """ Create a csv report from the issues"""
    config = get_login_config(args)
    LOGIN(**config)
    issue_export(jql=args.query, final_file=outfile)


if __name__ == '__main__':
    pred = """and (component = "Data Management" or component = 
           "System Performance")"""
    OUTPUT_MODES = ["txt", "tex"]
    description = __doc__
    formatter = argparse.RawDescriptionHelpFormatter
    parser = argparse.ArgumentParser(description=description,
                                     formatter_class=formatter)
    parser.add_argument('-a', '--ask', action='store_true',
                        help="""Ask for Jira Password for user.""")
    parser.add_argument('-c', '--caption', default=None,
                        help=""" Caption for the TeX tabel only with -t """)
    parser.add_argument("-d", "--dump",action='store_true',
                        help="""Just dump csv """)
    parser.add_argument('-f', '--fname', help="""Filename for output.""")
    parser.add_argument("-g", "--gantt",action='store_true',
                        help="""For specfied tickets plot a chart """)
    parser.add_argument("-j", "--jor",action='store_true',
                        help="""Joint Operations Review actions report""")
    parser.add_argument('-l', '--list', action='store_true',
                        help="""List milestones""")
    parser.add_argument("-m", "--mode", default="tex", choices=OUTPUT_MODES,
                        help="""Output mode for table.
                                verbose' displays all the information...""")
    parser.add_argument('-p', '--passwd', help="""Jira Password for user.""")
    parser.add_argument('-q', '--query', default=pred,
                        help=""" Partial predicate for milestones like 
                        'component = Data Management' """)
    parser.add_argument('-r', '--report', action='store_true',
                        help="""Just report dont update anything.""")
    parser.add_argument('-s', '--split', action='store_true',
                        help=""" Split milestones in two lists done and not done""")
    parser.add_argument('-t', '--tickets', action='store_true',
                        help="""List any ticket/issue incomplete""")
    parser.add_argument('-u', '--uname', help="""Username for Jira .""")
    parser.add_argument("-x", "--pop",action='store_true',
                        help="""Joint Operations POP report""")
    parser.add_argument("-y", "--year", default=2024, type=int,
                        help="""Start year for e.g. gantt """)

    args = parser.parse_args()
    user = args.uname

    user, pw, jira = get_jira(user, args.ask, args.passwd)

    if args.gantt:
        fname="USDFplan.tex"
        if args.fname:
            fname=args.fname
        start=2021
        if args.year:
            start=args.year
        gantt(fname, list_jira_issues(jira, args.query, ""), start=start)
        exit(0)

    if args.jor:
        jor("jor.csv")
        exit(0)

    if args.pop:
        pop("pop.csv")
        exit(0)

    if args.dump:
        dump("jira.csv", args)
        exit(0)

    if args.tickets:
        output(list_jira_issues(jira, args.query, ""), args.mode,
               caption=args.caption, split=args.split)
        exit(0)

    if args.list:
        output(list_milestones(jira, args.query), args.mode,
               caption=args.caption, split=args.split)
    else:
        update_tickets_j(jira, report=args.report)
