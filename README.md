
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
