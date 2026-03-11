"""
google_services.py
~~~~~~~~~~~~~~~~~~
Wraps Google Drive, Forms, and Sheets APIs for the Spotlight Scorecard workflow.

Authentication strategy:
  - For Drive/Forms/Sheets: uses OAuth2 user credentials (token.json) so that
    forms are created as a real Google account (required by the Forms API).
  - token.json is generated once by running: python scripts/authorize_google_oauth.py

Option A: Each created form auto-creates its own response Sheet when the first
          response is submitted. No programmatic response-destination linking needed.
"""

import os
import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/forms.body",
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

    # ------------------------------------------------------------------
    # Forms helpers
    # ------------------------------------------------------------------

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

    def copy_form_for_set(self, set_name: str, cycle_number: int, creator_name: str) -> dict:
        """
        Create a new Google Form that mirrors the template form's questions.
        Uses Forms API create + batchUpdate.

        Returns a dict with:
            form_id      — the new Form's id
            edit_url     — link to edit the form (admin use)
            response_url — public response URL
        """
        title = f"cycle {cycle_number} - {set_name} by {creator_name}"

        # 1. Create a blank form with the right title
        new_form = self.forms.forms().create(body={
            "info": {
                "title": title,
                "documentTitle": title
            }
        }).execute()
        form_id = new_form["formId"]

        # 2. Read the template items
        template_items = self._get_template_items()

        # 3. Build batchUpdate requests to add each item in order
        #    Strip itemId so the API assigns new ones; sanitize newlines too.
        requests = []
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

        # Move to the shared folder if configured
        folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "")
        if folder_id:
            try:
                file_meta = self.drive.files().get(
                    fileId=form_id, fields="parents"
                ).execute()
                current_parents = ",".join(file_meta.get("parents", []))
                self.drive.files().update(
                    fileId=form_id,
                    addParents=folder_id,
                    removeParents=current_parents,
                    fields="id, parents",
                ).execute()
            except Exception as e:
                print(f"Warning: Failed to move form {form_id} to folder {folder_id}: {e}")

        edit_url = f"https://docs.google.com/forms/d/{form_id}/edit"
        response_url = f"https://docs.google.com/forms/d/{form_id}/viewform"

        return {
            "form_id": form_id,
            "title": title,
            "edit_url": edit_url,
            "response_url": response_url,
        }



