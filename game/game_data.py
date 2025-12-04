import csv
import math
import random


class Pokemon:
    """
    Data model for a Pokemon entity.
    Stores stats, moves, and handles stat modifications (RFC 5.0).
    """

    def __init__(self, row, available_moves):
        self.name = row["name"]
        self.type1 = row["type1"]
        self.type2 = row["type2"] if row["type2"] else None

        # RFC 5.0: Base Stats (HP, Attack, Defense, Sp. Atk, Sp. Def, Speed)
        self.hp = int(row["hp"])
        self.max_hp = int(row["hp"])
        self.attack = int(row["attack"])
        self.defense = int(row["defense"])
        self.sp_attack = int(row["sp_attack"])
        self.sp_defense = int(row["sp_defense"])
        self.speed = int(row["speed"])

        # Pre-calculated type effectiveness from CSV (optimization for Type1 * Type2)
        self.resistances = {
            k.replace("against_", ""): float(v)
            for k, v in row.items()
            if k.startswith("against_")
        }

        if available_moves:
            self.moves = available_moves
        else:
            # Fallback move if database has no entries for this Pokemon
            self.moves = [("Struggle", 50, "Physical", "normal")]

        # RFC Abstract: Speed Tie Resolution
        # Random nonce generated at setup to deterministically resolve ties.
        self.nonce = random.randint(0, 1000000)

        # RFC 5.0: Stat Boosts
        # "An object containing the player's allocation of... special attack and special defense uses."
        self.stat_boosts = {"sp_attack": 2, "sp_defense": 2}

    def apply_boost(self, stat_name):
        """RFC 5.0: Consumable resource logic for modifying battle stats."""
        current_amount = self.stat_boosts.get(stat_name, 0)
        if current_amount > 0:
            self.stat_boosts[stat_name] -= 1
            if stat_name == "sp_attack":
                self.sp_attack = int(self.sp_attack * 1.5)
                print(f"[Boost] Special Attack rose to {self.sp_attack}!")
            elif stat_name == "sp_defense":
                self.sp_defense = int(self.sp_defense * 1.5)
                print(f"[Boost] Special Defense rose to {self.sp_defense}!")
            return True
        return False

    def to_dict(self):
        """Serializes Pokemon data for BATTLE_SETUP (RFC 4.2)."""
        return {
            "name": self.name,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "type1": self.type1,
            "type2": self.type2,
            "stats": {
                "attack": self.attack,
                "defense": self.defense,
                "sp_attack": self.sp_attack,
                "sp_defense": self.sp_defense,
                "speed": self.speed,
            },
            "resistances": self.resistances,
            "nonce": self.nonce,
            "stat_boosts": self.stat_boosts,
        }


def get_effectiveness_text(multiplier):
    """Returns flavor text based on the type effectiveness multiplier."""
    if multiplier > 1.0:
        return "It was super effective!"
    elif multiplier == 0:
        return "It had no effect..."
    elif multiplier < 1.0:
        return "It was not very effective..."
    else:
        return ""


def calculate_damage(
    attacker, defender_dict, move_name, move_power, move_category, move_type
):
    """
    RFC 5.0: Damage Calculation Formula.
    Damage = BasePower * (AttackerStat / DefenderStat) * Type1Eff * Type2Eff
    """
    cat = move_category.lower()

    # RFC 5.0: Select stats based on Physical/Special category
    if cat == "physical":
        atk = attacker.attack
        defn = defender_dict["stats"]["defense"]
        stat_label = "Atk/Def"
    else:
        atk = attacker.sp_attack
        defn = defender_dict["stats"]["sp_defense"]
        stat_label = "SpAtk/SpDef"

    # RFC 5.0: Type Effectiveness (Product of Type1 and Type2 effectiveness)
    # Note: 'resistances' from CSV already contains the pre-calculated product.
    effectiveness = defender_dict["resistances"].get(move_type.lower(), 1.0)

    # The Core Formula
    ratio = atk / defn
    raw_damage = float(move_power) * ratio * effectiveness
    final_damage = math.ceil(raw_damage)

    print(f"\n   [Math] Move: {move_name} ({cat})")
    print(f"   [Math] Stats ({stat_label}): {atk} / {defn} = {ratio:.2f}")
    print(
        f"   [Math] Formula: {move_power} * {ratio:.2f} * {effectiveness} = {raw_damage:.2f}"
    )
    print(f"   [Math] Final Damage: {final_damage}")

    return final_damage, effectiveness


def load_moves_map(filename="assets/moves.csv"):
    """Parses moves.csv to create a mapping of Pokemon -> List of Moves."""
    moves_map = {}
    try:
        with open(filename, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                m_name = row["move_name"]
                m_type = row["type"]
                m_power = int(row["base_power"])
                m_cat = row["damage_category"]
                learners = row["learns_by_pokemon"].split(";")
                move_tuple = (m_name, m_power, m_cat, m_type)
                for pokemon in learners:
                    p_name = pokemon.strip().lower()
                    if p_name not in moves_map:
                        moves_map[p_name] = []
                    moves_map[p_name].append(move_tuple)
    except FileNotFoundError:
        print(f"[Error] Could not find {filename}")
        pass
    return moves_map


def load_pokemon_db(poke_file="assets/pokemon.csv", moves_file="assets/moves.csv"):
    """Loads all Pokemon data and links moves to them."""
    moves_map = load_moves_map(moves_file)
    db = {}
    try:
        with open(poke_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                p_name = row["name"].lower()
                p_moves = moves_map.get(p_name, [])
                p = Pokemon(row, p_moves)
                db[p_name] = p
    except FileNotFoundError:
        print(f"[Error] Could not find {poke_file}")
    return db
