import os
from dotenv import load_dotenv
from mcp_firestore import MCPFirestore

# Load environment variables just in case
load_dotenv()

def main():
    db = MCPFirestore()
    metadata = db.get_cycle_metadata()
    print(f"Current metadata: {metadata}")
    
    metadata["state"] = "off"
    db.update_cycle_metadata(metadata)
    
    print(f"Updated metadata: {db.get_cycle_metadata()}")
    print("State successfully set to 'off'.")

if __name__ == "__main__":
    main()
