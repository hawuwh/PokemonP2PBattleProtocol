import queue
import random
import sys
import threading
import time

from game.chat_utils import ChatManager
from game.game_data import calculate_damage, get_effectiveness_text, load_pokemon_db

# Import project modules
from networking.network import DiscoveryManager, ReliableTransport


class InputListener:
    """Helper class for non-blocking console input to allow Async Chat (RFC 6.0)."""

    def __init__(self):
        self.input_queue = queue.Queue()
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self):
        while self.running:
            try:
                # This blocks waiting for input, but since it's a daemon thread,
                # it won't prevent the main program from exiting if we let it.
                text = input()
                self.input_queue.put(text)
            except EOFError:
                break
            except Exception:
                break

    def get_input(self):
        try:
            return self.input_queue.get_nowait()
        except queue.Empty:
            return None


class P2PGame:
    """
    Main State Machine Controller (RFC Abstract).
    Manages transitions: LOBBY -> SETUP -> BATTLE -> GAME_OVER.
    """

    def __init__(self):
        self.net = None
        self.pokemon_db = load_pokemon_db()
        self.running = True
        self.input_handler = InputListener()

        self.my_pokemon = None
        self.opp_pokemon = None
        self.state = "LOBBY"
        self.turn_owner = None

        self.battle_queue = queue.Queue()
        self.pending_damage = 0
        self.discovery = DiscoveryManager(game_port=8888)

    def start(self):
        print("\n=== POKE PROTOCOL BATTLE ===")
        print("[1] Host Game (Direct & Broadcast)")
        print("[2] Join Game (Direct IP)")
        print("[3] Scan for Games (Broadcast)")

        while True:
            choice = self.input_handler.get_input()
            if choice:
                choice = choice.strip()
                if choice == "1":
                    self.role_host()
                    break
                elif choice == "2":
                    self.role_join_direct()
                    break
                elif choice == "3":
                    self.role_join_scan()
                    break
                else:
                    print("Invalid choice.")
            time.sleep(0.1)

        print("\n[Tip] Type '/chat <msg>' or '/sticker <file>' anytime.")

        while self.running:
            try:
                if self.state == "LOBBY":
                    time.sleep(1)
                elif self.state == "SETUP":
                    self.perform_setup()
                elif self.state == "BATTLE":
                    self.battle_loop()
            except KeyboardInterrupt:
                break

        if self.net:
            self.net.running = False
        self.discovery.stop_broadcast()

    # --- NEW METHOD: Safe Exit Wait ---
    def wait_for_exit(self):
        """
        Waits for the user to press Enter before closing the window.
        Reuses the existing input thread to avoid race conditions with standard input().
        """
        print("\nPress Enter to exit...")

        # 1. Flush any leftover input (e.g., keys pressed during Game Over screen)
        while self.input_handler.get_input() is not None:
            pass

        # 2. Wait for a fresh keypress
        while True:
            if self.input_handler.get_input() is not None:
                break
            time.sleep(0.1)

    def role_host(self):
        print(f"[Host] Starting on port 8888...")
        self.net = ReliableTransport(port=8888, verbose=True)
        self.net.start(self.handle_message)
        self.discovery.start_broadcast()
        print("[Host] Waiting for players (Broadcasting on LAN)...")

    def role_join_direct(self):
        self.net = ReliableTransport(port=0, verbose=True)
        self.net.start(self.handle_message)
        print("Enter Host IP (127.0.0.1):")
        while True:
            ip_in = self.input_handler.get_input()
            if ip_in is not None:
                ip = ip_in.strip() or "127.0.0.1"
                break
            time.sleep(0.1)
        self.net.set_peer(ip, 8888)
        # RFC 3.1: Connection Establishment (Handshake)
        self.net.send_reliable("HANDSHAKE_REQUEST", {})

    def role_join_scan(self):
        self.net = ReliableTransport(port=0, verbose=True)
        self.net.start(self.handle_message)
        found = self.discovery.scan_for_games()

        if not found:
            print("[Scan] No games found. Defaulting to 127.0.0.1")
            ip = "127.0.0.1"
        else:
            print("\nAvailable Games:")
            ips = list(found.keys())
            for i, ip in enumerate(ips):
                print(f"[{i + 1}] {ip}")
            print("Select Game # > ")
            while True:
                sel = self.input_handler.get_input()
                if sel:
                    try:
                        idx = int(sel) - 1
                        if 0 <= idx < len(ips):
                            ip = ips[idx]
                            break
                        else:
                            print("Invalid number.")
                    except:
                        pass
                time.sleep(0.1)

        self.net.set_peer(ip, 8888)
        # RFC 3.1: Connection Establishment
        self.net.send_reliable("HANDSHAKE_REQUEST", {})

    def handle_chat_input(self, user_input):
        if not user_input:
            return False
        if user_input.startswith("/chat "):
            msg = user_input[6:]
            # RFC 6.0: Chat Message Format
            self.net.send_reliable(
                "CHAT_MESSAGE", {"sender": "Player", "type": "text", "content": msg}
            )
            print(f"[Me]: {msg}")
            return True
        elif user_input.startswith("/sticker "):
            filepath = user_input[9:].strip()
            b64_data = ChatManager.encode_image(filepath)
            if b64_data:
                print(f"[System] Sending sticker ({len(b64_data)} bytes)...")
                self.net.send_reliable(
                    "CHAT_MESSAGE",
                    {"sender": "Player", "type": "sticker", "content": b64_data},
                )
            return True
        return False

    def print_stats(self, p_data, is_mine=False):
        owner = "YOUR POKEMON" if is_mine else "OPPONENT POKEMON"
        if hasattr(p_data, "to_dict"):
            p_data = p_data.to_dict()

        print(f"\n{'=' * 10} {owner} {'=' * 10}")
        print(f"Name:      {p_data['name'].upper()}")
        print(f"HP:        {p_data['hp']} / {p_data['max_hp']}")
        type_str = p_data["type1"]
        if p_data["type2"]:
            type_str += f" / {p_data['type2']}"
        print(f"Type:      {type_str}")
        s = p_data["stats"]
        print(f"Attack:    {s['attack']:<5} Sp. Atk: {s['sp_attack']}")
        print(f"Defense:   {s['defense']:<5} Sp. Def: {s['sp_defense']}")
        print(f"Speed:     {s['speed']}")
        boosts = p_data.get("stat_boosts", {})
        if boosts:
            print(
                f"Boosts:    Sp.Atk ({boosts.get('sp_attack', 0)}) | Sp.Def ({boosts.get('sp_defense', 0)})"
            )
        print("=" * 34)

    def show_pokemon_list(self):
        names = sorted(list(self.pokemon_db.keys()))
        page_size = 20
        total = len(names)
        print(f"\n--- Available Pokemon ({total}) ---")
        for i in range(0, total, page_size):
            chunk = names[i : i + page_size]
            for name in chunk:
                print(f"  {name.title()}")
            if i + page_size < total:
                print(f"\n-- Press ENTER for next page (or type 'q' to stop) --")
                stop_listing = False
                while True:
                    user_in = self.input_handler.get_input()
                    if user_in is not None:
                        if self.handle_chat_input(user_in):
                            continue
                        if user_in.strip().lower() == "q":
                            stop_listing = True
                        break
                    time.sleep(0.1)
                if stop_listing:
                    break
        print("--- End of List ---")
        print("Enter Pokemon Name (or 'list'): ")

    def perform_setup(self):
        if self.my_pokemon is not None:
            return
        self.discovery.stop_broadcast()

        print("\n--- Choose your Pokemon ---")
        print("Enter Pokemon Name (e.g. Charmander) or type 'list': ")
        while True:
            user_in = self.input_handler.get_input()
            if user_in:
                if self.handle_chat_input(user_in):
                    continue
                name = user_in.strip().lower()
                if name == "list":
                    self.show_pokemon_list()
                    continue
                if name in self.pokemon_db:
                    self.my_pokemon = self.pokemon_db[name]
                    self.print_stats(self.my_pokemon, is_mine=True)
                    # RFC 4.2: Battle Setup - Exchange Pokemon Data
                    self.net.send_reliable("BATTLE_SETUP", self.my_pokemon.to_dict())
                    print("\nWaiting for opponent...")
                    break
                else:
                    print("Invalid name. Type 'list' to see options.")
            time.sleep(0.1)

        while self.opp_pokemon is None and self.running:
            self.check_input_queue_for_chat()
            time.sleep(0.1)

        if self.running:
            self.print_stats(self.opp_pokemon, is_mine=False)
            print(
                f"\n[Battle Ready] {self.my_pokemon.name} VS {self.opp_pokemon['name']}"
            )
            self.determine_first_turn()
            self.state = "BATTLE"

    def determine_first_turn(self):
        """
        RFC Abstract: Turn Order Determination.
        Uses Speed stat, then Nonce for tie-breaking.
        """
        my_speed = self.my_pokemon.speed
        opp_speed = self.opp_pokemon["stats"]["speed"]
        my_nonce = self.my_pokemon.nonce
        opp_nonce = self.opp_pokemon.get("nonce", 0)

        if my_speed > opp_speed:
            self.turn_owner = "me"
        elif opp_speed > my_speed:
            self.turn_owner = "opp"
        else:
            self.turn_owner = "me" if my_nonce > opp_nonce else "opp"
        print(
            f"[System] Result -> {'My' if self.turn_owner == 'me' else 'Opponent'} Turn"
        )

    def check_input_queue_for_chat(self):
        while True:
            user_in = self.input_handler.get_input()
            if user_in:
                if not self.handle_chat_input(user_in):
                    print(f"[System] Not your turn!")
            else:
                break

    def check_game_over(self):
        if self.my_pokemon.hp < 0:
            self.my_pokemon.hp = 0
        if self.opp_pokemon["hp"] < 0:
            self.opp_pokemon["hp"] = 0

        if self.my_pokemon.hp <= 0:
            print("\n=== GAME OVER: YOU FAINTED! ===")
            self.net.send_reliable("GAME_OVER", {"winner": self.opp_pokemon["name"]})
            self.running = False
            return True
        if self.opp_pokemon["hp"] <= 0:
            print("\n=== GAME OVER: YOU WON! ===")
            self.running = False
            return True
        return False

    def battle_loop(self):
        if self.state != "BATTLE":
            return
        if self.turn_owner == "me":
            self.play_my_turn()
        else:
            self.play_opp_turn()

    def play_my_turn(self):
        print(f"\n[{self.my_pokemon.name} (HP: {self.my_pokemon.hp})] Select Action:")
        print("[1] Attack")
        print("[2] Use Boost Item")

        while self.running:
            user_in = self.input_handler.get_input()
            if user_in:
                if self.handle_chat_input(user_in):
                    continue
                if user_in.strip() == "1":
                    self.menu_attack()
                    return
                elif user_in.strip() == "2":
                    if self.menu_boost():
                        return
                    else:
                        print("Select Action: [1] Attack, [2] Boost")
            time.sleep(0.1)

    def menu_boost(self):
        print("\nAvailable Boosts:")
        print(
            f"[1] X Special Attack (Left: {self.my_pokemon.stat_boosts['sp_attack']})"
        )
        print(
            f"[2] X Special Defense (Left: {self.my_pokemon.stat_boosts['sp_defense']})"
        )
        print("[3] Cancel")
        while self.running:
            user_in = self.input_handler.get_input()
            if user_in:
                if self.handle_chat_input(user_in):
                    continue
                ch = user_in.strip()
                if ch == "1":
                    if self.my_pokemon.apply_boost("sp_attack"):
                        self.execute_attack_sequence(
                            None, is_boost=True, boost_msg="used X Special Attack!"
                        )
                        return True
                    else:
                        print("No boosts left!")
                elif ch == "2":
                    if self.my_pokemon.apply_boost("sp_defense"):
                        self.execute_attack_sequence(
                            None, is_boost=True, boost_msg="used X Special Defense!"
                        )
                        return True
                    else:
                        print("No boosts left!")
                elif ch == "3":
                    return False
            time.sleep(0.1)

    def menu_attack(self):
        print("Select Move:")
        for i, move in enumerate(self.my_pokemon.moves):
            print(f"{i + 1}. {move[0]} (Pwr: {move[1]}, Type: {move[2]})")
        while self.running:
            user_in = self.input_handler.get_input()
            if user_in:
                if self.handle_chat_input(user_in):
                    continue
                try:
                    choice = int(user_in) - 1
                    if 0 <= choice < len(self.my_pokemon.moves):
                        self.execute_attack_sequence(self.my_pokemon.moves[choice])
                        return
                    else:
                        print("Invalid selection.")
                except ValueError:
                    pass
            time.sleep(0.1)

    def execute_attack_sequence(self, move, is_boost=False, boost_msg=""):
        """
        RFC 4.0: 4-Way Handshake Implementation.
        Sequence: ATTACK -> DEFENSE -> CALCULATION -> CONFIRM.
        """
        move_name = boost_msg if is_boost else move[0]
        power = 0 if is_boost else move[1]
        category = "Status" if is_boost else move[2]
        m_type = "normal" if is_boost else move[3]

        # STEP 1: RFC 4.5 Attack Announce
        print(f"[RFC] Sending ATTACK_ANNOUNCE...")
        self.net.send_reliable(
            "ATTACK_ANNOUNCE",
            {
                "move_name": move_name,
                "base_power": power,
                "damage_category": category,
                "move_type": m_type,
            },
        )

        # STEP 2: RFC 4.6 Defense Announce (Wait)
        self.wait_for_packet(["DEFENSE_ANNOUNCE"])

        # STEP 3: RFC 4.7 Calculation Report
        if is_boost:
            dmg, eff = 0, 1.0
            status_msg = f"{self.my_pokemon.name} {boost_msg}"
        else:
            dmg, eff = calculate_damage(
                self.my_pokemon, self.opp_pokemon, move_name, power, category, m_type
            )
            status_msg = f"{self.my_pokemon.name} used {move_name}! {get_effectiveness_text(eff)}"

        self.pending_damage = dmg
        new_opp_hp = max(0, self.opp_pokemon["hp"] - dmg)

        print(f"[RFC] Sending CALCULATION_REPORT ({dmg} dmg)...")
        self.net.send_reliable(
            "CALCULATION_REPORT",
            {
                "attacker": self.my_pokemon.name,
                "move_used": move_name,
                "remaining_health": self.my_pokemon.hp,
                "damage_dealt": dmg,
                "defender_hp_remaining": new_opp_hp,
                "status_message": status_msg,
            },
        )

        # STEP 4: RFC 4.8 Calculation Confirm (Wait)
        self.wait_for_packet(["CALCULATION_CONFIRM"])

        self.opp_pokemon["hp"] = new_opp_hp
        print(f"[Result] Opponent HP: {self.opp_pokemon['hp']}")

        if self.opp_pokemon["hp"] <= 0:
            print("Opponent fainted. Waiting for result...")
            try:
                m, p = self.battle_queue.get(timeout=3)
                if m == "GAME_OVER":
                    print("\n=== VICTORY! ===")
                    self.running = False
                    return
            except queue.Empty:
                pass
            if self.check_game_over():
                return

        self.turn_owner = "opp"

    def play_opp_turn(self):
        print(f"\n[Opponent Turn] Waiting...")
        # STEP 1: Wait for Attack
        msg_type, payload = self.wait_for_packet(["ATTACK_ANNOUNCE", "GAME_OVER"])
        if msg_type == "GAME_OVER":
            self.check_game_over()
            return
        print(f"[RFC] Opponent declared: {payload['move_name']}")

        # STEP 2: Send Defense
        self.net.send_reliable(
            "DEFENSE_ANNOUNCE", {"hp": self.my_pokemon.hp, "status": "ready"}
        )

        # STEP 3: Wait for Report
        msg_type, payload = self.wait_for_packet(["CALCULATION_REPORT"])
        damage = int(payload["damage_dealt"])
        status_msg = payload.get("status_message", "")
        print(f"\n**********************************************")
        print(f"BATTLE EVENT: {status_msg}")
        print(f"**********************************************\n")

        # STEP 4: Send Confirm
        self.pending_damage = damage
        self.net.send_reliable("CALCULATION_CONFIRM", {})

        print(f"[Result] You took {self.pending_damage} damage!")
        self.my_pokemon.hp = max(0, self.my_pokemon.hp - self.pending_damage)
        print(f"[Status] HP: {self.my_pokemon.hp}/{self.my_pokemon.max_hp}")

        if self.check_game_over():
            return
        self.turn_owner = "me"

    def wait_for_packet(self, expected_types):
        while self.running:
            user_in = self.input_handler.get_input()
            if user_in:
                self.handle_chat_input(user_in)
            try:
                msg_type, payload = self.battle_queue.get(timeout=0.1)
                if msg_type in expected_types:
                    return msg_type, payload
                elif msg_type == "GAME_OVER":
                    self.check_game_over()
                    return "GAME_OVER", {}
            except queue.Empty:
                continue
        return None, None

    def handle_message(self, msg_type, payload, addr):
        # RFC 3.1: 3-Way Handshake
        if msg_type == "HANDSHAKE_REQUEST":
            self.net.set_peer(addr[0], addr[1])
            self.net.send_reliable("HANDSHAKE_RESPONSE", {"seed": 12345})
            self.state = "SETUP"
        elif msg_type == "HANDSHAKE_RESPONSE":
            self.state = "SETUP"
        elif msg_type == "BATTLE_SETUP":
            self.opp_pokemon = payload
        elif msg_type == "CHAT_MESSAGE":
            sender = payload.get("sender", "Peer")
            ctype = payload.get("type", "text")
            content = payload.get("content", "")
            if ctype == "text":
                print(f"\n[CHAT] {sender}: {content}")
            elif ctype == "sticker":
                filename = ChatManager.save_sticker(content, sender)
                print(f"\n[CHAT] {sender} sent a sticker! Saved to {filename}")
        elif msg_type in [
            "ATTACK_ANNOUNCE",
            "DEFENSE_ANNOUNCE",
            "CALCULATION_REPORT",
            "CALCULATION_CONFIRM",
            "GAME_OVER",
        ]:
            self.battle_queue.put((msg_type, payload))


if __name__ == "__main__":
    game = P2PGame()
    try:
        game.start()
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        # Prevent race condition between input thread and input()
        game.wait_for_exit()
