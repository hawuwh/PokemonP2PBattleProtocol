import json


class PokeProtocol:
    """
    RFC 4.0: Message Format Implementation.
    Handles serialization/deserialization of the key-value pair text format.
    """

    @staticmethod
    def serialize(message_type, payload=None):
        """
        RFC 4.0: "All messages are plain text with newline-separated key: value pairs."
        """
        if payload is None:
            payload = {}

        # Header field required by protocol
        lines = [f"message_type: {message_type}"]

        for key, value in payload.items():
            # Complex structures (arrays/objects) are serialized as JSON strings
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            lines.append(f"{key}: {value}")

        message_str = "\n".join(lines)
        return message_str.encode("utf-8")

    @staticmethod
    def deserialize(data_bytes):
        """
        Parses the raw bytes into a python dictionary.
        Handles type conversion for integers (e.g. HP, Damage) and JSON objects (e.g. Stats).
        """
        try:
            text = data_bytes.decode("utf-8")
            lines = text.split("\n")
            data = {}

            for line in lines:
                if ": " in line:
                    key, value = line.split(": ", 1)

                    # Heuristic parsing for types
                    if value.startswith("{") or value.startswith("["):
                        try:
                            value = json.loads(value)
                        except json.JSONDecodeError:
                            pass
                    else:
                        try:
                            value = int(value)
                        except ValueError:
                            try:
                                value = float(value)
                            except ValueError:
                                pass

                    data[key] = value

            if "message_type" not in data:
                return None, {}

            return data["message_type"], data

        except Exception as e:
            print(f"[Protocol Error] Failed to parse: {e}")
            return None, {}
