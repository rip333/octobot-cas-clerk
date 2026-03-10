import sys
import os
import random

# Add parent dir to path so we can import mcp_firestore
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_firestore import MCPFirestore

MARVEL_HEROES = ["Spider-Man", "Iron Man", "Thor", "Hulk", "Wolverine", "Captain America", "Black Widow", "Doctor Strange", "Scarlet Spider", "Dum Dum Dugan", "Iron Patriot", "Sunfire"]
DC_HEROES = ["Batman", "Superman", "Wonder Woman", "Flash", "Green Lantern", "Steel", "Katana", "Nightwing", "Grifter"]
OTHER_HEROES = ["Leonardo", "Raphael", "Darth Vader", "Luke Skywalker", "Goku", "Vegeta", "Predator", "ROM", "Elemental Hero Neos"]

MARVEL_ENCOUNTERS = ["The Lizard", "Super-Skrull", "Battle of New York", "High Evolutionary", "Children of the Vault"]
DC_ENCOUNTERS = ["Reverse Flash", "Brainiac", "Catwoman"]
OTHER_ENCOUNTERS = ["Shredder", "King Hiss", "Frieza"]

CREATORS = [
    ("Neptune", "<@111>"), ("Rainy", "<@222>"), ("CptScorp", "<@333>"), 
    ("Merlin", "<@444>"), ("JackHKP", "<@555>"), ("supertnt73", "<@666>"),
    ("Inkwire", "<@777>"), ("Kajislav", "<@888>"), ("Karmi", "<@999>"),
    ("JustATuna", "<@000>"), ("Ripper3", "<@123>"), ("Cogahan", "<@456>")
]

def pick_category(item_type="hero"):
    r = random.random()
    if r < 0.5:
        return MARVEL_HEROES if item_type == "hero" else MARVEL_ENCOUNTERS
    elif r < 0.7:
        return DC_HEROES if item_type == "hero" else DC_ENCOUNTERS
    else:
        return OTHER_HEROES if item_type == "hero" else OTHER_ENCOUNTERS

def generate_dummy_data(count=30):
    db = MCPFirestore()
    print(f"Adding {count} dummy nominations...")
    
    for _ in range(count):
        is_hero = random.random() < 0.7
        cat_str = "hero" if is_hero else "encounter"
        db_cat = "HERO" if is_hero else "ENCOUNTER"
        
        pool = pick_category(cat_str)
        nominee = random.choice(pool)
        
        creator_name, creator_id = random.choice(CREATORS)
        nominator_name = f"User{random.randint(100,999)}"
        nominator_id = str(random.randint(100000, 999999))
        
        print(f"Adding {db_cat}: {nominee} by {creator_name}")
        db.add_nomination(
            nominator_id=nominator_id,
            nominator_name=nominator_name,
            nominee_name=nominee,
            category=db_cat,
            creator_name=creator_name,
            creator_discord_id=creator_id
        )
        
    print("Done!")

if __name__ == "__main__":
    # Feel free to change the number of dummy nominations
    count = 40
    if len(sys.argv) > 1:
        count = int(sys.argv[1])
    generate_dummy_data(count)
