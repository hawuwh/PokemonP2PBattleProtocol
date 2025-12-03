import json


class PokeProtocol:
    @staticmethod
    def serialize(message_type, payload=None):
        """
        Converts a message type and a payload dictionary into the RFC format.
        Format:
        message_type: TYPE
        key1: value1
        """
        if payload is None:
            payload = {}

        lines = [f"message_type: {message_type}"]

        for key, value in payload.items():
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            lines.append(f"{key}: {value}")

        message_str = "\n".join(lines)
        return message_str.encode("utf-8")

    @staticmethod
    def deserialize(data_bytes):
        """
        Parses raw bytes into a dictionary.
        Returns (message_type, full_data_dict)
        """
        try:
            text = data_bytes.decode("utf-8")
            lines = text.split("\n")
            data = {}

            for line in lines:
                if ": " in line:
                    key, value = line.split(": ", 1)

                    # 1. Try processing as JSON (for dicts/lists like 'stats')
                    if value.startswith("{") or value.startswith("["):
                        try:
                            value = json.loads(value)
                        except json.JSONDecodeError:
                            pass

                    # 2. Try processing as Integer
                    else:
                        try:
                            value = int(value)
                        except ValueError:
                            # 3. Try processing as Float
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
