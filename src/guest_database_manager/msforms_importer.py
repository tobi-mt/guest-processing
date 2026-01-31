"""
Microsoft Forms Importer for Guest Database Manager

- Authenticates interactively with Microsoft Graph
- Fetches responses from Excel file linked to Microsoft Forms
- Extracts guest info, using only the 'Email1' column for email
"""
import os
import requests
try:
    import msal
except ImportError:
    raise ImportError("The 'msal' package is required. Please install it with 'pip install msal'.")
from typing import List, Dict

CLIENT_ID = os.environ.get("MS_GRAPH_CLIENT_ID", "YOUR_CLIENT_ID")
TENANT_ID = os.environ.get("MS_GRAPH_TENANT_ID", "common")
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["Files.Read", "User.Read"]

class MSFormsImporter:
    def __init__(self, excel_url: str):
        self.excel_url = excel_url
        self.access_token = None

    def authenticate(self):
        """Interactive login to get access token."""
        app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY)
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise RuntimeError("Failed to create device flow")
        print(f"To authenticate, visit {flow['verification_uri']} and enter code: {flow['user_code']}")
        result = app.acquire_token_by_device_flow(flow)
        if "access_token" in result:
            self.access_token = result["access_token"]
            print("✅ Authentication successful!")
        else:
            raise RuntimeError(f"Authentication failed: {result}")

    def get_excel_id(self) -> str:
        """Extracts the Excel file ID from the OneDrive URL."""
        import re
        match = re.search(r"resid=([a-f0-9\-]+)", self.excel_url)
        if not match:
            raise ValueError("Could not extract Excel file ID from URL")
        return match.group(1)

    def fetch_responses(self) -> List[Dict]:
        """Fetches responses from the Excel file via Microsoft Graph."""
        if not self.access_token:
            raise RuntimeError("Not authenticated")
        excel_id = self.get_excel_id()
        endpoint = f"https://graph.microsoft.com/v1.0/me/drive/items/{excel_id}/workbook/worksheets"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        resp = requests.get(endpoint, headers=headers, timeout=15)
        resp.raise_for_status()
        worksheets = resp.json().get("value", [])
        if not worksheets:
            raise LookupError("No worksheets found in Excel file")
        sheet_id = worksheets[0]["id"]
        rows_endpoint = f"https://graph.microsoft.com/v1.0/me/drive/items/{excel_id}/workbook/worksheets/{sheet_id}/tables"
        resp = requests.get(rows_endpoint, headers=headers, timeout=15)
        resp.raise_for_status()
        tables = resp.json().get("value", [])
        if not tables:
            raise LookupError("No tables found in worksheet")
        table_id = tables[0]["id"]
        data_endpoint = f"https://graph.microsoft.com/v1.0/me/drive/items/{excel_id}/workbook/tables/{table_id}/rows"
        resp = requests.get(data_endpoint, headers=headers, timeout=15)
        resp.raise_for_status()
        rows = resp.json().get("value", [])
        # Extract only 'Email1' column
        email_idx = None
        guests = []
        for row in rows:
            values = row.get("values", [[]])[0]
            # Find 'Email1' column index from header row
            if email_idx is None and values:
                for i, v in enumerate(values):
                    if v == "Email1":
                        email_idx = i
                        break
                if email_idx is None:
                    raise LookupError("'Email1' column not found in table header")
                continue  # skip header row
            if email_idx is not None and len(values) > email_idx:
                guests.append({"email": values[email_idx]})
        return guests

if __name__ == "__main__":
    importer = MSFormsImporter("https://onedrive.live.com/personal/fe90a6a68cb3a59e/_layouts/15/doc.aspx?resid=85a17b8a-0e59-4646-8720-fbbe08328991&cid=fe90a6a68cb3a59e&action=edit&wdMsFormsCorrelationId=36a74e32-d7de-490b-9059-5137bff985b3")
    importer.authenticate()
    guests = importer.fetch_responses()
    print(f"Fetched {len(guests)} guests:")
    for guest in guests:
        print(guest)
