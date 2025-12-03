import json


class PokeProtocol:
    """
    Handles the serialization and deserialization of messages according to the RFC.
    The protocol uses a simple newline-delimited key:value text format.
    """

    @staticmethod
    def serialize(message_type, payload=None):
        """
        Converts a message type and payload dictionary into bytes.
        Format follows the RFC specification:
        message_type: TYPE
        key1: value1
        key2: value2
        """
        if payload is None:
            payload = {}

        # Every message starts with the message_type header
        lines = [f"message_type: {message_type}"]

        for key, value in payload.items():
            # complex objects like lists or dicts are JSON-encoded strings within the protocol
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            lines.append(f"{key}: {value}")

        message_str = "\n".join(lines)
        return message_str.encode("utf-8")

    @staticmethod
    def deserialize(data_bytes):
        """
        Parses raw bytes received from the network into a dictionary.
        Returns a tuple: (message_type, full_data_dict)
        """
        try:
            text = data_bytes.decode("utf-8")
            lines = text.split("\n")
            data = {}

            for line in lines:
                # Only process lines that follow the key: value structure
                if ": " in line:
                    key, value = line.split(": ", 1)

                    # Attempt to parse nested JSON structures (e.g., stats, arrays)
                    if value.startswith("{") or value.startswith("["):
                        try:
                            value = json.loads(value)
                        except json.JSONDecodeError:
                            pass  # If parsing fails, treat it as a raw string

                    # Attempt to convert numeric strings to integers or floats
                    else:
                        try:
                            value = int(value)
                        except ValueError:
                            try:
                                value = float(value)
                            except ValueError:
                                pass  # Keep as string if it's text

                    data[key] = value

            # Ensure the message has the required type field
            if "message_type" not in data:
                return None, {}

            return data["message_type"], data

        except Exception as e:
            # Catch parsing errors to prevent crashing on malformed packets
            print(f"[Protocol Error] Failed to parse: {e}")
            return None, {}
