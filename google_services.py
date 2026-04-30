import os
import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/forms",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/script.projects",
]

SCRIPT_ID = 'AKfycbwGRDRDItIC54juHuZ5fqFKyYLVAcozaf7B_GHbwhsjnDqBT8qVWY7IidM-xU60sdr7'

def _build_user_credentials() -> Credentials:
    """
    Load and auto-refresh OAuth2 user credentials from token.json.
    """
    token_path = os.environ.get("GOOGLE_OAUTH_TOKEN_PATH", "token.json")
    if not os.path.exists(token_path):
        raise FileNotFoundError(
            f"OAuth2 token file not found at '{token_path}'. "
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
        self.script = build("script", "v1", credentials=creds)

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
    
    def _apply_form_settings_via_script(self, form_id: str):
        """Calls the Apps Script to update form settings/logic."""
        request_body = {
            "function": "updateFormSettings",
            "parameters": [form_id],
            "devMode": True
        }
        try:
            response = self.script.scripts().run(scriptId=SCRIPT_ID, body=request_body).execute()
            if 'error' in response:
                print(f"Apps Script Error for form {form_id}: {response['error']['details'][0]['errorMessage']}")
            else:
                print(f"Successfully applied settings to form {form_id}")
        except Exception as e:
            print(f"Failed to trigger Apps Script: {e}")

    def copy_form_for_set(self, set_name: str, cycle_number: int, creator_name: str) -> dict:
        """
        Create a new Google Form that mirrors the template form's questions
        and applies specific general, presentation, and post-submission settings.
        """
        title = f"Cycle {cycle_number} - {set_name} by {creator_name}"
        if os.environ.get("ENVIRONMENT") == "test":
            title = f"[TEST] {title}"

        # 1. Copy the template form using Drive API to preserve formatting, line breaks, etc.
        template_form_id = os.environ.get("GOOGLE_TEMPLATE_FORM_ID", "")
        if not template_form_id:
            raise ValueError("GOOGLE_TEMPLATE_FORM_ID is not set in environment variables.")

        # Determine target folder
        folder_id = self._get_or_create_cycle_folder(cycle_number)

        copy_metadata = {
            'name': title,
            'parents': [folder_id]
        }
        
        try:
            new_form = self.drive.files().copy(
                fileId=template_form_id,
                body=copy_metadata,
                supportsAllDrives=True
            ).execute()
            form_id = new_form['id']
        except Exception as e:
            raise RuntimeError(f"Failed to copy template form via Drive API: {e}")

        # Update the internal form title (Drive API copy sets the documentTitle, but not necessarily the internal form title perfectly if it had logic)
        try:
            self.forms.forms().batchUpdate(
                formId=form_id,
                body={
                    "requests": [
                        {
                            "updateFormInfo": {
                                "info": {
                                    "title": title
                                },
                                "updateMask": "title"
                            }
                        }
                    ]
                }
            ).execute()
        except Exception as e:
            print(f"Warning: Failed to update internal form title for {form_id}: {e}")

        # 1.a Explicitly publish the form to handle API changes (Forms created after June 30, 2026 default to unpublished)
        try:
            # Try to explicitly publish using the newly introduced methods
            # using getattr to handle missing method during client library propagation
            publish_method = getattr(self.forms.forms(), 'setPublishSettings', None)
            if not publish_method:
                 publish_method = getattr(self.forms.forms(), 'setPublishedSettings', None)

            if publish_method:
                 publish_method(
                     formId=form_id, 
                     body={
                         "publishSettings": {
                             "publishState": {
                                 "isPublished": True
                             }
                         },
                         "updateMask": "publishState"
                     }
                 ).execute()
            else:
                 print(f"Notice: Explicit publishing methods 'setPublishSettings'/'setPublishedSettings' not found on current google client for form {form_id}.")
        except Exception as e:
             print(f"Warning: Failed to explicitly publish form {form_id}: {e}")

        # 1.b Share with responders (allow anyone with the link to respond)

        try:
            self.drive.permissions().create(
                fileId=form_id,
                body={
                    'type': 'anyone',
                    'role': 'reader'
                }
            ).execute()
        except Exception as e:
            print(f"Warning: Failed to set 'anyone' reader permission on form {form_id}: {e}")

        self._apply_form_settings_via_script(form_id)

        return {
            "form_id": form_id,
            "title": title,
            "edit_url": f"https://docs.google.com/forms/d/{form_id}/edit",
            "response_url": f"https://docs.google.com/forms/d/{form_id}/viewform",
            "analytics_url": f"https://docs.google.com/forms/d/{form_id}/viewanalytics",
        }

    def get_form(self, form_id: str) -> dict:
        """Fetch the full form structure, including questions."""
        return self.forms.forms().get(formId=form_id).execute()

    def get_form_responses(self, form_id: str) -> list:
        """Fetch all responses for a given form."""
        result = self.forms.forms().responses().list(formId=form_id).execute()
        return result.get('responses', [])

