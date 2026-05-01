import os
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

class MCPFirestore:
    def __init__(self):
        self.db = firestore.Client(database="octobot-cas-db")
        self.collection_prefix = "test_" if os.getenv("ENVIRONMENT") == "test" else ""

    def get_current_cycle_number(self) -> int:
        doc = self.db.collection(self.collection_prefix + 'cycles').document('current_cycle').get()
        if doc.exists:
            return int(doc.to_dict().get('number', 12))
            
        # If no current_cycle document exists, initialize it
        self.db.collection(self.collection_prefix + 'cycles').document('current_cycle').set({"number": 12})
        return 12

    def get_active_cycle(self) -> dict:
        cycle_num = self.get_current_cycle_number()
        doc = self.db.collection(self.collection_prefix + 'cycles').document(str(cycle_num)).get()
        
        if doc.exists:
            data = doc.to_dict()
            if 'number' in data:
                data['number'] = int(data['number'])
            return data
            
        # If it doesn't exist, create it with defaults
        default_cycle = {
            "number": cycle_num,
            "state": "planning",
            "is_active": True,
            "nomination_thread_id": 0,
        }
        self.db.collection(self.collection_prefix + 'cycles').document(str(cycle_num)).set(default_cycle)
        return default_cycle

    def get_cycle(self, cycle_number: int) -> dict:
        doc = self.db.collection(self.collection_prefix + 'cycles').document(str(cycle_number)).get()
        if doc.exists:
            return doc.to_dict()
        return {}

    def update_cycle(self, cycle_number: int, data: dict) -> bool:
        self.db.collection(self.collection_prefix + 'cycles').document(str(cycle_number)).set(data, merge=True)
        return True

    def get_cycle_metadata(self) -> dict:
        # Backwards compatibility for cogs
        return self.get_active_cycle()

    def update_cycle_metadata(self, data: dict) -> bool:
        # Backwards compatibility for cogs
        cycle_num = self.get_current_cycle_number()
        return self.update_cycle(cycle_num, data)

    def begin_cycle(self, thread_id: int) -> bool:
        cycle_num = self.get_current_cycle_number()
        return self.update_cycle(cycle_num, {
            "state": "nominations",
            "nomination_thread_id": thread_id
        })

    def end_cycle(self) -> bool:
        current_num = self.get_current_cycle_number()
        
        # Mark current as inactive
        self.update_cycle(current_num, {
            "state": "complete",
            "is_active": False
        })
            
        new_num = current_num + 1
        
        # Update current_cycle pointer
        self.db.collection(self.collection_prefix + 'cycles').document('current_cycle').set({"number": new_num})
        
        # Create new active cycle
        self.db.collection(self.collection_prefix + 'cycles').document(str(new_num)).set({
            "number": new_num,
            "state": "planning",
            "is_active": True,
            "nomination_thread_id": 0,
        })
        return True

    def get_nominations(self, cycle_number: int = None) -> list:
        if cycle_number is None:
            cycle_number = self.get_current_cycle_number()
            
        docs = self.db.collection(self.collection_prefix + 'cycles').document(str(cycle_number)).collection(self.collection_prefix + 'nominations').stream()
        nominations = []
        for doc in docs:
            data = doc.to_dict()
            for s in data.get('sets', []):
                nom = {
                    'nominatorId': data.get('nominator_id'),
                    'nominatorName': data.get('nominator_name'),
                    'set_name': s.get('set_name'),
                    'category': s.get('category'),
                    'creatorName': s.get('creatorName'),
                    'ip_category': s.get('ip_category'),
                    'type': s.get('type')
                }
                nominations.append(nom)
        return nominations

    def get_raw_nominations(self, cycle_number: int = None) -> list:
        if cycle_number is None:
            cycle_number = self.get_current_cycle_number()
            
        docs = self.db.collection(self.collection_prefix + 'cycles').document(str(cycle_number)).collection(self.collection_prefix + 'nominations').stream()
        return [doc.to_dict() for doc in docs]

    def add_nomination_batch(self, cycle_number: int, nominator_id: str, nominator_name: str, sets: list) -> str:
        doc_ref = self.db.collection(self.collection_prefix + 'cycles').document(str(cycle_number)).collection(self.collection_prefix + 'nominations').document(str(nominator_id))
        doc_ref.set({
            'nominator_id': str(nominator_id),
            'nominator_name': str(nominator_name),
            'sets': sets,
            'timestamp': firestore.SERVER_TIMESTAMP
        }, merge=True)
        return doc_ref.id

    def clear_nominations(self) -> int:
        cycle_number = self.get_current_cycle_number()
        docs = self.db.collection(self.collection_prefix + 'cycles').document(str(cycle_number)).collection(self.collection_prefix + 'nominations').stream()
        count = 0
        for doc in docs:
            doc.reference.delete()
            count += 1
        return count

    def record_user_vote(self, user_id: str, user_name: str, heroes: list, encounters: list) -> bool:
        cycle_number = self.get_current_cycle_number()
        doc_ref = self.db.collection(self.collection_prefix + 'cycles').document(str(cycle_number)).collection(self.collection_prefix + 'votes').document(str(user_id))
        doc_ref.set({
            'userId': str(user_id),
            'userName': str(user_name),
            'heroes': heroes,
            'encounters': encounters,
            'timestamp': firestore.SERVER_TIMESTAMP
        })
        return True

    def get_all_cycles(self) -> list:
        docs = self.db.collection(self.collection_prefix + 'cycles').stream()
        cycles = []
        for doc in docs:
            if doc.id == 'current_cycle': continue
            data = doc.to_dict()
            try:
                cycles.append(int(data.get('number', doc.id)))
            except ValueError:
                pass
        return sorted(cycles, reverse=True)

    def get_all_votes(self, cycle_number: int = None) -> list:
        if cycle_number is None:
            cycle_number = self.get_current_cycle_number()
        query = self.db.collection(self.collection_prefix + 'cycles').document(str(cycle_number)).collection(self.collection_prefix + 'votes').order_by('timestamp', direction=firestore.Query.DESCENDING)
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
        cycle_number = self.get_current_cycle_number()
        docs = self.db.collection(self.collection_prefix + 'cycles').document(str(cycle_number)).collection(self.collection_prefix + 'votes').stream()
        count = 0
        for doc in docs:
            doc.reference.delete()
            count += 1
        return count

    def _spotlights_ref(self, cycle_number: int):
        """Return a reference to the spotlights subcollection for a cycle."""
        return (
            self.db
            .collection(self.collection_prefix + 'cycles')
            .document(str(cycle_number))
            .collection(self.collection_prefix + 'spotlights')
        )

    def save_spotlight_roster(self, cycle_number: int, roster: list) -> bool:
        """Write the full spotlight roster as individual subcollection documents.
        Deletes any pre-existing entries first so the result is always a clean slate."""
        col = self._spotlights_ref(cycle_number)
        batch = self.db.batch()

        # Clear any previously saved spotlight docs
        for doc in col.stream():
            batch.delete(doc.reference)

        # Write each entry keyed by set_name
        for entry in roster:
            set_name = entry.get("set_name", "")
            if not set_name:
                continue
            batch.set(col.document(set_name), entry)

        batch.commit()
        return True

    def update_spotlight_entry(self, cycle_number: int, set_name: str, data: dict) -> bool:
        """Merge-update a single spotlight entry without touching other entries."""
        self._spotlights_ref(cycle_number).document(set_name).set(data, merge=True)
        return True
        
    def copy_to_sealed_sets(self, cycle_number: int, sealed_roster: list) -> bool:
        import logging
        logger = logging.getLogger('octobot')
        collection_name = self.collection_prefix + 'sealed_sets'
        logger.info(f"copy_to_sealed_sets: Writing {len(sealed_roster)} item(s) to '{collection_name}' for cycle {cycle_number}")
        
        if not sealed_roster:
            logger.warning("copy_to_sealed_sets: sealed_roster is empty, nothing to write.")
            return False
        
        batch = self.db.batch()
        for item in sealed_roster:
            doc_ref = self.db.collection(collection_name).document()
            item_data = item.copy()
            item_data['cycle_number'] = cycle_number
            item_data['timestamp'] = firestore.SERVER_TIMESTAMP
            batch.set(doc_ref, item_data)
            logger.info(f"copy_to_sealed_sets: Queued '{item_data.get('set_name', 'UNKNOWN')}' -> {doc_ref.path}")
        batch.commit()
        logger.info(f"copy_to_sealed_sets: Batch committed successfully.")
        return True

    def save_ip_assignment(self, cycle_number: int, set_name: str, ip_category: str) -> bool:
        docs = self.db.collection(self.collection_prefix + 'cycles').document(str(cycle_number)).collection(self.collection_prefix + 'nominations').stream()
        batch = self.db.batch()
        count = 0
        for doc in docs:
            data = doc.to_dict()
            changed = False
            sets = data.get('sets', [])
            for s in sets:
                if s.get('set_name') == set_name or s.get('nomineeName') == set_name:
                    s['ip_category'] = ip_category
                    changed = True
            
            if changed:
                batch.update(doc.reference, {"sets": sets})
                count += 1
                
        if count > 0:
            batch.commit()
            return True
        return False

    def get_spotlight_roster(self, cycle_number: int) -> dict:
        """Stream the spotlights subcollection and return entries as a list."""
        docs = self._spotlights_ref(cycle_number).stream()
        spotlights = [doc.to_dict() for doc in docs]
        return {'cycle': cycle_number, 'spotlights': spotlights}

    def get_ineligible_creators(self, cycle_number: int) -> tuple[list, list]:
        previous_cycle = cycle_number - 1
        
        # Query sealed_sets for the previous cycle
        query = self.db.collection(self.collection_prefix + 'sealed_sets').where(filter=FieldFilter('cycle_number', '==', previous_cycle))
        docs = query.stream()
        
        hero_creators = set()
        encounter_creators = set()
        
        for doc in docs:
            item = doc.to_dict()
            creator_name = item.get('creatorName')
            if not creator_name or creator_name == 'Unknown':
                continue
                
            item_type = item.get('type')
            if not item_type:
                cat = item.get('category', '')
                item_type = 'villain' if cat == 'Encounter' else 'hero'
                
            if item_type == 'hero':
                hero_creators.add(creator_name)
            elif item_type in ['villain', 'encounter']:
                encounter_creators.add(creator_name)
                
        return list(hero_creators), list(encounter_creators)

    def log_error(self, text: str) -> str:
        doc_ref = self.db.collection(self.collection_prefix + 'errors').document()
        doc_ref.set({
            'text': text,
            'timestamp': firestore.SERVER_TIMESTAMP
        })
        return doc_ref.id

    def get_rules(self) -> str:
        rules_path = os.path.join(os.path.dirname(__file__), 'rules.txt')
        try:
            with open(rules_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            return "Rules document not found."
