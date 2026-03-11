import sys
import os
import random

# Add parent dir to path so we can import mcp_firestore
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_firestore import MCPFirestore

MARVEL_HEROES = [
    "Spider-Man", "Iron Man", "Thor", "Hulk", "Wolverine", "Captain America", 
    "Black Widow", "Doctor Strange", "Scarlet Spider", "Dum Dum Dugan", 
    "Iron Patriot", "Sunfire", "Daredevil", "Punisher", "Ghost Rider", 
    "Silver Surfer", "Black Panther", "Captain Marvel", "Nova", "Star-Lord",
    "Rocket Raccoon", "Groot", "Gamora", "Drax", "Ant-Man", "Wasp", "Vision",
    "Scarlet Witch", "Quicksilver", "Falcon", "Winter Soldier", "Hawkeye",
    "Moon Knight", "She-Hulk", "Shang-Chi", "Iron Fist", "Luke Cage", 
    "Jessica Jones", "Blade", "Deadpool", "Cable", "Domino", "Colossus",
    "Nightcrawler", "Storm", "Jean Grey", "Cyclops", "Beast", "Iceman"
]
DC_HEROES = ["Batman", "Superman", "Wonder Woman", "Flash", "Green Lantern", "Steel", "Katana", "Nightwing", "Grifter", "Aquaman", "Cyborg", "Martian Manhunter", "Shazam", "Green Arrow"]
OTHER_HEROES = ["Leonardo", "Raphael", "Darth Vader", "Luke Skywalker", "Goku", "Vegeta", "Predator", "ROM", "Elemental Hero Neos", "Donatello", "Michelangelo"]

MARVEL_ENCOUNTERS = [
    "The Lizard", "Super-Skrull", "Battle of New York", "High Evolutionary", 
    "Children of the Vault", "Thanos", "Doctor Doom", "Green Goblin", 
    "Doctor Octopus", "Venom", "Carnage", "Magneto", "Apocalypse", 
    "Mister Sinister", "Sabretooth", "Juggernaut", "Mystique", "Kingpin", 
    "Bullseye", "Red Skull", "Arnim Zola", "Baron Zemo", "Loki", "Hela", 
    "Surtur", "Malekith", "Ronan the Accuser", "Ego the Living Planet", 
    "Kang the Conqueror", "Ultron"
]
DC_ENCOUNTERS = ["Reverse Flash", "Brainiac", "Catwoman", "Joker", "Lex Luthor", "Darkseid", "Doomsday", "Cheetah", "Black Manta"]
OTHER_ENCOUNTERS = ["Shredder", "King Hiss", "Frieza", "Cell", "Majin Buu", "Boba Fett"]

CREATORS = [
    ("Neptune", "<@111>"), ("Rainy", "<@222>"), ("CptScorp", "<@333>"), 
    ("Merlin", "<@444>"), ("JackHKP", "<@555>"), ("supertnt73", "<@666>"),
    ("Inkwire", "<@777>"), ("Kajislav", "<@888>"), ("Karmi", "<@999>"),
    ("JustATuna", "<@000>"), ("Ripper3", "<@123>"), ("Cogahan", "<@456>")
]

FACTION_TO_IP = {"marvel": "Marvel", "dc": "DC", "other": "Other"}
NO_IP_QUOTA = 2  # Guarantee at least this many blank-IP nominations for testing

def generate_dummy_data(count=30):
    db = MCPFirestore()
    print(f"Adding {count} dummy nominations...")
    
    pools = {
        "hero_marvel": MARVEL_HEROES.copy(),
        "hero_dc": DC_HEROES.copy(),
        "hero_other": OTHER_HEROES.copy(),
        "encounter_marvel": MARVEL_ENCOUNTERS.copy(),
        "encounter_dc": DC_ENCOUNTERS.copy(),
        "encounter_other": OTHER_ENCOUNTERS.copy()
    }
    
    blanks_so_far = 0
    
    for i in range(count):
        is_hero = random.random() < 0.7
        cat_str = "hero" if is_hero else "encounter"
        db_cat = "HERO" if is_hero else "ENCOUNTER"
        
        r = random.random()
        if r < 0.5:
            faction = "marvel"
        elif r < 0.7:
            faction = "dc"
        else:
            faction = "other"
            
        pool_key = f"{cat_str}_{faction}"
        pool = pools[pool_key]
        
        if not pool:
            # Fall back to any non-empty pool of the same type
            fallbacks = [(k, p) for k, p in pools.items() if k.startswith(cat_str) and p]
            if fallbacks:
                pool_key, pool = random.choice(fallbacks)
                faction = pool_key.split("_")[1]
            else:
                print(f"Ran out of {db_cat} choices!")
                continue
                
        nominee = random.choice(pool)
        pool.remove(nominee)
        
        creator_name, creator_id = random.choice(CREATORS)
        nominator_name = f"User{random.randint(100,999)}"
        nominator_id = str(random.randint(100000, 999999))
        
        # Force blank for the final NO_IP_QUOTA entries if not already done;
        # also randomly drop ~5% of earlier ones up to the quota.
        remaining = count - i
        force_blank = blanks_so_far < NO_IP_QUOTA and remaining <= (NO_IP_QUOTA - blanks_so_far)
        random_blank = blanks_so_far < NO_IP_QUOTA and random.random() < 0.05
        
        if force_blank or random_blank:
            ip_category = ""
            blanks_so_far += 1
            print(f"Adding {db_cat}: {nominee} by {creator_name} [NO IP]")
        else:
            ip_category = FACTION_TO_IP[faction]
            print(f"Adding {db_cat}: {nominee} by {creator_name} [{ip_category}]")
        
        db.add_nomination(
            nominator_id=nominator_id,
            nominator_name=nominator_name,
            nominee_name=nominee,
            category=db_cat,
            creator_name=creator_name,
            creator_discord_id=creator_id,
            ip_category=ip_category
        )
        
    print(f"Done! ({blanks_so_far} nomination(s) left without IP for testing)")

if __name__ == "__main__":
    # Feel free to change the number of dummy nominations
    count = 40
    if len(sys.argv) > 1:
        count = int(sys.argv[1])
    generate_dummy_data(count)
