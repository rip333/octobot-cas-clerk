import os

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter


class MCPFirestore:
    def __init__(self):
        self.db = firestore.Client(database="octobot-cas-db")

    def end_cycle(self) -> bool:
        """
        Archive the current cycle as a snapshot and reset 'current' for the next cycle.
        """
        current_metadata = self.get_cycle_metadata()
        current_num = current_metadata.get("number", 0)

        archive_ref = self.db.collection('cycle_metadata').document(f"cycle_{current_num}")
        
        archive_data = current_metadata.copy()
        archive_data["state"] = "complete"
        archive_data["active"] = False
        archive_ref.set(archive_data)

        # Clean up cycle data
        self.clear_nominations()
        self.clear_votes()

        new_current_data = {
            "number": current_num + 1,
            "state": "planning",
            "active": False,
            "nomination_thread_id": 0
        }
        
        return self.update_cycle_metadata(new_current_data)

    def begin_cycle(self, thread_id: int) -> bool:
        """
        Transition the current cycle from 'planning' to 'nominations'.
        Sets active to True, state to 'nominations', and stores the thread ID.
        """
        metadata = self.get_cycle_metadata()
        metadata["active"] = True
        metadata["state"] = "nominations"
        metadata["nomination_thread_id"] = thread_id
        return self.update_cycle_metadata(metadata)

    def get_nominations(self) -> list:
        """
        Read all nominations from the nominations collection.
        """
        query = self.db.collection('nominations').order_by('timestamp', direction=firestore.Query.DESCENDING)
        results = query.stream()
        nominations = []
        for doc in results:
            data = doc.to_dict()
            data['id'] = doc.id
            if 'timestamp' in data and data['timestamp']:
                data['timestamp'] = str(data['timestamp'])
            nominations.append(data)
        return nominations

    def add_nomination(self, nominator_id: str, nominator_name: str, set_name: str, category: str, creator_name: str = "", creator_discord_id: str = "", ip_category: str = "") -> str:
        """
        Add a new nomination to the nominations collection.
        """
        doc_ref = self.db.collection('nominations').document()
        data = {
            'nominatorId': str(nominator_id),
            'nominatorName': str(nominator_name),
            'set_name': set_name,
            'category': category,
            'creatorName': creator_name,
            'creatorDiscordId': creator_discord_id,
            'ip_category': ip_category,
            'timestamp': firestore.SERVER_TIMESTAMP
        }
        doc_ref.set(data)
        return doc_ref.id

    def remove_nomination(self, nomination_id: str) -> bool:
        """
        Remove a nomination from the nominations collection by its document ID.
        """
        doc_ref = self.db.collection('nominations').document(nomination_id)
        doc_ref.delete()
        return True

    def log_error(self, text: str) -> str:
        """
        Log an error to the errors collection.
        """
        doc_ref = self.db.collection('errors').document()
        doc_ref.set({
            'text': text,
            'timestamp': firestore.SERVER_TIMESTAMP
        })
        return doc_ref.id

    def get_rules(self) -> str:
        """
        Pull the rules text from a static document.
        """
        rules_path = os.path.join(os.path.dirname(__file__), 'rules.txt')
        try:
            with open(rules_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            return "Rules document not found."

    def get_cycle_metadata(self) -> dict:
        """
        Get the current cycle metadata. Initializes to default if it doesn't exist.
        """
        doc_ref = self.db.collection('cycle_metadata').document('current')
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        else:
            default_data = {
                "number": 100,
                "active": True,
                "nomination_thread_id": 0,
                "state": "off"
            }
            doc_ref.set(default_data)
            return default_data

    def update_cycle_metadata(self, data: dict) -> bool:
        """
        Update the cycle metadata document.
        """
        doc_ref = self.db.collection('cycle_metadata').document('current')
        doc_ref.set(data, merge=True)
        return True

    def clear_nominations(self) -> int:
        """
        Delete all documents in the nominations collection.
        Returns the number of documents deleted.
        """
        nominations_ref = self.db.collection('nominations')
        docs = nominations_ref.stream()
        
        deleted_count = 0
        for doc in docs:
            doc.reference.delete()
            deleted_count += 1
            
        return deleted_count

    def record_user_vote(self, user_id: str, user_name: str, heroes: list, encounters: list) -> bool:
        """
        Record a user's vote in the votes collection.
        Uses their user_id as the document ID so they can only vote once (overwrites previous).
        """
        doc_ref = self.db.collection('votes').document(str(user_id))
        doc_ref.set({
            'userId': str(user_id),
            'userName': str(user_name),
            'heroes': heroes,
            'encounters': encounters,
            'timestamp': firestore.SERVER_TIMESTAMP
        })
        return True

    def get_all_votes(self) -> list:
        """
        Retrieve all votes from the votes collection.
        """
        query = self.db.collection('votes').order_by('timestamp', direction=firestore.Query.DESCENDING)
        results = query.stream()
        votes = []
        for doc in results:
            data = doc.to_dict()
            data['id'] = doc.id
            if 'timestamp' in data and data['timestamp']:
                data['timestamp'] = str(data['timestamp'])
            votes.append(data)
        return votes

    def clear_votes(self) -> int:
        """
        Delete all documents in the votes collection.
        Returns the number of documents deleted.
        """
        votes_ref = self.db.collection('votes')
        docs = votes_ref.stream()
        
        deleted_count = 0
        for doc in docs:
            doc.reference.delete()
            deleted_count += 1
            
        return deleted_count

    def save_spotlight_roster(self, cycle_number: int, roster: list) -> bool:
        """
        Record the finalized spotlight roster and its form data for a specific cycle.
        """
        doc_ref = self.db.collection('spotlight_roster').document(str(cycle_number))
        doc_ref.set({
            'cycle': int(cycle_number),
            'spotlights': roster,
            'timestamp': firestore.SERVER_TIMESTAMP
        })
        return True

    def save_ip_assignment(self, cycle_number: int, set_name: str, ip_category: str) -> bool:
        """
        Record the IP assignment for a specific set in the nominations collection directly.
        """
        # Batch update all matching nominations
        query = self.db.collection('nominations').where(filter=FieldFilter('set_name', '==', set_name))
        docs = query.stream()
        
        batch = self.db.batch()
        count = 0
        for doc in docs:
            batch.update(doc.reference, {"ip_category": ip_category})
            count += 1
            
        if count == 0:
            # Fallback for old schema
            query2 = self.db.collection('nominations').where(filter=FieldFilter('nomineeName', '==', set_name))
            docs2 = query2.stream()
            for doc in docs2:
                batch.update(doc.reference, {"ip_category": ip_category})
                count += 1
                
        if count > 0:
            batch.commit()
            return True
            
        return False

    def get_spotlight_roster(self, cycle_number: int) -> dict:
        """
        Retrieve the spotlight roster and form data saved for a cycle.
        Returns the document dict, or an empty dict if not found.
        """
        doc_ref = self.db.collection('spotlight_roster').document(str(cycle_number))
        doc = doc_ref.get()
        return doc.to_dict() if doc.exists else {}

    def get_ineligible_creators(self, cycle_number: int) -> tuple[list, list]:
        """
        Retrieves the creators who had sealed content in the previous cycle.
        Returns a tuple of two lists: (hero_creators, encounter_creators).
        """
        previous_cycle = cycle_number - 1
        roster_data = self.get_spotlight_roster(previous_cycle)
        spotlights = roster_data.get('spotlights', [])
        
        hero_creators = set()
        encounter_creators = set()
        
        hero_categories = ['Marvel', 'DC', 'Other', 'Wildcard']
        
        for item in spotlights:
            creator_name = item.get('creatorName')
            if not creator_name or creator_name == 'Unknown':
                continue
                
            category = item.get('category')
            if category in hero_categories:
                hero_creators.add(creator_name)
            elif category == 'Encounter':
                encounter_creators.add(creator_name)
                
        return list(hero_creators), list(encounter_creators)

