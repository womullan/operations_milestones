#!/usr/bin/env python3

r"""This script will extract cells in a google sheet.
You must pass the sheet Identifier and Sheet name(s) you wish to process.

To access google you have to do some setup
``https://developers.google.com/sheets/api/quickstart/python``
roughly you must create a client secret for OAUTH using this wizard
``https://console.developers.google.com/start/api?id=sheets.googleapis.com``
Accept the blurb and go to the APIs
click CANCEL on the next screen to get to the `create credentials`
hit create credentials choose OATH client
Configure a product - just put in a name like `LSST DOCS`
Create web application id
Give it a name hit ok on the next screen
now you can download the client id - call it client_secret.json
as expected below.
You have to do this once to allow the script to access your google stuff
from this machine.
"""
import argparse
import os
import os.path
import pickle
import sys
from typing import Dict, Any

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from oauth2client.client import Credentials

# If modifying these scopes, delete your previously saved credentials
# at ~/.credentials/sheets.googleapis.com-python-quickstart.json
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

CLIENT_SECRET_FILE = 'client_secret.json'
APPLICATION_NAME = 'Ops Tables from Google Sheet'
SAMPLE_SPREADSHEET_ID = '1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms'
SAMPLE_RANGE_NAME = 'Class Data!A2:E'

def get_credentials() -> Credentials:
    """Gets valid user credentials from storage.

    If nothing has been stored, or if the stored credentials are invalid,
    the OAuth2 flow is completed to obtain the new credentials.

    Returns:
        Credentials, the obtained credential.
    """

    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    return creds


def dump(s, tout=sys.stdout):
    """
    convenience function to sump sheets
    values contains the selected cells from a google sheet
    this routine goes through the rows and outputs them
    :Dict sheets:  sheet data dictionary as returned from get_sheets
    """

    values = s.get('values', [])

    if not s:
        print('No data found.')
    else:
        print("Sheet:  "+s['range'], file=tout)
        for r in values:
           print(",".join(r), file=tout)
    return


def get_sheet(sheet_id, range):
    """
    grab the google sheet and return data from sheet
    :String sheetId: GoogelSheet Id like 1R1h41KVtN2gKXJAVzd4KLlcF-FnNhpt1G06YhzwuWiY
    :String sheets: List of TabName\!An:Zn  ranges

    """
    creds = get_credentials()
    service = build('sheets', 'v4', credentials=creds)
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=sheet_id,
                                range=range ).execute()
    return result

if __name__ == '__main__':
    description = __doc__
    formatter = argparse.RawDescriptionHelpFormatter
    parser = argparse.ArgumentParser(description=description,
                                     formatter_class=formatter)

    parser.add_argument('id', help="""ID of the google sheet like
                                18wu9f4ov79YDMR1CTEciqAhCawJ7n47C8L9pTAxe""")
    parser.add_argument('range', nargs='+',
                        help="""Sheet names  and ranges to process
                             within the google sheet e.g. Model!A1:H""")
    parser.add_argument('-s', '--sample', action='store_true',
                        help="""Just access quickstart sheet""")
    args = parser.parse_args()
    sheetId = args.id
    ranges = args.range

    if (args.sample):
        sheetId=SAMPLE_SPREADSHEET_ID
        ranges=[SAMPLE_RANGE_NAME]

    for r in ranges:
        data = get_sheet(sheetId, r)
        dump(data)