import sys
import os
import random

# Add parent dir to path so we can import mcp_firestore
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_firestore import MCPFirestore

def generate_dummy_votes():
    db = MCPFirestore()
    
    noms = db.get_nominations()
    if not noms:
        print("No nominations found. Please add nominations first.")
        return
        
    heroes = set()
    encounters = set()
    
    for nom in noms:
        nominee = nom.get('nomineeName', 'Unknown')
        creator_name = nom.get('creatorName', '')
        display_name = f"{nominee} — {creator_name}" if creator_name else nominee
        
        if nom.get('category') == 'HERO':
            heroes.add(display_name)
        else:
            encounters.add(display_name)
            
    heroes = list(heroes)
    encounters = list(encounters)
    
    print(f"Found {len(heroes)} unique heroes and {len(encounters)} unique encounters nominated.")
    
    if not heroes and not encounters:
        print("No heroes or encounters found in nominations.")
        return
        
    # Generate target votes with normal distribution
    # Heroes: mean 10, stddev 4, bounded [1, 20]
    hero_targets = {}
    for h in heroes:
        votes = int(random.gauss(mu=10, sigma=4))
        votes = max(1, min(20, votes))
        hero_targets[h] = votes
        
    # Encounters: mean 7.5, stddev 3, bounded [1, 15]
    enc_targets = {}
    for e in encounters:
        votes = int(random.gauss(mu=7.5, sigma=3))
        votes = max(1, min(15, votes))
        enc_targets[e] = votes
        
    print("\nTarget hero votes:")
    for h, count in sorted(hero_targets.items(), key=lambda x: -x[1]):
        print(f"  {count}: {h}")
        
    print("\nTarget encounter votes:")
    for e, count in sorted(enc_targets.items(), key=lambda x: -x[1]):
        print(f"  {count}: {e}")
        
    # Create voters
    max_hero_votes = max(hero_targets.values()) if hero_targets else 0
    max_enc_votes = max(enc_targets.values()) if enc_targets else 0
    
    total_hero_votes = sum(hero_targets.values())
    total_enc_votes = sum(enc_targets.values())
    
    # We need enough users so that no one exceeds 10 heroes or 2 encounters
    required_for_heroes = (total_hero_votes // 8) + 1  # assuming max 10, avg 8 heroes per voter
    required_for_encs = (total_enc_votes // 1.5) + 1   # assuming max 2, avg 1.5 encs per voter
    
    num_users = max(25, max_hero_votes, max_enc_votes, int(required_for_heroes), int(required_for_encs))
    
    print(f"\nSimulating {num_users} voters...")
    
    users = [{"id": f"dummy_{i}", "name": f"DummyVoter_{i}", "heroes": [], "encounters": []} for i in range(num_users)]
    
    # The matching algorithm works best if we allocate the highest voted items first
    for h, target in sorted(hero_targets.items(), key=lambda x: -x[1]):
        available = [u for u in users if len(u["heroes"]) < 10]
        if len(available) < target:
            chosen = available
        else:
            chosen = random.sample(available, target)
        for u in chosen:
            u["heroes"].append(h)
            
    for e, target in sorted(enc_targets.items(), key=lambda x: -x[1]):
        available = [u for u in users if len(u["encounters"]) < 2]
        if len(available) < target:
            chosen = available
        else:
            chosen = random.sample(available, target)
        for u in chosen:
            u["encounters"].append(e)
            
    print("Writing votes to Firestore...")
    votes_written = 0
    for u in users:
        # only add if they voted for something
        if u["heroes"] or u["encounters"]:
            db.record_user_vote(u["id"], u["name"], u["heroes"], u["encounters"])
            votes_written += 1
            
    print(f"Done! Successfully generated {votes_written} dummy ballots.")
    
if __name__ == "__main__":
    generate_dummy_votes()
