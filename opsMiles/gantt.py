from datetime import datetime
from io import StringIO

from .utility import write_output, format_latex


GANTT_PREAMBLE_STANDALONE = """
\\documentclass{article}
\\usepackage[
    paperwidth=26cm,
    paperheight=10cm,  % Manually tweaked to fit chart
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
  \\gantttitle{2021}{12} 
   \\gantttitle{2022}{12}
  \\gantttitle{2023}{12} 
  \\ganttnewline\n
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

    output = StringIO()
    output.write(preamble)

    for ms in milestones:
        ddate = datetime.fromisoformat(ms.fields.duedate)
        if ms.fields.issuetype.name == "Milestone":
            output_string = (
                f"\\ganttmilestone[name={get_milestone_name(ms.key)},"
                f"progress label text={ms.fields.summary}"
                f"\\phantom{{#1}},progress=100]{{{ms.key}}}"
                f"{{{get_month_number(start, ddate)}}} \\ganttnewline"
            )
        else:
            startdate = ms.fields.customfield_11303
            if startdate == None :
                print(f" {ms.key} has no Start Date ")
                startdate = "2021-07-01"
            sdate = datetime.fromisoformat(startdate)
            output_string = (
                f"\\ganttbar[name={get_milestone_name(ms.key)},"
                f"progress label text={ms.fields.summary}"
                f"\\phantom{{#1}},progress=100]{{{ms.key}}}"
                f"{{{get_month_number(start, sdate)}}} "
                f"{{{get_month_number(start, ddate)}}} \\ganttnewline"
            )

        output.write(format_latex(output_string))
        # format_latex() strips trailing newlines; add one for cosmetic reasons
        output.write("\n")

    output.write(postamble)
    return output.getvalue()


def gantt_standalone(milestones):
    return format_gantt(
        milestones,
        GANTT_PREAMBLE_STANDALONE,
        GANTT_POSTAMBLE_STANDALONE,
    )



def gantt(fname, milestones):
    tex_source = gantt_standalone(milestones)
    write_output(fname , tex_source)
