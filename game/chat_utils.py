import base64
import os
import time


class ChatManager:
    """
    Handles functionality for RFC Section 6.0: Chat & Stickers.
    Specifically deals with the Base64 encoding requirement for images.
    """

    @staticmethod
    def encode_image(filepath):
        """
        RFC 6.0: "Stickers are sent as Base64 encoded strings."
        Reads a local file and converts it for transmission.
        """
        try:
            with open(filepath, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
                return encoded_string
        except FileNotFoundError:
            print(f"[Chat Error] File '{filepath}' not found.")
            return None
        except Exception as e:
            print(f"[Chat Error] Could not encode image: {e}")
            return None

    @staticmethod
    def save_sticker(base64_string, sender_name):
        """
        Decodes incoming sticker data and saves to disk.
        """
        try:
            timestamp = int(time.time())
            filename = f"sticker_{sender_name}_{timestamp}.png"

            with open(filename, "wb") as fh:
                fh.write(base64.b64decode(base64_string))

            return filename
        except Exception as e:
            print(f"[Chat Error] Could not save sticker: {e}")
            return None
