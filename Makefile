VENVDIR = venv
USER='rubinjiraapiaccess@gmail.com'

.FORCE:

jira.csv: venv .FORCE
	( \
		source $(VENVDIR)/bin/activate; \
		python opsMiles.py -d -q "filter=11498"  -u ${USER} \
	)

jor.csv: venv .FORCE
	( \
		source $(VENVDIR)/bin/activate; \
		python opsMiles.py -j -q "filter=11340"  -u ${USER} \
	)

pop.csv: venv .FORCE
	( \
		source $(VENVDIR)/bin/activate; \
		python opsMiles.py --pop -q "filter=11380"  -u ${USER} \
	)

FY23.tex: venv .FORCE
	( \
		source $(VENVDIR)/bin/activate; \
		python opsMiles.py -g -q "and labels=FY23 and type  != story"  -u ${USER} \
	)

FY23.pdf:  FY23.tex
	pdflatex FY23.tex

USDFplan.tex: venv .FORCE
	( \
		source $(VENVDIR)/bin/activate; \
		python opsMiles.py -g -q "and labels=USDF AND type  != story"  -u ${USER} \
	)

gantt: USDFplan.tex
	pdflatex USDFplan.tex 

list: venv
	( \
		source $(VENVDIR)/bin/activate; \
		python opsMiles.py -l -m txt -u ${USER} \
	)

table: venv
	( \
		source $(VENVDIR)/bin/activate; \
		python opsMiles.py -ls -u ${USER} \
	)

report: venv
	( \
		source $(VENVDIR)/bin/activate; \
		python opsMiles.py -r -u ${USER} \
	)

venv:
	python -m venv $(VENVDIR)
	( \
		source $(VENVDIR)/bin/activate; \
	)

update: venv
	( \
		source $(VENVDIR)/bin/activate; \
		python opsMiles.py -u ${USER} \
	)


jira: venv
	( \
		source $(VENVDIR)/bin/activate; \
		python opsMiles/ojira.py -u ${USER} \
	)

google: venv
	( \
		source $(VENVDIR)/bin/activate; \
		python opsMiles/ogoogle.py -s sheet range \
	)

