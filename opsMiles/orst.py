# Use rstcloth to make rst doc/table
from datetime import datetime

from rstcloth import RstCloth

def jordoc(cols: list[str], rows: list[list[str]]) -> str :
    """
    Create rst table from cols and rows
    :param cols: list of column names
    :param rows: list of rows
    """
    fn = "index.rst"
    with open(fn, 'w') as output_file:
        doc = RstCloth(output_file)
        doc.title('JOR recommendations')
        doc.newline()
        doc.content('Review recommendations extracted from Jira.')
        doc.newline()
        doc.content('`Download jor.csv here. <./jor.csv>`_')
        doc.newline()
        time = datetime.now()
        doc.content(time.strftime('%Y-%m-%d %H:%M'))
        doc.newline()
        doc.table(cols, rows)

    return fn