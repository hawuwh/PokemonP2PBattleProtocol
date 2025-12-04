

# P2P Pokémon Battle Protocol (PokeProtocol) 

This project implements the PokeProtocol (RFC Specification) using Python and UDP sockets. It creates a robust, turn-based Peer-to-Peer (P2P) battle system with a custom reliability layer, broadcast discovery, and asynchronous chat functionality. 

[RFC Protocol Specifications](https://docs.google.com/document/d/1rmI5kONoxxxjrNkilspUStmXXFjtcSW39dvrd6p7Sxg/edit?tab=t.0)

## Features Implemented

1. **Networking & Reliability**
    - Pure UDP
    - Implements a custom TCP-like layer over UDP using:
    - Broadcast Discovery

2. **Game Logic (RFC Compliant)**
    - Strict turn-based flow (`LOBBY` -> `SETUP` -> `BATTLE`)
    - Every turn follows the strict RFC sequence:
        - Attacker declares move
        - Defender acknowledges
        - Attacker calculates damage/crit/effectiveness
        - Defender applies damage
    - Damage calculation implements the specific formula: `Power * (Atk/Def) * TypeEffectiveness`.
    - Consumable items (X Special Attack/Defense) implemented as per RFC.

3. **Chat & Stickers**
    - Chat operates on a separate thread, allowing users to chat while waiting for opponent moves.
    - Supports sending image files converted to Base64 strings.


## Project Structure
- `main.py`: The entry point. Handles the UI, Game State Machine, and Input threading.

- `network.py`: Handles the raw UDP sockets, Reliability Layer (ACKs/Retries), and Broadcast Discovery.

- `protocol.py`: Serializes and deserializes messages into the RFC key: value format.

- `game_data.py`: Parses pokemon.csv and moves.csv. Handles stats, type effectiveness, and damage math.

- `chat_utils.py`: Handles Base64 encoding/decoding for stickers.

## Usage
### Prerequisites
- Python 3.8+
- No external `pip` packages required (only uses standard library)

### Instructions
1. Clone this repository.
2. Ensure `pokemon.csv` and `moves.csv` are in the same folder.
3. Run the game:

    ```
    python3 main.py
    ```

## Credits
### Contribution
This project was created with the help of Gemini AI, which assisted in debugging, troubleshooting, and implementing the game logic.

  -----------------------------------------------------------------------
  Member             Key Responsibilities
  ------------------ ----------------------------------------------------
  **Caesar, Kyeeona  • Generated the initial project code template in
  Nickolae V.**      Python`<br>`{=html}• Implemented the **handshaking
                     process** and role assignment (Host goes first,
                     Joiner second)`<br>`{=html}• Built the
                     **build_statements** for proper message
                     display`<br>`{=html}• Implemented the **chat
                     messaging system**`<br>`{=html}• Established
                     **spectator mode**`<br>`{=html}• Performed extensive
                     **testing** and **general Python code
                     modifications**

  **Cruz, Richman    • Loaded and parsed **CSV data** in
  Justin**           Python`<br>`{=html}• Implemented all **18 Pokémon
                     type matchups** in Python data
                     structures`<br>`{=html}• Developed the **type
                     effectiveness mechanics**`<br>`{=html}• Conducted
                     **late-stage testing** and fixed remaining
                     inconsistencies

  **Paclijan, Howard • Implemented the **reliability layer** (ACK sending
  Gabriel**          and sequence verification)`<br>`{=html}• Developed
                     **message parsing** for attack, defense, and
                     calculation reports`<br>`{=html}• Implemented
                     **deterministic damage calculation** using shared
                     seeds, stats, and move data`<br>`{=html}• Built a
                     **Linear Congruential Generator (LCG)** for
                     synchronized randomness`<br>`{=html}• Designed the
                     **discrepancy resolution protocol** to detect and
                     correct mismatches between peers
  -----------------------------------------------------------------------

### Sticker preset
Credits to [mira x33](https://emoji.gg/pack/53103-pikapika-pokemon-emojis#) for the stickers
