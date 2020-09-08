# operations_milestones

This script opsMiles.py looks up google milestones and sets due dates on jira tickets with the same label.
The -r (report) option will just report on the tickets needing update or not. 

Ask @womullan for client_secret.json which you will need to access google. 

Use the virtual environment to run this stuff activate it thus :

      >  python -m venv venv 

For an easy use replace womullan with your Jira ID in:
<pre>
  > source venv/bin/activate 
  > python opsMiles.py -r -u womullan 

  Jira user:womullan
  PREOPS-97 due 2020-12-15 ok  DP-MW-M03 date 2020-12-15
  PREOPS-96 due 2020-12-15 ok  DP-MW-M03 date 2020-12-15
  PREOPS-95 due 2021-06-30 ok  DP-EX-M01 date 2021-06-30
  PREOPS-93 due 2021-06-30 ok  DP-EX-M01 date 2021-06-30
  PREOPS-89 due 2020-12-15 ok  DP-MW-M03 date 2020-12-15
  PREOPS-88 due 2021-03-31 ok  DP-MW-M05 date 2021-03-31
  PREOPS-87 due 2021-03-31 ok  DP-MW-M05 date 2021-03-31
  PREOPS-86 due 2021-09-30 ok  DP-EX-M08 date 2021-09-30
  PREOPS-85 due 2020-09-30 ok  DP-AP-M01 date 2020-09-30
  got 184 milestones and 11 tickets.
</pre>


Alternatively use the Make file as long as $USER is also you Jira user ... 

      > make report 

will do all the above.

## Note Jira
The Jira password is prompted for the first time you use the script. Then it is stored in your
keychain (I assume this might work on windows no idea) so you are not prompted again. 
If you do not pass a username you will be prompted for it - this is also the way to refresh the 
keychain if the password becomes invalid. 
