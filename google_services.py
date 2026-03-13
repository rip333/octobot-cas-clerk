import os
import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/forms.responses.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
]


def _build_user_credentials() -> Credentials:
    """
    Load and auto-refresh OAuth2 user credentials from token.json.
    The token.json file is created once by running scripts/authorize_google_oauth.py.
    """
    token_path = os.environ.get("GOOGLE_OAUTH_TOKEN_PATH", "token.json")
    if not os.path.exists(token_path):
        raise FileNotFoundError(
            f"OAuth2 token file not found at '{token_path}'. "
            "Run scripts/authorize_google_oauth.py once to generate it."
        )
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    # Auto-refresh if expired
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # Persist the refreshed token
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return creds


class GoogleServices:
    """Thin wrapper around Google Drive / Forms / Sheets APIs."""

    def __init__(self):
        creds = _build_user_credentials()
        self.drive = build("drive", "v3", credentials=creds)
        self.forms = build("forms", "v1", credentials=creds)

    def _get_template_items(self) -> list:
        """Read all items (questions/sections) from the template form."""
        template_form_id = os.environ.get("GOOGLE_TEMPLATE_FORM_ID", "")
        if not template_form_id:
            raise ValueError("GOOGLE_TEMPLATE_FORM_ID is not set in environment variables.")
        form = self.forms.forms().get(formId=template_form_id).execute()
        return form.get("items", [])

    def _sanitize_item(self, item: dict) -> dict:
        """
        Recursively replace newline characters in string values.
        The Forms API rejects \\n in any displayed text field.
        """
        if isinstance(item, dict):
            return {k: self._sanitize_item(v) for k, v in item.items()}
        if isinstance(item, list):
            return [self._sanitize_item(v) for v in item]
        if isinstance(item, str):
            return item.replace("\n", " ").replace("\r", " ")
        return item

    def _get_or_create_cycle_folder(self, cycle_number: int) -> str:
        """
        Gets or creates a folder named 'Spotlight Cycle {cycle_number}'.
        If GOOGLE_DRIVE_FOLDER_ID is set in env, it looks/creates inside that parent.
        Otherwise, it does so at the root of the user's Drive.
        """
        folder_name = f"Spotlight Cycle {cycle_number}"
        parent_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "").strip()
        
        # Build query
        query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
        if parent_id:
            query += f" and '{parent_id}' in parents"
            
        results = self.drive.files().list(
            q=query, 
            fields="files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        files = results.get('files', [])
        
        if files:
            return files[0]['id']
            
        # Create it mapping to root (or parent_id if available)
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        if parent_id:
            file_metadata['parents'] = [parent_id]
            
        folder = self.drive.files().create(
            body=file_metadata, 
            fields='id',
            supportsAllDrives=True
        ).execute()
        
        return folder.get('id')

    def copy_form_for_set(self, set_name: str, cycle_number: int, creator_name: str) -> dict:
        """
        Create a new Google Form that mirrors the template form's questions
        and applies specific general, presentation, and post-submission settings.
        """
        title = f"Cycle {cycle_number} - {set_name} by {creator_name}"

        # 1. Create a blank form
        new_form = self.forms.forms().create(body={
            "info": {
                "title": title,
                "documentTitle": title
            }
        }).execute()
        form_id = new_form["formId"]

        # 2. Read the template items
        template_items = self._get_template_items()

        # 3. Build batchUpdate requests
        requests = []
        
        # Add questions from template
        for idx, item in enumerate(template_items):
            item_copy = {k: v for k, v in item.items() if k != "itemId"}
            item_copy = self._sanitize_item(item_copy)
            requests.append({
                "createItem": {
                    "item": item_copy,
                    "location": {"index": idx},
                }
            })

        

        if requests:
            self.forms.forms().batchUpdate(
                formId=form_id,
                body={"requests": requests},
            ).execute()

        # Move to the cycle folder (existing logic)
        try:
            folder_id = self._get_or_create_cycle_folder(cycle_number)
            self.drive.files().update(
                fileId=form_id,
                addParents=folder_id,
                removeParents='root', # Simplified for example
                fields="id, parents",
                supportsAllDrives=True
            ).execute()
        except Exception as e:
            print(f"Warning: Failed to move form {form_id} to folder: {e}")

        return {
            "form_id": form_id,
            "title": title,
            "edit_url": f"https://docs.google.com/forms/d/{form_id}/edit",
            "response_url": f"https://docs.google.com/forms/d/{form_id}/viewform",
        }

    def get_form(self, form_id: str) -> dict:
        """Fetch the full form structure, including questions."""
        return self.forms.forms().get(formId=form_id).execute()

    def get_form_responses(self, form_id: str) -> list:
        """Fetch all responses for a given form."""
        result = self.forms.forms().responses().list(formId=form_id).execute()
        return result.get('responses', [])

