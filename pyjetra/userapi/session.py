import json
import os
import hashlib

class JetraSession:
    def __init__(self, session_file="jetra_session.json"):
        self.session_file = session_file
        self.dc_id = 2
        self.server_address = "web.jetra.ir"
        self.port = 443
        self.auth_key = None
        self.auth_key_id = None
        self.server_salt = None
        self.session_id = None
        self.user_id = None
        self.access_hash = None
        self.load()

    def set_auth_key(self, auth_key_bytes):
        self.auth_key = auth_key_bytes
        self.auth_key_id = hashlib.sha1(auth_key_bytes).digest()[-8:]
        self.save()

    def save(self):
        data = {
            "dc_id": self.dc_id,
            "server_address": self.server_address,
            "port": self.port,
            "auth_key": self.auth_key.hex() if self.auth_key else None,
            "auth_key_id": self.auth_key_id.hex() if self.auth_key_id else None,
            "server_salt": self.server_salt.hex() if self.server_salt else None,
            "session_id": self.session_id.hex() if self.session_id else None,
            "user_id": self.user_id,
            "access_hash": self.access_hash,
        }
        with open(self.session_file, "w") as f:
            json.dump(data, f, indent=4)
        print(f"Session saved to {self.session_file}")

    def load(self):
        if not os.path.exists(self.session_file):
            print("No session file found. Creating new session...")
            self.session_id = os.urandom(8)
            self.save()
            return

        try:
            with open(self.session_file, "r") as f:
                data = json.load(f)
            
            self.dc_id = data.get("dc_id", 2)
            self.server_address = data.get("server_address", "web.jetra.ir")
            self.port = data.get("port", 443)
            self.user_id = data.get("user_id")
            self.access_hash = data.get("access_hash")
            
            if data.get("auth_key"):
                self.auth_key = bytes.fromhex(data["auth_key"])
            if data.get("auth_key_id"):
                self.auth_key_id = bytes.fromhex(data["auth_key_id"])
            if data.get("server_salt"):
                self.server_salt = bytes.fromhex(data["server_salt"])
            if data.get("session_id"):
                self.session_id = bytes.fromhex(data["session_id"])
            else:
                self.session_id = os.urandom(8)
                
            print(f"Session loaded from {self.session_file}")
        except Exception as e:
            print(f"Error loading session: {e}. Creating new one...")
            self.session_id = os.urandom(8)
            self.save()

    def is_authorized(self):
        return self.auth_key is not None and self.user_id is not None
