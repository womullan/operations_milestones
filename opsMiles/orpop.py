# Use rstcloth to make rst doc/table
from datetime import datetime

from rstcloth import RstCloth

def popdoc(cols: list[str], rows: list[list[str]]) -> str :
    """
    Create rst table from cols and rows
    seems to be a problem with multipline cosl so i am limiting the output
    :param cols: list of column names
    :param rows: list of rows
    """
    fn = "index.rst"
    with open(fn, 'w') as output_file:
        doc = RstCloth(output_file)
        doc.title('POP milestones')
        doc.newline()
        doc.content('POP status extracted from Jira.')
        doc.newline()
        doc.content('`Download pop.csv here. <./pop.csv>`_')
        doc.newline()
        time = datetime.now()
        doc.content(time.strftime('%Y-%m-%d %H:%M'))
        doc.newline()
        doc.table(cols, rows)

    return fn