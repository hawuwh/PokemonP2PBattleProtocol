import queue
import random
import sys
import threading
import time

from chat_utils import ChatManager
from game_data import calculate_damage, get_effectiveness_text, load_pokemon_db
from network import ReliableTransport


# --- NEW: Threaded Input Handler ---
class InputListener:
    """
    Reads user input in a background thread so the main game loop
    doesn't freeze while waiting for 'input()'.
    """

    def __init__(self):
        self.input_queue = queue.Queue()
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self):
        while self.running:
            try:
                # This blocks this specific thread, but not the main game
                text = input()
                self.input_queue.put(text)
            except EOFError:
                break
            except Exception:
                break

    def get_input(self):
        """Non-blocking check for new input"""
        try:
            return self.input_queue.get_nowait()
        except queue.Empty:
            return None


class P2PGame:
    def __init__(self):
        self.net = None
        self.pokemon_db = load_pokemon_db()
        self.running = True

        # Initialize Async Input
        self.input_handler = InputListener()

        self.my_pokemon = None
        self.opp_pokemon = None
        self.state = "LOBBY"
        self.turn_owner = None

        self.battle_queue = queue.Queue()
        self.pending_damage = 0

    def start(self):
        print("Select Role (host/join):")
        # We can use blocking input here since game hasn't started
        while True:
            role_in = self.input_handler.get_input()
            if role_in:
                role = role_in.strip().lower()
                break
            time.sleep(0.1)

        if role == "host":
            print(f"[Host] Starting on port 8888...")
            self.net = ReliableTransport(port=8888, verbose=True)
            self.net.start(self.handle_message)
        elif role == "join":
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
            self.net.send_reliable("HANDSHAKE_REQUEST", {})
        else:
            print("Invalid role")
            return

        print(
            "\n[Tip] You can chat anytime by typing '/chat <msg>' or '/sticker <filename>'"
        )

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

    def handle_chat_input(self, user_input):
        """Returns True if input was a chat command, False if battle command."""
        if not user_input:
            return False

        if user_input.startswith("/chat "):
            msg = user_input[6:]
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
        print("=" * 34)

    def perform_setup(self):
        if self.my_pokemon is not None:
            return

        print("\n--- Choose your Pokemon ---")
        print("Enter Pokemon Name (e.g. Charmander): ")

        while True:
            # Non-blocking wait for input
            user_in = self.input_handler.get_input()
            if user_in:
                if self.handle_chat_input(user_in):
                    continue

                name = user_in.strip().lower()
                if name in self.pokemon_db:
                    self.my_pokemon = self.pokemon_db[name]
                    self.print_stats(self.my_pokemon, is_mine=True)
                    print(f"Moves: {[m[0] for m in self.my_pokemon.moves]}")

                    self.net.send_reliable("BATTLE_SETUP", self.my_pokemon.to_dict())
                    print("\nWaiting for opponent...")
                    break
                else:
                    print("Invalid name. Try again.")

            time.sleep(0.1)

        while self.opp_pokemon is None and self.running:
            self.check_input_queue_for_chat()  # Allow chat while waiting
            time.sleep(0.1)

        if self.running:
            self.print_stats(self.opp_pokemon, is_mine=False)
            print(
                f"\n[Battle Ready] {self.my_pokemon.name} VS {self.opp_pokemon['name']}"
            )
            self.determine_first_turn()
            self.state = "BATTLE"

    def determine_first_turn(self):
        my_speed = self.my_pokemon.speed
        opp_speed = self.opp_pokemon["stats"]["speed"]
        my_nonce = self.my_pokemon.nonce
        opp_nonce = self.opp_pokemon.get("nonce", 0)

        if my_speed > opp_speed:
            self.turn_owner = "me"
        elif opp_speed > my_speed:
            self.turn_owner = "opp"
        else:
            if my_nonce > opp_nonce:
                self.turn_owner = "me"
            else:
                self.turn_owner = "opp"

        print(
            f"[System] Result -> {'My' if self.turn_owner == 'me' else 'Opponent'} Turn"
        )

    def check_input_queue_for_chat(self):
        """Helper to process any pending chats in the queue without blocking."""
        while True:
            user_in = self.input_handler.get_input()
            if user_in:
                if not self.handle_chat_input(user_in):
                    print(f"[System] Not your turn! You can only chat.")
            else:
                break

    def check_game_over(self):
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
        print(f"\n[{self.my_pokemon.name} (HP: {self.my_pokemon.hp})] Select Move:")
        for i, move in enumerate(self.my_pokemon.moves):
            print(f"{i + 1}. {move[0]} (Pwr: {move[1]}, Type: {move[2]})")

        print("Enter Move Number > ")

        while self.running:
            user_in = self.input_handler.get_input()

            if user_in:
                if self.handle_chat_input(user_in):
                    continue

                try:
                    choice = int(user_in) - 1
                    if 0 <= choice < len(self.my_pokemon.moves):
                        move = self.my_pokemon.moves[choice]
                        self.execute_attack_sequence(move)
                        return
                    else:
                        print("Invalid selection.")
                except ValueError:
                    pass
            time.sleep(0.1)

    def execute_attack_sequence(self, move):
        move_name = move[0]

        # --- RFC Step 1: ATTACK_ANNOUNCE ---
        print(f"[RFC] Sending ATTACK_ANNOUNCE: {move_name}...")
        self.net.send_reliable(
            "ATTACK_ANNOUNCE",
            {
                "move_name": move_name,
                "base_power": move[1],
                "damage_category": move[2],
                "move_type": move[3],
            },
        )

        # --- RFC Step 2: Wait for DEFENSE ---
        msg_type, payload = self.wait_for_packet(["DEFENSE_ANNOUNCE"])

        # --- RFC Step 3: CALCULATION ---
        dmg, eff = calculate_damage(
            self.my_pokemon, self.opp_pokemon, move_name, move[1], move[2], move[3]
        )
        self.pending_damage = dmg

        new_opp_hp = self.opp_pokemon["hp"] - dmg
        eff_text = get_effectiveness_text(eff)
        status_msg = f"{self.my_pokemon.name} used {move_name}! {eff_text}"

        print(f"[RFC] Sending CALCULATION_REPORT ({dmg} dmg)...")

        report_payload = {
            "attacker": self.my_pokemon.name,
            "move_used": move_name,
            "remaining_health": self.my_pokemon.hp,
            "damage_dealt": dmg,
            "defender_hp_remaining": new_opp_hp,
            "status_message": status_msg,
        }

        self.net.send_reliable("CALCULATION_REPORT", report_payload)

        # --- RFC Step 4: Wait for CONFIRM ---
        msg_type, payload = self.wait_for_packet(["CALCULATION_CONFIRM"])

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

        # --- RFC Step 1: Wait for ATTACK ---
        msg_type, payload = self.wait_for_packet(["ATTACK_ANNOUNCE", "GAME_OVER"])
        if msg_type == "GAME_OVER":
            self.check_game_over()
            return

        m_name = payload["move_name"]
        print(f"[RFC] Opponent declared attack: {m_name}")

        # --- RFC Step 2: Send DEFENSE ---
        self.net.send_reliable(
            "DEFENSE_ANNOUNCE", {"hp": self.my_pokemon.hp, "status": "ready"}
        )

        # --- RFC Step 3: Wait for REPORT ---
        msg_type, payload = self.wait_for_packet(["CALCULATION_REPORT"])

        damage = int(payload["damage_dealt"])
        status_msg = payload.get("status_message", "")

        print(f"\n**********************************************")
        print(f"BATTLE EVENT: {status_msg}")
        print(f"**********************************************\n")

        self.pending_damage = damage

        # --- RFC Step 4: Send CONFIRM ---
        self.net.send_reliable("CALCULATION_CONFIRM", {})

        print(f"[Result] You took {self.pending_damage} damage!")
        self.my_pokemon.hp -= self.pending_damage
        print(f"[Status] HP: {self.my_pokemon.hp}/{self.my_pokemon.max_hp}")

        if self.check_game_over():
            return

        self.turn_owner = "me"

    def wait_for_packet(self, expected_types):
        while self.running:
            # 1. Check if user typed a chat message
            user_in = self.input_handler.get_input()
            if user_in:
                if not self.handle_chat_input(user_in):
                    # If they typed a move number during opponent turn, ignore it
                    pass

            # 2. Check Network Queue
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
    game.start()
