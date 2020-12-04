VENVDIR = venv

list: venv
	( \
		source $(VENVDIR)/bin/activate; \
		python opsMiles.py -l -m txt -u ${USER} \
	)

table: venv
	( \
		source $(VENVDIR)/bin/activate; \
		python opsMiles.py -l -u ${USER} \
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

