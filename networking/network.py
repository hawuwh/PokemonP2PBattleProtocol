import socket
import threading
import time

# Use relative import for package internal reference
from .protocol import PokeProtocol

# RFC 3.2: Reliability Layer Configuration
# "The recommended timeout is 500 milliseconds, and the recommended maximum number of retries is 3."
RETRY_DELAY = 0.5  # 500ms timeout
MAX_RETRIES = 3  # Retry limit

# RFC Abstract: Sticker Support
# Buffer size increased to ~64KB to accommodate Base64 encoded images.
BUFFER_SIZE = 65535

# RFC Abstract: Broadcast Mode
# Dedicated port for LAN discovery packets.
DISCOVERY_PORT = 8890


class ReliableTransport:
    """
    Implements a reliable messaging layer over UDP as specified in RFC Section 3.
    Features include Sequence Numbers, Acknowledgements (ACKs), and Retransmission.
    """

    def __init__(self, port=0, verbose=False):
        # RFC Abstract: Transport Layer must use UDP.
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Allow reusing the address to prevent 'Address already in use' errors
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self.sock.bind(("0.0.0.0", port))
        except OSError:
            # Fallback to a random port if the specific one is taken
            self.sock.bind(("0.0.0.0", 0))

        self.port = self.sock.getsockname()[1]
        self.peer_addr = None
        self.verbose = verbose
        self.running = True

        # RFC 3.2: Sequence Numbering
        # "Every non-ACK message MUST include a sequence_number."
        self.seq_num = 0  # Monotonic sequence number for outgoing messages

        # Buffer for tracking unacknowledged messages for retransmission
        self.unacked_msgs = {}
        self.lock = threading.Lock()  # Thread safety for message buffer
        self.on_message = None  # Callback function for received messages

        # Background threads for listening and reliability management
        self.listener = threading.Thread(target=self._listen_loop, daemon=True)
        self.retry_worker = threading.Thread(target=self._retry_loop, daemon=True)

    def start(self, on_message_callback):
        """Starts the network threads."""
        self.on_message = on_message_callback
        self.listener.start()
        self.retry_worker.start()
        print(f"[Net] Listening on port {self.port}")

    def set_peer(self, ip, port):
        """Sets the target address for outgoing messages."""
        self.peer_addr = (ip, int(port))

    def send_reliable(self, msg_type, payload):
        """
        Sends a message with reliability guarantees (RFC 3.2).
        Assigns a sequence number and stores it for potential retransmission.
        """
        with self.lock:
            seq = self.seq_num
            self.seq_num += 1

            # RFC 3.2: Inject sequence number into payload for tracking
            payload["sequence_number"] = seq

            data = PokeProtocol.serialize(msg_type, payload)

            if len(data) > BUFFER_SIZE:
                print(
                    f"[Error] Message too large ({len(data)} bytes)! Max is {BUFFER_SIZE}."
                )
                return

            # Buffer the message for the retry loop
            self.unacked_msgs[seq] = {
                "data": data,
                "time": time.time(),
                "retries": 0,
                "type": msg_type,
            }
            self._send_raw(data)
            if self.verbose:
                print(f"[Sent] {msg_type} (Seq: {seq})")

    def send_ack(self, seq_to_ack, addr):
        """
        RFC 3.2: Acknowledgements.
        "Upon receiving a message... the peer MUST send an ACK message."
        """
        ack_payload = {"sequence_number": seq_to_ack}
        data = PokeProtocol.serialize("ACK", ack_payload)
        self.sock.sendto(data, addr)

    def _send_raw(self, data):
        """Helper to send bytes to the peer if address is set."""
        if self.peer_addr:
            self.sock.sendto(data, self.peer_addr)

    def _listen_loop(self):
        """Background thread loop for receiving UDP packets."""
        while self.running:
            try:
                data, addr = self.sock.recvfrom(BUFFER_SIZE)
                msg_type, payload = PokeProtocol.deserialize(data)

                if not msg_type:
                    continue

                # RFC 3.2: Handling Incoming ACKs
                if msg_type == "ACK":
                    seq_acked = int(payload.get("sequence_number", -1))
                    with self.lock:
                        if seq_acked in self.unacked_msgs:
                            if self.verbose:
                                print(f"[Ack] Received ACK for Seq {seq_acked}")
                            # Remove from buffer -> Stop retransmitting
                            del self.unacked_msgs[seq_acked]
                    continue

                # RFC 3.2: Handling Incoming Reliable Messages
                # Automatically respond with an ACK before processing
                sender_seq = payload.get("sequence_number")
                if sender_seq is not None:
                    self.send_ack(sender_seq, addr)

                # Pass valid game messages up to the main application
                if self.on_message:
                    self.on_message(msg_type, payload, addr)

            except Exception as e:
                if self.running:
                    print(f"[Net Error] {e}")

    def _retry_loop(self):
        """
        RFC 3.2: Retransmission Logic.
        Checks for timeouts (500ms) and resends messages up to 3 times.
        """
        while self.running:
            time.sleep(0.1)  # Check every 100ms
            with self.lock:
                now = time.time()
                # Iterate over copy to allow safe deletion
                for seq, info in list(self.unacked_msgs.items()):
                    if now - info["time"] > RETRY_DELAY:
                        if info["retries"] < MAX_RETRIES:
                            print(f"[Retry] Resending {info['type']} (Seq {seq})...")
                            info["retries"] += 1
                            info["time"] = now
                            self._send_raw(info["data"])
                        else:
                            # RFC 3.2: "If max retries reached... assume connection lost."
                            print(
                                f"[Timeout] Failed to deliver {info['type']} (Seq {seq})"
                            )
                            del self.unacked_msgs[seq]


class DiscoveryManager:
    """
    Implements RFC Abstract: Broadcast Mode.
    Allows peers to announce presence on the local network.
    """

    def __init__(self, game_port=8888):
        self.game_port = game_port
        self.broadcasting = False
        self.broadcast_thread = None

    def start_broadcast(self):
        """Starts announcing presence on the LAN."""
        self.broadcasting = True
        self.broadcast_thread = threading.Thread(
            target=self._broadcast_loop, daemon=True
        )
        self.broadcast_thread.start()

    def stop_broadcast(self):
        self.broadcasting = False

    def _broadcast_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        msg = PokeProtocol.serialize("BROADCAST_ANNOUNCE", {"port": self.game_port})

        print("[Discovery] Broadcasting game availability...")
        while self.broadcasting:
            try:
                sock.sendto(msg, ("<broadcast>", DISCOVERY_PORT))
                time.sleep(2)  # Announce presence every 2 seconds
            except Exception as e:
                print(f"[Discovery Error] {e}")
                time.sleep(5)

    @staticmethod
    def scan_for_games(timeout=5):
        """Listens for Broadcast packets to find available hosts."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", DISCOVERY_PORT))
        except OSError:
            print("[Discovery] Port busy. Cannot scan.")
            return []

        sock.settimeout(1.0)
        found_hosts = {}

        start_time = time.time()
        print(f"[Discovery] Scanning for {timeout} seconds...")

        while time.time() - start_time < timeout:
            try:
                data, addr = sock.recvfrom(1024)
                msg_type, payload = PokeProtocol.deserialize(data)

                if msg_type == "BROADCAST_ANNOUNCE":
                    host_port = payload.get("port", 8888)
                    if addr[0] not in found_hosts:
                        found_hosts[addr[0]] = host_port
                        print(f"  > Found Game at {addr[0]}:{host_port}")
            except socket.timeout:
                continue
            except Exception:
                pass

        sock.close()
        return found_hosts
