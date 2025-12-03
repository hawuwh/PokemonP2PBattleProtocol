import socket
import threading
import time

from protocol import PokeProtocol

# Constants
RETRY_DELAY = 0.5
MAX_RETRIES = 3
# UPDATED: Increased to 65535 to support small images/stickers
BUFFER_SIZE = 65535


class ReliableTransport:
    def __init__(self, port=0, verbose=False):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.sock.bind(("0.0.0.0", port))
        except OSError:
            self.sock.bind(("0.0.0.0", 0))

        self.port = self.sock.getsockname()[1]
        self.peer_addr = None
        self.verbose = verbose
        self.running = True

        self.seq_num = 0
        self.unacked_msgs = {}
        self.lock = threading.Lock()
        self.on_message = None

        self.listener = threading.Thread(target=self._listen_loop, daemon=True)
        self.retry_worker = threading.Thread(target=self._retry_loop, daemon=True)

    def start(self, on_message_callback):
        self.on_message = on_message_callback
        self.listener.start()
        self.retry_worker.start()
        print(f"[Net] Listening on port {self.port}")

    def set_peer(self, ip, port):
        self.peer_addr = (ip, int(port))

    def send_reliable(self, msg_type, payload):
        with self.lock:
            seq = self.seq_num
            self.seq_num += 1

            payload["sequence_number"] = seq

            data = PokeProtocol.serialize(msg_type, payload)

            # Check size before sending
            if len(data) > BUFFER_SIZE:
                print(
                    f"[Error] Message too large ({len(data)} bytes)! Max is {BUFFER_SIZE}."
                )
                return

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
        ack_payload = {"sequence_number": seq_to_ack}
        data = PokeProtocol.serialize("ACK", ack_payload)
        self.sock.sendto(data, addr)

    def _send_raw(self, data):
        if self.peer_addr:
            self.sock.sendto(data, self.peer_addr)

    def _listen_loop(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(BUFFER_SIZE)
                msg_type, payload = PokeProtocol.deserialize(data)

                if not msg_type:
                    continue

                if msg_type == "ACK":
                    seq_acked = int(payload.get("sequence_number", -1))
                    with self.lock:
                        if seq_acked in self.unacked_msgs:
                            if self.verbose:
                                print(f"[Ack] Received ACK for Seq {seq_acked}")
                            del self.unacked_msgs[seq_acked]
                    continue

                sender_seq = payload.get("sequence_number")
                if sender_seq is not None:
                    self.send_ack(sender_seq, addr)

                if self.on_message:
                    self.on_message(msg_type, payload, addr)

            except Exception as e:
                if self.running:
                    print(f"[Net Error] {e}")

    def _retry_loop(self):
        while self.running:
            time.sleep(0.1)
            with self.lock:
                now = time.time()
                for seq, info in list(self.unacked_msgs.items()):
                    if now - info["time"] > RETRY_DELAY:
                        if info["retries"] < MAX_RETRIES:
                            print(f"[Retry] Resending {info['type']} (Seq {seq})...")
                            info["retries"] += 1
                            info["time"] = now
                            self._send_raw(info["data"])
                        else:
                            print(
                                f"[Timeout] Failed to deliver {info['type']} (Seq {seq})"
                            )
                            del self.unacked_msgs[seq]
