import os

from google.cloud import firestore


class MCPFirestore:
    def __init__(self):
        self.db = firestore.Client(database="octobot-cas-db")

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

    def add_nomination(self, nominator_id: str, nominator_name: str, nominee_name: str, category: str, creator_name: str = "", creator_discord_id: str = "", ip_category: str = "") -> str:
        """
        Add a new nomination to the nominations collection.
        """
        doc_ref = self.db.collection('nominations').document()
        data = {
            'nominatorId': str(nominator_id),
            'nominatorName': str(nominator_name),
            'nomineeName': nominee_name,
            'category': category,
            'timestamp': firestore.SERVER_TIMESTAMP
        }
        if creator_name:
            data['creatorName'] = creator_name
        if creator_discord_id:
            data['creatorDiscordId'] = creator_discord_id
        if ip_category:
            data['ip_category'] = ip_category
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
                "number": 11,
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
        Record the finalized spotlight roster for a specific cycle.
        """
        batch = self.db.batch()
        for hero in roster:
            doc_ref = self.db.collection('spotlight_roster').document()
            data = {
                'cycle': int(cycle_number),
                'nominee': str(hero['name']),
                'category': str(hero['category']),
                'timestamp': firestore.SERVER_TIMESTAMP
            }
            if 'creatorName' in hero:
                data['creatorName'] = str(hero['creatorName'])
            if 'creatorDiscordId' in hero:
                data['creatorDiscordId'] = str(hero['creatorDiscordId'])
            batch.set(doc_ref, data)
        batch.commit()
        return True

    def save_ip_assignment(self, cycle_number: int, nominee: str, ip_category: str) -> bool:
        """
        Record the IP assignment for a specific nominee in a cycle.
        """
        doc_id = f"{cycle_number}_{nominee}".replace('/', '_')
        doc_ref = self.db.collection('ip_assignments').document(doc_id)
        doc_ref.set({
            'cycle': int(cycle_number),
            'nominee': str(nominee),
            'ip_category': str(ip_category),
            'timestamp': firestore.SERVER_TIMESTAMP
        }, merge=True)
        return True

    def get_ip_assignments(self, cycle_number: int) -> dict:
        """
        Get all IP assignments for a specific cycle. Returns a dict mapping nominee to ip_category.
        """
        query = self.db.collection('ip_assignments').where('cycle', '==', int(cycle_number))
        results = query.stream()
        assignments = {}
        for doc in results:
            data = doc.to_dict()
            assignments[data['nominee']] = data['ip_category']
        return assignments

