import os
from google_auth_oauthlib.flow import InstalledAppFlow

# The scopes required by the bot
SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/forms",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/script.projects",
]

def main():
    print("Starting Google OAuth login flow...")
    
    # Check if credentials exist
    if not os.path.exists("credentials.json"):
        print("Error: 'credentials.json' not found. Please ensure your OAuth Client ID file is in this folder named 'credentials.json'.")
        return

    # Create the flow using the client secrets file from the Google API Console
    flow = InstalledAppFlow.from_client_secrets_file(
        "credentials.json", SCOPES
    )
    
    # This opens the browser
    creds = flow.run_local_server(port=0)
    
    # Save the credentials for the next run
    with open("token.json", "w") as token:
        token.write(creds.to_json())
        
    print("\n✅ Success! New permanent 'token.json' has been generated.")

if __name__ == "__main__":
    main()
