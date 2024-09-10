from datetime import datetime, timedelta
from io import StringIO
import sys

from .utility import write_output, format_latex


GANTT_PREAMBLE_STANDALONE = """
\\documentclass{article}
\\usepackage[
    paperwidth=26cm,
    paperheight=PHEIGHTcm,  % pass in
    left=0mm,
    top=0mm,
    bottom=0mm,
    right=0mm,
    noheadfoot,
    marginparwidth=0pt,
    includemp=false
]{geometry}
\\usepackage{pgfgantt}
\\begin{document}
\\begin{center}
\\begin{ganttchart}[
%    vgrid,  % disabled for aesthetic reasons
%    hgrid,  % disabled for aesthetic reasons
    expand chart=0.98\\textwidth,
    title label font=\\sffamily\\bfseries,
    milestone label font=\\sffamily\\bfseries,
    progress label text={#1},
    milestone progress label node/.append style={right=0.2cm},
    milestone progress label font=\\sffamily,
    y unit chart=0.55cm,
    y unit title=0.8cm
]{1}{40}
"""

GANTT_POSTAMBLE_STANDALONE = """
\\end{ganttchart}
\\end{center}
\\end{document}
"""




def format_gantt(milestones, preamble, postamble, start=datetime(2021, 1, 1)):
    def get_month_number(start, date):
        # First month is month 1; all other months sequentially.
        return 1 + (date.year * 12 + date.month) - (start.year * 12 + start.month)

    def get_milestone_name(code):
        return code.lower().replace("-", "").replace("&", "")

    def fix_summary(sum):
        return sum.replace(",", "-")

    output = StringIO()
    height = 0.7 * len(milestones)  + 0.8
    opreamble = preamble.replace("PHEIGHT",str(height))
    output.write(opreamble)

    for ms in milestones:
        ddate = None
        sdate = ms.fields.duedate
        if sdate:
            ddate = datetime.fromisoformat(sdate)
        else:
            print(f"{ms.key} has no Due Date set", sys.stderr)
        if ms.fields.issuetype.name == "Milestone":
            output_string = (
                f"\\ganttmilestone[name={get_milestone_name(ms.key)},"
                f"progress label text={fix_summary(ms.fields.summary)}"
                f"\\phantom{{#1}},progress=100]{{{ms.key}}}"
                f"{{{get_month_number(start, ddate)}}} \\ganttnewline"
            )
        else:
            startdate = ms.raw['fields']['Start date']
            if startdate == None :
                print(f"{ms.fields.issuetype}-{ms.key} has no Start Date ")
                startdate = "2024-09-01"
            sdate = datetime.fromisoformat(startdate)
            if not ddate:
                ddate=sdate
            output_string = (
                f"\\ganttbar[name={get_milestone_name(ms.key)},"
                f"progress label text={fix_summary(ms.fields.summary)}"
                f"\\phantom{{#1}},progress=100]{{{ms.key}}}"
                f"{{{get_month_number(start, sdate)}}} "
                f"{{{get_month_number(start, ddate)}}} \\ganttnewline"
            )

        output.write(format_latex(output_string))
        # format_latex() strips trailing newlines; add one for cosmetic reasons
        output.write("\n")

    output.write(postamble)
    return output.getvalue()


def gantt_standalone(milestones, start):
    years = [start, start+1, start+2]

    DATES = f"""
      \\gantttitle{{{years[0]}}}{{12}}
       \\gantttitle{{{years[1]}}}{{12}}
      \\gantttitle{{{years[2]}}}{{12}}
      \\ganttnewline\n
    """

    return format_gantt(
        milestones,
        GANTT_PREAMBLE_STANDALONE + DATES,
        GANTT_POSTAMBLE_STANDALONE,
        datetime(start,1,1)
    )



def gantt(fname, milestones, start):
    tex_source = gantt_standalone(milestones, start)
    write_output(fname , tex_source)
