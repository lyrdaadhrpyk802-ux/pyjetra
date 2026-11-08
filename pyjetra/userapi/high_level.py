import asyncio
import struct
import gzip
import hashlib
import datetime
import random
import os
import time

from pyjetra.userapi.tl_builder import tl_string
from pyjetra.userapi.schema import METHODS as TL_METHODS, CONSTRUCTORS as TL_CTORS
from pyjetra.userapi.parsers import parse_sent_message, _parse_message_at
from pyjetra.userapi.client import JetraClient as LowLevelClient, wrap_init_connection, aes_ige_decrypt
from pyjetra.userapi.session import JetraSession
from pyjetra.userapi.message import Message, MessageEntity
from pyjetra.userapi.database import Database
from pyjetra.userapi.exceptions import (
    JetraError,
    JetraConnectionError,
    JetraRPCError,
    JetraAuthError
)

INPUT_PEER_USER = 0xDDE8A54C
INPUT_PEER_SELF = 0x7DA07EC9
INPUT_PEER_CHANNEL = 0x27BCBBFC
INPUT_CHANNEL = 0xF35AEC28

PEER_USER = 0x59511722
PEER_CHANNEL = 0xA2A5371E

# --- Additional TL methods (confirmed to exist on Jetra layer 228) ---
READ_HISTORY_ID = 0x0E306D3A
SET_TYPING_ID = 0x58943EE2
UPDATE_PROFILE_ID = 0x78515775
CHECK_USERNAME_ID = 0x2714D86C
GET_FULL_USER_ID = 0xB60F5918
GET_USERS_ID = 0x0D91A548
GET_CONTACTS_ID = 0xC4A353EE
RESOLVE_USERNAME_ID = 0xF93CD45C
GET_HISTORY_ID = 0x4423E6C5
GET_CONFIG_ID = 0xC4F9186B
GET_NEAREST_DC_ID = 0x1FB33026

# --- InputUser constructors ---
INPUT_USER = 0xD8292816
INPUT_USER_SELF = 0xF7C1B13F

# --- SendMessageAction constructors ---
ACTION_TYPING = 0x16BF744E
ACTION_CANCEL = 0xE7C6B8D3

# --- Additional TL methods (batch 2, confirmed to exist) ---
GET_MESSAGES_ID = 0x63C66506
GET_CHANNELS_ID = 0x0A7F6BBB
DELETE_CONTACTS_ID = 0x96A0E00
UNBLOCK_ID = 0xB550D328
UPDATE_STATUS_ID = 0x6628562C
GET_AUTHORIZATIONS_ID = 0xE320C158
RESET_AUTHORIZATION_ID = 0xDF77F3BC
GET_USER_PHOTOS_ID = 0x91CD32A8
GET_EMOJI_KEYWORDS_ID = 0x35A0E062
UPLOAD_MEDIA_ID = 0x519BC2B1

# --- InputChannel / InputUserEmpty ---
INPUT_PEER_USER = 0xDDE8A54C  # re-declared for safety
INPUT_USER_EMPTY = 0xB98886CF

# --- Common TL constructors ---
VECTOR_CTOR = 0x1CB5C415

MSG_CTOR_JETRA = 0x7600B9D3
SERVICE_MSG_CTOR_JETRA = 0x7A800E0A
CHANNEL_CTOR = 0xD49F34C6
USER_CTOR = 0xB1B8CC83

SEND_MESSAGE_ID = 0xFEF48F62
GET_DIALOGS_ID = 0xA0F4CB4F
GET_STATE_ID = 0xEDD4882A
GET_PARTICIPANTS_ID = 0x77CED9D0
GET_FULL_CHANNEL_ID = 0x08736A09
LEAVE_CHANNEL_ID = 0xF836AA95
CONTACTS_SEARCH_ID = 0x11F812D8

RPC_ERROR = 0x2144CA19
GZIP_PACKED = 0x3072CFA1
UPDATES = 0x74AE4240
UPDATE_NEW_MESSAGE = 0x1F2B0AFD
UPDATE_NEW_CHANNEL_MESSAGE = 0x62BA04D9


class JetraClient:
    # Default Jetra web credentials (extracted from web.jetra.ir JS)
    DEFAULT_API_ID = 3893396
    DEFAULT_API_HASH = "acc55ace25b659164ce6a365260b71d7"

    def __init__(self, session_file="jetra_session.json", db_file="jetra_local.db",
                 api_id=None, api_hash=None):
        self._api_id = api_id if api_id is not None else self.DEFAULT_API_ID
        self._api_hash = api_hash if api_hash is not None else self.DEFAULT_API_HASH
        self.session = JetraSession(session_file)
        self.db = Database(db_file)
        self.client = LowLevelClient(session=self.session)

        self._message_handlers = []
        self._ready_handlers = []
        self._is_running = False
        self._listen_task = None
        self._reconnect_delay = 5
        self._max_reconnect_attempts = 10
        self._ready_event = asyncio.Event()

        self._recv_lock = asyncio.Lock()

        client_ref = self.client

        def _patched_pack_msg_id():
            client_ref._msg_counter = getattr(client_ref, '_msg_counter', 0) + 1
            current_time = int(time.time())
            msg_id = (current_time << 32) | (client_ref._msg_counter << 2)
            return struct.pack("<Q", msg_id)

        self.client._pack_msg_id = _patched_pack_msg_id

        original_send_request = self.client.send_request
        client_ref_for_patch = self

        async def _patched_send_request(method_bytes):
            async with client_ref_for_patch._recv_lock:
                return await original_send_request(method_bytes)

        self.client.send_request = _patched_send_request

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

    def on_message(self, func=None, *, peer_type=None, predicate=None):
        """
        Register a message handler.

        Can be used in two ways:

            @client.on_message
            async def handler(message): ...

            @client.on_message(peer_type="user")
            async def handler(message): ...

            @client.on_message(predicate=lambda m: "hi" in m.text)
            async def handler(message): ...

        Args:
            func:       Handler function (used internally when decorator
                        is applied without arguments).
            peer_type:  Optional "user" or "group" filter.
            predicate:  Optional callable(message) -> bool filter.
        """
        def register(fn):
            self._message_handlers.append((fn, peer_type, predicate))
            return fn
        if func is None:
            return register
        return register(func)

    def on_ready(self, func):
        self._ready_handlers.append(func)
        return func

    async def _trigger_message_handlers(self, message):
        for handler, peer_type, predicate in self._message_handlers:
            try:
                if peer_type is not None and message.peer_type != peer_type:
                    continue
                if predicate is not None and not predicate(message):
                    continue
                if asyncio.iscoroutinefunction(handler):
                    await handler(message)
                else:
                    handler(message)
            except Exception as e:
                print(f"Error in message handler: {e}")

    async def _trigger_ready_handlers(self):
        for handler in self._ready_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler()
                else:
                    handler()
            except Exception as e:
                print(f"Error in ready handler: {e}")

    async def start(self, wait_ready=True, timeout=30, require_auth=True):
        """
        Connect and start the client.

        Args:
            wait_ready:    wait until client is fully synced.
            timeout:       seconds to wait for ready state.
            require_auth:  if True (default), raise JetraAuthError
                           when no session is present. Set to False
                           for fresh-login flows (send_code, sign_in).
        """
        if require_auth and not self.session.is_authorized():
            raise JetraAuthError(
                "Not logged in. Please run login.py first, "
                "or call start(require_auth=False) for a fresh login."
            )

        self._is_running = True
        self._listen_task = asyncio.create_task(self._main_loop())

        # Always wait for the ready event (connect complete), even if
        # wait_ready=False. The difference is: when wait_ready=False, we
        # skip the requirement that auth is done, but we still need the
        # transport to be up.
        if wait_ready or not self.session.is_authorized():
            try:
                await asyncio.wait_for(self._ready_event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                raise JetraConnectionError(f"Client did not become ready within {timeout}s")

    async def _main_loop(self):
        attempt = 0
        while self._is_running:
            try:
                await self._connect_and_run()
                attempt = 0
            except Exception as e:
                if not self._is_running:
                    break

                attempt += 1
                if attempt > self._max_reconnect_attempts:
                    print(f"Max reconnect attempts ({self._max_reconnect_attempts}) reached. Giving up.")
                    self._is_running = False
                    break

                print(f"Connection lost: {e}")
                print(f"Reconnecting in {self._reconnect_delay}s... (attempt {attempt}/{self._max_reconnect_attempts})")
                await asyncio.sleep(self._reconnect_delay)

    async def _connect_and_run(self):
        print("Connecting to Jetra...")
        await self.client.connect()

        if not self.session.is_authorized():
            # Fresh-login flow.
            if self.client.auth_key is None:
                print("No auth key yet. Completing MTProto DH handshake...")
                await self._complete_dh_only()
                print("DH complete. Waiting for send_code/sign_in...")
            else:
                print("Auth key present but user not authorized. Waiting for sign_in...")
            self._ready_event.set()
            await self._trigger_ready_handlers()
            await self._listen_loop()
            return

        print("Syncing state...")
        get_state = struct.pack("<I", GET_STATE_ID)
        result = await self.client.send_request(wrap_init_connection(get_state))
        if result:
            result = self._unwrap_gzip(result)
            if len(result) >= 4 and struct.unpack("<I", result[:4])[0] == 0xA56C2A3E:
                pts = struct.unpack("<i", result[4:8])[0]
                print(f"State synced. pts={pts}")

        await asyncio.sleep(0.2)

        print("Loading dialogs...")
        await self._load_dialogs()

        print("Client started. Listening for messages...")
        self._ready_event.set()
        await self._trigger_ready_handlers()

        await self._listen_loop()

    async def _listen_loop(self):
        while self._is_running:
            try:
                raw = None
                try:
                    async with asyncio.timeout(0.1):
                        await self._recv_lock.acquire()
                        try:
                            raw = await self.client.ws.recv()
                        finally:
                            self._recv_lock.release()
                except (asyncio.TimeoutError, TimeoutError):
                    await asyncio.sleep(0.01)
                    continue

                if raw is None:
                    continue

                decrypted = self.client.dec_cipher.decrypt(raw)

                if len(decrypted) < 1:
                    continue

                first_byte = decrypted[0]
                if first_byte < 0x7F:
                    payload = decrypted[1:1 + (first_byte << 2)]
                elif first_byte == 0x7F:
                    frame_len = int.from_bytes(decrypted[1:4], 'little') << 2
                    payload = decrypted[4:4 + frame_len]
                else:
                    payload = decrypted

                if len(payload) < 24 or payload[0:8] != self.client.auth_key_id:
                    continue

                msg_key_received = payload[8:24]
                encrypted_data = payload[24:]
                if len(encrypted_data) % 16 != 0:
                    encrypted_data = encrypted_data[:-(len(encrypted_data) % 16)]

                i = 8
                a = bytearray(52)
                a[0:16] = msg_key_received
                a[16:52] = self.client.auth_key[i:i + 36]
                s0 = hashlib.sha256(bytes(a)).digest()

                o = bytearray(52)
                o[0:36] = self.client.auth_key[40 + i:40 + i + 36]
                o[36:52] = msg_key_received
                s1 = hashlib.sha256(bytes(o)).digest()

                aes_key = s0[0:8] + s1[8:24] + s0[24:32]
                aes_iv = s1[0:8] + s0[8:24] + s1[24:32]

                inner = aes_ige_decrypt(encrypted_data, aes_key, aes_iv)
                offset = 8 + 8 + 8 + 4
                msg_len = struct.unpack('<I', inner[offset:offset + 4])[0]
                offset += 4
                msg_data = inner[offset:offset + msg_len]

                if len(msg_data) >= 4:
                    ctor = struct.unpack('<I', msg_data[:4])[0]
                    if ctor == UPDATES:
                        await self._handle_updates(msg_data)

            except Exception as e:
                if not self._is_running:
                    break
                # Check if websocket is closed (works with old and new websockets)
                ws_closed = False
                try:
                    # New websockets (>=11): state attribute
                    if hasattr(self.client.ws, "state"):
                        ws_closed = str(self.client.ws.state) != "State.OPEN"
                    elif hasattr(self.client.ws, "closed"):
                        ws_closed = self.client.ws.closed
                    elif hasattr(self.client.ws, "close_code"):
                        ws_closed = self.client.ws.close_code is not None
                except Exception:
                    pass
                if ws_closed:
                    raise JetraConnectionError("WebSocket closed")
                await asyncio.sleep(0.1)

    async def stop(self):
        print("Stopping client...")
        self._is_running = False
        self._ready_event.clear()
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        await self.client.close()
        self.db.close()
        print("Client stopped.")

    async def _handle_updates(self, msg_data):
        pos = msg_data.find(struct.pack("<I", UPDATE_NEW_MESSAGE))
        channel_pos = msg_data.find(struct.pack("<I", UPDATE_NEW_CHANNEL_MESSAGE))

        if channel_pos != -1:
            pos = channel_pos

        if pos == -1:
            return

        msg_pos = pos + 4
        if len(msg_data) < msg_pos + 4:
            return

        msg_ctor = struct.unpack("<I", msg_data[msg_pos:msg_pos + 4])[0]
        if msg_ctor not in (MSG_CTOR_JETRA, SERVICE_MSG_CTOR_JETRA):
            return

        message = self._parse_message(msg_data, msg_pos, msg_ctor)
        if message:
            self.db.save_message(message)
            await self._trigger_message_handlers(message)

    def _parse_message(self, data, offset, ctor):
        try:
            offset += 4
            if ctor == SERVICE_MSG_CTOR_JETRA:
                offset += 4
                msg_id = struct.unpack("<i", data[offset:offset + 4])[0]
                offset += 4
                flags = 0
            else:
                flags = struct.unpack("<i", data[offset:offset + 4])[0]
                offset += 4
                offset += 4
                msg_id = struct.unpack("<i", data[offset:offset + 4])[0]
                offset += 4

            from_peer_ctor = struct.unpack("<I", data[offset:offset + 4])[0]
            offset += 4
            from_id = struct.unpack("<q", data[offset:offset + 8])[0]
            offset += 8

            peer_ctor = struct.unpack("<I", data[offset:offset + 4])[0]
            offset += 4
            peer_id = struct.unpack("<q", data[offset:offset + 8])[0]
            offset += 8

            date = struct.unpack("<i", data[offset:offset + 4])[0]
            offset += 4

            reply_to_msg_id = None
            if ctor != SERVICE_MSG_CTOR_JETRA and (flags & 0x1):
                try:
                    reply_to_msg_id = struct.unpack("<i", data[offset:offset + 4])[0]
                    offset += 4
                except Exception:
                    pass

            text = ""
            try:
                text_len = data[offset]
                text = data[offset + 1:offset + 1 + text_len].decode('utf-8', errors='ignore')
                offset += 1 + text_len
                offset = (offset + 3) & ~3
            except:
                pass

            entities = []
            if offset + 8 <= len(data):
                vec_ctor = struct.unpack("<I", data[offset:offset+4])[0]
                if vec_ctor == 0x1CB5C415:
                    count = struct.unpack("<i", data[offset+4:offset+8])[0]
                    offset += 8
                    for _ in range(count):
                        if offset + 12 > len(data): break
                        e_ctor = struct.unpack("<I", data[offset:offset+4])[0]
                        e_offset = struct.unpack("<i", data[offset+4:offset+8])[0]
                        e_length = struct.unpack("<i", data[offset+8:offset+12])[0]
                        offset += 12
                        
                        e_type = "unknown"
                        extra = None
                        if e_ctor == 0xBD610BC9: e_type = "bold"
                        elif e_ctor == 0x826F8B60: e_type = "italic"
                        elif e_ctor == 0x9C4E7E8B: e_type = "underline"
                        elif e_ctor == 0xBF0693D4: e_type = "strike"
                        elif e_ctor == 0x28A20571: e_type = "code"
                        elif e_ctor == 0x73924BE0: 
                            e_type = "pre"
                            if offset < len(data):
                                lang_len = data[offset]
                                offset += 1 + lang_len
                                offset = (offset + 3) & ~3
                        elif e_ctor == 0x6ED02538: e_type = "url"
                        elif e_ctor == 0x76A6D327: 
                            e_type = "text_url"
                            if offset < len(data):
                                url_len = data[offset]
                                extra = data[offset+1:offset+1+url_len].decode('utf-8', errors='ignore')
                                offset += 1 + url_len
                                offset = (offset + 3) & ~3
                        elif e_ctor == 0xFA04579D: e_type = "mention"
                        elif e_ctor == 0x6F635B0D: e_type = "hashtag"
                        elif e_ctor == 0x6CEF8AC7: e_type = "bot_command"
                        elif e_ctor == 0x64E475C2: e_type = "email"
                        elif e_ctor == 0x9B69E34B: e_type = "phone"
                        
                        entities.append(MessageEntity(e_type, e_offset, e_length, extra))

            if peer_ctor == PEER_USER:
                peer_type = 'user'
            elif peer_ctor == PEER_CHANNEL:
                peer_type = 'group'
            else:
                peer_type = 'unknown'

            return Message(
                msg_id=msg_id,
                from_id=from_id,
                peer_id=peer_id,
                peer_type=peer_type,
                date=date,
                text=text,
                reply_to_msg_id=reply_to_msg_id,
                entities=entities
            )
        except Exception as e:
            print(f"Failed to parse message: {e}")
            return None

    async def invoke(self, method_id: int, *args):
        """
        Generic invoke for any TL method.

        Serializes method_id followed by args and calls the server.
        Automatically unwraps gzip responses and raises JetraRPCError
        when the server returns an RPC error.

        Args:
            method_id: 32-bit method constructor id (int).
            *args:     Positional arguments. Supported types:
                         - bytes   -> appended raw
                         - bool    -> TL boolTrue / boolFalse
                         - int     -> 32-bit signed integer
                         - str     -> TL string (UTF-8, length-prefixed)

        Returns:
            Unwrapped response bytes (after gzip, without RPC error).
        """
        if not self._is_running:
            raise JetraError(
                "Client is not started. Call await client.start() first."
            )

        body = struct.pack("<I", method_id)
        for arg in args:
            if isinstance(arg, bytes):
                body += arg
            elif isinstance(arg, bool):
                body += struct.pack("<I", 0x997275B5 if arg else 0xBC799737)
            elif isinstance(arg, int):
                body += struct.pack("<i", arg)
            elif isinstance(arg, str):
                body += self._tl_string(arg)
            else:
                raise ValueError(
                    f"Unsupported arg type for invoke: {type(arg).__name__}"
                )

        result = await self.client.send_request(wrap_init_connection(body))
        if not result:
            raise JetraConnectionError(
                f"No response from method {hex(method_id)}"
            )

        result = self._unwrap_gzip(result)
        ctor = struct.unpack("<I", result[:4])[0]
        if ctor == RPC_ERROR:
            raise JetraRPCError(
                f"Server error: {self._parse_rpc_error(result)}",
                method=hex(method_id),
            )
        return result

    async def send_message(self, peer_id, text, peer_type=None, reply_to=None,
                            schedule_date=None, silent=False,
                            background=False, no_webpage=False,
                            clear_draft=False, entities=None,
                            parse_mode=None):
        """
        Send a text message with advanced options.

        Args:
            peer_id:       target peer.
            text:          message text.
            peer_type:     "user" or "group" (auto-detected if None).
            reply_to:      Message or int (reply to a message).
            schedule_date: unix timestamp for scheduled sending (None = immediate).
            silent:        send without notification sound.
            background:    send in background (no notification).
            no_webpage:    disable web page preview.
            clear_draft:   clear draft after sending.
            entities:      list of MessageEntity or Formatted object.
            parse_mode:    "markdown", "html", or None (uses entities if given).

        Returns:
            int: real msg_id from server.
        """
        if not self._is_running:
            raise JetraError("Client not started. Call await client.start() first.")

        # Auto-detect peer type
        if peer_type is None:
            dialogs = self.db.get_dialogs()
            for d in dialogs:
                if d["peer_id"] == peer_id:
                    peer_type = d["peer_type"]
                    break
            else:
                peer_type = "group" if peer_id > 1000 else "user"

        # Build InputPeer
        if peer_type == "user":
            input_peer = (
                struct.pack("<I", INPUT_PEER_USER) +
                struct.pack("<Q", peer_id) +
                struct.pack("<q", 0)
            )
        else:
            access_hash = 0
            for d in self.db.get_dialogs():
                if d["peer_id"] == peer_id:
                    access_hash = d["access_hash"] or 0
                    break
            input_peer = (
                struct.pack("<I", INPUT_PEER_CHANNEL) +
                struct.pack("<q", peer_id) +
                struct.pack("<q", access_hash)
            )

        # Resolve reply_to
        reply_to_msg_id = None
        if reply_to is not None:
            if isinstance(reply_to, Message):
                reply_to_msg_id = reply_to.id
            elif isinstance(reply_to, int):
                reply_to_msg_id = reply_to
            else:
                raise TypeError("reply_to must be Message or int")
            if reply_to_msg_id == 0:
                raise ValueError("reply_to msg_id is 0 (invalid)")

        # Build flags and payload
        flags = 0
        reply_bytes = b""
        schedule_bytes = b""
        entities_bytes = b""

        if no_webpage:
            flags |= 0x2  # bit 1

        if silent:
            flags |= 0x20  # bit 5

        if background:
            flags |= 0x40  # bit 6

        if clear_draft:
            flags |= 0x80  # bit 7

        if reply_to_msg_id is not None:
            flags |= 0x1  # bit 0
            reply_bytes = (
                struct.pack("<I", 0x3BD4B7C2) +
                struct.pack("<I", 0) +
                struct.pack("<i", reply_to_msg_id)
            )

        # Entities
        if entities is not None:
            from pyjetra.userapi.format import Formatted
            if isinstance(entities, Formatted):
                entities = entities.entities

            if entities:
                flags |= 0x8  # bit 3
                ent_items = b""
                for e in entities:
                    ent_items += self._build_message_entity(e)
                entities_bytes = (
                    struct.pack("<I", VECTOR_CTOR) +
                    struct.pack("<i", len(entities)) +
                    ent_items
                )

        # Schedule
        if schedule_date is not None:
            flags |= 0x400  # bit 10
            schedule_bytes = struct.pack("<i", schedule_date)

        random_id = random.getrandbits(63)
        # Correct order per schema:
        # peer, reply_to, message, random_id, reply_markup, entities, schedule_date
        body = (
            struct.pack("<I", SEND_MESSAGE_ID) +
            struct.pack("<I", flags) +
            input_peer +
            reply_bytes +
            self._tl_string(text) +
            struct.pack("<q", random_id) +
            entities_bytes +
            schedule_bytes
        )

        result = await self.client.send_request(wrap_init_connection(body))
        if not result:
            raise JetraConnectionError("No response from sendMessage")

        result = self._unwrap_gzip(result)
        ctor = struct.unpack('<I', result[:4])[0]
        if ctor == RPC_ERROR:
            raise JetraRPCError(f"Server error: {self._parse_rpc_error(result)}", method="sendMessage")

        parsed = parse_sent_message(result)
        if parsed:
            real_msg_id = parsed["msg_id"]
            real_date = parsed["date"]
        else:
            real_msg_id = 0
            real_date = int(datetime.datetime.now().timestamp())

        sent_msg = Message(
            msg_id=real_msg_id,
            from_id=self.session.user_id,
            peer_id=peer_id,
            peer_type=peer_type,
            date=real_date,
            text=text,
            reply_to_msg_id=reply_to_msg_id
        )
        self.db.save_message(sent_msg)
        return real_msg_id

    def _build_message_entity(self, entity):
        """Build a single MessageEntity TL bytes."""
        ctors = {
            "bold": 0xBD610BC9,
            "italic": 0x826F8B60,
            "underline": 0x9C4E7E8B,
            "strike": 0xBF0693D4,
            "code": 0x28A20571,
            "pre": 0x73924BE0,
            "text_url": 0x76A6D327,
            "mention": 0xFA04579D,
            "hashtag": 0x6F635B0D,
            "bot_command": 0x6CEF8AC7,
            "email": 0x64E475C2,
            "phone": 0x9B69E34B,
            "url": 0x6ED02538,
        }
        etype = entity.type
        if etype not in ctors:
            raise ValueError(f"Unknown entity type: {etype}")

        ctor = ctors[etype]
        result = (
            struct.pack("<I", ctor) +
            struct.pack("<i", entity.offset) +
            struct.pack("<i", entity.length)
        )

        # Extra fields
        if etype == "pre":
            lang = entity.extra or ""
            result += self._tl_string(lang)
        elif etype == "text_url":
            url = entity.extra or ""
            result += self._tl_string(url)

        return result

    async def send_to_saved(self, text):
        if not self._is_running:
            raise JetraError("Client is not started.")

        random_id = random.getrandbits(63)
        body = (
            struct.pack("<I", SEND_MESSAGE_ID) +
            struct.pack("<I", 0) +
            struct.pack("<I", INPUT_PEER_SELF) +
            self._tl_string(text) +
            struct.pack("<q", random_id)
        )

        result = await self.client.send_request(wrap_init_connection(body))
        if not result:
            raise JetraConnectionError("No response from sendMessage")
        return True

    async def _complete_dh_only(self):
        """
        Perform a full MTProto DH handshake to obtain auth_key,
        but skip auth-protected calls (getState, getDialogs).
        Used for the login flow before the user is signed in.
        """
        # req_pq_multi
        await self.client.send_req_pq()

        for _ in range(10):
            resp = await asyncio.wait_for(self.client.recv(), timeout=10.0)
            if not resp or len(resp) < 8:
                continue
            # Try parse as resPQ
            try:
                parsed = self.client.parse_res_pq(resp)
            except Exception:
                continue
            # send_req_dh_params
            await self.client.send_req_dh_params(parsed)
            break
        else:
            raise JetraConnectionError("DH step 1 (req_pq) failed")

        # Wait for server_DH_params_ok
        for _ in range(10):
            resp = await asyncio.wait_for(self.client.recv(), timeout=10.0)
            if not resp or len(resp) < 8:
                continue
            try:
                parsed = self.client.parse_server_dh_params_ok(resp)
            except Exception:
                continue

            # Decrypt inner data
            from pyjetra.userapi.client import aes_ige_decrypt, JETRA_DH_PRIME
            import hashlib

            server_nonce = parsed["server_nonce"]
            enc_answer = parsed["encrypted_answer"]

            sha1_a = hashlib.sha1(self.client.new_nonce + server_nonce).digest()
            sha1_b = hashlib.sha1(server_nonce + self.client.new_nonce).digest()
            sha1_c = hashlib.sha1(self.client.new_nonce + self.client.new_nonce).digest()
            tmp_aes_key = sha1_a + sha1_b[:12]
            tmp_aes_iv = sha1_b[12:] + sha1_c + self.client.new_nonce[:4]

            decrypted = aes_ige_decrypt(enc_answer, tmp_aes_key, tmp_aes_iv)

            await self.client.complete_auth(parsed, decrypted)
            break
        else:
            raise JetraConnectionError("DH step 2 (dh_params) failed")

        # Wait for dh_gen_ok
        for _ in range(10):
            resp = await asyncio.wait_for(self.client.recv(), timeout=10.0)
            if not resp or len(resp) < 8:
                continue
            # Just wait one message and assume it's dh_gen_ok
            break

        # Persist new auth_key
        self.session.auth_key = self.client.auth_key
        self.session.auth_key_id = self.client.auth_key_id
        self.session.server_salt = self.client.server_salt
        self.session.session_id = self.client.session_id
        self.session.save()

    async def _load_dialogs(self):
        get_dialogs = (
            struct.pack("<I", GET_DIALOGS_ID) +
            struct.pack("<I", 0) +
            struct.pack("<i", 0) +
            struct.pack("<i", 0) +
            struct.pack("<I", 0x7F3B18EA) +
            struct.pack("<i", 100) +
            struct.pack("<q", 0)
        )

        result = await self.client.send_request(wrap_init_connection(get_dialogs))
        if not result:
            return

        data = self._unwrap_gzip(result)

        pos = 0
        count = 0
        while True:
            pos = data.find(struct.pack("<I", CHANNEL_CTOR), pos)
            if pos == -1:
                break

            try:
                offset = pos + 4
                flags = struct.unpack("<q", data[offset:offset + 8])[0]
                offset += 8
                channel_id = struct.unpack("<q", data[offset:offset + 8])[0]
                offset += 8
                access_hash = struct.unpack("<q", data[offset:offset + 8])[0]
                offset += 8

                title_len = data[offset]
                offset += 1
                if title_len < 0xFE:
                    title = data[offset:offset + title_len].decode('utf-8', errors='ignore')
                    offset += title_len
                else:
                    title_len = int.from_bytes(data[offset:offset + 3], 'little')
                    offset += 3
                    title = data[offset:offset + title_len].decode('utf-8', errors='ignore')
                    offset += title_len

                if flags & 0x100:
                    self.db.save_dialog(channel_id, 'group', title, access_hash)
                    count += 1
            except:
                pass

            pos += 4

        pos = 0
        while True:
            pos = data.find(struct.pack("<I", USER_CTOR), pos)
            if pos == -1:
                break

            try:
                offset = pos + 4
                offset += 8
                user_id = struct.unpack("<q", data[offset:offset + 8])[0]
                offset += 8
                access_hash = struct.unpack("<q", data[offset:offset + 8])[0]
                offset += 8

                strings = []
                for _ in range(3):
                    if offset >= len(data): break
                    
                    str_len = data[offset]
                    if str_len < 0xFE:
                        s = data[offset+1:offset+1+str_len].decode('utf-8', errors='ignore')
                        offset += 1 + str_len
                    else:
                        str_len = int.from_bytes(data[offset+1:offset+4], 'little')
                        s = data[offset+4:offset+4+str_len].decode('utf-8', errors='ignore')
                        offset += 4 + str_len
                    
                    offset = (offset + 3) & ~3
                    strings.append(s)
                
                first_name = strings[0] if len(strings) > 0 else ""
                last_name = strings[1] if len(strings) > 1 else ""
                username = strings[2] if len(strings) > 2 else ""
                
                if username and not all(c.isalnum() or c == '_' for c in username):
                    username = ""

                first_name = ''.join(c for c in first_name if c.isprintable() and c not in '\ufffd')
                last_name = ''.join(c for c in last_name if c.isprintable() and c not in '\ufffd')

                full_name = f"{first_name} {last_name}".strip()
                if not full_name:
                    full_name = f"User {user_id}"
                if username:
                    full_name += f" (@{username})"

                self.db.save_dialog(user_id, 'user', full_name, access_hash)
                count += 1
            except Exception as e:
                pass

            pos += 4

        print(f"Loaded {count} dialogs into database.")

    async def get_dialogs(self, peer_type=None):
        return self.db.get_dialogs(peer_type)

    async def get_dialog_by_title(self, title, peer_type=None):
        """
        Find a single dialog whose title contains the given string.

        Args:
            title:      Substring to search for (case-sensitive).
            peer_type:  Optional "user" or "group" filter.

        Returns:
            dict from Database.get_dialogs() (peer_id, peer_type, title,
            access_hash) or None if no match.
        """
        if peer_type not in (None, "user", "group"):
            raise ValueError(
                "peer_type must be None, 'user' or 'group'"
            )
        dialogs = self.db.get_dialogs(peer_type)
        for d in dialogs:
            if title in (d.get("title") or ""):
                return d
        return None

    async def get_groups(self):
        return self.db.get_dialogs('group')


    def get_history(self, peer_id=None, limit=100):
        return self.db.get_messages(peer_id, limit)


    async def _fetch_participants_raw(self, peer_id):
        """
        Fetch participants of a group/channel and return list of dicts
        with user_id and access_hash.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        channel_input = self._get_channel_input(peer_id)

        body = (
            struct.pack("<I", GET_PARTICIPANTS_ID) +
            channel_input +
            struct.pack("<I", 0xDE3F3C79) +
            struct.pack("<i", 0) +
            struct.pack("<i", 100) +
            struct.pack("<q", 0)
        )

        result = await self.client.send_request(wrap_init_connection(body))
        if not result:
            return []
        result = self._unwrap_gzip(result)
        resp_ctor = struct.unpack("<I", result[:4])[0]
        if resp_ctor == RPC_ERROR:
            raise JetraRPCError(
                f"Server error: {self._parse_rpc_error(result)}",
                method="getParticipants",
            )

        users = []
        seen = set()
        pos = 0
        needle = struct.pack("<I", USER_CTOR)
        while True:
            pos = result.find(needle, pos)
            if pos == -1:
                break
            try:
                offset = pos + 4 + 8
                user_id = struct.unpack("<q", result[offset:offset+8])[0]
                offset += 8
                access_hash = struct.unpack("<q", result[offset:offset+8])[0]
                if user_id not in seen:
                    seen.add(user_id)
                    users.append({
                        "user_id": user_id,
                        "access_hash": access_hash,
                    })
            except Exception:
                pass
            pos += 4

        return users

    async def get_participants(self, peer_id):
        """
        Return list of user_ids of a group/channel participants.

        For access_hash too, use get_participants_full().
        """
        raw = await self._fetch_participants_raw(peer_id)
        return [u["user_id"] for u in raw]

    async def get_participants_full(self, peer_id):
        """
        Return list of dicts with user_id and access_hash
        for a group/channel participants.

        access_hash is required for ban/kick operations.
        """
        return await self._fetch_participants_raw(peer_id)

    async def get_full_channel(self, peer_id):
        if not self._is_running: raise JetraError("Client not started.")
        channel_input = self._get_channel_input(peer_id)
        
        body = struct.pack("<I", GET_FULL_CHANNEL_ID) + channel_input
        
        result = await self.client.send_request(wrap_init_connection(body))
        if not result: return None
        result = self._unwrap_gzip(result)
        resp_ctor = struct.unpack("<I", result[:4])[0]
        if resp_ctor == RPC_ERROR:
            raise JetraRPCError(f"Server error: {self._parse_rpc_error(result)}", method="getFullChannel")
            
        channels = []
        pos = 0
        needle = struct.pack("<I", CHANNEL_CTOR)
        while True:
            pos = result.find(needle, pos)
            if pos == -1: break
            try:
                offset = pos + 4 + 8
                channel_id = struct.unpack("<q", result[offset:offset+8])[0]
                offset += 16
                title_len = result[offset]
                offset += 1
                title = result[offset:offset+title_len].decode('utf-8', errors='ignore')
                channels.append({"channel_id": channel_id, "title": title})
            except Exception: pass
            pos += 4
        return channels

    async def leave_channel(self, peer_id):
        if not self._is_running: raise JetraError("Client not started.")
        channel_input = self._get_channel_input(peer_id)
        
        body = struct.pack("<I", LEAVE_CHANNEL_ID) + channel_input
        
        result = await self.client.send_request(wrap_init_connection(body))
        if not result: return False
        result = self._unwrap_gzip(result)
        resp_ctor = struct.unpack("<I", result[:4])[0]
        if resp_ctor == RPC_ERROR:
            raise JetraRPCError(f"Server error: {self._parse_rpc_error(result)}", method="leaveChannel")
        return True

    async def resolve_username(self, username):
        if not self._is_running:
            raise JetraError("Client not started.")
            
        clean_username = username.replace("@", "").strip()
        if not clean_username:
            raise ValueError("Username cannot be empty")

        body = (
            struct.pack("<I", CONTACTS_SEARCH_ID) +
            self._tl_string(clean_username) +
            struct.pack("<i", 10)
        )
        
        result = await self.client.send_request(wrap_init_connection(body))
        if not result:
            raise JetraConnectionError("No response from contacts.search")
            
        result = self._unwrap_gzip(result)
        resp_ctor = struct.unpack("<I", result[:4])[0]
        if resp_ctor == RPC_ERROR:
            raise JetraRPCError(f"Server error: {self._parse_rpc_error(result)}", method="contacts.search")
            
        PEER_USER = 0x59511722
        PEER_CHANNEL = 0xA2A5371E
        
        pos_user = result.find(struct.pack("<I", PEER_USER))
        pos_channel = result.find(struct.pack("<I", PEER_CHANNEL))
        
        if pos_user != -1:
            offset = pos_user + 4
            peer_id = struct.unpack("<q", result[offset:offset+8])[0]
            return {"peer_id": peer_id, "peer_type": "user"}
        elif pos_channel != -1:
            offset = pos_channel + 4
            peer_id = struct.unpack("<q", result[offset:offset+8])[0]
            return {"peer_id": peer_id, "peer_type": "group"}
        
        return None

    def _get_input_peer(self, peer_id, peer_type=None):
        """Return TL-serialized InputPeer for a peer (user or group)."""
        if peer_type is None:
            found = False
            for d in self.db.get_dialogs():
                if d["peer_id"] == peer_id:
                    peer_type = d["peer_type"]
                    found = True
                    break
            if not found:
                peer_type = "group" if peer_id > 1000 else "user"

        if peer_type == "user":
            return (
                struct.pack("<I", INPUT_PEER_USER) +
                struct.pack("<Q", peer_id) +
                struct.pack("<q", 0)
            )

        access_hash = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == peer_id:
                access_hash = d["access_hash"] or 0
                break
        return (
            struct.pack("<I", INPUT_PEER_CHANNEL) +
            struct.pack("<q", peer_id) +
            struct.pack("<q", access_hash)
        )

    def _extract_users(self, data):
        """Scan data for User ctors and parse basic info dicts."""
        users = []
        seen = set()
        pos = 0
        needle = struct.pack("<I", USER_CTOR)
        while True:
            pos = data.find(needle, pos)
            if pos == -1:
                break
            try:
                offset = pos + 4 + 8
                user_id = struct.unpack("<q", data[offset:offset+8])[0]
                offset += 8
                access_hash = struct.unpack("<q", data[offset:offset+8])[0]
                offset += 8

                strings = []
                for _ in range(3):
                    if offset >= len(data):
                        break
                    s_len = data[offset]
                    if s_len < 0xFE:
                        s = data[offset+1:offset+1+s_len].decode(
                            "utf-8", errors="ignore"
                        )
                        offset += 1 + s_len
                    else:
                        s_len = int.from_bytes(
                            data[offset+1:offset+4], "little"
                        )
                        s = data[offset+4:offset+4+s_len].decode(
                            "utf-8", errors="ignore"
                        )
                        offset += 4 + s_len
                    offset = (offset + 3) & ~3
                    strings.append(s)

                if user_id not in seen:
                    seen.add(user_id)
                    users.append({
                        "user_id": user_id,
                        "access_hash": access_hash,
                        "first_name": strings[0] if len(strings) > 0 else "",
                        "last_name": strings[1] if len(strings) > 1 else "",
                        "username": strings[2] if len(strings) > 2 else "",
                    })
            except Exception:
                pass
            pos += 4
        return users

    async def _send_api_request(self, body, method_name="unknown"):
        """Send a TL request, unwrap gzip, raise on RPC error."""
        result = await self.client.send_request(wrap_init_connection(body))
        if not result:
            raise JetraConnectionError(f"No response from {method_name}")
        result = self._unwrap_gzip(result)
        ctor = struct.unpack("<I", result[:4])[0]
        if ctor == RPC_ERROR:
            raise JetraRPCError(
                f"Server error: {self._parse_rpc_error(result)}",
                method=method_name,
            )
        return result

    # ------------------------------------------------------------------
    #  New methods (confirmed to exist on Jetra layer 228)
    # ------------------------------------------------------------------

    async def mark_as_read(self, peer_id, max_id=0, peer_type=None):
        """Mark messages up to max_id as read in a chat."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        body = (
            struct.pack("<I", READ_HISTORY_ID) +
            input_peer +
            struct.pack("<i", max_id)
        )
        await self._send_api_request(body, "readHistory")
        return True

    async def set_typing(self, peer_id, peer_type=None):
        """Send 'typing' action to a chat."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        body = (
            struct.pack("<I", SET_TYPING_ID) +
            struct.pack("<I", 0) +
            input_peer +
            struct.pack("<I", ACTION_TYPING)
        )
        await self._send_api_request(body, "setTyping")
        return True

    async def check_username(self, username):
        """
        Check if a username is available.
        Returns True if available, False if occupied/invalid.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", CHECK_USERNAME_ID) + self._tl_string(username)
        try:
            await self._send_api_request(body, "checkUsername")
            return True
        except JetraRPCError as e:
            msg = str(e)
            if "USERNAME_OCCUPIED" in msg or "USERNAME_INVALID" in msg:
                return False
            raise

    async def get_config(self):
        """Fetch server config. Returns raw TL response bytes."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", GET_CONFIG_ID)
        return await self._send_api_request(body, "getConfig")

    async def get_nearest_dc(self):
        """Fetch nearest DC info. Returns raw TL response bytes."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", GET_NEAREST_DC_ID)
        return await self._send_api_request(body, "getNearestDc")

    async def update_profile(self, first_name=None, last_name=None, about=None):
        """
        Update the current user's profile. Any subset of fields.

        WARNING: This modifies the real profile of the account.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        if first_name is None and last_name is None and about is None:
            raise ValueError(
                "Provide at least one of first_name, last_name, about"
            )

        flags = 0
        payload = b""
        if first_name is not None:
            flags |= 0x1
            payload += self._tl_string(first_name)
        if last_name is not None:
            flags |= 0x2
            payload += self._tl_string(last_name)
        if about is not None:
            flags |= 0x4
            payload += self._tl_string(about)

        body = (
            struct.pack("<I", UPDATE_PROFILE_ID) +
            struct.pack("<I", flags) +
            payload
        )
        result = await self._send_api_request(body, "updateProfile")
        users = self._extract_users(result)
        return users[0] if users else None

    async def get_contacts(self):
        """
        Fetch contact list. Returns list of user dicts.

        Note: Jetra's contacts.getContacts does not accept a hash
        argument (unlike standard Telegram). Sending bare ctor is correct.

        If the account has no contacts, returns an empty list.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", GET_CONTACTS_ID)
        result = await self._send_api_request(body, "getContacts")
        return self._extract_users(result)

    async def get_full_user(self, user_id=None):
        """
        Get full info of a user. If user_id is None, returns own profile.
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        if user_id is None:
            input_user = struct.pack("<I", INPUT_USER_SELF)
        else:
            access_hash = 0
            for d in self.db.get_dialogs():
                if d["peer_id"] == user_id:
                    access_hash = d["access_hash"] or 0
                    break
            input_user = (
                struct.pack("<I", INPUT_USER) +
                struct.pack("<q", user_id) +
                struct.pack("<q", access_hash)
            )

        body = struct.pack("<I", GET_FULL_USER_ID) + input_user
        result = await self._send_api_request(body, "getFullUser")
        users = self._extract_users(result)
        return users[0] if users else None

    async def get_users(self, user_ids):
        """
        Fetch user info for the given user_ids.

        Jetra only accepts InputUserSelf in users.getUsers vector.
        For other users, we fall back to dialogs DB cached info.

        Returns list of user dicts (may be shorter than input if some
        users are unknown).
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        if not user_ids:
            return []

        results = []
        seen = set()
        my_id = self.session.user_id

        # If self is requested, use the vector form (works on Jetra)
        if my_id in user_ids or None in user_ids:
            try:
                vector = (
                    struct.pack("<I", VECTOR_CTOR) +
                    struct.pack("<i", 1) +
                    struct.pack("<I", INPUT_USER_SELF)
                )
                body = struct.pack("<I", GET_USERS_ID) + vector
                result = await self._send_api_request(body, "getUsers")
                for u in self._extract_users(result):
                    if u["user_id"] not in seen:
                        seen.add(u["user_id"])
                        results.append(u)
            except Exception:
                pass

        # For other users: try get_full_user via InputPeerUser
        dialogs_map = {d["peer_id"]: d for d in self.db.get_dialogs("user")}
        for uid in user_ids:
            if uid == my_id or uid in seen:
                continue
            d = dialogs_map.get(uid)
            if not d:
                continue
            ah = d["access_hash"] or 0
            try:
                body = (
                    struct.pack("<I", GET_FULL_USER_ID) +
                    struct.pack("<I", INPUT_PEER_USER) +
                    struct.pack("<Q", uid) +
                    struct.pack("<q", ah)
                )
                result = await self._send_api_request(body, "getFullUser")
                for u in self._extract_users(result):
                    if u["user_id"] not in seen:
                        seen.add(u["user_id"])
                        results.append(u)
                        break
            except Exception:
                pass

        return results

    async def get_server_history(self, peer_id, limit=100, offset_id=0,
                                 max_id=0, min_id=0, peer_type=None):
        """
        Fetch message history from the server for a peer.
        Returns list of message dicts.
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        input_peer = self._get_input_peer(peer_id, peer_type)
        body = (
            struct.pack("<I", GET_HISTORY_ID) +
            input_peer +
            struct.pack("<i", offset_id) +
            struct.pack("<i", 0) +
            struct.pack("<i", 0) +
            struct.pack("<i", limit) +
            struct.pack("<i", max_id) +
            struct.pack("<i", min_id) +
            struct.pack("<q", 0)
        )
        result = await self._send_api_request(body, "getHistory")

        messages = []
        pos = 0
        needle = struct.pack("<I", MSG_CTOR_JETRA)
        while True:
            pos = result.find(needle, pos)
            if pos == -1:
                break
            parsed = _parse_message_at(result, pos)
            if parsed:
                messages.append(parsed)
            pos += 4
        return messages

    async def get_messages(self, message_ids):
        """
        Fetch messages by their IDs (list of ints).
        Returns list of parsed message dicts.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        if not message_ids:
            return []

        # messages.getMessages requires Vector<InputMessage>,
        # not Vector<int>. Wrap each id in InputMessage#a54f6b07.
        INPUT_MESSAGE_ID = 0xA54F6B07
        items = b"".join(
            struct.pack("<I", INPUT_MESSAGE_ID) + struct.pack("<i", mid)
            for mid in message_ids
        )
        vector = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(message_ids)) +
            items
        )
        body = struct.pack("<I", GET_MESSAGES_ID) + vector
        result = await self._send_api_request(body, "getMessages")

        messages = []
        pos = 0
        needle = struct.pack("<I", MSG_CTOR_JETRA)
        while True:
            pos = result.find(needle, pos)
            if pos == -1:
                break
            parsed = _parse_message_at(result, pos)
            if parsed:
                messages.append(parsed)
            pos += 4
        return messages

    async def get_channels(self, channel_ids):
        """
        Fetch info about multiple channels/groups.
        Returns list of dicts with channel_id, access_hash, title.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        if not channel_ids:
            return []

        items = []
        for cid in channel_ids:
            access_hash = 0
            for d in self.db.get_dialogs():
                if d["peer_id"] == cid:
                    access_hash = d["access_hash"] or 0
                    break
            items.append(
                struct.pack("<I", INPUT_CHANNEL) +
                struct.pack("<q", cid) +
                struct.pack("<q", access_hash)
            )

        vector = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(items)) +
            b"".join(items)
        )
        body = struct.pack("<I", GET_CHANNELS_ID) + vector
        result = await self._send_api_request(body, "getChannels")

        channels = []
        seen = set()
        pos = 0
        needle = struct.pack("<I", CHANNEL_CTOR)
        while True:
            pos = result.find(needle, pos)
            if pos == -1:
                break
            try:
                offset = pos + 4 + 8
                channel_id = struct.unpack("<q", result[offset:offset+8])[0]
                offset += 8
                ah = struct.unpack("<q", result[offset:offset+8])[0]
                offset += 8

                title_len = result[offset]
                offset += 1
                if title_len < 0xFE:
                    title = result[offset:offset+title_len].decode("utf-8", errors="ignore")
                else:
                    title_len = int.from_bytes(result[offset:offset+3], "little")
                    offset += 3
                    title = result[offset:offset+title_len].decode("utf-8", errors="ignore")

                if channel_id not in seen:
                    seen.add(channel_id)
                    channels.append({
                        "channel_id": channel_id,
                        "access_hash": ah,
                        "title": title,
                    })
            except Exception:
                pass
            pos += 4
        return channels

    async def delete_contacts(self, user_ids):
        """
        Remove users from contacts (does NOT delete the users).
        Returns raw response bytes.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        if not user_ids:
            return b""

        items = []
        for uid in user_ids:
            access_hash = 0
            for d in self.db.get_dialogs():
                if d["peer_id"] == uid:
                    access_hash = d["access_hash"] or 0
                    break
            items.append(
                struct.pack("<I", INPUT_USER) +
                struct.pack("<q", uid) +
                struct.pack("<q", access_hash)
            )

        vector = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(items)) +
            b"".join(items)
        )
        body = struct.pack("<I", DELETE_CONTACTS_ID) + vector
        return await self._send_api_request(body, "deleteContacts")

    async def unblock_user(self, user_id):
        """Unblock a previously blocked user. Returns raw response."""
        if not self._is_running:
            raise JetraError("Client not started.")
        access_hash = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == user_id:
                access_hash = d["access_hash"] or 0
                break
        body = (
            struct.pack("<I", UNBLOCK_ID) +
            struct.pack("<I", INPUT_PEER_USER) +
            struct.pack("<Q", user_id) +
            struct.pack("<q", access_hash)
        )
        return await self._send_api_request(body, "unblock")

    async def update_status(self, offline=True):
        """
        Set account online/offline.
        offline=True -> offline, False -> online.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", UPDATE_STATUS_ID) +
            struct.pack("<I", 0x997275B5 if offline else 0xBC799737)
        )
        return await self._send_api_request(body, "updateStatus")

    async def get_authorizations(self):
        """
        List active sessions/authorizations on this account.
        Returns raw response bytes (parse manually if needed).
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", GET_AUTHORIZATIONS_ID)
        return await self._send_api_request(body, "getAuthorizations")

    async def reset_authorization(self, auth_hash):
        """
        Terminate a remote session by its hash (from get_authorizations).
        Returns raw response bytes.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", RESET_AUTHORIZATION_ID) +
            struct.pack("<q", auth_hash)
        )
        return await self._send_api_request(body, "resetAuthorization")

    async def get_user_photos(self, user_id=None, offset=0, max_id=0, limit=50):
        """
        Fetch profile photos of a user (self if user_id is None).
        Returns raw response bytes.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        if user_id is None:
            input_user = struct.pack("<I", INPUT_USER_SELF)
        else:
            access_hash = 0
            for d in self.db.get_dialogs():
                if d["peer_id"] == user_id:
                    access_hash = d["access_hash"] or 0
                    break
            input_user = (
                struct.pack("<I", INPUT_USER) +
                struct.pack("<q", user_id) +
                struct.pack("<q", access_hash)
            )

        body = (
            struct.pack("<I", GET_USER_PHOTOS_ID) +
            input_user +
            struct.pack("<i", offset) +
            struct.pack("<q", max_id) +
            struct.pack("<i", limit)
        )
        return await self._send_api_request(body, "getUserPhotos")

    async def get_emoji_keywords(self, lang_code="en"):
        """
        Fetch emoji keyword mapping for a language.
        Returns raw response bytes.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", GET_EMOJI_KEYWORDS_ID) +
            self._tl_string(lang_code)
        )
        return await self._send_api_request(body, "getEmojiKeywords")

    async def delete_messages(self, message_ids, revoke=True):
        """
        Delete messages by their IDs.

        Args:
            message_ids: list of int (message ids).
            revoke:      if True, delete for everyone (default True).

        Returns:
            dict with pts and pts_count, or raw response bytes.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        if not message_ids:
            return {}

        items = b"".join(struct.pack("<i", mid) for mid in message_ids)
        vector = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(message_ids)) +
            items
        )
        flags = 0x1 if revoke else 0
        body = (
            struct.pack("<I", TL_METHODS["messages.deleteMessages"]) +
            struct.pack("<I", flags) +
            vector
        )
        result = await self._send_api_request(body, "messages.deleteMessages")
        return result

    async def delete_message(self, peer_id, msg_id, revoke=True):
        """Convenience wrapper to delete a single message."""
        return await self.delete_messages([msg_id], revoke=revoke)

    async def forward_messages(self, from_peer_id, message_ids, to_peer_id):
        """
        Forward messages from one chat to another.

        Args:
            from_peer_id: source peer id.
            message_ids:  list of int.
            to_peer_id:   destination peer id.

        Returns:
            raw response bytes.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        if not message_ids:
            return b""

        from_input = self._get_input_peer(from_peer_id)

        # For self (saved messages) we need a valid access_hash
        if to_peer_id == self.session.user_id or to_peer_id is None:
            try:
                me = await self.get_full_user()
                my_ah = me["access_hash"] if me else 0
            except Exception:
                my_ah = 0
            to_input = (
                struct.pack("<I", INPUT_PEER_USER) +
                struct.pack("<Q", self.session.user_id) +
                struct.pack("<q", my_ah)
            )
        else:
            to_input = self._get_input_peer(to_peer_id)

        # Generate random_id for each message
        rnd_ids = [random.getrandbits(63) for _ in message_ids]
        ids_vector = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(message_ids)) +
            b"".join(struct.pack("<i", mid) for mid in message_ids)
        )
        rnd_vector = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(rnd_ids)) +
            b"".join(struct.pack("<q", r) for r in rnd_ids)
        )
        body = (
            struct.pack("<I", TL_METHODS["messages.forwardMessages"]) +
            struct.pack("<I", 0) +  # flags
            from_input +
            ids_vector +
            rnd_vector +
            to_input
        )
        return await self._send_api_request(body, "messages.forwardMessages")

    async def update_username(self, username):
        """
        Change the account username.

        Args:
            username: new username (without @). Empty string removes it.

        Returns:
            parsed user dict or raw response.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["account.updateUsername"]) +
            self._tl_string(username)
        )
        result = await self._send_api_request(body, "account.updateUsername")
        users = self._extract_users(result)
        return users[0] if users else result

    async def edit_message(self, peer_id, msg_id, new_text, peer_type=None):
        """
        Edit an existing message.

        Args:
            peer_id:    peer where the message lives.
            msg_id:     message id to edit.
            new_text:   new text for the message.
            peer_type:  optional "user" or "group".

        Returns:
            raw response bytes.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        if not msg_id:
            raise ValueError("msg_id must be non-zero")

        input_peer = self._get_input_peer(peer_id, peer_type)
        # flags bit 11 = "message field present"
        flags = 0x800
        body = (
            struct.pack("<I", TL_METHODS["messages.editMessage"]) +
            struct.pack("<I", flags) +
            input_peer +
            struct.pack("<i", msg_id) +
            self._tl_string(new_text)
        )
        return await self._send_api_request(body, "messages.editMessage")

    async def pin_message(self, peer_id, msg_id, peer_type=None, notify=True):
        """Pin a message in a chat."""
        if not self._is_running:
            raise JetraError("Client not started.")
        if not msg_id:
            raise ValueError("msg_id must be non-zero")

        input_peer = self._get_input_peer(peer_id, peer_type)
        flags = 0x1 if notify else 0
        body = (
            struct.pack("<I", TL_METHODS["messages.updatePinnedMessage"]) +
            struct.pack("<I", flags) +
            input_peer +
            struct.pack("<i", msg_id)
        )
        return await self._send_api_request(body, "messages.updatePinnedMessage")

    async def unpin_message(self, peer_id, msg_id, peer_type=None):
        """Unpin a message. Uses updatePinnedMessage with unpin flag."""
        if not self._is_running:
            raise JetraError("Client not started.")
        if not msg_id:
            raise ValueError("msg_id must be non-zero")

        input_peer = self._get_input_peer(peer_id, peer_type)
        # unpin flag is bit 1 (0x2)
        flags = 0x2
        body = (
            struct.pack("<I", TL_METHODS["messages.updatePinnedMessage"]) +
            struct.pack("<I", flags) +
            input_peer +
            struct.pack("<i", msg_id)
        )
        return await self._send_api_request(body, "messages.updatePinnedMessage")

    async def search_messages(self, peer_id, query, limit=20, peer_type=None):
        """
        Search messages in a chat by text.

        Returns raw response bytes (use get_server_history or parse manually).
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        body = (
            struct.pack("<I", TL_METHODS["messages.search"]) +
            struct.pack("<I", 0) +       # flags
            input_peer +
            self._tl_string(query) +
            struct.pack("<I", 0x57E2F66C) +  # filter: inputMessagesFilterEmpty
            struct.pack("<i", 0) +       # min_date
            struct.pack("<i", 0) +       # max_date
            struct.pack("<i", 0) +       # offset_id
            struct.pack("<i", 0) +       # add_offset
            struct.pack("<i", limit) +   # limit
            struct.pack("<i", 0) +       # max_id
            struct.pack("<i", 0) +       # min_id
            struct.pack("<q", 0)         # hash
        )
        return await self._send_api_request(body, "messages.search")

    async def add_contact(self, user_id, first_name, last_name="", phone=""):
        """
        Add a user to contacts.

        Args:
            user_id:    the user's id.
            first_name: contact first name.
            last_name:  contact last name (optional).
            phone:      phone number (optional).

        Returns:
            raw response bytes.
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        # Get access_hash from dialogs
        access_hash = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == user_id:
                access_hash = d["access_hash"] or 0
                break

        # contacts.addContact expects InputUser (0xF21158C6), not InputPeerUser
        INPUT_USER_CTOR = 0xF21158C6
        input_user = (
            struct.pack("<I", INPUT_USER_CTOR) +
            struct.pack("<q", user_id) +
            struct.pack("<q", access_hash)
        )
        body = (
            struct.pack("<I", TL_METHODS["contacts.addContact"]) +
            struct.pack("<I", 0) +       # flags (no phone privacy exception)
            input_user +
            self._tl_string(first_name) +
            self._tl_string(last_name) +
            self._tl_string(phone)
        )
        return await self._send_api_request(body, "contacts.addContact")

    async def block_contact(self, user_id):
        """Block a user. Note: block_contact is different from blocking a bot."""
        if not self._is_running:
            raise JetraError("Client not started.")
        access_hash = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == user_id:
                access_hash = d["access_hash"] or 0
                break
        input_peer = (
            struct.pack("<I", INPUT_PEER_USER) +
            struct.pack("<Q", user_id) +
            struct.pack("<q", access_hash)
        )
        # flags bit 0 = my_stories_from (report_spam in newer layer)
        body = (
            struct.pack("<I", TL_METHODS["contacts.block"]) +
            struct.pack("<I", 0) +
            input_peer
        )
        return await self._send_api_request(body, "contacts.block")

    async def join_channel(self, channel_id):
        """Join a channel/group by id."""
        if not self._is_running:
            raise JetraError("Client not started.")
        access_hash = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == channel_id:
                access_hash = d["access_hash"] or 0
                break
        channel_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", access_hash)
        )
        body = (
            struct.pack("<I", TL_METHODS["channels.joinChannel"]) +
            channel_input
        )
        return await self._send_api_request(body, "channels.joinChannel")

    # ------------------------------------------------------------------
    #  Batch B: typing actions, blocklist, channel management, admins
    # ------------------------------------------------------------------

    async def send_action(self, peer_id, action="typing", peer_type=None, top_msg_id=None):
        """
        Send a "typing-like" action. Actions:
            typing, cancel, upload_photo, upload_video, upload_document,
            record_audio, record_video, choose_sticker, geo, record_round,
            upload_round, speaking (voice call)

        Not all actions may be supported by Jetra.
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        # (ctor, extra_payload_bytes)
        # Upload actions require progress:int argument
        progress_zero = struct.pack("<i", 0)
        actions = {
            "typing":        (0x16BF744E, b""),
            "cancel":        (0xFD5EC8F5, b""),
            "record_audio":  (0xD52F73F7, b""),
            "record_round":  (0x88F27FBC, b""),
            "geo":           (0x176F8BA1, b""),
            "choose_sticker":(0xB05AC6B1, b""),
            "choose_contact":(0x628CBC6F, b""),
            "speaking":      (0xD92C2285, b""),
            "upload_photo":  (0xD1D34A26, progress_zero),
            "upload_video":  (0xE9763AEC, progress_zero),
            "upload_doc":    (0xAA0CD9E4, progress_zero),
            "upload_round":  (0x243E1C66, progress_zero),
        }
        action_lower = action.lower()
        if action_lower not in actions:
            raise ValueError(f"Unknown action: {action}. Valid: {list(actions.keys())}")
        action_ctor, action_extra = actions[action_lower]

        input_peer = self._get_input_peer(peer_id, peer_type)
        flags = 0
        top_bytes = b""
        if top_msg_id is not None:
            flags |= 0x1
            top_bytes = struct.pack("<i", top_msg_id)

        body = (
            struct.pack("<I", TL_METHODS["messages.setTyping"]) +
            struct.pack("<I", flags) +
            input_peer +
            top_bytes +
            struct.pack("<I", action_ctor) +
            action_extra
        )
        return await self._send_api_request(body, "messages.setTyping")

    async def get_blocked(self, offset=0, limit=100):
        """
        List blocked users.

        Returns raw response bytes (blocked users list).
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["contacts.getBlocked"]) +
            struct.pack("<I", 0) +      # flags
            struct.pack("<i", offset) +
            struct.pack("<i", limit)
        )
        return await self._send_api_request(body, "contacts.getBlocked")

    async def create_channel(self, title, about="", megagroup=True,
                             broadcast=False, forum=False):
        """
        Create a channel or supergroup.

        Args:
            title:     channel title.
            about:     channel description.
            megagroup: True for group, False for broadcast channel.
            broadcast: True for broadcast channel (mutually exclusive
                       with megagroup; if both False, basic group).
            forum:     True for forum topics.

        Returns:
            raw response bytes (Updates with new channel).
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        flags = 0
        if broadcast:
            flags |= 0x1
        if megagroup:
            flags |= 0x2
        if forum:
            flags |= 0x20

        body = (
            struct.pack("<I", TL_METHODS["channels.createChannel"]) +
            struct.pack("<I", flags) +
            self._tl_string(title) +
            self._tl_string(about)
        )
        return await self._send_api_request(body, "channels.createChannel")

    async def delete_channel(self, channel_id):
        """
        Delete (or leave) a channel/supergroup.

        If you are the creator, deletes it. Otherwise leaves it.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        access_hash = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == channel_id:
                access_hash = d["access_hash"] or 0
                break
        channel_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", access_hash)
        )
        body = (
            struct.pack("<I", TL_METHODS["channels.deleteChannel"]) +
            channel_input
        )
        return await self._send_api_request(body, "channels.deleteChannel")

    async def mute_chat(self, peer_id, mute_until=0, peer_type=None, silent=False):
        """
        Mute or unmute a chat.

        Args:
            peer_id:    peer to mute.
            mute_until: unix timestamp (0 for permanent mute, or
                        ~2147483647 for forever). Use -1 to UNMUTE.
            silent:     if True, no notification sound.
            peer_type:  optional "user" or "group".

        Returns:
            raw response bytes.
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        input_peer = self._get_input_peer(peer_id, peer_type)

        # InputNotifyPeer wrapping
        notify_peer = (
            struct.pack("<I", 0xB8BC5B0C) +  # inputNotifyPeer
            input_peer
        )

        # Build InputPeerNotifySettings with proper flag ordering:
        #   bit 0 = show_previews present  -> Bool
        #   bit 1 = silent present         -> Bool
        #   bit 2 = mute_until present     -> int
        # Fields MUST be sent in the schema order.
        settings_flags = 0x1 | 0x4  # show_previews + mute_until
        settings_payload = b""
        # show_previews = boolTrue
        settings_payload += struct.pack("<I", 0x997275B5)
        # silent (only if flag set)
        if silent:
            settings_flags |= 0x2
            settings_payload += struct.pack("<I", 0x997275B5)
        # mute_until (always)
        settings_payload += struct.pack("<i", mute_until)

        settings = (
            struct.pack("<I", 0xCACB6AE2) +  # inputPeerNotifySettings
            struct.pack("<I", settings_flags) +
            settings_payload
        )

        body = (
            struct.pack("<I", TL_METHODS["account.updateNotifySettings"]) +
            notify_peer +
            settings
        )
        return await self._send_api_request(body, "account.updateNotifySettings")

    async def unmute_chat(self, peer_id, peer_type=None):
        """Unmute a chat (shortcut for mute_chat with mute_until=-1... use 0)."""
        # mute_until = 0 means unmuted
        return await self.mute_chat(peer_id, mute_until=0, peer_type=peer_type)

    async def toggle_forum(self, channel_id, enabled=True, tabs=True):
        """
        Enable or disable forum (topics) mode for a supergroup.

        Args:
            channel_id: supergroup id.
            enabled:    True to enable forum mode.
            tabs:       True to show tab bar (default True).
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        access_hash = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == channel_id:
                access_hash = d["access_hash"] or 0
                break
        channel_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", access_hash)
        )

        bool_true = 0x997275B5
        bool_false = 0xBC799737

        body = (
            struct.pack("<I", TL_METHODS["channels.toggleForum"]) +
            channel_input +
            struct.pack("<I", bool_true if enabled else bool_false) +
            struct.pack("<I", bool_true if tabs else bool_false)
        )
        return await self._send_api_request(body, "channels.toggleForum")

    async def ban_user(self, channel_id, user_id, until_date=0):
        """
        Ban a user from a channel/supergroup.

        Args:
            channel_id: group/channel id.
            user_id:    user to ban.
            until_date: unix timestamp until which ban lasts.
                        0 = permanent ban.
                        A far-future value means "kick only" (no message access).
        """
        return await self._edit_banned(channel_id, user_id, view_messages=True, until_date=until_date)

    async def unban_user(self, channel_id, user_id):
        """Unban a user (remove ban)."""
        return await self._edit_banned(channel_id, user_id, view_messages=False, until_date=0)

    async def kick_user(self, channel_id, user_id):
        """
        Kick a user (ban + immediate unban pattern, so they can rejoin).
        In Telegram, kicking = ban with view_messages=True but short duration.
        """
        # ban then unban
        await self.ban_user(channel_id, user_id, until_date=60)
        await asyncio.sleep(0.5)
        await self.unban_user(channel_id, user_id)

    async def _edit_banned(self, channel_id, user_id, view_messages,
                           until_date=0, **rights):
        """
        Internal helper for channels.editBanned.

        Args:
            view_messages: True for ban (view_messages restricted).
            until_date:    unix timestamp for ban duration.
            **rights:      other ChatBannedRights flags:
                             send_messages, send_media, send_stickers,
                             send_gifs, send_games, send_inline, embed_links,
                             send_polls, change_info, invite_users,
                             pin_messages, manage_topics, send_photos,
                             send_videos, send_roundvideos, send_audios,
                             send_voices, send_docs, send_plain,
                             edit_rank, send_reactions, manage_linked_peers
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        # Find access hash
        ch_ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == channel_id:
                ch_ah = d["access_hash"] or 0
                break

        user_ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == user_id:
                user_ah = d["access_hash"] or 0
                break

        channel_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", ch_ah)
        )
        participant_input = (
            struct.pack("<I", INPUT_PEER_USER) +
            struct.pack("<Q", user_id) +
            struct.pack("<q", user_ah)
        )

        # Build ChatBannedRights
        rights_bits = {
            "view_messages": 0,
            "send_messages": 1,
            "send_media": 2,
            "send_stickers": 3,
            "send_gifs": 4,
            "send_games": 5,
            "send_inline": 6,
            "embed_links": 7,
            "send_polls": 8,
            "change_info": 10,
            "invite_users": 15,
            "pin_messages": 17,
            "manage_topics": 18,
            "send_photos": 19,
            "send_videos": 20,
            "send_roundvideos": 21,
            "send_audios": 22,
            "send_voices": 23,
            "send_docs": 24,
            "send_plain": 25,
            "edit_rank": 26,
            "send_reactions": 27,
            "manage_linked_peers": 28,
        }

        flags = 0
        if view_messages:
            flags |= (1 << rights_bits["view_messages"])
        for name, val in rights.items():
            if name not in rights_bits:
                raise ValueError(f"Unknown ChatBannedRights flag: {name}")
            if val:
                flags |= (1 << rights_bits[name])

        banned_rights = (
            struct.pack("<I", 0x9F120418) +  # chatBannedRights
            struct.pack("<I", flags) +
            struct.pack("<i", until_date)
        )

        body = (
            struct.pack("<I", TL_METHODS["channels.editBanned"]) +
            channel_input +
            participant_input +
            banned_rights
        )
        return await self._send_api_request(body, "channels.editBanned")

    async def promote_admin(self, channel_id, user_id, rights=None, rank="",
                             add_admins=False, manage_call=False):
        """
        Promote a user to admin.

        Args:
            rights: dict of admin rights (e.g. {"change_info": True}).
            rank:   custom title (optional).
        """
        return await self._edit_admin(channel_id, user_id, rights or {}, rank)

    async def demote_admin(self, channel_id, user_id):
        """Demote an admin back to regular user."""
        return await self._edit_admin(channel_id, user_id, {}, "")

    async def _edit_admin(self, channel_id, user_id, admin_rights_dict, rank=""):
        """
        Internal helper for channels.editAdmin.
        admin_rights_dict keys: change_info, post_messages, edit_messages,
        delete_messages, ban_users, invite_users, pin_messages, add_admins,
        anonymous, manage_call, other, manage_topics, post_stories,
        edit_stories, delete_stories, manage_direct_messages,
        manage_ranks, manage_linked_peers
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        ch_ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == channel_id:
                ch_ah = d["access_hash"] or 0
                break
        user_ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == user_id:
                user_ah = d["access_hash"] or 0
                break

        channel_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", ch_ah)
        )
        user_input = (
            struct.pack("<I", 0xF21158C6) +  # inputUser
            struct.pack("<q", user_id) +
            struct.pack("<q", user_ah)
        )

        admin_bits = {
            "change_info": 0,
            "post_messages": 1,
            "edit_messages": 2,
            "delete_messages": 3,
            "ban_users": 4,
            "invite_users": 5,
            "pin_messages": 7,
            "add_admins": 9,
            "anonymous": 10,
            "manage_call": 11,
            "other": 12,
            "manage_topics": 13,
            "post_stories": 14,
            "edit_stories": 15,
            "delete_stories": 16,
            "manage_direct_messages": 17,
            "manage_ranks": 18,
            "manage_linked_peers": 19,
        }

        ar_flags = 0
        for name, val in admin_rights_dict.items():
            if name not in admin_bits:
                raise ValueError(f"Unknown ChatAdminRights flag: {name}")
            if val:
                ar_flags |= (1 << admin_bits[name])

        admin_rights = (
            struct.pack("<I", 0x5FB224D5) +  # chatAdminRights
            struct.pack("<I", ar_flags)
        )

        edit_flags = 0
        rank_bytes = b""
        if rank:
            edit_flags |= 0x1
            rank_bytes = self._tl_string(rank)

        body = (
            struct.pack("<I", TL_METHODS["channels.editAdmin"]) +
            struct.pack("<I", edit_flags) +
            channel_input +
            user_input +
            admin_rights +
            rank_bytes
        )
        return await self._send_api_request(body, "channels.editAdmin")

    async def invite_user(self, channel_id, user_id):
        """Invite a user to a channel/supergroup."""
        if not self._is_running:
            raise JetraError("Client not started.")

        ch_ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == channel_id:
                ch_ah = d["access_hash"] or 0
                break
        user_ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == user_id:
                user_ah = d["access_hash"] or 0
                break

        channel_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", ch_ah)
        )
        user_input = (
            struct.pack("<I", 0xF21158C6) +  # inputUser
            struct.pack("<q", user_id) +
            struct.pack("<q", user_ah)
        )
        vector = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", 1) +
            user_input
        )
        body = (
            struct.pack("<I", TL_METHODS["channels.inviteToChannel"]) +
            channel_input +
            vector
        )
        return await self._send_api_request(body, "channels.inviteToChannel")

    # ------------------------------------------------------------------
    #  Authentication (login flow)
    # ------------------------------------------------------------------

    async def send_code(self, phone_number, api_id=None, api_hash=None):
        """
        Request an SMS/App code for logging in.

        Args:
            phone_number: international format, e.g. "+989123456789"
            api_id:       defaults to the built-in Jetra web api_id.
            api_hash:     defaults to the built-in Jetra web api_hash.

        Returns:
            dict with phone_code_hash (and other raw response bytes),
            or raises JetraRPCError on failure.
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        if not phone_number.startswith("+"):
            phone_number = "+" + phone_number

        if api_id is None:
            api_id = self._api_id
        if api_hash is None:
            api_hash = self._api_hash

        # codeSettings with flags=0 (no special options)
        settings = struct.pack("<I", 0xAD253D78) + struct.pack("<I", 0)

        body = (
            struct.pack("<I", TL_METHODS["auth.sendCode"]) +
            self._tl_string(phone_number) +
            struct.pack("<i", api_id) +
            self._tl_string(api_hash) +
            settings
        )
        result = await self._send_api_request(body, "auth.sendCode")

        # Parse phone_code_hash from response.
        # Structure of auth.sentCode: flags:int, type:SentCodeType, phone_code_hash:string
        # We skip flags(4) and type(ctor 4 + rest). Simpler: search for the
        # longest string of hex-like content following the ctor.
        # We fall back to scanning for a plausible hex string after ctor.
        phone_code_hash = self._extract_phone_code_hash(result)
        return {
            "phone_code_hash": phone_code_hash,
            "raw_len": len(result),
        }

    def _extract_phone_code_hash(self, data):
        """
        Extract phone_code_hash from auth.sentCode response.

        Jetra's auth.sentCode layout (observed):
            ctor: 4 (0x5E002502)
            flags: 4
            type: SentCodeType (ctor + params, variable)
            phone_code_hash: string (TL bytes: len prefix + content + pad)
            [timeout: int]
            ...

        Strategy: scan for a plausible TL string that is 16 characters long
        and consists of hex digits. That is the phone_code_hash format on
        Jetra.
        """
        # Fast path: find any 16-char hex-like TL string
        i = 0
        n = len(data)
        while i < n:
            c = data[i]
            if c == 16 and i + 1 + 16 <= n:
                chunk = data[i+1:i+17]
                try:
                    s = chunk.decode("ascii")
                    if all(ch in "0123456789abcdef" for ch in s):
                        return s
                except Exception:
                    pass
            i += 1

        # Fallback: longest printable TL string
        candidates = []
        i = 0
        while i < n:
            c = data[i]
            if 1 <= c <= 60 and i + 1 + c <= n:
                chunk = data[i+1:i+1+c]
                try:
                    s = chunk.decode("utf-8")
                    if s.isprintable():
                        candidates.append(s)
                except Exception:
                    pass
                i += 1 + c
                pad = (4 - ((1 + c) % 4)) % 4
                i += pad
                continue
            i += 1
        if candidates:
            candidates.sort(key=len, reverse=True)
            return candidates[0]
        return None

    async def sign_in(self, phone_number, phone_code_hash, phone_code,
                      api_id=None, api_hash=None):
        """
        Sign in with a phone code (and optionally a password later).

        Returns:
            dict with 'user_id', 'access_hash', and raw 'authorization' info
            if successful. Raises JetraRPCError on failure.
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        if not phone_number.startswith("+"):
            phone_number = "+" + phone_number

        # flags: phone_code present (bit 0)
        flags = 0x1

        body = (
            struct.pack("<I", TL_METHODS["auth.signIn"]) +
            struct.pack("<I", flags) +
            self._tl_string(phone_number) +
            self._tl_string(phone_code_hash) +
            self._tl_string(phone_code)
        )
        result = await self._send_api_request(body, "auth.signIn")
        return result

    async def import_web_token(self, web_auth_token, dc_id=2,
                                api_id=None, api_hash=None):
        """
        Import a Jetra web auth token (from URL fragment #?tgaddr=...
        or QR code). This logs in without SMS code.

        Returns:
            raw auth.authorization response.
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        if api_id is None:
            api_id = self._api_id
        if api_hash is None:
            api_hash = self._api_hash

        body = (
            struct.pack("<I", TL_METHODS["auth.importWebTokenAuthorization"]) +
            struct.pack("<i", api_id) +
            self._tl_string(api_hash) +
            self._tl_string(web_auth_token)
        )
        return await self._send_api_request(body, "auth.importWebTokenAuthorization")

    async def log_out(self):
        """
        Log out the current session. This invalidates the auth_key.

        After this, calling start() will raise JetraAuthError.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", TL_METHODS["auth.logOut"])
        return await self._send_api_request(body, "auth.logOut")

    async def get_password(self):
        """
        Fetch the account's password state (2FA info).

        Returns the raw TL response bytes. If account has 2FA enabled,
        contains: srp_B, srp_id, current_algo (password KDF algo).
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", TL_METHODS["account.getPassword"])
        return await self._send_api_request(body, "account.getPassword")

    def _parse_account_password(self, data):
        """
        Parse account.password response into dict.

        Returns dict with:
            has_password: bool
            hint: str (optional)
            srp_B: bytes (if has_password)
            srp_id: int (if has_password)
            current_algo: dict (if has_password) with salt1,salt2,g,p
        """
        offset = 0
        ctor = struct.unpack("<I", data[offset:offset+4])[0]
        offset += 4
        # account.password#957b50fb
        if ctor != 0x957B50FB:
            raise ValueError(f"Unexpected ctor: 0x{ctor:08X}")

        flags = struct.unpack("<I", data[offset:offset+4])[0]
        offset += 4

        result = {
            "has_password": bool(flags & 0x4),
            "has_recovery": bool(flags & 0x1),
            "has_secure_values": bool(flags & 0x2),
        }

        # current_algo (bit 2)
        algo = None
        if flags & 0x4:
            algo_ctor = struct.unpack("<I", data[offset:offset+4])[0]
            offset += 4
            if algo_ctor != 0x3A912D4A:  # passwordKdfAlgoSHA256SHA256PBKDF2HMACSHA512iter100000SHA256ModPow
                raise ValueError(f"Unsupported KDF algo: 0x{algo_ctor:08X}")
            salt1_len = data[offset]
            offset += 1
            salt1 = data[offset:offset+salt1_len]
            offset += salt1_len
            offset = (offset + 3) & ~3
            salt2_len = data[offset]
            offset += 1
            salt2 = data[offset:offset+salt2_len]
            offset += salt2_len
            offset = (offset + 3) & ~3
            g = struct.unpack("<i", data[offset:offset+4])[0]
            offset += 4
            p_len = data[offset]
            if p_len < 0xFE:
                offset += 1
            else:
                p_len = int.from_bytes(data[offset+1:offset+4], "little")
                offset += 4
            p_bytes = data[offset:offset+p_len]
            offset += p_len
            offset = (offset + 3) & ~3
            algo = {"salt1": salt1, "salt2": salt2, "g": g, "p": p_bytes}
        result["current_algo"] = algo

        # srp_B (bit 2)
        if flags & 0x4:
            b_len = data[offset]
            if b_len < 0xFE:
                offset += 1
            else:
                b_len = int.from_bytes(data[offset+1:offset+4], "little")
                offset += 4
            srp_B = data[offset:offset+b_len]
            offset += b_len
            offset = (offset + 3) & ~3
            result["srp_B"] = srp_B

            srp_id = struct.unpack("<q", data[offset:offset+8])[0]
            offset += 8
            result["srp_id"] = srp_id

        # hint (bit 3)
        if flags & 0x8:
            hint_len = data[offset]
            offset += 1
            hint = data[offset:offset+hint_len].decode("utf-8", errors="ignore")
            offset += hint_len
            offset = (offset + 3) & ~3
            result["hint"] = hint

        return result

    async def check_password(self, password):
        """
        Complete 2FA login by providing the account password.

        Call this after sign_in raises SESSION_PASSWORD_NEEDED.

        Args:
            password: plain text 2FA password (str).

        Returns:
            auth.Authorization response (or raises).
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        from pyjetra.userapi.srp import compute_srp

        # Step 1: get password state
        pw_data = await self.get_password()
        pw_info = self._parse_account_password(pw_data)

        if not pw_info["has_password"]:
            raise JetraError("Account has no 2FA password set")

        algo = pw_info["current_algo"]
        srp_B = pw_info["srp_B"]
        srp_id = pw_info["srp_id"]

        # Step 2: compute SRP proof
        proof = compute_srp(algo, srp_B, srp_id, password.encode("utf-8"))

        # Step 3: send auth.checkPassword
        body = (
            struct.pack("<I", TL_METHODS["auth.checkPassword"]) +
            struct.pack("<I", 0xD27FF082) +  # inputCheckPasswordSRP
            struct.pack("<q", proof["srp_id"]) +
            self._tl_bytes(proof["A"]) +
            self._tl_bytes(proof["M1"])
        )
        result = await self._send_api_request(body, "auth.checkPassword")
        return result

    def _tl_bytes(self, data):
        """TL-encode a byte string."""
        n = len(data)
        if n <= 253:
            buf = bytes([n]) + data
        else:
            buf = b'\xfe' + n.to_bytes(3, 'little') + data
        return buf + b'\x00' * ((4 - len(buf) % 4) % 4)

    # ------------------------------------------------------------------
    #  Media upload pipeline (two-step: uploadMedia then sendMedia)
    # ------------------------------------------------------------------

    async def upload_file(self, local_path, file_name=None):
        """Upload local file to server, return InputFile info."""
        import hashlib

        if not os.path.isfile(local_path):
            raise FileNotFoundError(local_path)

        size = os.path.getsize(local_path)
        if size == 0:
            raise ValueError("File is empty")

        if file_name is None:
            file_name = os.path.basename(local_path)

        file_id = random.getrandbits(63)
        chunk_size = 1024 * 1024
        parts = (size + chunk_size - 1) // chunk_size
        is_big = size > 10 * 1024 * 1024

        # Compute md5 for small files (required for inputFile validation)
        md5 = ""
        if not is_big:
            h = hashlib.md5()
            with open(local_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
            md5 = h.hexdigest()

        save_method = (
            TL_METHODS["upload.saveBigFilePart"]
            if is_big
            else TL_METHODS["upload.saveFilePart"]
        )

        with open(local_path, "rb") as f:
            for part_index in range(parts):
                chunk = f.read(chunk_size)
                if not chunk:
                    break

                if is_big:
                    body = (
                        struct.pack("<I", save_method) +
                        struct.pack("<q", file_id) +
                        struct.pack("<i", part_index) +
                        struct.pack("<i", parts) +
                        self._tl_bytes(chunk)
                    )
                else:
                    body = (
                        struct.pack("<I", save_method) +
                        struct.pack("<q", file_id) +
                        struct.pack("<i", part_index) +
                        self._tl_bytes(chunk)
                    )

                await self._send_api_request(body, "upload.saveFilePart")

        if is_big:
            input_file = (
                struct.pack("<I", 0xFA4F0BB5) +
                struct.pack("<q", file_id) +
                struct.pack("<i", parts) +
                self._tl_string(file_name)
            )
        else:
            input_file = (
                struct.pack("<I", 0xF52FF27F) +
                struct.pack("<q", file_id) +
                struct.pack("<i", parts) +
                self._tl_string(file_name) +
                self._tl_string(md5)
            )

        return {
            "file_id": file_id,
            "parts": parts,
            "name": file_name,
            "md5": md5,
            "size": size,
            "input_file": input_file,
            "is_big": is_big,
        }

    def _guess_media_type(self, path):
        """Determine media kind from file extension."""
        ext = os.path.splitext(path)[1].lower()
        image_exts = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
        video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

        if ext in image_exts:
            return "photo"
        if ext in video_exts:
            return "video"
        return "document"

    async def _upload_media_register(self, peer_id, input_media, peer_type=None):
        """
        Register uploaded file via messages.uploadMedia.
        Returns messageMediaPhoto or messageMediaDocument response.
        """
        input_peer = self._get_input_peer(peer_id, peer_type)
        body = (
            struct.pack("<I", TL_METHODS["messages.uploadMedia"]) +
            struct.pack("<I", 0) +  # flags (no business_connection_id)
            input_peer +
            input_media
        )
        result = await self._send_api_request(body, "messages.uploadMedia")
        return result

    def _parse_message_media(self, data):
        """
        Parse MessageMedia response from uploadMedia.

        Returns dict with:
            type: "photo" or "document"
            id, access_hash, file_reference, dc_id
        """
        if len(data) < 4:
            return None

        ctor = struct.unpack("<I", data[:4])[0]
        offset = 4

        if ctor == 0xE216EB63:  # messageMediaPhoto
            # flags:# spoiler:flags.3?true live_photo:flags.4?true
            # photo:flags.0?Photo ttl_seconds:flags.2?int video:flags.4?Document
            flags = struct.unpack("<I", data[offset:offset+4])[0]
            offset += 4

            if not (flags & 0x1):  # no photo
                return None

            photo_ctor = struct.unpack("<I", data[offset:offset+4])[0]
            offset += 4
            if photo_ctor != 0xFB197A65:  # photo
                return None
            # photo: flags:# has_stickers:flags.0?true
            # id:long access_hash:long file_reference:bytes
            # date:int sizes:Vector<PhotoSize>
            # video_sizes:flags.1?Vector<VideoSize> dc_id:int
            photo_flags = struct.unpack("<I", data[offset:offset+4])[0]
            offset += 4
            photo_id = struct.unpack("<q", data[offset:offset+8])[0]
            offset += 8
            access_hash = struct.unpack("<q", data[offset:offset+8])[0]
            offset += 8
            fr_len = data[offset]
            if fr_len < 0xFE:
                offset += 1
            else:
                fr_len = int.from_bytes(data[offset+1:offset+4], "little")
                offset += 4
            file_reference = data[offset:offset+fr_len]
            offset += fr_len
            offset = (offset + 3) & ~3

            return {
                "type": "photo",
                "id": photo_id,
                "access_hash": access_hash,
                "file_reference": file_reference,
            }

        elif ctor == 0x52D8CCD9:  # messageMediaDocument
            # flags:# ... document:flags.0?Document ...
            flags = struct.unpack("<I", data[offset:offset+4])[0]
            offset += 4

            if not (flags & 0x1):  # no document
                return None

            doc_ctor = struct.unpack("<I", data[offset:offset+4])[0]
            offset += 4
            if doc_ctor != 0x8FD4C4D8:  # document
                return None
            # document: flags:# id:long access_hash:long file_reference:bytes
            # date:int mime_type:string size:long ...
            doc_flags = struct.unpack("<I", data[offset:offset+4])[0]
            offset += 4
            doc_id = struct.unpack("<q", data[offset:offset+8])[0]
            offset += 8
            access_hash = struct.unpack("<q", data[offset:offset+8])[0]
            offset += 8
            fr_len = data[offset]
            if fr_len < 0xFE:
                offset += 1
            else:
                fr_len = int.from_bytes(data[offset+1:offset+4], "little")
                offset += 4
            file_reference = data[offset:offset+fr_len]
            offset += fr_len
            offset = (offset + 3) & ~3

            return {
                "type": "document",
                "id": doc_id,
                "access_hash": access_hash,
                "file_reference": file_reference,
            }

        return None

    async def send_media(self, peer_id, local_path, caption="", peer_type=None,
                         force_file=False, attributes=None, mime_type=None,
                         reply_to=None, silent=False, schedule_date=None):
        """
        Upload and send a media file via two-step process:
          1. Upload raw bytes (saveFilePart)
          2. Register with messages.uploadMedia -> get Photo/Document ref
          3. Send with messages.sendMedia -> inputMediaPhoto/Document
        """
        import mimetypes

        if not self._is_running:
            raise JetraError("Client not started.")

        input_peer = self._get_input_peer(peer_id, peer_type)

        # Step 1: upload
        upload_info = await self.upload_file(local_path)
        input_file_bytes = upload_info["input_file"]

        media_type = self._guess_media_type(local_path)
        if force_file:
            media_type = "document"

        if mime_type is None:
            mime_type, _ = mimetypes.guess_type(local_path)
            if not mime_type:
                mime_type = "application/octet-stream"

        # Step 2: build inputMediaUploaded* and register
        # Try photo first for images; if server rejects, fallback to document.
        tried_photo = False
        if media_type == "photo":
            tried_photo = True
            input_media_uploaded = (
                struct.pack("<I", 0x7D8375DA) +  # inputMediaUploadedPhoto
                struct.pack("<I", 0) +  # flags
                input_file_bytes
            )
        else:
            flags = 0  # no special flags (flags.4 = force_file = 0x10)

            if attributes is None:
                filename_attr = (
                    struct.pack("<I", 0x15590068) +  # documentAttributeFilename
                    self._tl_string(os.path.basename(local_path))
                )
                attrs_list = [filename_attr]
            else:
                attrs_list = attributes

            vector = (
                struct.pack("<I", VECTOR_CTOR) +
                struct.pack("<i", len(attrs_list)) +
                b"".join(attrs_list)
            )

            input_media_uploaded = (
                struct.pack("<I", 0x037C9330) +  # inputMediaUploadedDocument
                struct.pack("<I", flags) +
                input_file_bytes +
                self._tl_string(mime_type) +
                vector
            )

        try:
            registered = await self._upload_media_register(
                peer_id, input_media_uploaded, peer_type
            )
        except JetraRPCError as e:
            if tried_photo and "PHOTO_INVALID" in str(e):
                # Fallback: send as document instead
                filename_attr = (
                    struct.pack("<I", 0x15590068) +  # documentAttributeFilename
                    self._tl_string(os.path.basename(local_path))
                )
                attrs = (
                    struct.pack("<I", VECTOR_CTOR) +
                    struct.pack("<i", 1) +
                    filename_attr
                )
                input_media_uploaded = (
                    struct.pack("<I", 0x037C9330) +  # inputMediaUploadedDocument
                    struct.pack("<I", 0) +  # flags
                    input_file_bytes +
                    self._tl_string(mime_type) +
                    attrs
                )
                registered = await self._upload_media_register(
                    peer_id, input_media_uploaded, peer_type
                )
                # Override media_type so sendMedia uses document
                media_type = "document"
            else:
                raise

        parsed_media = self._parse_message_media(registered)
        if not parsed_media:
            raise JetraRPCError(
                "Could not parse MessageMedia from uploadMedia response"
            )

        # Step 3: build inputMediaPhoto/Document from parsed refs
        if parsed_media["type"] == "photo":
            # inputMediaPhoto#e3af4434 flags:# spoiler:flags.1?true ...
            # id:InputPhoto ttl_seconds:flags.0?int video:flags.2?InputDocument
            input_photo = (
                struct.pack("<I", 0x3BB3B94A) +  # inputPhoto
                struct.pack("<q", parsed_media["id"]) +
                struct.pack("<q", parsed_media["access_hash"]) +
                self._tl_bytes(parsed_media["file_reference"])
            )
            input_media_final = (
                struct.pack("<I", 0xE3AF4434) +  # inputMediaPhoto
                struct.pack("<I", 0) +  # flags
                input_photo
            )
        else:
            input_doc = (
                struct.pack("<I", 0x1ABFB575) +  # inputDocument
                struct.pack("<q", parsed_media["id"]) +
                struct.pack("<q", parsed_media["access_hash"]) +
                self._tl_bytes(parsed_media["file_reference"])
            )
            input_media_final = (
                struct.pack("<I", 0xA8763AB5) +  # inputMediaDocument
                struct.pack("<I", 0) +  # flags
                input_doc
            )

        # Step 4: send with advanced flags
        flags = 0
        extra_before = b""
        extra_after = b""

        # reply_to
        reply_to_msg_id = None
        if reply_to is not None:
            if isinstance(reply_to, Message):
                reply_to_msg_id = reply_to.id
            elif isinstance(reply_to, int):
                reply_to_msg_id = reply_to
            if reply_to_msg_id and reply_to_msg_id != 0:
                flags |= 0x1  # bit 0 (reply)
                extra_before = (
                    struct.pack("<I", 0x3BD4B7C2) +
                    struct.pack("<I", 0) +
                    struct.pack("<i", reply_to_msg_id)
                )

        if silent:
            flags |= 0x20  # bit 5

        if schedule_date is not None:
            flags |= 0x400  # bit 10
            extra_after = struct.pack("<i", schedule_date)

        random_id = random.getrandbits(63)
        body = (
            struct.pack("<I", TL_METHODS["messages.sendMedia"]) +
            struct.pack("<I", flags) +
            input_peer +
            extra_before +
            input_media_final +
            self._tl_string(caption) +
            struct.pack("<q", random_id) +
            extra_after
        )
        result = await self._send_api_request(body, "messages.sendMedia")

        parsed = parse_sent_message(result)
        return parsed or {"raw_len": len(result)}

    async def send_photo(self, peer_id, local_path, caption="", peer_type=None):
        return await self.send_media(peer_id, local_path, caption=caption,
                                      peer_type=peer_type, force_file=False)

    async def send_document(self, peer_id, local_path, caption="", peer_type=None):
        return await self.send_media(peer_id, local_path, caption=caption,
                                      peer_type=peer_type, force_file=True)

    async def send_video(self, peer_id, local_path, caption="", peer_type=None):
        return await self.send_media(peer_id, local_path, caption=caption,
                                      peer_type=peer_type, force_file=False)

    # ------------------------------------------------------------------
    #  G1: Invite links
    # ------------------------------------------------------------------

    async def export_chat_invite(self, peer_id, title="", expire_date=0,
                                  usage_limit=0, request_needed=False,
                                  peer_type=None):
        """
        Create a chat invite link.

        Args:
            peer_id:        peer to create invite for.
            title:          optional link name (empty = default).
            expire_date:    unix timestamp (0 = never expires).
            usage_limit:    max uses (0 = unlimited).
            request_needed: if True, requires admin approval to join.
            peer_type:      "user" or "group".

        Returns:
            raw ExportedChatInvite bytes (parse 'link' field manually
            or use _extract_invite_link).
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)

        flags = 0
        extra = b""
        if expire_date:
            flags |= 0x1
            extra += struct.pack("<i", expire_date)
        if usage_limit:
            flags |= 0x2
            extra += struct.pack("<i", usage_limit)
        if request_needed:
            flags |= 0x8
        if title:
            flags |= 0x10
            extra += self._tl_string(title)

        body = (
            struct.pack("<I", TL_METHODS["messages.exportChatInvite"]) +
            struct.pack("<I", flags) +
            input_peer +
            extra
        )
        return await self._send_api_request(body, "messages.exportChatInvite")

    def _extract_invite_link(self, data):
        """Extract 'link' string from ExportedChatInvite response."""
        # chatInviteExported#a22cbd96 flags:# link:string ...
        if len(data) < 4:
            return None
        ctor = struct.unpack("<I", data[:4])[0]
        if ctor != 0xA22CBD96:
            return None
        offset = 4
        flags = struct.unpack("<I", data[offset:offset+4])[0]
        offset += 4
        # link:string (always present)
        try:
            link_len = data[offset]
            link = data[offset+1:offset+1+link_len].decode("utf-8", errors="ignore")
            return link
        except Exception:
            return None

    async def check_chat_invite(self, invite_hash):
        """Check if an invite link/hash is valid. Returns raw ChatInvite."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["messages.checkChatInvite"]) +
            self._tl_string(invite_hash)
        )
        return await self._send_api_request(body, "messages.checkChatInvite")

    async def import_chat_invite(self, invite_hash):
        """Join a chat using an invite hash."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["messages.importChatInvite"]) +
            self._tl_string(invite_hash)
        )
        return await self._send_api_request(body, "messages.importChatInvite")

    async def edit_chat_invite(self, peer_id, link, title="",
                                expire_date=0, usage_limit=0,
                                request_needed=None, revoked=False,
                                peer_type=None):
        """Edit an existing invite link."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)

        flags = 0
        extra = b""
        if expire_date:
            flags |= 0x1
            extra += struct.pack("<i", expire_date)
        if usage_limit:
            flags |= 0x2
            extra += struct.pack("<i", usage_limit)
        if revoked:
            flags |= 0x4
        if request_needed is not None:
            flags |= 0x8
            if request_needed:
                extra += struct.pack("<I", 0x997275B5)
            else:
                extra += struct.pack("<I", 0xBC799737)
        if title:
            flags |= 0x10
            extra += self._tl_string(title)

        body = (
            struct.pack("<I", TL_METHODS["messages.editExportedChatInvite"]) +
            struct.pack("<I", flags) +
            input_peer +
            self._tl_string(link) +
            extra
        )
        return await self._send_api_request(body, "messages.editExportedChatInvite")

    async def delete_chat_invite(self, peer_id, link, peer_type=None):
        """Delete an invite link."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        body = (
            struct.pack("<I", TL_METHODS["messages.deleteExportedChatInvite"]) +
            input_peer +
            self._tl_string(link)
        )
        return await self._send_api_request(body, "messages.deleteExportedChatInvite")

    async def get_chat_invites(self, peer_id, admin_id=None, limit=100,
                                revoked=False, offset_date=0, offset_link="",
                                peer_type=None):
        """List invite links for a chat."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)

        # admin_id is InputUser; default to self
        if admin_id is None:
            admin_id = self.session.user_id
        ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == admin_id:
                ah = d["access_hash"] or 0
                break
        input_admin = (
            struct.pack("<I", 0xF21158C6) +  # inputUser
            struct.pack("<q", admin_id) +
            struct.pack("<q", ah)
        )

        flags = 0
        offset_bytes = b""
        if offset_date or offset_link:
            flags |= 0x4
            offset_bytes += struct.pack("<i", offset_date)
            offset_bytes += self._tl_string(offset_link)
        if revoked:
            flags |= 0x8

        body = (
            struct.pack("<I", TL_METHODS["messages.getExportedChatInvites"]) +
            struct.pack("<I", flags) +
            input_peer +
            input_admin +
            offset_bytes +
            struct.pack("<i", limit)
        )
        return await self._send_api_request(body, "messages.getExportedChatInvites")

    # ------------------------------------------------------------------
    #  G2: Chat settings
    # ------------------------------------------------------------------

    async def edit_chat_title(self, channel_id, new_title):
        """Change chat/group title."""
        if not self._is_running:
            raise JetraError("Client not started.")
        ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == channel_id:
                ah = d["access_hash"] or 0
                break
        channel_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", ah)
        )
        body = (
            struct.pack("<I", TL_METHODS["channels.editTitle"]) +
            channel_input +
            self._tl_string(new_title)
        )
        return await self._send_api_request(body, "channels.editTitle")

    async def edit_chat_photo(self, channel_id, photo_path):
        """
        Set chat/group profile photo from a local file.

        Uploads the photo, then applies via channels.editPhoto.
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        # Upload the photo as inputFile
        upload_info = await self.upload_file(photo_path)
        input_file = upload_info["input_file"]

        # Build inputChatUploadedPhoto
        # inputChatUploadedPhoto#bdcd1e79 flags:# file:InputFile
        input_photo = (
            struct.pack("<I", 0xBDCD1E79) +
            struct.pack("<I", 0) +
            input_file
        )

        ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == channel_id:
                ah = d["access_hash"] or 0
                break
        channel_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", ah)
        )
        body = (
            struct.pack("<I", TL_METHODS["channels.editPhoto"]) +
            channel_input +
            input_photo
        )
        return await self._send_api_request(body, "channels.editPhoto")

    async def update_channel_username(self, channel_id, username):
        """Set or clear channel/group username."""
        if not self._is_running:
            raise JetraError("Client not started.")
        ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == channel_id:
                ah = d["access_hash"] or 0
                break
        channel_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", ah)
        )
        body = (
            struct.pack("<I", TL_METHODS["channels.updateUsername"]) +
            channel_input +
            self._tl_string(username)
        )
        return await self._send_api_request(body, "channels.updateUsername")

    async def check_channel_username(self, channel_id, username):
        """Check if a channel username is available."""
        if not self._is_running:
            raise JetraError("Client not started.")
        ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == channel_id:
                ah = d["access_hash"] or 0
                break
        channel_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", ah)
        )
        body = (
            struct.pack("<I", TL_METHODS["channels.checkUsername"]) +
            channel_input +
            self._tl_string(username)
        )
        try:
            await self._send_api_request(body, "channels.checkUsername")
            return True
        except JetraRPCError as e:
            msg = str(e)
            if "USERNAME_OCCUPIED" in msg or "USERNAME_INVALID" in msg:
                return False
            raise

    async def toggle_slow_mode(self, channel_id, seconds):
        """Enable slow mode (seconds = delay, 0 = disabled)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == channel_id:
                ah = d["access_hash"] or 0
                break
        channel_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", ah)
        )
        body = (
            struct.pack("<I", TL_METHODS["channels.toggleSlowMode"]) +
            channel_input +
            struct.pack("<i", seconds)
        )
        return await self._send_api_request(body, "channels.toggleSlowMode")

    async def toggle_signatures(self, channel_id, enabled=True,
                                 profiles_enabled=False):
        """Enable/disable message signatures in channel."""
        if not self._is_running:
            raise JetraError("Client not started.")
        ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == channel_id:
                ah = d["access_hash"] or 0
                break
        channel_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", ah)
        )
        flags = 0
        if enabled:
            flags |= 0x1
        if profiles_enabled:
            flags |= 0x2
        body = (
            struct.pack("<I", TL_METHODS["channels.toggleSignatures"]) +
            struct.pack("<I", flags) +
            channel_input
        )
        return await self._send_api_request(body, "channels.toggleSignatures")

    async def toggle_join_request(self, channel_id, enabled=True):
        """Require admin approval for new members."""
        if not self._is_running:
            raise JetraError("Client not started.")
        ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == channel_id:
                ah = d["access_hash"] or 0
                break
        channel_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", ah)
        )
        bool_true = 0x997275B5
        bool_false = 0xBC799737
        body = (
            struct.pack("<I", TL_METHODS["channels.toggleJoinRequest"]) +
            struct.pack("<I", 0) +  # flags
            channel_input +
            struct.pack("<I", bool_true if enabled else bool_false)
        )
        return await self._send_api_request(body, "channels.toggleJoinRequest")

    async def toggle_pre_history_hidden(self, channel_id, enabled=True):
        """Hide chat history from new members."""
        if not self._is_running:
            raise JetraError("Client not started.")
        ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == channel_id:
                ah = d["access_hash"] or 0
                break
        channel_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", ah)
        )
        bool_true = 0x997275B5
        bool_false = 0xBC799737
        body = (
            struct.pack("<I", TL_METHODS["channels.togglePreHistoryHidden"]) +
            channel_input +
            struct.pack("<I", bool_true if enabled else bool_false)
        )
        return await self._send_api_request(body, "channels.togglePreHistoryHidden")

    # ------------------------------------------------------------------
    #  G3: Participant details
    # ------------------------------------------------------------------

    async def get_participant(self, channel_id, user_id):
        """Get details for a single participant."""
        if not self._is_running:
            raise JetraError("Client not started.")
        ch_ah = 0
        user_ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == channel_id:
                ch_ah = d["access_hash"] or 0
            if d["peer_id"] == user_id:
                user_ah = d["access_hash"] or 0

        channel_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", ch_ah)
        )
        participant_input = (
            struct.pack("<I", INPUT_PEER_USER) +
            struct.pack("<Q", user_id) +
            struct.pack("<q", user_ah)
        )
        body = (
            struct.pack("<I", TL_METHODS["channels.getParticipant"]) +
            channel_input +
            participant_input
        )
        return await self._send_api_request(body, "channels.getParticipant")

    async def get_send_as(self, peer_id, peer_type=None):
        """Get peers you can send-as in a chat."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        body = (
            struct.pack("<I", TL_METHODS["channels.getSendAs"]) +
            struct.pack("<I", 0) +
            input_peer
        )
        return await self._send_api_request(body, "channels.getSendAs")

    # ------------------------------------------------------------------
    #  G4: Admin log and history
    # ------------------------------------------------------------------

    async def get_admin_log(self, channel_id, query="", limit=50):
        """Fetch admin log for a channel/group."""
        if not self._is_running:
            raise JetraError("Client not started.")
        ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == channel_id:
                ah = d["access_hash"] or 0
                break
        channel_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", ah)
        )
        body = (
            struct.pack("<I", TL_METHODS["channels.getAdminLog"]) +
            struct.pack("<I", 0) +  # flags
            channel_input +
            self._tl_string(query) +
            struct.pack("<q", 0) +  # max_id
            struct.pack("<q", 0) +  # min_id
            struct.pack("<i", limit)
        )
        return await self._send_api_request(body, "channels.getAdminLog")

    async def delete_channel_history(self, channel_id, for_everyone=True):
        """Delete all history of a channel/group."""
        if not self._is_running:
            raise JetraError("Client not started.")
        ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == channel_id:
                ah = d["access_hash"] or 0
                break
        channel_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", ah)
        )
        flags = 0x1 if for_everyone else 0
        body = (
            struct.pack("<I", TL_METHODS["channels.deleteHistory"]) +
            struct.pack("<I", flags) +
            channel_input +
            struct.pack("<i", 0)  # max_id
        )
        return await self._send_api_request(body, "channels.deleteHistory")

    async def delete_user_history(self, channel_id, user_id):
        """Delete history of a single user in a chat."""
        if not self._is_running:
            raise JetraError("Client not started.")
        ch_ah = 0
        user_ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == channel_id:
                ch_ah = d["access_hash"] or 0
            if d["peer_id"] == user_id:
                user_ah = d["access_hash"] or 0

        channel_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", ch_ah)
        )
        participant_input = (
            struct.pack("<I", INPUT_PEER_USER) +
            struct.pack("<Q", user_id) +
            struct.pack("<q", user_ah)
        )
        body = (
            struct.pack("<I", TL_METHODS["channels.deleteParticipantHistory"]) +
            channel_input +
            participant_input
        )
        return await self._send_api_request(body, "channels.deleteParticipantHistory")

    async def get_channel_messages(self, channel_id, message_ids):
        """Fetch messages from a channel by their IDs."""
        if not self._is_running:
            raise JetraError("Client not started.")
        ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == channel_id:
                ah = d["access_hash"] or 0
                break
        channel_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", ah)
        )
        # id: Vector<InputMessage> = Vector of inputMessage#a54f6b07 (id:int)
        INPUT_MESSAGE = 0xA676A322  # inputMessageID per schema.py
        items = b"".join(
            struct.pack("<I", INPUT_MESSAGE) + struct.pack("<i", mid)
            for mid in message_ids
        )
        vector = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(message_ids)) +
            items
        )
        body = (
            struct.pack("<I", TL_METHODS["channels.getMessages"]) +
            channel_input +
            vector
        )
        return await self._send_api_request(body, "channels.getMessages")

    async def read_channel_history(self, channel_id, max_id=0):
        """Mark channel messages as read."""
        if not self._is_running:
            raise JetraError("Client not started.")
        ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == channel_id:
                ah = d["access_hash"] or 0
                break
        channel_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", ah)
        )
        body = (
            struct.pack("<I", TL_METHODS["channels.readHistory"]) +
            channel_input +
            struct.pack("<i", max_id)
        )
        return await self._send_api_request(body, "channels.readHistory")

    async def get_left_channels(self, offset=0):
        """List channels/groups you have left."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["channels.getLeftChannels"]) +
            struct.pack("<i", offset)
        )
        return await self._send_api_request(body, "channels.getLeftChannels")

    # ------------------------------------------------------------------
    #  H: Privacy, birthday, emoji status
    # ------------------------------------------------------------------

    def _privacy_key_ctor(self, key_name):
        """Map a privacy key name to its InputPrivacyKey ctor."""
        keys = {
            "status_timestamp": 0x4F96CB18,       # last seen
            "chat_invite":      0xBDFB0426,       # who can add me to chats
            "phone_number":     0x0352DAFA,       # who can see my phone
            "profile_photo":    0x5719BACC,       # who can see profile photo
            "phone_call":       0xFABADC5F,       # who can call me
            "phone_p2p":        0xDB9E70D2,       # P2P calls
            "forwards":         0xA4DD4C08,       # who can forward my messages
            "birthday":         0xD65A11CC,       # who can see birthday
        }
        if key_name not in keys:
            raise ValueError(f"Unknown privacy key: {key_name}. Valid: {list(keys.keys())}")
        return keys[key_name]

    def _privacy_rules_ctors(self, rules):
        """
        Convert simple rule names to InputPrivacyRule ctors.

        Args:
            rules: list of strings like ["allow_all"], ["allow_contacts"],
                   ["disallow_all"].

        Returns:
            list of ctor IDs
        """
        rule_map = {
            "allow_all":         0x184B35CE,
            "allow_contacts":    0x0D09E07B,
            "disallow_all":      0xD66B66C9,
            "allow_close_friends": 0xEC3B12DE,
            "allow_premium":     0xCA4DAED5,
        }
        if not isinstance(rules, list):
            rules = [rules]
        result = []
        for r in rules:
            if r not in rule_map:
                raise ValueError(f"Unknown privacy rule: {r}. Valid: {list(rule_map.keys())}")
            result.append(rule_map[r])
        return result

    async def get_privacy(self, key_name):
        """
        Get privacy setting for a specific key.

        Args:
            key_name: one of "status_timestamp", "chat_invite",
                      "phone_number", "profile_photo", "phone_call",
                      "phone_p2p", "forwards", "birthday".

        Returns:
            raw account.privacyRules response.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        key_ctor = self._privacy_key_ctor(key_name)
        body = (
            struct.pack("<I", TL_METHODS["account.getPrivacy"]) +
            struct.pack("<I", key_ctor)
        )
        return await self._send_api_request(body, "account.getPrivacy")

    async def set_privacy(self, key_name, rules):
        """
        Set privacy rules for a key.

        Args:
            key_name: same as get_privacy.
            rules:    list of strings (e.g. ["allow_contacts"])
                      or single string.

        Returns:
            raw account.privacyRules response.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        key_ctor = self._privacy_key_ctor(key_name)
        rule_ctors = self._privacy_rules_ctors(rules)

        items = b"".join(struct.pack("<I", c) for c in rule_ctors)
        vector = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(rule_ctors)) +
            items
        )
        body = (
            struct.pack("<I", TL_METHODS["account.setPrivacy"]) +
            struct.pack("<I", key_ctor) +
            vector
        )
        return await self._send_api_request(body, "account.setPrivacy")

    async def update_birthday(self, day=0, month=0, year=0):
        """
        Update account birthday.

        Args:
            day, month: 1-indexed (day 1-31, month 1-12).
            year:       0 to hide year; otherwise 4-digit year.

        Returns:
            True on success.
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        if day == 0 and month == 0:
            # Clear birthday
            body = (
                struct.pack("<I", TL_METHODS["account.updateBirthday"]) +
                struct.pack("<I", 0)  # flags = no birthday
            )
            return await self._send_api_request(body, "account.updateBirthday")

        # Validate
        if not (1 <= day <= 31):
            raise ValueError(f"Invalid day: {day}")
        if not (1 <= month <= 12):
            raise ValueError(f"Invalid month: {month}")

        # birthday ctor: birthday#6c8e1e06 flags:# day:int month:int year:flags.0?int
        bday_flags = 0x1 if year else 0
        birthday = (
            struct.pack("<I", 0x6C8E1E06) +
            struct.pack("<I", bday_flags) +
            struct.pack("<i", day) +
            struct.pack("<i", month)
        )
        if year:
            birthday += struct.pack("<i", year)

        body = (
            struct.pack("<I", TL_METHODS["account.updateBirthday"]) +
            struct.pack("<I", 0x1) +  # flags = birthday present
            birthday
        )
        return await self._send_api_request(body, "account.updateBirthday")

    async def update_emoji_status(self, document_id, until=0):
        """
        Set a custom emoji status.

        Args:
            document_id: the document ID of the custom emoji.
            until:       unix timestamp until it expires (0 = forever).

        Returns:
            True on success.
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        # emojiStatus ctor
        status_flags = 0x1 if until else 0
        emoji_status = (
            struct.pack("<I", 0xE7FF068A) +
            struct.pack("<I", status_flags) +
            struct.pack("<q", document_id)
        )
        if until:
            emoji_status += struct.pack("<i", until)

        body = (
            struct.pack("<I", TL_METHODS["account.updateEmojiStatus"]) +
            emoji_status
        )
        return await self._send_api_request(body, "account.updateEmojiStatus")

    async def clear_emoji_status(self):
        """Clear current emoji status (reset to default)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        # emojiStatusEmpty#2de11aae
        body = (
            struct.pack("<I", TL_METHODS["account.updateEmojiStatus"]) +
            struct.pack("<I", 0x2DE11AAE)
        )
        return await self._send_api_request(body, "account.updateEmojiStatus")

    async def get_password_settings(self, password):
        """Get current 2FA password settings (needs password to decrypt)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        # This requires SRP proof first
        raise NotImplementedError(
            "get_password_settings requires SRP; use get_password() for state"
        )

    # ------------------------------------------------------------------
    #  I: Profile photos
    # ------------------------------------------------------------------

    async def upload_profile_photo(self, photo_path, fallback=False):
        """
        Set or update the current user's profile photo.

        Args:
            photo_path: path to image on disk.
            fallback:   if True, use as fallback photo (shown only
                        when main photo is hidden by privacy).

        Returns:
            dict with 'photo_id', 'access_hash', 'dc_id' or raw response.
        """
        import mimetypes

        if not self._is_running:
            raise JetraError("Client not started.")

        # Step 1: upload the image
        upload_info = await self.upload_file(photo_path)
        input_file_bytes = upload_info["input_file"]

        # Step 2: call photos.uploadProfilePhoto
        # Structure: flags:# fallback:flags.3?true bot:flags.5?InputUser
        #            file:flags.0?InputFile ...
        flags = 0x1  # file present
        if fallback:
            flags |= 0x8  # bit 3

        body = (
            struct.pack("<I", TL_METHODS["photos.uploadProfilePhoto"]) +
            struct.pack("<I", flags) +
            input_file_bytes
        )
        result = await self._send_api_request(body, "photos.uploadProfilePhoto")
        return self._parse_photos_photo(result)

    async def delete_profile_photo(self, photo_id, access_hash, file_reference=b""):
        """
        Delete a profile photo.

        Args:
            photo_id, access_hash, file_reference: from get_user_photos response.

        Returns:
            raw response (Vector<long>).
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        # Build InputPhoto
        input_photo = (
            struct.pack("<I", 0x3BB3B94A) +  # inputPhoto
            struct.pack("<q", photo_id) +
            struct.pack("<q", access_hash) +
            self._tl_bytes(file_reference)
        )
        vector = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", 1) +
            input_photo
        )
        body = (
            struct.pack("<I", TL_METHODS["photos.deletePhotos"]) +
            vector
        )
        return await self._send_api_request(body, "photos.deletePhotos")

    def _parse_photos_photo(self, data):
        """Parse photos.Photo response."""
        # photos.photo#20212ca8 photo:Photo users:Vector<User>
        if len(data) < 4:
            return None
        ctor = struct.unpack("<I", data[:4])[0]
        if ctor != 0x20212CA8:
            return {"raw_len": len(data), "ctor": ctor}

        offset = 4

        # photo:Photo
        photo_ctor = struct.unpack("<I", data[offset:offset+4])[0]
        offset += 4
        if photo_ctor != 0xFB197A65:  # photo
            return {"raw_len": len(data), "photo_ctor": photo_ctor}

        flags = struct.unpack("<I", data[offset:offset+4])[0]
        offset += 4
        photo_id = struct.unpack("<q", data[offset:offset+8])[0]
        offset += 8
        access_hash = struct.unpack("<q", data[offset:offset+8])[0]
        offset += 8
        fr_len = data[offset]
        if fr_len < 0xFE:
            offset += 1
        else:
            fr_len = int.from_bytes(data[offset+1:offset+4], "little")
            offset += 4
        file_reference = data[offset:offset+fr_len]
        offset += fr_len
        offset = (offset + 3) & ~3
        date = struct.unpack("<i", data[offset:offset+4])[0]
        offset += 4
        # sizes vector - skip
        # dc_id at end
        # for now return partial
        return {
            "photo_id": photo_id,
            "access_hash": access_hash,
            "file_reference": file_reference,
            "date": date,
        }

    # ------------------------------------------------------------------
    #  H2: Security (password, phone, email, account)
    # ------------------------------------------------------------------

    async def send_change_phone_code(self, new_phone):
        """Request code to change phone number. Phone must be +xxx format."""
        if not self._is_running:
            raise JetraError("Client not started.")
        if not new_phone.startswith("+"):
            new_phone = "+" + new_phone
        # codeSettings with default flags (allow_app_hash)
        settings = (
            struct.pack("<I", 0xAD253D78) +  # codeSettings
            struct.pack("<I", 0)             # flags
        )
        body = (
            struct.pack("<I", TL_METHODS["account.sendChangePhoneCode"]) +
            self._tl_string(new_phone) +
            settings
        )
        return await self._send_api_request(body, "account.sendChangePhoneCode")

    async def change_phone(self, new_phone, phone_code_hash, code):
        """
        Change account phone number.

        Args:
            new_phone:       new phone in +xxx format.
            phone_code_hash: from send_change_phone_code.
            code:            SMS code received.

        Returns:
            Parsed user dict or raw response.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        if not new_phone.startswith("+"):
            new_phone = "+" + new_phone
        body = (
            struct.pack("<I", TL_METHODS["account.changePhone"]) +
            self._tl_string(new_phone) +
            self._tl_string(phone_code_hash) +
            self._tl_string(code)
        )
        result = await self._send_api_request(body, "account.changePhone")
        users = self._extract_users(result)
        return users[0] if users else result

    async def verify_phone(self, phone, phone_code_hash, code):
        """Verify a phone (usually after change_phone failure with PHONE_VERIFICATION_NEEDED)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        if not phone.startswith("+"):
            phone = "+" + phone
        body = (
            struct.pack("<I", TL_METHODS["account.verifyPhone"]) +
            self._tl_string(phone) +
            self._tl_string(phone_code_hash) +
            self._tl_string(code)
        )
        return await self._send_api_request(body, "account.verifyPhone")

    async def send_verify_email_code(self, email, purpose=0x2A86654D):
        """
        Send email verification code.

        Args:
            email:   email address to verify.
            purpose: 0x2A86654D = emailVerifyPurposeLoginSetup (default)
                     0xEE86987D = emailVerifyPurposeLoginChange
                     0x1D4E7B58 = emailVerifyPurposePassport
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["account.sendVerifyEmailCode"]) +
            struct.pack("<I", purpose) +
            self._tl_string(email)
        )
        return await self._send_api_request(body, "account.sendVerifyEmailCode")

    async def verify_email(self, code, purpose=0x2A86654D):
        """
        Verify email with code.

        Args:
            code:    verification code from email.
            purpose: same as send_verify_email_code.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        # emailVerificationCode#922e6e10 code:string
        verification = (
            struct.pack("<I", 0x922E6E10) +
            self._tl_string(code)
        )
        body = (
            struct.pack("<I", TL_METHODS["account.verifyEmail"]) +
            struct.pack("<I", purpose) +
            verification
        )
        return await self._send_api_request(body, "account.verifyEmail")

    async def delete_account(self, reason="", password=None):
        """
        Delete the account.

        Args:
            reason:   deletion reason (free text).
            password: 2FA password (needed if 2FA is enabled).
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        flags = 0
        password_bytes = b""
        if password:
            # Need SRP proof
            pw_data = await self.get_password()
            pw_info = self._parse_account_password(pw_data)
            if not pw_info["has_password"]:
                raise JetraError("2FA not enabled but password provided")
            from pyjetra.userapi.srp import compute_srp
            algo = pw_info["current_algo"]
            srp_B = pw_info["srp_B"]
            srp_id = pw_info["srp_id"]
            proof = compute_srp(algo, srp_B, srp_id, password.encode("utf-8"))
            flags |= 0x1
            password_bytes = (
                struct.pack("<I", 0xD27FF082) +  # inputCheckPasswordSRP
                struct.pack("<q", proof["srp_id"]) +
                self._tl_bytes(proof["A"]) +
                self._tl_bytes(proof["M1"])
            )

        body = (
            struct.pack("<I", TL_METHODS["account.deleteAccount"]) +
            struct.pack("<I", flags) +
            self._tl_string(reason) +
            password_bytes
        )
        return await self._send_api_request(body, "account.deleteAccount")

    async def reset_authorizations(self):
        """Log out all other sessions (does not affect current session)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", TL_METHODS["auth.resetAuthorizations"])
        return await self._send_api_request(body, "auth.resetAuthorizations")

    async def confirm_password_email(self, code):
        """Confirm password recovery email with the code sent to it."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["account.confirmPasswordEmail"]) +
            self._tl_string(code)
        )
        return await self._send_api_request(body, "account.confirmPasswordEmail")

    async def resend_password_email(self):
        """Resend password recovery email."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", TL_METHODS["account.resendPasswordEmail"])
        return await self._send_api_request(body, "account.resendPasswordEmail")

    async def cancel_password_email(self):
        """Cancel password recovery email."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", TL_METHODS["account.cancelPasswordEmail"])
        return await self._send_api_request(body, "account.cancelPasswordEmail")

    # ------------------------------------------------------------------
    #  H3: Profile advanced
    # ------------------------------------------------------------------

    async def get_global_privacy(self):
        """Get global privacy settings (e.g. hide read receipts, non-contacts)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", TL_METHODS["account.getGlobalPrivacySettings"])
        return await self._send_api_request(body, "account.getGlobalPrivacySettings")

    async def set_global_privacy(self, archive_and_mute_new_noncontact=True,
                                  keep_archived_unmuted=False,
                                  keep_archived_folders=False,
                                  hide_read_marks=False,
                                  new_noncontact_peers_require_premium=False):
        """
        Set global privacy settings.

        Args:
            archive_and_mute_new_noncontact: auto-archive non-contacts
            keep_archived_unmuted:           keep archived chats unmuted
            keep_archived_folders:           keep folders archived
            hide_read_marks:                 hide read receipts (blue ticks)
            new_noncontact_peers_require_premium: require premium for new peers
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        # globalPrivacySettings#fe41b34f flags:#
        #   archive_and_mute_new_noncontact_peers:flags.0?true
        #   keep_archived_unmuted:flags.1?true
        #   keep_archived_folders:flags.2?true
        #   hide_read_marks:flags.3?true
        #   new_noncontact_peers_require_premium:flags.4?true
        flags = 0
        if archive_and_mute_new_noncontact:
            flags |= 0x1
        if keep_archived_unmuted:
            flags |= 0x2
        if keep_archived_folders:
            flags |= 0x4
        if hide_read_marks:
            flags |= 0x8
        if new_noncontact_peers_require_premium:
            flags |= 0x10

        settings = (
            struct.pack("<I", 0xFE41B34F) +
            struct.pack("<I", flags)
        )
        body = (
            struct.pack("<I", TL_METHODS["account.setGlobalPrivacySettings"]) +
            settings
        )
        return await self._send_api_request(body, "account.setGlobalPrivacySettings")

    async def toggle_username(self, username, active=True):
        """Enable/disable a specific username (if multiple are set)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        bool_true = 0x997275B5
        bool_false = 0xBC799737
        body = (
            struct.pack("<I", TL_METHODS["account.toggleUsername"]) +
            self._tl_string(username) +
            struct.pack("<I", bool_true if active else bool_false)
        )
        return await self._send_api_request(body, "account.toggleUsername")

    async def report_peer(self, peer_id, reason_ctor=0xAAB4CFA0, message="",
                          peer_type=None):
        """
        Report a peer.

        Args:
            reason_ctor: 0xAAB4CFA0 (spam), 0x3DB051BE (violence),
                         0x1A8B17AB (pornography), 0x58E36D13 (child abuse),
                         0xEEB2B30E (copyright), 0xFA01F2B4 (other)
            message:     optional description
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        reason = struct.pack("<I", reason_ctor)
        body = (
            struct.pack("<I", TL_METHODS["account.reportPeer"]) +
            input_peer +
            reason +
            self._tl_string(message)
        )
        return await self._send_api_request(body, "account.reportPeer")

    async def report_profile_photo(self, peer_id, photo_id, access_hash,
                                    file_reference=b"", reason_ctor=0xAAB4CFA0,
                                    message="", peer_type=None):
        """Report a profile photo of a peer."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        input_photo = (
            struct.pack("<I", 0x3BB3B94A) +
            struct.pack("<q", photo_id) +
            struct.pack("<q", access_hash) +
            self._tl_bytes(file_reference)
        )
        reason = struct.pack("<I", reason_ctor)
        body = (
            struct.pack("<I", TL_METHODS["account.reportProfilePhoto"]) +
            input_peer +
            input_photo +
            reason +
            self._tl_string(message)
        )
        return await self._send_api_request(body, "account.reportProfilePhoto")

    # ------------------------------------------------------------------
    #  H4: Appearance (themes, wallpapers, ringtones, emoji statuses)
    # ------------------------------------------------------------------

    async def get_themes(self, hash_val=0):
        """List available themes."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["account.getThemes"]) +
            self._tl_string("") +  # format empty
            struct.pack("<q", hash_val)
        )
        return await self._send_api_request(body, "account.getThemes")

    async def get_wallpapers(self, hash_val=0):
        """List available wallpapers."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["account.getWallPapers"]) +
            struct.pack("<q", hash_val)
        )
        return await self._send_api_request(body, "account.getWallPapers")

    async def get_saved_ringtones(self, hash_val=0):
        """List saved ringtones."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["account.getSavedRingtones"]) +
            struct.pack("<q", hash_val)
        )
        return await self._send_api_request(body, "account.getSavedRingtones")

    async def get_default_emoji_statuses(self, hash_val=0):
        """List default emoji statuses."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["account.getDefaultEmojiStatuses"]) +
            struct.pack("<q", hash_val)
        )
        return await self._send_api_request(body, "account.getDefaultEmojiStatuses")

    async def get_recent_emoji_statuses(self, hash_val=0):
        """List recent emoji statuses."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["account.getRecentEmojiStatuses"]) +
            struct.pack("<q", hash_val)
        )
        return await self._send_api_request(body, "account.getRecentEmojiStatuses")

    # ------------------------------------------------------------------
    #  H5: Account TTL and notify
    # ------------------------------------------------------------------

    async def get_account_ttl(self):
        """Get account TTL (auto-delete if inactive for N days)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", TL_METHODS["account.getAccountTTL"])
        return await self._send_api_request(body, "account.getAccountTTL")

    async def set_account_ttl(self, days):
        """
        Set account TTL in days.

        Args:
            days: 30, 90, 180, 365, or 730 (valid values per Telegram).
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        if days not in (30, 90, 180, 365, 730):
            raise ValueError("days must be one of: 30, 90, 180, 365, 730")
        ttl = (
            struct.pack("<I", 0xB8D0AFDF) +  # accountDaysTTL (Jetra ctor)
            struct.pack("<i", days)
        )
        body = (
            struct.pack("<I", TL_METHODS["account.setAccountTTL"]) +
            ttl
        )
        return await self._send_api_request(body, "account.setAccountTTL")

    async def set_authorization_ttl(self, days):
        """Set session TTL in days (auto-logout inactive sessions)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["account.setAuthorizationTTL"]) +
            struct.pack("<i", days)
        )
        return await self._send_api_request(body, "account.setAuthorizationTTL")

    async def get_notify_settings(self, peer_id, peer_type=None):
        """Get notification settings for a peer."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        notify_peer = (
            struct.pack("<I", 0xB8BC5B0C) +
            input_peer
        )
        body = (
            struct.pack("<I", TL_METHODS["account.getNotifySettings"]) +
            notify_peer
        )
        return await self._send_api_request(body, "account.getNotifySettings")

    async def reset_notify_settings(self):
        """Reset all notification settings to default."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", TL_METHODS["account.resetNotifySettings"])
        return await self._send_api_request(body, "account.resetNotifySettings")

    # ------------------------------------------------------------------
    #  P: 2FA password management (set / change / remove)
    # ------------------------------------------------------------------

    def _build_password_input_settings(self, new_algo, new_password, hint,
                                        email=None):
        """
        Build account.passwordInputSettings with new password hash.

        Per Telegram spec:
          1. Append 32 random bytes to salt1
          2. Compute x = PH2(password, new_salt1, salt2)
          3. Compute v = pow(g, x) mod p, padded to 256 bytes
          4. v is the new_password_hash

        new_algo: dict with salt1, salt2, g, p
        new_password: bytes (utf-8 encoded)
        hint: str (empty to use default)
        email: optional email string
        """
        import os
        from pyjetra.userapi.srp import compute_x

        # Step 1: append 32 random bytes to salt1
        new_salt1 = new_algo["salt1"] + os.urandom(32)

        # Step 2: compute x with new salt1
        x_int = compute_x(new_password, new_salt1, new_algo["salt2"])

        # Step 3: v = g^x mod p
        p_int = int.from_bytes(new_algo["p"], "big")
        g = new_algo["g"]
        v_int = pow(g, x_int, p_int)
        new_password_hash = v_int.to_bytes(256, "big")

        # Build new_algo with new_salt1
        new_algo_bytes = (
            struct.pack("<I", 0x3A912D4A) +  # passwordKdfAlgoSHA256...
            self._tl_bytes(new_salt1) +
            self._tl_bytes(new_algo["salt2"]) +
            struct.pack("<i", g) +
            self._tl_bytes(new_algo["p"])
        )

        # Build flags: bit 0 = new_algo + new_password_hash + hint
        flags = 0x1
        extra = b""
        extra += new_algo_bytes
        extra += self._tl_bytes(new_password_hash)
        extra += self._tl_string(hint or "")

        if email is not None:
            flags |= 0x2
            extra += self._tl_string(email)

        return (
            struct.pack("<I", 0xC23727C9) +  # account.passwordInputSettings
            struct.pack("<I", flags) +
            extra
        )

    async def set_password(self, new_password, hint="", email=None):
        """
        Set 2FA password on an account that has none.

        Args:
            new_password: password string.
            hint:         optional hint shown to user (empty = default).
            email:        optional recovery email (requires separate verify).

        Returns:
            True on success.
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        # Get current state
        pw_data = await self.get_password()
        pw_info = self._parse_account_password(pw_data)
        if pw_info.get("has_password"):
            raise JetraError(
                "Account already has 2FA password; use change_password instead"
            )

        # We need new_algo. current_algo is None (no password).
        # Account.getPassword returns 'new_algo' when has_password=False.
        # We need to parse it - our current parser only reads current_algo.
        # Let's re-parse raw to get new_algo.

        # Simpler: parse raw manually here
        # password ctor flags: bit0 = has_recovery, bit1 = has_secure, bit2 = has_password
        # if bit2 not set, then current_algo/srp_B/srp_id are absent
        # new_algo comes AFTER hint/email_unconfirmed_pattern (both optional)
        # Structure: ctor flags [current_algo srp_B srp_id] [hint] [email_unconfirmed_pattern] new_algo new_secure_algo secure_random ...

        # Let's use a helper to extract new_algo
        new_algo = self._extract_new_algo(pw_data)
        if not new_algo:
            raise JetraError("Could not extract new_algo from account.getPassword")

        # Build settings
        settings = self._build_password_input_settings(
            new_algo,
            new_password.encode("utf-8"),
            hint,
            email,
        )

        # No current password, so use inputCheckPasswordEmpty
        empty_pw = struct.pack("<I", 0x9880F658)

        body = (
            struct.pack("<I", TL_METHODS["account.updatePasswordSettings"]) +
            empty_pw +
            settings
        )
        return await self._send_api_request(body, "account.updatePasswordSettings")

    def _extract_new_algo(self, pw_data):
        """Extract new_algo from account.password response."""
        # Parse the full password object to find new_algo
        if len(pw_data) < 4:
            return None
        ctor = struct.unpack("<I", pw_data[:4])[0]
        if ctor != 0x957B50FB:
            return None

        offset = 4
        flags = struct.unpack("<I", pw_data[offset:offset+4])[0]
        offset += 4

        # If has_password (bit 2), skip current_algo, srp_B, srp_id
        if flags & 0x4:
            # Skip current_algo
            algo_ctor = struct.unpack("<I", pw_data[offset:offset+4])[0]
            offset += 4
            if algo_ctor == 0x3A912D4A:
                s1_len = pw_data[offset]
                offset += 1 + s1_len
                offset = (offset + 3) & ~3
                s2_len = pw_data[offset]
                offset += 1 + s2_len
                offset = (offset + 3) & ~3
                offset += 4  # g
                p_len = pw_data[offset]
                if p_len < 0xFE:
                    offset += 1
                else:
                    p_len = int.from_bytes(pw_data[offset+1:offset+4], "little")
                    offset += 4
                offset += p_len
                offset = (offset + 3) & ~3
            # Skip srp_B
            b_len = pw_data[offset]
            if b_len < 0xFE:
                offset += 1
            else:
                b_len = int.from_bytes(pw_data[offset+1:offset+4], "little")
                offset += 4
            offset += b_len
            offset = (offset + 3) & ~3
            # Skip srp_id
            offset += 8

        # Hint (bit 3)
        if flags & 0x8:
            h_len = pw_data[offset]
            offset += 1 + h_len
            offset = (offset + 3) & ~3

        # email_unconfirmed_pattern (bit 4)
        if flags & 0x10:
            e_len = pw_data[offset]
            offset += 1 + e_len
            offset = (offset + 3) & ~3

        # Now new_algo
        if offset + 4 > len(pw_data):
            return None
        algo_ctor = struct.unpack("<I", pw_data[offset:offset+4])[0]
        offset += 4
        if algo_ctor != 0x3A912D4A:
            return None
        s1_len = pw_data[offset]
        offset += 1
        salt1 = pw_data[offset:offset+s1_len]
        offset += s1_len
        offset = (offset + 3) & ~3
        s2_len = pw_data[offset]
        offset += 1
        salt2 = pw_data[offset:offset+s2_len]
        offset += s2_len
        offset = (offset + 3) & ~3
        g = struct.unpack("<i", pw_data[offset:offset+4])[0]
        offset += 4
        p_len = pw_data[offset]
        if p_len < 0xFE:
            offset += 1
        else:
            p_len = int.from_bytes(pw_data[offset+1:offset+4], "little")
            offset += 4
        p_bytes = pw_data[offset:offset+p_len]
        return {"salt1": salt1, "salt2": salt2, "g": g, "p": p_bytes}

    async def change_password(self, old_password, new_password, hint=""):
        """
        Change 2FA password (requires current password).

        Args:
            old_password: current password (string).
            new_password: new password (string).
            hint:         new hint.
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        from pyjetra.userapi.srp import compute_srp

        pw_data = await self.get_password()
        pw_info = self._parse_account_password(pw_data)
        if not pw_info.get("has_password"):
            raise JetraError(
                "Account has no 2FA; use set_password instead"
            )

        # Compute SRP proof for old password
        algo = pw_info["current_algo"]
        srp_B = pw_info["srp_B"]
        srp_id = pw_info["srp_id"]
        proof = compute_srp(algo, srp_B, srp_id, old_password.encode("utf-8"))

        # Compute new password hash using same algo
        new_algo = self._extract_new_algo(pw_data)
        if not new_algo:
            new_algo = algo  # fallback

        settings = self._build_password_input_settings(
            new_algo,
            new_password.encode("utf-8"),
            hint,
        )

        password_input = (
            struct.pack("<I", 0xD27FF082) +
            struct.pack("<q", proof["srp_id"]) +
            self._tl_bytes(proof["A"]) +
            self._tl_bytes(proof["M1"])
        )

        body = (
            struct.pack("<I", TL_METHODS["account.updatePasswordSettings"]) +
            password_input +
            settings
        )
        return await self._send_api_request(body, "account.updatePasswordSettings")

    async def remove_password(self, current_password):
        """
        Remove 2FA password from account.

        WARNING: As of Jetra layer 228, this operation returns boolTrue
        but the password is NOT actually removed on the server. This is
        a Jetra server limitation. Use the official Jetra app to remove
        2FA if needed. Kept here for future Jetra versions that may
        support it.

        Args:
            current_password: current 2FA password.
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        from pyjetra.userapi.srp import compute_srp

        pw_data = await self.get_password()
        pw_info = self._parse_account_password(pw_data)
        if not pw_info.get("has_password"):
            raise JetraError("Account has no 2FA to remove")

        algo = pw_info["current_algo"]
        srp_B = pw_info["srp_B"]
        srp_id = pw_info["srp_id"]
        proof = compute_srp(algo, srp_B, srp_id, current_password.encode("utf-8"))

        # Remove 2FA: flags=0x1 with new_algo, but empty new_password_hash
        # (new_algo with random salt, no password hash = no password)
        import os
        new_salt1 = os.urandom(32)
        new_salt2 = os.urandom(32)

        new_algo_bytes = (
            struct.pack("<I", 0x3A912D4A) +
            self._tl_bytes(new_salt1) +
            self._tl_bytes(new_salt2) +
            struct.pack("<i", algo["g"]) +
            self._tl_bytes(algo["p"])
        )

        settings = (
            struct.pack("<I", 0xC23727C9) +
            struct.pack("<I", 0x1) +
            new_algo_bytes +
            self._tl_bytes(b"") +  # empty new_password_hash
            self._tl_string("")     # empty hint
        )

        password_input = (
            struct.pack("<I", 0xD27FF082) +
            struct.pack("<q", proof["srp_id"]) +
            self._tl_bytes(proof["A"]) +
            self._tl_bytes(proof["M1"])
        )

        body = (
            struct.pack("<I", TL_METHODS["account.updatePasswordSettings"]) +
            password_input +
            settings
        )
        return await self._send_api_request(body, "account.updatePasswordSettings")

    # ------------------------------------------------------------------
    #  Additional group management
    # ------------------------------------------------------------------

    async def toggle_join_to_send(self, channel_id, enabled=True):
        """Require joining before sending messages in group."""
        if not self._is_running:
            raise JetraError("Client not started.")
        ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == channel_id:
                ah = d["access_hash"] or 0
                break
        channel_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", ah)
        )
        bool_true = 0x997275B5
        bool_false = 0xBC799737
        body = (
            struct.pack("<I", TL_METHODS["channels.toggleJoinToSend"]) +
            channel_input +
            struct.pack("<I", bool_true if enabled else bool_false)
        )
        return await self._send_api_request(body, "channels.toggleJoinToSend")

    async def toggle_participants_hidden(self, channel_id, enabled=True):
        """Hide participant list from non-admins."""
        if not self._is_running:
            raise JetraError("Client not started.")
        ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == channel_id:
                ah = d["access_hash"] or 0
                break
        channel_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", ah)
        )
        bool_true = 0x997275B5
        bool_false = 0xBC799737
        body = (
            struct.pack("<I", TL_METHODS["channels.toggleParticipantsHidden"]) +
            channel_input +
            struct.pack("<I", bool_true if enabled else bool_false)
        )
        return await self._send_api_request(body, "channels.toggleParticipantsHidden")

    async def toggle_anti_spam(self, channel_id, enabled=True):
        """Enable/disable automatic anti-spam."""
        if not self._is_running:
            raise JetraError("Client not started.")
        ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == channel_id:
                ah = d["access_hash"] or 0
                break
        channel_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", ah)
        )
        bool_true = 0x997275B5
        bool_false = 0xBC799737
        body = (
            struct.pack("<I", TL_METHODS["channels.toggleAntiSpam"]) +
            channel_input +
            struct.pack("<I", bool_true if enabled else bool_false)
        )
        return await self._send_api_request(body, "channels.toggleAntiSpam")

    async def set_discussion_group(self, channel_id, group_id):
        """
        Link a discussion group to a channel.

        Args:
            channel_id: broadcast channel.
            group_id:   supergroup to link as discussion.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        ch_ah = 0
        grp_ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == channel_id:
                ch_ah = d["access_hash"] or 0
            if d["peer_id"] == group_id:
                grp_ah = d["access_hash"] or 0

        channel_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", ch_ah)
        )
        group_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", group_id) +
            struct.pack("<q", grp_ah)
        )
        body = (
            struct.pack("<I", TL_METHODS["channels.setDiscussionGroup"]) +
            channel_input +
            group_input
        )
        return await self._send_api_request(body, "channels.setDiscussionGroup")

    async def convert_to_gigagroup(self, channel_id):
        """
        Convert a broadcast channel to a gigagroup (megagroup with unlimited members).

        IRREVERSIBLE. Requires admin rights.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == channel_id:
                ah = d["access_hash"] or 0
                break
        channel_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", ah)
        )
        body = (
            struct.pack("<I", TL_METHODS["channels.convertToGigagroup"]) +
            channel_input
        )
        return await self._send_api_request(body, "channels.convertToGigagroup")

    async def set_channel_stickers(self, channel_id, sticker_set_id=None,
                                    sticker_set_access_hash=0):
        """
        Set or clear the sticker set for a channel/group.

        Pass None for sticker_set_id to clear.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == channel_id:
                ah = d["access_hash"] or 0
                break
        channel_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", ah)
        )

        if sticker_set_id is None:
            stickers = struct.pack("<I", 0x0C1E9CC6)  # inputStickerSetEmpty
        else:
            stickers = (
                struct.pack("<I", 0xFFB62B5E) +  # inputStickerSetID
                struct.pack("<q", sticker_set_id) +
                struct.pack("<q", sticker_set_access_hash)
            )

        body = (
            struct.pack("<I", TL_METHODS["channels.setStickers"]) +
            channel_input +
            stickers
        )
        return await self._send_api_request(body, "channels.setStickers")

    async def get_admined_public_channels(self, by_location=False,
                                            check_limit=False,
                                            for_personal=False,
                                            for_community_peer=False):
        """
        List public channels you admin.

        Args:
            by_location:          filter by location.
            check_limit:          check username limit.
            for_personal:         only personal channels.
            for_community_peer:   only community channels.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        flags = 0
        if by_location:
            flags |= 0x1
        if check_limit:
            flags |= 0x2
        if for_personal:
            flags |= 0x4
        if for_community_peer:
            flags |= 0x8
        body = (
            struct.pack("<I", TL_METHODS["channels.getAdminedPublicChannels"]) +
            struct.pack("<I", flags)
        )
        return await self._send_api_request(body, "channels.getAdminedPublicChannels")

    async def delete_channel_messages(self, channel_id, message_ids, revoke=True):
        """Delete messages in a channel/group (channel-specific path)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == channel_id:
                ah = d["access_hash"] or 0
                break
        channel_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", ah)
        )
        ids_vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(message_ids)) +
            b"".join(struct.pack("<i", mid) for mid in message_ids)
        )
        # channels.deleteMessages: channel:InputChannel id:Vector<int>
        body = (
            struct.pack("<I", TL_METHODS["channels.deleteMessages"]) +
            channel_input +
            ids_vec
        )
        return await self._send_api_request(body, "channels.deleteMessages")

    async def report_channel_spam(self, channel_id, user_id, message_ids):
        """Report spam messages from a user in a channel."""
        if not self._is_running:
            raise JetraError("Client not started.")
        ch_ah = 0
        user_ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == channel_id:
                ch_ah = d["access_hash"] or 0
            if d["peer_id"] == user_id:
                user_ah = d["access_hash"] or 0

        channel_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", ch_ah)
        )
        participant_input = (
            struct.pack("<I", INPUT_PEER_USER) +
            struct.pack("<Q", user_id) +
            struct.pack("<q", user_ah)
        )
        ids_vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(message_ids)) +
            b"".join(struct.pack("<i", mid) for mid in message_ids)
        )
        body = (
            struct.pack("<I", TL_METHODS["channels.reportSpam"]) +
            channel_input +
            participant_input +
            ids_vec
        )
        return await self._send_api_request(body, "channels.reportSpam")

    async def export_message_link(self, channel_id, msg_id, grouped=False):
        """
        Get a direct link to a message in a channel/group.

        Args:
            channel_id: the channel/group id.
            msg_id:     message id.
            grouped:    if True, return link for grouped media.

        Returns:
            Raw messages.ExportedMessageLink response.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == channel_id:
                ah = d["access_hash"] or 0
                break
        channel_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", ah)
        )
        flags = 0x1 if grouped else 0
        body = (
            struct.pack("<I", TL_METHODS["channels.exportMessageLink"]) +
            struct.pack("<I", flags) +
            channel_input +
            struct.pack("<i", msg_id)
        )
        return await self._send_api_request(body, "channels.exportMessageLink")

    # ------------------------------------------------------------------
    #  Low-priority group methods
    # ------------------------------------------------------------------

    def _get_channel_input(self, channel_id):
        """Return serialized InputChannel for a channel id."""
        ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == channel_id:
                ah = d["access_hash"] or 0
                break
        return (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", ah)
        )

    async def toggle_channel_username(self, channel_id, username, active=True):
        """Enable/disable a specific username on a channel/group."""
        if not self._is_running:
            raise JetraError("Client not started.")
        channel_input = self._get_channel_input(channel_id)
        bool_true = 0x997275B5
        bool_false = 0xBC799737
        body = (
            struct.pack("<I", TL_METHODS["channels.toggleUsername"]) +
            channel_input +
            self._tl_string(username) +
            struct.pack("<I", bool_true if active else bool_false)
        )
        return await self._send_api_request(body, "channels.toggleUsername")

    async def reorder_channel_usernames(self, channel_id, usernames):
        """Reorder channel usernames (first = primary)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        channel_input = self._get_channel_input(channel_id)
        items = b"".join(self._tl_string(u) for u in usernames)
        vector = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(usernames)) +
            items
        )
        body = (
            struct.pack("<I", TL_METHODS["channels.reorderUsernames"]) +
            channel_input +
            vector
        )
        return await self._send_api_request(body, "channels.reorderUsernames")

    async def deactivate_all_usernames(self, channel_id):
        """Deactivate all usernames on a channel."""
        if not self._is_running:
            raise JetraError("Client not started.")
        channel_input = self._get_channel_input(channel_id)
        body = (
            struct.pack("<I", TL_METHODS["channels.deactivateAllUsernames"]) +
            channel_input
        )
        return await self._send_api_request(body, "channels.deactivateAllUsernames")

    async def update_channel_color(self, channel_id, color=0, background_emoji_id=0):
        """Update channel color / profile theme."""
        if not self._is_running:
            raise JetraError("Client not started.")
        channel_input = self._get_channel_input(channel_id)
        # peerColor#b54baccd flags:# color:flags.0?int background_emoji_id:flags.1?long
        flags = 0
        extra = b""
        if color:
            flags |= 0x1
            extra += struct.pack("<i", color)
        if background_emoji_id:
            flags |= 0x2
            extra += struct.pack("<q", background_emoji_id)
        peer_color = (
            struct.pack("<I", 0xB54BACCD) +
            struct.pack("<I", flags) +
            extra
        )
        body = (
            struct.pack("<I", TL_METHODS["channels.updateColor"]) +
            struct.pack("<I", 0x1) +  # flags: color present
            channel_input +
            peer_color
        )
        return await self._send_api_request(body, "channels.updateColor")

    async def update_channel_emoji_status(self, channel_id, document_id, until=0):
        """Update channel's emoji status."""
        if not self._is_running:
            raise JetraError("Client not started.")
        channel_input = self._get_channel_input(channel_id)
        status_flags = 0x1 if until else 0
        emoji_status = (
            struct.pack("<I", 0xE7FF068A) +
            struct.pack("<I", status_flags) +
            struct.pack("<q", document_id)
        )
        if until:
            emoji_status += struct.pack("<i", until)
        body = (
            struct.pack("<I", TL_METHODS["channels.updateEmojiStatus"]) +
            channel_input +
            emoji_status
        )
        return await self._send_api_request(body, "channels.updateEmojiStatus")

    async def set_main_profile_tab(self, channel_id, tab=0):
        """
        Set main profile tab (0 = posts, 1 = photos, 2 = files, ...).
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        channel_input = self._get_channel_input(channel_id)
        body = (
            struct.pack("<I", TL_METHODS["channels.setMainProfileTab"]) +
            channel_input +
            struct.pack("<i", tab)
        )
        return await self._send_api_request(body, "channels.setMainProfileTab")

    async def set_channel_emoji_stickers(self, channel_id, sticker_set_ids):
        """Set emoji sticker sets for a channel."""
        if not self._is_running:
            raise JetraError("Client not started.")
        channel_input = self._get_channel_input(channel_id)
        # Vector<InputStickerSet>
        items = b""
        for set_id, ah in sticker_set_ids:
            items += (
                struct.pack("<I", 0xFFB62B5E) +  # inputStickerSetID
                struct.pack("<q", set_id) +
                struct.pack("<q", ah)
            )
        vector = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(sticker_set_ids)) +
            items
        )
        body = (
            struct.pack("<I", TL_METHODS["channels.setEmojiStickers"]) +
            channel_input +
            vector
        )
        return await self._send_api_request(body, "channels.setEmojiStickers")

    async def edit_channel_location(self, channel_id, geo_point_bytes=None, address=""):
        """
        Update channel location.

        Args:
            geo_point_bytes: serialized InputGeoPoint (or None to clear).
            address:         text address.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        channel_input = self._get_channel_input(channel_id)
        flags = 0
        extra = b""
        if geo_point_bytes:
            flags |= 0x1
            extra += geo_point_bytes
        if address:
            flags |= 0x2
            extra += self._tl_string(address)
        body = (
            struct.pack("<I", TL_METHODS["channels.editLocation"]) +
            struct.pack("<I", flags) +
            channel_input +
            extra
        )
        return await self._send_api_request(body, "channels.editLocation")

    async def read_channel_message_contents(self, channel_id, message_ids):
        """Mark message contents (media) as read in a channel."""
        if not self._is_running:
            raise JetraError("Client not started.")
        channel_input = self._get_channel_input(channel_id)
        ids_vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(message_ids)) +
            b"".join(struct.pack("<i", mid) for mid in message_ids)
        )
        body = (
            struct.pack("<I", TL_METHODS["channels.readMessageContents"]) +
            channel_input +
            ids_vec
        )
        return await self._send_api_request(body, "channels.readMessageContents")

    async def get_channel_message_author(self, channel_id, msg_id):
        """Get author of a channel message (peer info)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        channel_input = self._get_channel_input(channel_id)
        body = (
            struct.pack("<I", TL_METHODS["channels.getMessageAuthor"]) +
            channel_input +
            struct.pack("<i", msg_id)
        )
        return await self._send_api_request(body, "channels.getMessageAuthor")

    # ------------------------------------------------------------------
    #  Reactions
    # ------------------------------------------------------------------

    async def send_reaction(self, peer_id, msg_id, emoji, big=False,
                             peer_type=None):
        """
        Send an emoji reaction to a message.

        WARNING: As of Jetra layer 228, this operation may return
        REACTION_INVALID for all emojis tested (getAvailableReactions
        returns a list, but sendReaction rejects them). This appears to
        be a Jetra server limitation. Kept here for future versions.

        Args:
            peer_id: peer of the message.
            msg_id:  message id.
            emoji:   emoji string (e.g. "👍") or empty to clear.
            big:     True for large animated reaction.
            peer_type: "user" or "group".
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)

        flags = 0
        if big:
            flags |= 0x2

        # reaction is Vector<Reaction> if flag.0 set
        if emoji:
            flags |= 0x1
            # reactionEmoji#1b2286b8 emoticon:string
            reaction_item = (
                struct.pack("<I", 0x1B2286B8) +
                self._tl_string(emoji)
            )
            reaction_vec = (
                struct.pack("<I", VECTOR_CTOR) +
                struct.pack("<i", 1) +
                reaction_item
            )
        else:
            reaction_vec = b""

        body = (
            struct.pack("<I", TL_METHODS["messages.sendReaction"]) +
            struct.pack("<I", flags) +
            input_peer +
            struct.pack("<i", msg_id) +
            reaction_vec
        )
        return await self._send_api_request(body, "messages.sendReaction")

    async def get_available_reactions(self):
        """Get list of available reactions."""
        if not self._is_running:
            raise JetraError("Client not started.")
        # messages.getAvailableReactions#18dea0ac hash:int
        body = (
            struct.pack("<I", TL_METHODS["messages.getAvailableReactions"]) +
            struct.pack("<i", 0)
        )
        return await self._send_api_request(body, "messages.getAvailableReactions")

    async def get_unread_reactions(self, peer_id, offset_id=0, add_offset=0,
                                     limit=50, max_id=0, min_id=0, peer_type=None):
        """Get unread reactions in a peer."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        body = (
            struct.pack("<I", TL_METHODS["messages.getUnreadReactions"]) +
            struct.pack("<I", 0) +
            input_peer +
            struct.pack("<i", offset_id) +
            struct.pack("<i", add_offset) +
            struct.pack("<i", limit) +
            struct.pack("<i", max_id) +
            struct.pack("<i", min_id)
        )
        return await self._send_api_request(body, "messages.getUnreadReactions")

    async def read_reactions(self, peer_id, peer_type=None, top_msg_id=None):
        """Mark all reactions in a peer as read."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        flags = 0
        top_bytes = b""
        if top_msg_id is not None:
            flags |= 0x1
            top_bytes = struct.pack("<i", top_msg_id)
        body = (
            struct.pack("<I", TL_METHODS["messages.readReactions"]) +
            struct.pack("<I", flags) +
            input_peer +
            top_bytes
        )
        return await self._send_api_request(body, "messages.readReactions")

    # ------------------------------------------------------------------
    #  Drafts
    # ------------------------------------------------------------------

    async def save_draft(self, peer_id, text="", reply_to_msg_id=0,
                          no_webpage=False, peer_type=None):
        """
        Save a draft message for a peer.

        Pass empty text to clear draft.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)

        # messages.saveDraft flags:# no_webpage:flags.1?true
        #   invert_media:flags.6?true reply_to:flags.4?InputReplyTo
        #   peer:InputPeer message:string ...
        outer_flags = 0
        extra = b""
        if reply_to_msg_id:
            outer_flags |= 0x10  # bit 4
            # inputReplyToMessage#3bd4b7c2 flags:# reply_to_msg_id:int
            extra += (
                struct.pack("<I", 0x3BD4B7C2) +
                struct.pack("<I", 0) +
                struct.pack("<i", reply_to_msg_id)
            )
        if no_webpage:
            outer_flags |= 0x2  # bit 1

        body = (
            struct.pack("<I", TL_METHODS["messages.saveDraft"]) +
            struct.pack("<I", outer_flags) +
            input_peer +
            self._tl_string(text) +
            extra
        )
        return await self._send_api_request(body, "messages.saveDraft")

    async def clear_draft(self, peer_id, peer_type=None):
        """Clear draft for a peer."""
        return await self.save_draft(peer_id, text="", peer_type=peer_type)

    async def get_all_drafts(self):
        """Get all draft messages."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", TL_METHODS["messages.getAllDrafts"])
        return await self._send_api_request(body, "messages.getAllDrafts")

    async def clear_all_drafts(self):
        """Clear all drafts."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", TL_METHODS["messages.clearAllDrafts"])
        return await self._send_api_request(body, "messages.clearAllDrafts")

    # ------------------------------------------------------------------
    #  Mentions
    # ------------------------------------------------------------------

    async def get_unread_mentions(self, peer_id, offset_id=0, add_offset=0,
                                    limit=50, max_id=0, min_id=0, peer_type=None):
        """Get unread mentions in a peer."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        body = (
            struct.pack("<I", TL_METHODS["messages.getUnreadMentions"]) +
            struct.pack("<I", 0) +
            input_peer +
            struct.pack("<i", offset_id) +
            struct.pack("<i", add_offset) +
            struct.pack("<i", limit) +
            struct.pack("<i", max_id) +
            struct.pack("<i", min_id)
        )
        return await self._send_api_request(body, "messages.getUnreadMentions")

    async def read_mentions(self, peer_id, peer_type=None, top_msg_id=None):
        """Mark all mentions in a peer as read."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        flags = 0
        top_bytes = b""
        if top_msg_id is not None:
            flags |= 0x1
            top_bytes = struct.pack("<i", top_msg_id)
        body = (
            struct.pack("<I", TL_METHODS["messages.readMentions"]) +
            struct.pack("<I", flags) +
            input_peer +
            top_bytes
        )
        return await self._send_api_request(body, "messages.readMentions")

    # ------------------------------------------------------------------
    #  Pinned Dialogs
    # ------------------------------------------------------------------

    async def get_pinned_dialogs(self, folder_id=0):
        """Get pinned dialogs in a folder."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["messages.getPinnedDialogs"]) +
            struct.pack("<i", folder_id)
        )
        return await self._send_api_request(body, "messages.getPinnedDialogs")

    async def toggle_dialog_pin(self, peer_id, pinned=True, peer_type=None):
        """Pin/unpin a dialog to the top of chat list."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)

        # inputDialogPeer#fcaafeb7 peer:InputPeer
        dialog_peer = (
            struct.pack("<I", 0xFCAAFEB7) +
            input_peer
        )
        body = (
            struct.pack("<I", TL_METHODS["messages.toggleDialogPin"]) +
            struct.pack("<I", 0x1 if pinned else 0) +
            dialog_peer
        )
        return await self._send_api_request(body, "messages.toggleDialogPin")

    async def reorder_pinned_dialogs(self, folder_id=0, peer_order=None):
        """Reorder pinned dialogs in a folder."""
        if not self._is_running:
            raise JetraError("Client not started.")
        # peer_order: list of (peer_id, peer_type)
        items = b""
        for pid, ptype in (peer_order or []):
            input_peer = self._get_input_peer(pid, ptype)
            items += (
                struct.pack("<I", 0xFCAAFEB7) +  # inputDialogPeer
                input_peer
            )
        vector = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(peer_order or [])) +
            items
        )
        body = (
            struct.pack("<I", TL_METHODS["messages.reorderPinnedDialogs"]) +
            struct.pack("<I", 0x1) +
            struct.pack("<i", folder_id) +
            vector
        )
        return await self._send_api_request(body, "messages.reorderPinnedDialogs")

    # ------------------------------------------------------------------
    #  Saved Messages
    # ------------------------------------------------------------------

    async def get_saved_history(self, offset_id=0, offset_date=0, add_offset=0,
                                  limit=100, max_id=0, min_id=0):
        """Get saved messages (Saved Messages chat history)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        me = await self.get_full_user()
        input_peer = self._get_input_peer(me["user_id"], "user")
        # messages.getSavedHistory flags:# parent_peer:flags.0?InputPeer peer:InputPeer
        body = (
            struct.pack("<I", TL_METHODS["messages.getSavedHistory"]) +
            struct.pack("<I", 0) +  # flags
            input_peer +
            struct.pack("<i", offset_id) +
            struct.pack("<i", offset_date) +
            struct.pack("<i", add_offset) +
            struct.pack("<i", limit) +
            struct.pack("<i", max_id) +
            struct.pack("<i", min_id) +
            struct.pack("<q", 0)
        )
        return await self._send_api_request(body, "messages.getSavedHistory")

    async def get_saved_dialogs(self, limit=100):
        """Get saved dialog list."""
        if not self._is_running:
            raise JetraError("Client not started.")
        # messages.getSavedDialogs flags:# ... offset_date:int offset_id:int
        #   offset_peer:InputPeer limit:int hash:long
        # Use inputPeerEmpty for offset_peer
        input_peer_empty = struct.pack("<I", 0x7DA07EC9)  # inputPeerEmpty
        body = (
            struct.pack("<I", TL_METHODS["messages.getSavedDialogs"]) +
            struct.pack("<I", 0) +  # flags
            struct.pack("<i", 0) +  # offset_date
            struct.pack("<i", 0) +  # offset_id
            input_peer_empty +
            struct.pack("<i", limit) +
            struct.pack("<q", 0)
        )
        return await self._send_api_request(body, "messages.getSavedDialogs")

    async def delete_saved_history(self):
        """Delete saved messages history."""
        if not self._is_running:
            raise JetraError("Client not started.")
        me = await self.get_full_user()
        input_peer = self._get_input_peer(me["user_id"], "user")
        body = (
            struct.pack("<I", TL_METHODS["messages.deleteSavedHistory"]) +
            input_peer +
            struct.pack("<i", 0)  # max_id
        )
        return await self._send_api_request(body, "messages.deleteSavedHistory")

    # ------------------------------------------------------------------
    #  Stickers
    # ------------------------------------------------------------------

    async def get_stickers(self, emoji):
        """
        Search stickers by emoji (e.g. "😀").

        Returns raw messages.Stickers response.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        # messages.getStickers#d5a5d3a1 emoticon:string hash:long
        body = (
            struct.pack("<I", TL_METHODS["messages.getStickers"]) +
            self._tl_string(emoji) +
            struct.pack("<q", 0)
        )
        return await self._send_api_request(body, "messages.getStickers")

    async def get_all_stickers(self, hash_val=0):
        """Get all installed sticker sets."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["messages.getAllStickers"]) +
            struct.pack("<q", hash_val)
        )
        return await self._send_api_request(body, "messages.getAllStickers")

    async def get_featured_stickers(self, hash_val=0):
        """Get featured (trending) sticker sets."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["messages.getFeaturedStickers"]) +
            struct.pack("<q", hash_val)
        )
        return await self._send_api_request(body, "messages.getFeaturedStickers")

    async def install_sticker_set(self, set_id, access_hash, archived=False):
        """Install a sticker set by id/hash."""
        if not self._is_running:
            raise JetraError("Client not started.")
        # inputStickerSetID#ffb62b5e id:long access_hash:long
        input_set = (
            struct.pack("<I", 0xFFB62B5E) +
            struct.pack("<q", set_id) +
            struct.pack("<q", access_hash)
        )
        body = (
            struct.pack("<I", TL_METHODS["messages.installStickerSet"]) +
            input_set +
            struct.pack("<I", 0x997275B5 if archived else 0xBC799737)
        )
        return await self._send_api_request(body, "messages.installStickerSet")

    # ------------------------------------------------------------------
    #  Bots
    # ------------------------------------------------------------------

    async def start_bot(self, bot_id, peer_id=None, start_param=None):
        """
        Start a bot conversation.

        Args:
            bot_id: the bot user id.
            peer_id: peer to send /start to (default: self).
            start_param: optional deep-link start parameter.
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        bot_ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == bot_id:
                bot_ah = d["access_hash"] or 0
                break
        bot_input = (
            struct.pack("<I", 0xF21158C6) +  # inputUser
            struct.pack("<q", bot_id) +
            struct.pack("<q", bot_ah)
        )

        if peer_id is None:
            me = await self.get_full_user()
            peer_id = me["user_id"]
        input_peer = self._get_input_peer(peer_id)

        random_id = random.getrandbits(63)
        flags = 0
        extra = b""
        if start_param:
            flags |= 0x1
            extra = self._tl_string(start_param)

        body = (
            struct.pack("<I", TL_METHODS["messages.startBot"]) +
            struct.pack("<I", flags) +
            bot_input +
            input_peer +
            struct.pack("<q", random_id) +
            extra
        )
        return await self._send_api_request(body, "messages.startBot")

    async def get_inline_bot_results(self, bot_id, query, offset=""):
        """Query inline results from a bot."""
        if not self._is_running:
            raise JetraError("Client not started.")
        bot_ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == bot_id:
                bot_ah = d["access_hash"] or 0
                break
        bot_input = (
            struct.pack("<I", 0xF21158C6) +
            struct.pack("<q", bot_id) +
            struct.pack("<q", bot_ah)
        )
        # geo_point + peer_type needed
        # messages.getInlineBotResults flags:# bot:InputUser peer:InputPeer
        #   geo_point:flags.0?InputGeoPoint query:string offset:string
        me = await self.get_full_user()
        my_input_peer = self._get_input_peer(me["user_id"], "user")
        body = (
            struct.pack("<I", TL_METHODS["messages.getInlineBotResults"]) +
            struct.pack("<I", 0) +  # flags
            bot_input +
            my_input_peer +
            self._tl_string(query) +
            self._tl_string(offset)
        )
        return await self._send_api_request(body, "messages.getInlineBotResults")

    async def get_bot_info(self, bot_id=None, lang_code=""):
        """Get info about a bot."""
        if not self._is_running:
            raise JetraError("Client not started.")
        flags = 0
        bot_bytes = b""
        if bot_id is not None:
            bot_ah = 0
            for d in self.db.get_dialogs():
                if d["peer_id"] == bot_id:
                    bot_ah = d["access_hash"] or 0
                    break
            bot_input = (
                struct.pack("<I", 0xF21158C6) +
                struct.pack("<q", bot_id) +
                struct.pack("<q", bot_ah)
            )
            flags |= 0x1
            bot_bytes = bot_input
        body = (
            struct.pack("<I", TL_METHODS["bots.getBotInfo"]) +
            struct.pack("<I", flags) +
            bot_bytes +
            self._tl_string(lang_code)
        )
        return await self._send_api_request(body, "bots.getBotInfo")

    # ------------------------------------------------------------------
    #  Albums / Multi-Media
    # ------------------------------------------------------------------

    async def send_album(self, peer_id, file_paths, caption="", peer_type=None):
        """
        Send multiple media as an album.

        Args:
            peer_id: target peer.
            file_paths: list of file paths.
            caption: applied to first media only.
            peer_type: "user" or "group".

        Returns:
            raw messages.sendMultiMedia response.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        if not file_paths:
            return b""

        input_peer = self._get_input_peer(peer_id, peer_type)

        # Upload each file and build inputSingleMedia for each
        import mimetypes
        items = []
        for idx, path in enumerate(file_paths):
            upload_info = await self.upload_file(path)
            input_file = upload_info["input_file"]

            mime, _ = mimetypes.guess_type(path)
            if not mime:
                mime = "application/octet-stream"

            media_type = self._guess_media_type(path)

            if media_type == "photo":
                input_media_uploaded = (
                    struct.pack("<I", 0x7D8375DA) +
                    struct.pack("<I", 0) +
                    input_file
                )
            else:
                filename_attr = (
                    struct.pack("<I", 0x15590068) +
                    self._tl_string(os.path.basename(path))
                )
                attrs = (
                    struct.pack("<I", VECTOR_CTOR) +
                    struct.pack("<i", 1) +
                    filename_attr
                )
                input_media_uploaded = (
                    struct.pack("<I", 0x037C9330) +
                    struct.pack("<I", 0) +
                    input_file +
                    self._tl_string(mime) +
                    attrs
                )

            # Register
            registered = await self._upload_media_register(
                peer_id, input_media_uploaded, peer_type
            )
            parsed = self._parse_message_media(registered)

            if parsed["type"] == "photo":
                input_photo = (
                    struct.pack("<I", 0x3BB3B94A) +
                    struct.pack("<q", parsed["id"]) +
                    struct.pack("<q", parsed["access_hash"]) +
                    self._tl_bytes(parsed["file_reference"])
                )
                final_media = (
                    struct.pack("<I", 0xE3AF4434) +
                    struct.pack("<I", 0) +
                    input_photo
                )
            else:
                input_doc = (
                    struct.pack("<I", 0x1ABFB575) +
                    struct.pack("<q", parsed["id"]) +
                    struct.pack("<q", parsed["access_hash"]) +
                    self._tl_bytes(parsed["file_reference"])
                )
                final_media = (
                    struct.pack("<I", 0xA8763AB5) +
                    struct.pack("<I", 0) +
                    input_doc
                )

            # inputSingleMedia#1cc6e91f flags:# media:InputMedia
            #   random_id:long message:string entities:flags.0?Vector<MessageEntity>
            random_id = random.getrandbits(63)
            msg = caption if idx == 0 else ""
            single = (
                struct.pack("<I", 0x1CC6E91F) +
                struct.pack("<I", 0) +  # flags
                final_media +
                struct.pack("<q", random_id) +
                self._tl_string(msg)
            )
            items.append(single)

        multi_vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(items)) +
            b"".join(items)
        )
        body = (
            struct.pack("<I", TL_METHODS["messages.sendMultiMedia"]) +
            struct.pack("<I", 0) +  # flags
            input_peer +
            multi_vec
        )
        return await self._send_api_request(body, "messages.sendMultiMedia")

    # ------------------------------------------------------------------
    #  Forum Topics
    # ------------------------------------------------------------------

    async def create_forum_topic(self, channel_id, title, icon_color=0,
                                   icon_emoji_id=0):
        """Create a forum topic in a supergroup."""
        if not self._is_running:
            raise JetraError("Client not started.")
        channel_input = self._get_channel_input(channel_id)
        # messages.createForumTopic flags:# channel:InputChannel
        #   title:string icon_color:flags.0?int icon_emoji_id:flags.1?long random_id:long
        flags = 0
        extra = b""
        if icon_color:
            flags |= 0x1
            extra += struct.pack("<i", icon_color)
        if icon_emoji_id:
            flags |= 0x2
            extra += struct.pack("<q", icon_emoji_id)
        random_id = random.getrandbits(63)
        body = (
            struct.pack("<I", TL_METHODS["messages.createForumTopic"]) +
            struct.pack("<I", flags) +
            channel_input +
            self._tl_string(title) +
            extra +
            struct.pack("<q", random_id)
        )
        return await self._send_api_request(body, "messages.createForumTopic")

    async def edit_forum_topic(self, channel_id, topic_id, title=None,
                                 icon_emoji_id=None, closed=None, hidden=None):
        """Edit a forum topic."""
        if not self._is_running:
            raise JetraError("Client not started.")
        channel_input = self._get_channel_input(channel_id)
        flags = 0
        extra = b""
        if title is not None:
            flags |= 0x1
            extra += self._tl_string(title)
        if icon_emoji_id is not None:
            flags |= 0x2
            extra += struct.pack("<q", icon_emoji_id)
        if closed is not None:
            flags |= 0x4
            if closed:
                extra += struct.pack("<I", 0x997275B5)
            else:
                extra += struct.pack("<I", 0xBC799737)
        if hidden is not None:
            flags |= 0x8
            if hidden:
                extra += struct.pack("<I", 0x997275B5)
            else:
                extra += struct.pack("<I", 0xBC799737)
        body = (
            struct.pack("<I", TL_METHODS["messages.editForumTopic"]) +
            struct.pack("<I", flags) +
            channel_input +
            struct.pack("<i", topic_id) +
            extra
        )
        return await self._send_api_request(body, "messages.editForumTopic")

    # ------------------------------------------------------------------
    #  Users extras
    # ------------------------------------------------------------------

    async def get_requirements_to_contact(self, user_id):
        """Check requirements to message a user (privacy)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == user_id:
                ah = d["access_hash"] or 0
                break
        user_input = (
            struct.pack("<I", 0xF21158C6) +
            struct.pack("<q", user_id) +
            struct.pack("<q", ah)
        )
        body = (
            struct.pack("<I", TL_METHODS["users.getRequirementsToContact"]) +
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", 1) +
            user_input
        )
        return await self._send_api_request(body, "users.getRequirementsToContact")

    # ------------------------------------------------------------------
    #  Help
    # ------------------------------------------------------------------

    async def get_app_config(self, hash_val=0):
        """Get app configuration (limits, features)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["help.getAppConfig"]) +
            struct.pack("<i", hash_val)
        )
        return await self._send_api_request(body, "help.getAppConfig")

    async def get_support(self, user_id=None):
        """Get support user info."""
        if not self._is_running:
            raise JetraError("Client not started.")
        ah = 0
        if user_id is not None:
            for d in self.db.get_dialogs():
                if d["peer_id"] == user_id:
                    ah = d["access_hash"] or 0
                    break
        # help.getSupport#9cdf08cd
        body = struct.pack("<I", TL_METHODS["help.getSupport"])
        return await self._send_api_request(body, "help.getSupport")

    # ------------------------------------------------------------------
    #  Contacts extras
    # ------------------------------------------------------------------

    async def resolve_phone(self, phone):
        """Resolve a phone number to user info."""
        if not self._is_running:
            raise JetraError("Client not started.")
        if not phone.startswith("+"):
            phone = "+" + phone
        body = (
            struct.pack("<I", TL_METHODS["contacts.resolvePhone"]) +
            self._tl_string(phone)
        )
        return await self._send_api_request(body, "contacts.resolvePhone")

    async def get_birthdays(self):
        """Get list of contacts' birthdays."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", TL_METHODS["contacts.getBirthdays"])
        return await self._send_api_request(body, "contacts.getBirthdays")

    async def get_top_peers(self, offset=0, limit=100, correspondents=False,
                            bots_pm=False, bots_inline=False, phone_calls=False,
                            forward_users=False, forward_chats=False,
                            groups=False, channels=False):
        """Get top peers (frequently contacted)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        flags = 0
        if correspondents: flags |= 0x1
        if bots_pm: flags |= 0x2
        if bots_inline: flags |= 0x4
        if phone_calls: flags |= 0x8
        if forward_users: flags |= 0x10
        if forward_chats: flags |= 0x20
        if groups: flags |= 0x400
        if channels: flags |= 0x800
        body = (
            struct.pack("<I", TL_METHODS["contacts.getTopPeers"]) +
            struct.pack("<I", flags) +
            struct.pack("<i", offset) +
            struct.pack("<i", limit) +
            struct.pack("<q", 0)
        )
        return await self._send_api_request(body, "contacts.getTopPeers")

    # ------------------------------------------------------------------
    #  Photos extras
    # ------------------------------------------------------------------

    async def delete_photos(self, photo_refs):
        """
        Delete photos from profile.

        Args:
            photo_refs: list of (photo_id, access_hash, file_reference_bytes)
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        items = b""
        for pid, ah, fr in photo_refs:
            items += (
                struct.pack("<I", 0x3BB3B94A) +
                struct.pack("<q", pid) +
                struct.pack("<q", ah) +
                self._tl_bytes(fr)
            )
        vector = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(photo_refs)) +
            items
        )
        body = (
            struct.pack("<I", TL_METHODS["photos.deletePhotos"]) +
            vector
        )
        return await self._send_api_request(body, "photos.deletePhotos")

    # ------------------------------------------------------------------
    #  Chatlists (folder invites)
    # ------------------------------------------------------------------

    def _build_input_chatlist(self, folder_id):
        """inputChatlistDialogFilter#f0e5b0a4 filter_id:int"""
        return (
            struct.pack("<I", 0xF0E5B0A4) +
            struct.pack("<i", folder_id)
        )

    async def export_chatlist_invite(self, folder_id, title, peer_ids):
        """
        Create an invite link for a chat folder (chatlist).

        Args:
            folder_id: folder id (1-255).
            title:     link title.
            peer_ids:  list of (peer_id, peer_type) to include.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        chatlist = self._build_input_chatlist(folder_id)
        items = b""
        for pid, ptype in peer_ids:
            items += self._get_input_peer(pid, ptype)
        peers_vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(peer_ids)) +
            items
        )
        body = (
            struct.pack("<I", TL_METHODS["chatlists.exportChatlistInvite"]) +
            chatlist +
            self._tl_string(title) +
            peers_vec
        )
        return await self._send_api_request(body, "chatlists.exportChatlistInvite")

    async def delete_exported_invite(self, folder_id, slug):
        """Delete a folder invite link."""
        if not self._is_running:
            raise JetraError("Client not started.")
        chatlist = self._build_input_chatlist(folder_id)
        body = (
            struct.pack("<I", TL_METHODS["chatlists.deleteExportedInvite"]) +
            chatlist +
            self._tl_string(slug)
        )
        return await self._send_api_request(body, "chatlists.deleteExportedInvite")

    async def edit_exported_invite(self, folder_id, slug, title=None, peer_ids=None):
        """Edit a folder invite link."""
        if not self._is_running:
            raise JetraError("Client not started.")
        chatlist = self._build_input_chatlist(folder_id)
        flags = 0
        extra = b""
        if title is not None:
            flags |= 0x2
            extra += self._tl_string(title)
        if peer_ids is not None:
            flags |= 0x4
            items = b"".join(self._get_input_peer(pid, ptype) for pid, ptype in peer_ids)
            extra += (
                struct.pack("<I", VECTOR_CTOR) +
                struct.pack("<i", len(peer_ids)) +
                items
            )
        body = (
            struct.pack("<I", TL_METHODS["chatlists.editExportedInvite"]) +
            struct.pack("<I", flags) +
            chatlist +
            self._tl_string(slug) +
            extra
        )
        return await self._send_api_request(body, "chatlists.editExportedInvite")

    async def get_exported_invites(self, folder_id):
        """List invite links for a folder."""
        if not self._is_running:
            raise JetraError("Client not started.")
        chatlist = self._build_input_chatlist(folder_id)
        body = (
            struct.pack("<I", TL_METHODS["chatlists.getExportedInvites"]) +
            chatlist
        )
        return await self._send_api_request(body, "chatlists.getExportedInvites")

    async def check_chatlist_invite(self, slug):
        """Check a folder invite link."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["chatlists.checkChatlistInvite"]) +
            self._tl_string(slug)
        )
        return await self._send_api_request(body, "chatlists.checkChatlistInvite")

    async def join_chatlist_invite(self, slug, peer_ids):
        """Join a folder via invite link, selecting some peers."""
        if not self._is_running:
            raise JetraError("Client not started.")
        items = b"".join(self._get_input_peer(pid, ptype) for pid, ptype in peer_ids)
        peers_vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(peer_ids)) +
            items
        )
        body = (
            struct.pack("<I", TL_METHODS["chatlists.joinChatlistInvite"]) +
            self._tl_string(slug) +
            peers_vec
        )
        return await self._send_api_request(body, "chatlists.joinChatlistInvite")

    async def get_leave_chatlist_suggestions(self, folder_id):
        """Get suggestions for which peers to leave from a folder."""
        if not self._is_running:
            raise JetraError("Client not started.")
        chatlist = self._build_input_chatlist(folder_id)
        body = (
            struct.pack("<I", TL_METHODS["chatlists.getLeaveChatlistSuggestions"]) +
            chatlist
        )
        return await self._send_api_request(body, "chatlists.getLeaveChatlistSuggestions")

    async def leave_chatlist(self, folder_id, peer_ids):
        """Leave folder, removing peers."""
        if not self._is_running:
            raise JetraError("Client not started.")
        chatlist = self._build_input_chatlist(folder_id)
        items = b"".join(self._get_input_peer(pid, ptype) for pid, ptype in peer_ids)
        peers_vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(peer_ids)) +
            items
        )
        body = (
            struct.pack("<I", TL_METHODS["chatlists.leaveChatlist"]) +
            chatlist +
            peers_vec
        )
        return await self._send_api_request(body, "chatlists.leaveChatlist")

    async def get_chatlist_updates(self, folder_id):
        """Get updates (new peers) for a folder."""
        if not self._is_running:
            raise JetraError("Client not started.")
        chatlist = self._build_input_chatlist(folder_id)
        body = (
            struct.pack("<I", TL_METHODS["chatlists.getChatlistUpdates"]) +
            chatlist
        )
        return await self._send_api_request(body, "chatlists.getChatlistUpdates")

    async def join_chatlist_updates(self, folder_id, peer_ids):
        """Join new peers added to a folder."""
        if not self._is_running:
            raise JetraError("Client not started.")
        chatlist = self._build_input_chatlist(folder_id)
        items = b"".join(self._get_input_peer(pid, ptype) for pid, ptype in peer_ids)
        peers_vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(peer_ids)) +
            items
        )
        body = (
            struct.pack("<I", TL_METHODS["chatlists.joinChatlistUpdates"]) +
            chatlist +
            peers_vec
        )
        return await self._send_api_request(body, "chatlists.joinChatlistUpdates")

    async def hide_chatlist_updates(self, folder_id):
        """Hide updates for a folder."""
        if not self._is_running:
            raise JetraError("Client not started.")
        chatlist = self._build_input_chatlist(folder_id)
        body = (
            struct.pack("<I", TL_METHODS["chatlists.hideChatlistUpdates"]) +
            chatlist
        )
        return await self._send_api_request(body, "chatlists.hideChatlistUpdates")

    # ------------------------------------------------------------------
    #  Langpack
    # ------------------------------------------------------------------

    async def get_languages(self, lang_pack="webk"):
        """Get available languages for a langpack."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["langpack.getLanguages"]) +
            self._tl_string(lang_pack)
        )
        return await self._send_api_request(body, "langpack.getLanguages")

    async def get_language(self, lang_pack="webk", lang_code="en"):
        """Get language info."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["langpack.getLanguage"]) +
            self._tl_string(lang_pack) +
            self._tl_string(lang_code)
        )
        return await self._send_api_request(body, "langpack.getLanguage")

    async def get_langpack(self, lang_pack="webk", lang_code="en"):
        """Get full language pack."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["langpack.getLangPack"]) +
            self._tl_string(lang_pack) +
            self._tl_string(lang_code)
        )
        return await self._send_api_request(body, "langpack.getLangPack")

    async def get_langpack_strings(self, keys, lang_pack="webk", lang_code="en"):
        """Get specific language strings."""
        if not self._is_running:
            raise JetraError("Client not started.")
        items = b"".join(self._tl_string(k) for k in keys)
        strings_vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(keys)) +
            items
        )
        body = (
            struct.pack("<I", TL_METHODS["langpack.getStrings"]) +
            self._tl_string(lang_pack) +
            self._tl_string(lang_code) +
            strings_vec
        )
        return await self._send_api_request(body, "langpack.getStrings")

    async def get_langpack_difference(self, from_version, lang_pack="webk", lang_code="en"):
        """Get language pack difference since a version."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["langpack.getDifference"]) +
            self._tl_string(lang_pack) +
            self._tl_string(lang_code) +
            struct.pack("<i", from_version)
        )
        return await self._send_api_request(body, "langpack.getDifference")

    # ------------------------------------------------------------------
    #  Folders
    # ------------------------------------------------------------------

    async def edit_peer_folders(self, folder_id, peer_ids):
        """
        Move peers to a folder (dialog filter).

        Args:
            folder_id: target folder id (0 = remove from all).
            peer_ids:  list of (peer_id, peer_type).
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        # inputFolderPeer#fbd2c296 peer:InputPeer folder_id:int
        items = b""
        for pid, ptype in peer_ids:
            input_peer = self._get_input_peer(pid, ptype)
            items += (
                struct.pack("<I", 0xFBD2C296) +
                input_peer +
                struct.pack("<i", folder_id)
            )
        folder_peers_vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(peer_ids)) +
            items
        )
        body = (
            struct.pack("<I", TL_METHODS["folders.editPeerFolders"]) +
            folder_peers_vec
        )
        return await self._send_api_request(body, "folders.editPeerFolders")

    # ------------------------------------------------------------------
    #  Communities
    # ------------------------------------------------------------------

    async def get_joined_communities(self):
        """Get list of communities you're a member of."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", TL_METHODS["communities.getJoinedCommunities"])
        return await self._send_api_request(body, "communities.getJoinedCommunities")

    # ------------------------------------------------------------------
    #  Stats
    # ------------------------------------------------------------------

    async def get_broadcast_stats(self, channel_id, dark=False):
        """Get statistics for a broadcast channel (requires admin)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        channel_input = self._get_channel_input(channel_id)
        flags = 0x1 if dark else 0
        body = (
            struct.pack("<I", TL_METHODS["stats.getBroadcastStats"]) +
            struct.pack("<I", flags) +
            channel_input
        )
        return await self._send_api_request(body, "stats.getBroadcastStats")

    async def get_megagroup_stats(self, channel_id, dark=False):
        """Get statistics for a megagroup (requires admin)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        channel_input = self._get_channel_input(channel_id)
        flags = 0x1 if dark else 0
        body = (
            struct.pack("<I", TL_METHODS["stats.getMegagroupStats"]) +
            struct.pack("<I", flags) +
            channel_input
        )
        return await self._send_api_request(body, "stats.getMegagroupStats")

    # ------------------------------------------------------------------
    #  Premium
    # ------------------------------------------------------------------

    async def get_my_boosts(self):
        """Get your boosts."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", TL_METHODS["premium.getMyBoosts"])
        return await self._send_api_request(body, "premium.getMyBoosts")

    async def get_boosts_status(self, peer_id, peer_type=None):
        """Get boost status for a peer."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        body = (
            struct.pack("<I", TL_METHODS["premium.getBoostsStatus"]) +
            input_peer
        )
        return await self._send_api_request(body, "premium.getBoostsStatus")

    # ------------------------------------------------------------------
    #  Phone (basic reads)
    # ------------------------------------------------------------------

    async def get_call_config(self):
        """Get call config (encryption, p2p settings)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", TL_METHODS["phone.getCallConfig"])
        return await self._send_api_request(body, "phone.getCallConfig")

    async def get_group_call_join_as(self, peer_id, peer_type=None):
        """Get peers you can join a group call as."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        body = (
            struct.pack("<I", TL_METHODS["phone.getGroupCallJoinAs"]) +
            input_peer
        )
        return await self._send_api_request(body, "phone.getGroupCallJoinAs")

    # ------------------------------------------------------------------
    #  Stories
    # ------------------------------------------------------------------

    async def get_all_stories(self, state="", next_page=False, hidden=False):
        """Get all stories (self + contacts)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        flags = 0
        if next_page:
            flags |= 0x2
        if hidden:
            flags |= 0x4
        if state:
            flags |= 0x1
            extra = self._tl_string(state)
        else:
            extra = b""
        body = (
            struct.pack("<I", TL_METHODS["stories.getAllStories"]) +
            struct.pack("<I", flags) +
            extra
        )
        return await self._send_api_request(body, "stories.getAllStories")

    async def get_peer_stories(self, peer_id, peer_type=None):
        """Get stories for a specific peer."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        body = (
            struct.pack("<I", TL_METHODS["stories.getPeerStories"]) +
            input_peer
        )
        return await self._send_api_request(body, "stories.getPeerStories")

    async def can_send_story(self, peer_id, peer_type=None):
        """Check if you can send a story for a peer."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        body = (
            struct.pack("<I", TL_METHODS["stories.canSendStory"]) +
            input_peer
        )
        return await self._send_api_request(body, "stories.canSendStory")

    # ------------------------------------------------------------------
    #  Ephemeral messages
    # ------------------------------------------------------------------

    async def send_ephemeral_message(self, peer_id, receiver_id, text,
                                      receiver_access_hash=0, peer_type=None):
        """
        Send an ephemeral message.

        Args:
            peer_id:             chat peer.
            receiver_id:         ephemeral receiver user id.
            text:                message text.
            receiver_access_hash: receiver's access_hash.
            peer_type:           "user" or "group".
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)

        input_user = (
            struct.pack("<I", 0xF21158C6) +
            struct.pack("<q", receiver_id) +
            struct.pack("<q", receiver_access_hash)
        )

        flags = 0
        random_id = random.getrandbits(63)
        body = (
            struct.pack("<I", TL_METHODS["ephemeral.sendMessage"]) +
            struct.pack("<I", flags) +
            input_peer +
            input_user +
            self._tl_string(text) +
            struct.pack("<q", random_id)
        )
        return await self._send_api_request(body, "ephemeral.sendMessage")

    async def delete_ephemeral_message(self, peer_id, receiver_id, msg_id,
                                        receiver_access_hash=0, peer_type=None):
        """Delete an ephemeral message."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        input_user = (
            struct.pack("<I", 0xF21158C6) +
            struct.pack("<q", receiver_id) +
            struct.pack("<q", receiver_access_hash)
        )
        body = (
            struct.pack("<I", TL_METHODS["ephemeral.deleteMessage"]) +
            input_peer +
            input_user +
            struct.pack("<i", msg_id)
        )
        return await self._send_api_request(body, "ephemeral.deleteMessage")

    # ------------------------------------------------------------------
    #  Stories (full)
    # ------------------------------------------------------------------

    async def activate_stealth_mode(self, past=False, future=False):
        """Activate stealth mode (hide view for 25 min)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        flags = 0
        if past: flags |= 0x1
        if future: flags |= 0x2
        body = (
            struct.pack("<I", TL_METHODS["stories.activateStealthMode"]) +
            struct.pack("<I", flags)
        )
        return await self._send_api_request(body, "stories.activateStealthMode")

    async def create_story_album(self, peer_id, title, story_ids, peer_type=None):
        """Create an album of stories."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        ids_vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(story_ids)) +
            b"".join(struct.pack("<i", sid) for sid in story_ids)
        )
        body = (
            struct.pack("<I", TL_METHODS["stories.createAlbum"]) +
            input_peer +
            self._tl_string(title) +
            ids_vec
        )
        return await self._send_api_request(body, "stories.createAlbum")

    async def delete_story_album(self, peer_id, album_id, peer_type=None):
        """Delete a story album."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        body = (
            struct.pack("<I", TL_METHODS["stories.deleteAlbum"]) +
            input_peer +
            struct.pack("<i", album_id)
        )
        return await self._send_api_request(body, "stories.deleteAlbum")

    async def delete_stories(self, peer_id, story_ids, peer_type=None):
        """Delete stories by id."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        ids_vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(story_ids)) +
            b"".join(struct.pack("<i", sid) for sid in story_ids)
        )
        body = (
            struct.pack("<I", TL_METHODS["stories.deleteStories"]) +
            input_peer +
            ids_vec
        )
        return await self._send_api_request(body, "stories.deleteStories")

    async def edit_story(self, peer_id, story_id, caption=None,
                          privacy_rules=None, peer_type=None):
        """Edit a story caption or privacy."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        flags = 0
        extra = b""
        if caption is not None:
            flags |= 0x2
            extra += self._tl_string(caption)
        if privacy_rules is not None:
            flags |= 0x4
            rule_items = b"".join(struct.pack("<I", r) for r in privacy_rules)
            extra += (
                struct.pack("<I", VECTOR_CTOR) +
                struct.pack("<i", len(privacy_rules)) +
                rule_items
            )
        body = (
            struct.pack("<I", TL_METHODS["stories.editStory"]) +
            struct.pack("<I", flags) +
            input_peer +
            struct.pack("<i", story_id) +
            extra
        )
        return await self._send_api_request(body, "stories.editStory")

    async def export_story_link(self, peer_id, story_id, peer_type=None):
        """Get a shareable link for a story."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        body = (
            struct.pack("<I", TL_METHODS["stories.exportStoryLink"]) +
            input_peer +
            struct.pack("<i", story_id)
        )
        return await self._send_api_request(body, "stories.exportStoryLink")

    async def get_album_stories(self, peer_id, album_id, offset=0, limit=50,
                                 peer_type=None):
        """Get stories in an album."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        body = (
            struct.pack("<I", TL_METHODS["stories.getAlbumStories"]) +
            input_peer +
            struct.pack("<i", album_id) +
            struct.pack("<i", offset) +
            struct.pack("<i", limit)
        )
        return await self._send_api_request(body, "stories.getAlbumStories")

    async def get_albums(self, peer_id, hash_val=0, peer_type=None):
        """Get albums for a peer."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        body = (
            struct.pack("<I", TL_METHODS["stories.getAlbums"]) +
            input_peer +
            struct.pack("<q", hash_val)
        )
        return await self._send_api_request(body, "stories.getAlbums")

    async def get_all_read_peer_stories(self):
        """Get peer ids of all stories you have read."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", TL_METHODS["stories.getAllReadPeerStories"])
        return await self._send_api_request(body, "stories.getAllReadPeerStories")

    async def get_chats_to_send(self):
        """Get chats to which you can send stories."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", TL_METHODS["stories.getChatsToSend"])
        return await self._send_api_request(body, "stories.getChatsToSend")

    async def get_peer_max_ids(self, peer_refs):
        """Get max story ids for multiple peers."""
        if not self._is_running:
            raise JetraError("Client not started.")
        items = b"".join(self._get_input_peer(pid, pt) for pid, pt in peer_refs)
        vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(peer_refs)) +
            items
        )
        body = (
            struct.pack("<I", TL_METHODS["stories.getPeerMaxIDs"]) +
            vec
        )
        return await self._send_api_request(body, "stories.getPeerMaxIDs")

    async def get_pinned_stories(self, peer_id, offset_id=0, limit=50, peer_type=None):
        """Get pinned stories for a peer."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        body = (
            struct.pack("<I", TL_METHODS["stories.getPinnedStories"]) +
            input_peer +
            struct.pack("<i", offset_id) +
            struct.pack("<i", limit)
        )
        return await self._send_api_request(body, "stories.getPinnedStories")

    async def get_stories_archive(self, peer_id, offset_id=0, limit=50, peer_type=None):
        """Get archived stories for a peer."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        body = (
            struct.pack("<I", TL_METHODS["stories.getStoriesArchive"]) +
            input_peer +
            struct.pack("<i", offset_id) +
            struct.pack("<i", limit)
        )
        return await self._send_api_request(body, "stories.getStoriesArchive")

    async def get_stories_by_id(self, peer_id, story_ids, peer_type=None):
        """Get specific stories by their ids."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        ids_vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(story_ids)) +
            b"".join(struct.pack("<i", sid) for sid in story_ids)
        )
        body = (
            struct.pack("<I", TL_METHODS["stories.getStoriesByID"]) +
            input_peer +
            ids_vec
        )
        return await self._send_api_request(body, "stories.getStoriesByID")

    async def get_stories_views(self, peer_id, story_ids, peer_type=None):
        """Get view counts for stories."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        ids_vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(story_ids)) +
            b"".join(struct.pack("<i", sid) for sid in story_ids)
        )
        body = (
            struct.pack("<I", TL_METHODS["stories.getStoriesViews"]) +
            input_peer +
            ids_vec
        )
        return await self._send_api_request(body, "stories.getStoriesViews")

    async def get_story_reactions_list(self, peer_id, story_id, limit=50,
                                        offset="", peer_type=None):
        """Get reactions on a story."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        flags = 0
        extra = b""
        if offset:
            flags |= 0x2
            extra += self._tl_string(offset)
        body = (
            struct.pack("<I", TL_METHODS["stories.getStoryReactionsList"]) +
            struct.pack("<I", flags) +
            input_peer +
            struct.pack("<i", story_id) +
            extra +
            struct.pack("<i", limit)
        )
        return await self._send_api_request(body, "stories.getStoryReactionsList")

    async def get_story_views_list(self, peer_id, story_id, offset="", limit=50,
                                     peer_type=None):
        """Get list of viewers for a story."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        body = (
            struct.pack("<I", TL_METHODS["stories.getStoryViewsList"]) +
            struct.pack("<I", 0) +  # flags
            input_peer +
            struct.pack("<i", story_id) +
            self._tl_string(offset) +
            struct.pack("<i", limit)
        )
        return await self._send_api_request(body, "stories.getStoryViewsList")

    async def increment_story_views(self, peer_id, story_ids, peer_type=None):
        """Increment view count for stories."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        ids_vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(story_ids)) +
            b"".join(struct.pack("<i", sid) for sid in story_ids)
        )
        body = (
            struct.pack("<I", TL_METHODS["stories.incrementStoryViews"]) +
            input_peer +
            ids_vec
        )
        return await self._send_api_request(body, "stories.incrementStoryViews")

    async def read_stories(self, peer_id, max_id, peer_type=None):
        """Mark stories as read up to max_id."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        body = (
            struct.pack("<I", TL_METHODS["stories.readStories"]) +
            input_peer +
            struct.pack("<i", max_id)
        )
        return await self._send_api_request(body, "stories.readStories")

    async def reorder_story_albums(self, peer_id, order, peer_type=None):
        """Reorder albums."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        order_vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(order)) +
            b"".join(struct.pack("<i", o) for o in order)
        )
        body = (
            struct.pack("<I", TL_METHODS["stories.reorderAlbums"]) +
            input_peer +
            order_vec
        )
        return await self._send_api_request(body, "stories.reorderAlbums")

    async def report_story(self, peer_id, story_ids, option, message="", peer_type=None):
        """Report stories."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        ids_vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(story_ids)) +
            b"".join(struct.pack("<i", sid) for sid in story_ids)
        )
        body = (
            struct.pack("<I", TL_METHODS["stories.report"]) +
            input_peer +
            ids_vec +
            self._tl_bytes(option) +
            self._tl_string(message)
        )
        return await self._send_api_request(body, "stories.report")

    async def send_story_reaction(self, peer_id, story_id, emoji, peer_type=None):
        """React to a story."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        reaction = (
            struct.pack("<I", 0x1B2286B8) +  # reactionEmoji
            self._tl_string(emoji)
        )
        body = (
            struct.pack("<I", TL_METHODS["stories.sendReaction"]) +
            struct.pack("<I", 0) +
            input_peer +
            struct.pack("<i", story_id) +
            reaction
        )
        return await self._send_api_request(body, "stories.sendReaction")

    async def toggle_all_stories_hidden(self, hidden=True):
        """Hide all stories (global toggle)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        bool_true = 0x997275B5
        bool_false = 0xBC799737
        body = (
            struct.pack("<I", TL_METHODS["stories.toggleAllStoriesHidden"]) +
            struct.pack("<I", bool_true if hidden else bool_false)
        )
        return await self._send_api_request(body, "stories.toggleAllStoriesHidden")

    async def toggle_peer_stories_hidden(self, peer_id, hidden=True, peer_type=None):
        """Hide stories from a specific peer."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        bool_true = 0x997275B5
        bool_false = 0xBC799737
        body = (
            struct.pack("<I", TL_METHODS["stories.togglePeerStoriesHidden"]) +
            input_peer +
            struct.pack("<I", bool_true if hidden else bool_false)
        )
        return await self._send_api_request(body, "stories.togglePeerStoriesHidden")

    async def toggle_story_pinned(self, peer_id, story_ids, pinned=True, peer_type=None):
        """Pin/unpin stories."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        ids_vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(story_ids)) +
            b"".join(struct.pack("<i", sid) for sid in story_ids)
        )
        body = (
            struct.pack("<I", TL_METHODS["stories.togglePinned"]) +
            input_peer +
            ids_vec +
            struct.pack("<I", 0x997275B5 if pinned else 0xBC799737)
        )
        return await self._send_api_request(body, "stories.togglePinned")

    async def toggle_pinned_to_top(self, peer_id, story_ids, peer_type=None):
        """Move pinned stories to top."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        ids_vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(story_ids)) +
            b"".join(struct.pack("<i", sid) for sid in story_ids)
        )
        body = (
            struct.pack("<I", TL_METHODS["stories.togglePinnedToTop"]) +
            input_peer +
            ids_vec
        )
        return await self._send_api_request(body, "stories.togglePinnedToTop")

    async def update_story_album(self, peer_id, album_id, title=None,
                                  delete_stories=None, add_stories=None,
                                  order=None, peer_type=None):
        """Update a story album."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        flags = 0
        extra = b""
        if title is not None:
            flags |= 0x1
            extra += self._tl_string(title)
        if delete_stories:
            flags |= 0x2
            extra += (
                struct.pack("<I", VECTOR_CTOR) +
                struct.pack("<i", len(delete_stories)) +
                b"".join(struct.pack("<i", s) for s in delete_stories)
            )
        if add_stories:
            flags |= 0x4
            extra += (
                struct.pack("<I", VECTOR_CTOR) +
                struct.pack("<i", len(add_stories)) +
                b"".join(struct.pack("<i", s) for s in add_stories)
            )
        if order:
            flags |= 0x8
            extra += (
                struct.pack("<I", VECTOR_CTOR) +
                struct.pack("<i", len(order)) +
                b"".join(struct.pack("<i", o) for o in order)
            )
        body = (
            struct.pack("<I", TL_METHODS["stories.updateAlbum"]) +
            struct.pack("<I", flags) +
            input_peer +
            struct.pack("<i", album_id) +
            extra
        )
        return await self._send_api_request(body, "stories.updateAlbum")

    # ------------------------------------------------------------------
    #  Payments (Stars)
    # ------------------------------------------------------------------

    async def get_stars_status(self, peer_id=None, ton=False, peer_type=None):
        """
        Get stars balance and status for a peer.

        Args:
            peer_id: target peer (default: self).
            ton:     if True, use TON instead of stars.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        if peer_id is None:
            me = await self.get_full_user()
            peer_id = me["user_id"]
            peer_type = "user"
        input_peer = self._get_input_peer(peer_id, peer_type)
        flags = 0x1 if ton else 0
        body = (
            struct.pack("<I", TL_METHODS["payments.getStarsStatus"]) +
            struct.pack("<I", flags) +
            input_peer
        )
        return await self._send_api_request(body, "payments.getStarsStatus")

    async def get_stars_topup_options(self):
        """Get available stars topup packages."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", TL_METHODS["payments.getStarsTopupOptions"])
        return await self._send_api_request(body, "payments.getStarsTopupOptions")

    async def get_stars_revenue_stats(self, peer_id=None, dark=False,
                                       ton=False, peer_type=None):
        """Get stars revenue stats for a channel/bot you own."""
        if not self._is_running:
            raise JetraError("Client not started.")
        if peer_id is None:
            me = await self.get_full_user()
            peer_id = me["user_id"]
            peer_type = "user"
        input_peer = self._get_input_peer(peer_id, peer_type)
        flags = 0
        if dark: flags |= 0x1
        if ton: flags |= 0x2
        body = (
            struct.pack("<I", TL_METHODS["payments.getStarsRevenueStats"]) +
            struct.pack("<I", flags) +
            input_peer
        )
        return await self._send_api_request(body, "payments.getStarsRevenueStats")

    async def get_stars_transactions(self, peer_id=None, inbound=False,
                                       outbound=False, ascending=False,
                                       ton=False, offset="", limit=50,
                                       peer_type=None):
        """Get stars transactions history."""
        if not self._is_running:
            raise JetraError("Client not started.")
        if peer_id is None:
            me = await self.get_full_user()
            peer_id = me["user_id"]
            peer_type = "user"
        input_peer = self._get_input_peer(peer_id, peer_type)
        flags = 0
        if inbound: flags |= 0x1
        if outbound: flags |= 0x2
        if ascending: flags |= 0x4
        if ton: flags |= 0x10
        body = (
            struct.pack("<I", TL_METHODS["payments.getStarsTransactions"]) +
            struct.pack("<I", flags) +
            input_peer +
            self._tl_string(offset) +
            struct.pack("<i", limit)
        )
        return await self._send_api_request(body, "payments.getStarsTransactions")

    async def get_stars_subscriptions(self, peer_id=None, missing_balance=False,
                                       offset="", peer_type=None):
        """Get stars subscriptions for a peer."""
        if not self._is_running:
            raise JetraError("Client not started.")
        if peer_id is None:
            me = await self.get_full_user()
            peer_id = me["user_id"]
            peer_type = "user"
        input_peer = self._get_input_peer(peer_id, peer_type)
        flags = 0x1 if missing_balance else 0
        body = (
            struct.pack("<I", TL_METHODS["payments.getStarsSubscriptions"]) +
            struct.pack("<I", flags) +
            input_peer +
            self._tl_string(offset)
        )
        return await self._send_api_request(body, "payments.getStarsSubscriptions")

    async def get_star_gifts(self, hash_val=0):
        """Get available star gifts (catalog)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["payments.getStarGifts"]) +
            struct.pack("<i", hash_val)
        )
        return await self._send_api_request(body, "payments.getStarGifts")

    async def get_premium_gift_code_options(self, boost_peer_id=None,
                                              boost_peer_type=None):
        """Get premium gift code options."""
        if not self._is_running:
            raise JetraError("Client not started.")
        flags = 0
        extra = b""
        if boost_peer_id is not None:
            flags |= 0x1
            extra = self._get_input_peer(boost_peer_id, boost_peer_type)
        body = (
            struct.pack("<I", TL_METHODS["payments.getPremiumGiftCodeOptions"]) +
            struct.pack("<I", flags) +
            extra
        )
        return await self._send_api_request(body, "payments.getPremiumGiftCodeOptions")

    # ------------------------------------------------------------------
    #  AI Compose
    # ------------------------------------------------------------------

    async def get_ai_tones(self, hash_val=0):
        """Get available AI compose tones."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["aicompose.getTones"]) +
            struct.pack("<q", hash_val)
        )
        return await self._send_api_request(body, "aicompose.getTones")

    async def get_ai_tone(self, tone_id, access_hash):
        """Get a specific AI tone."""
        if not self._is_running:
            raise JetraError("Client not started.")
        # inputAiComposeTone#... id:long access_hash:long
        tone = (
            struct.pack("<I", 0xF7A71E30) +
            struct.pack("<q", tone_id) +
            struct.pack("<q", access_hash)
        )
        body = (
            struct.pack("<I", TL_METHODS["aicompose.getTone"]) +
            tone
        )
        return await self._send_api_request(body, "aicompose.getTone")

    async def get_ai_tone_example(self, tone_id, access_hash, num=3):
        """Get example text for an AI tone."""
        if not self._is_running:
            raise JetraError("Client not started.")
        tone = (
            struct.pack("<I", 0xF7A71E30) +
            struct.pack("<q", tone_id) +
            struct.pack("<q", access_hash)
        )
        body = (
            struct.pack("<I", TL_METHODS["aicompose.getToneExample"]) +
            tone +
            struct.pack("<i", num)
        )
        return await self._send_api_request(body, "aicompose.getToneExample")

    # ------------------------------------------------------------------
    #  SMS Jobs
    # ------------------------------------------------------------------

    async def smsjobs_get_status(self):
        """Get SMS jobs status."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", TL_METHODS["smsjobs.getStatus"])
        return await self._send_api_request(body, "smsjobs.getStatus")

    async def smsjobs_is_eligible_to_join(self):
        """Check if eligible to join SMS jobs program."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", TL_METHODS["smsjobs.isEligibleToJoin"])
        return await self._send_api_request(body, "smsjobs.isEligibleToJoin")

    # ------------------------------------------------------------------
    #  Stickers
    # ------------------------------------------------------------------

    async def check_sticker_short_name(self, short_name):
        """Check sticker set short name availability."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["stickers.checkShortName"]) +
            self._tl_string(short_name)
        )
        return await self._send_api_request(body, "stickers.checkShortName")

    async def suggest_sticker_short_name(self, title):
        """Suggest a short name based on title."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["stickers.suggestShortName"]) +
            self._tl_string(title)
        )
        return await self._send_api_request(body, "stickers.suggestShortName")

    async def delete_sticker_set(self, set_id, access_hash):
        """Delete a sticker set you created."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_set = (
            struct.pack("<I", 0xFFB62B5E) +
            struct.pack("<q", set_id) +
            struct.pack("<q", access_hash)
        )
        body = (
            struct.pack("<I", TL_METHODS["stickers.deleteStickerSet"]) +
            input_set
        )
        return await self._send_api_request(body, "stickers.deleteStickerSet")

    async def rename_sticker_set(self, set_id, access_hash, new_title):
        """Rename a sticker set."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_set = (
            struct.pack("<I", 0xFFB62B5E) +
            struct.pack("<q", set_id) +
            struct.pack("<q", access_hash)
        )
        body = (
            struct.pack("<I", TL_METHODS["stickers.renameStickerSet"]) +
            input_set +
            self._tl_string(new_title)
        )
        return await self._send_api_request(body, "stickers.renameStickerSet")

    async def remove_sticker_from_set(self, sticker_doc_id, sticker_doc_ah,
                                       sticker_file_ref=b""):
        """Remove a sticker from a set."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_doc = (
            struct.pack("<I", 0x1ABFB575) +
            struct.pack("<q", sticker_doc_id) +
            struct.pack("<q", sticker_doc_ah) +
            self._tl_bytes(sticker_file_ref)
        )
        body = (
            struct.pack("<I", TL_METHODS["stickers.removeStickerFromSet"]) +
            input_doc
        )
        return await self._send_api_request(body, "stickers.removeStickerFromSet")

    async def change_sticker_position(self, sticker_doc_id, sticker_doc_ah,
                                        position, sticker_file_ref=b""):
        """Move a sticker to a new position in its set."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_doc = (
            struct.pack("<I", 0x1ABFB575) +
            struct.pack("<q", sticker_doc_id) +
            struct.pack("<q", sticker_doc_ah) +
            self._tl_bytes(sticker_file_ref)
        )
        body = (
            struct.pack("<I", TL_METHODS["stickers.changeStickerPosition"]) +
            input_doc +
            struct.pack("<i", position)
        )
        return await self._send_api_request(body, "stickers.changeStickerPosition")

    # ------------------------------------------------------------------
    #  Messages extras (chat management, views, gifs, previews)
    # ------------------------------------------------------------------

    async def delete_message_history(self, peer_id, just_clear=False,
                                       revoke=False, max_id=0, peer_type=None):
        """Delete message history in a chat."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        flags = 0
        if just_clear: flags |= 0x1
        if revoke: flags |= 0x2
        body = (
            struct.pack("<I", TL_METHODS["messages.deleteHistory"]) +
            struct.pack("<I", flags) +
            input_peer +
            struct.pack("<i", max_id)
        )
        return await self._send_api_request(body, "messages.deleteHistory")

    async def get_chats(self, chat_ids):
        """Get basic groups (not channels) by their ids."""
        if not self._is_running:
            raise JetraError("Client not started.")
        items = b"".join(struct.pack("<q", cid) for cid in chat_ids)
        vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(chat_ids)) +
            items
        )
        body = (
            struct.pack("<I", TL_METHODS["messages.getChats"]) +
            vec
        )
        return await self._send_api_request(body, "messages.getChats")

    async def get_full_chat(self, chat_id):
        """Get full info for a basic group."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["messages.getFullChat"]) +
            struct.pack("<q", chat_id)
        )
        return await self._send_api_request(body, "messages.getFullChat")



    async def add_chat_user(self, chat_id, user_id, fwd_limit=0):
        """Add user to a basic group."""
        if not self._is_running:
            raise JetraError("Client not started.")
        ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == user_id:
                ah = d["access_hash"] or 0
                break
        input_user = (
            struct.pack("<I", 0xF21158C6) +
            struct.pack("<q", user_id) +
            struct.pack("<q", ah)
        )
        body = (
            struct.pack("<I", TL_METHODS["messages.addChatUser"]) +
            struct.pack("<q", chat_id) +
            input_user +
            struct.pack("<i", fwd_limit)
        )
        return await self._send_api_request(body, "messages.addChatUser")

    async def delete_chat_user(self, chat_id, user_id):
        """Remove user from a basic group."""
        if not self._is_running:
            raise JetraError("Client not started.")
        ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == user_id:
                ah = d["access_hash"] or 0
                break
        input_user = (
            struct.pack("<I", 0xF21158C6) +
            struct.pack("<q", user_id) +
            struct.pack("<q", ah)
        )
        body = (
            struct.pack("<I", TL_METHODS["messages.deleteChatUser"]) +
            struct.pack("<q", chat_id) +
            input_user
        )
        return await self._send_api_request(body, "messages.deleteChatUser")

    async def create_basic_chat(self, title, user_ids):
        """Create a basic group chat (not megagroup)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        items = b""
        for uid in user_ids:
            ah = 0
            for d in self.db.get_dialogs():
                if d["peer_id"] == uid:
                    ah = d["access_hash"] or 0
                    break
            items += (
                struct.pack("<I", 0xF21158C6) +
                struct.pack("<q", uid) +
                struct.pack("<q", ah)
            )
        vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(user_ids)) +
            items
        )
        body = (
            struct.pack("<I", TL_METHODS["messages.createChat"]) +
            struct.pack("<I", 0) +
            self._tl_string(title) +
            vec
        )
        return await self._send_api_request(body, "messages.createChat")

    async def migrate_chat(self, chat_id):
        """Migrate a basic group to a megagroup."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["messages.migrateChat"]) +
            struct.pack("<q", chat_id)
        )
        return await self._send_api_request(body, "messages.migrateChat")

    async def get_messages_views(self, peer_id, message_ids, increment=False,
                                  peer_type=None):
        """Get view counts for messages."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        ids_vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(message_ids)) +
            b"".join(struct.pack("<i", mid) for mid in message_ids)
        )
        body = (
            struct.pack("<I", TL_METHODS["messages.getMessagesViews"]) +
            input_peer +
            ids_vec +
            struct.pack("<I", 0x997275B5 if increment else 0xBC799737)
        )
        return await self._send_api_request(body, "messages.getMessagesViews")

    async def report_spam(self, peer_id, peer_type=None):
        """Report spam for a chat (moves to spam folder)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        body = (
            struct.pack("<I", TL_METHODS["messages.reportSpam"]) +
            input_peer
        )
        return await self._send_api_request(body, "messages.reportSpam")

    async def report_messages(self, peer_id, message_ids, reason_ctor,
                               message="", peer_type=None):
        """Report messages in a chat."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        ids_vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(message_ids)) +
            b"".join(struct.pack("<i", mid) for mid in message_ids)
        )
        reason = struct.pack("<I", reason_ctor)
        body = (
            struct.pack("<I", TL_METHODS["messages.report"]) +
            input_peer +
            ids_vec +
            reason +
            self._tl_string(message)
        )
        return await self._send_api_request(body, "messages.report")

    async def read_message_contents(self, message_ids):
        """Mark messages contents (media) as read (non-channel)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        ids_vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(message_ids)) +
            b"".join(struct.pack("<i", mid) for mid in message_ids)
        )
        body = (
            struct.pack("<I", TL_METHODS["messages.readMessageContents"]) +
            ids_vec
        )
        return await self._send_api_request(body, "messages.readMessageContents")

    async def get_saved_gifs(self, hash_val=0):
        """Get saved GIFs."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["messages.getSavedGifs"]) +
            struct.pack("<q", hash_val)
        )
        return await self._send_api_request(body, "messages.getSavedGifs")

    async def save_gif(self, doc_id, doc_ah, file_ref=b"", unsave=False):
        """Save/unsave a GIF."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_doc = (
            struct.pack("<I", 0x1ABFB575) +
            struct.pack("<q", doc_id) +
            struct.pack("<q", doc_ah) +
            self._tl_bytes(file_ref)
        )
        body = (
            struct.pack("<I", TL_METHODS["messages.saveGif"]) +
            input_doc +
            struct.pack("<I", 0x997275B5 if unsave else 0xBC799737)
        )
        return await self._send_api_request(body, "messages.saveGif")

    async def search_global(self, query, limit=20):
        """Global message search across all chats."""
        if not self._is_running:
            raise JetraError("Client not started.")
        # messages.searchGlobal flags:# ... q:string filter:MessagesFilter
        #   min_date:int max_date:int offset_rate:int offset_peer:InputPeer
        #   offset_id:int limit:int
        body = (
            struct.pack("<I", TL_METHODS["messages.searchGlobal"]) +
            struct.pack("<I", 0) +              # flags
            self._tl_string(query) +
            struct.pack("<I", 0x57E2F66C) +     # inputMessagesFilterEmpty
            struct.pack("<i", 0) +              # min_date
            struct.pack("<i", 0) +              # max_date
            struct.pack("<i", 0) +              # offset_rate
            struct.pack("<I", 0x7DA07EC9) +     # inputPeerEmpty
            struct.pack("<i", 0) +              # offset_id
            struct.pack("<i", limit)
        )
        return await self._send_api_request(body, "messages.searchGlobal")

    async def get_sticker_set(self, set_id, access_hash, hash_val=0):
        """Get details of a sticker set."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_set = (
            struct.pack("<I", 0xFFB62B5E) +
            struct.pack("<q", set_id) +
            struct.pack("<q", access_hash)
        )
        body = (
            struct.pack("<I", TL_METHODS["messages.getStickerSet"]) +
            input_set +
            struct.pack("<i", hash_val)
        )
        return await self._send_api_request(body, "messages.getStickerSet")

    async def uninstall_sticker_set(self, set_id, access_hash):
        """Uninstall a sticker set."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_set = (
            struct.pack("<I", 0xFFB62B5E) +
            struct.pack("<q", set_id) +
            struct.pack("<q", access_hash)
        )
        body = (
            struct.pack("<I", TL_METHODS["messages.uninstallStickerSet"]) +
            input_set
        )
        return await self._send_api_request(body, "messages.uninstallStickerSet")

    async def get_webpage_preview(self, text):
        """Get preview data for a URL."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["messages.getWebPagePreview"]) +
            struct.pack("<I", 0) +  # flags
            self._tl_string(text)
        )
        return await self._send_api_request(body, "messages.getWebPagePreview")

    async def get_peer_settings(self, peer_id, peer_type=None):
        """Get privacy settings for a peer."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        body = (
            struct.pack("<I", TL_METHODS["messages.getPeerSettings"]) +
            input_peer
        )
        return await self._send_api_request(body, "messages.getPeerSettings")

    # ------------------------------------------------------------------
    #  Reactions extras
    # ------------------------------------------------------------------

    async def get_message_reactions_list(self, peer_id, msg_id, limit=50,
                                           offset="", peer_type=None):
        """Get reactions list for a specific message."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        flags = 0
        extra = b""
        if offset:
            flags |= 0x1
            extra += self._tl_string(offset)
        body = (
            struct.pack("<I", TL_METHODS["messages.getMessageReactionsList"]) +
            struct.pack("<I", flags) +
            input_peer +
            struct.pack("<i", msg_id) +
            extra +
            struct.pack("<i", limit)
        )
        return await self._send_api_request(body, "messages.getMessageReactionsList")

    async def get_top_reactions(self, limit=50):
        """Get top reactions globally."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["messages.getTopReactions"]) +
            struct.pack("<i", limit) +
            struct.pack("<q", 0)  # hash
        )
        return await self._send_api_request(body, "messages.getTopReactions")

    async def get_recent_reactions(self):
        """Get recent reactions."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["messages.getRecentReactions"]) +
            struct.pack("<i", 50) +  # limit
            struct.pack("<q", 0)     # hash
        )
        return await self._send_api_request(body, "messages.getRecentReactions")

    async def clear_recent_reactions(self):
        """Clear recent reactions."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", TL_METHODS["messages.clearRecentReactions"])
        return await self._send_api_request(body, "messages.clearRecentReactions")

    # ------------------------------------------------------------------
    #  Stories: send / live / search
    # ------------------------------------------------------------------

    async def send_story(self, peer_id, photo_path, caption="", period=86400,
                          pinned=False, noforwards=False, peer_type=None):
        """
        Send a story with a photo.

        Args:
            peer_id:     target peer (usually yourself).
            photo_path:  path to image.
            caption:     optional text.
            period:      lifetime in seconds (86400 = 24h, 21600 = 6h).
            pinned:      pin the story.
            noforwards:  prevent forwarding.
            peer_type:   "user" or "group".
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        # Upload photo
        upload_info = await self.upload_file(photo_path)
        input_file = upload_info["input_file"]

        # Build inputMediaUploadedPhoto
        input_media = (
            struct.pack("<I", 0x7D8375DA) +
            struct.pack("<I", 0) +
            input_file
        )

        # Register with uploadMedia to get MessageMedia
        input_peer = self._get_input_peer(peer_id, peer_type)
        registered = await self._upload_media_register(
            peer_id, input_media, peer_type
        )
        parsed = self._parse_message_media(registered)

        if parsed["type"] == "photo":
            input_photo = (
                struct.pack("<I", 0x3BB3B94A) +
                struct.pack("<q", parsed["id"]) +
                struct.pack("<q", parsed["access_hash"]) +
                self._tl_bytes(parsed["file_reference"])
            )
            final_media = (
                struct.pack("<I", 0xE3AF4434) +
                struct.pack("<I", 0) +
                input_photo
            )
        else:
            raise JetraError("Expected photo from uploadMedia")

        flags = 0
        if pinned:
            flags |= 0x4  # bit 2
        if noforwards:
            flags |= 0x10  # bit 4
        if caption:
            flags |= 0x1
        # period always (bit 3 = 0x8)
        flags |= 0x8

        # privacy_rules: allow_all (0x184B35CE)
        privacy_rule = struct.pack("<I", 0x184B35CE)  # inputPrivacyValueAllowAll
        rules_vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", 1) +
            privacy_rule
        )

        random_id = random.getrandbits(63)

        body = (
            struct.pack("<I", TL_METHODS["stories.sendStory"]) +
            struct.pack("<I", flags) +
            input_peer +
            final_media +
            (self._tl_string(caption) if caption else b"") +
            rules_vec +
            struct.pack("<q", random_id) +
            struct.pack("<i", period)
        )
        return await self._send_api_request(body, "stories.sendStory")

    async def search_stories(self, query="", hashtag=None, peer_id=None,
                              peer_type=None, offset="", limit=20):
        """Search stories (posts)."""
        if not self._is_running:
            raise JetraError("Client not started.")

        flags = 0
        extra = b""
        if hashtag:
            flags |= 0x1
            extra += self._tl_string(hashtag)
        if peer_id is not None:
            flags |= 0x4
            extra += self._get_input_peer(peer_id, peer_type)

        body = (
            struct.pack("<I", TL_METHODS["stories.searchPosts"]) +
            struct.pack("<I", flags) +
            extra +
            self._tl_string(offset) +
            struct.pack("<i", limit)
        )
        return await self._send_api_request(body, "stories.searchPosts")

    # ------------------------------------------------------------------
    #  Photos extras
    # ------------------------------------------------------------------

    async def update_profile_photo(self, photo_id, photo_ah, file_ref=b"",
                                    fallback=False):
        """Set existing photo as profile photo."""
        if not self._is_running:
            raise JetraError("Client not started.")

        input_photo = (
            struct.pack("<I", 0x3BB3B94A) +
            struct.pack("<q", photo_id) +
            struct.pack("<q", photo_ah) +
            self._tl_bytes(file_ref)
        )

        flags = 0x1 if fallback else 0
        body = (
            struct.pack("<I", TL_METHODS["photos.updateProfilePhoto"]) +
            struct.pack("<I", flags) +
            input_photo
        )
        return await self._send_api_request(body, "photos.updateProfilePhoto")

    async def upload_contact_profile_photo(self, user_id, photo_path,
                                            save=False, suggest=False,
                                            user_access_hash=0):
        """Upload a profile photo for a contact."""
        if not self._is_running:
            raise JetraError("Client not started.")

        upload_info = await self.upload_file(photo_path)
        input_file = upload_info["input_file"]

        input_user = (
            struct.pack("<I", 0xF21158C6) +
            struct.pack("<q", user_id) +
            struct.pack("<q", user_access_hash)
        )

        flags = 0
        if save:
            flags |= 0x10  # bit 4
        if suggest:
            flags |= 0x8   # bit 3
        # file always present (bit 0)
        flags |= 0x1

        body = (
            struct.pack("<I", TL_METHODS["photos.uploadContactProfilePhoto"]) +
            struct.pack("<I", flags) +
            input_user +
            input_file
        )
        return await self._send_api_request(body, "photos.uploadContactProfilePhoto")

    # ------------------------------------------------------------------
    #  Contacts extras
    # ------------------------------------------------------------------

    async def import_contacts(self, contacts):
        """
        Import multiple contacts.

        Args:
            contacts: list of (phone, first_name, last_name) tuples.

        Returns:
            Raw contacts.importedContacts response.
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        items = b""
        for phone, first, last in contacts:
            # inputPhoneContact#f392b7f4 flags:# client_id:long
            #   phone:string first_name:string last_name:string
            client_id = random.getrandbits(63)
            items += (
                struct.pack("<I", 0xF392B7F4) +
                struct.pack("<I", 0) +
                struct.pack("<q", client_id) +
                self._tl_string(phone) +
                self._tl_string(first) +
                self._tl_string(last)
            )
        vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(contacts)) +
            items
        )
        body = (
            struct.pack("<I", TL_METHODS["contacts.importContacts"]) +
            vec
        )
        return await self._send_api_request(body, "contacts.importContacts")

    async def get_contact_statuses(self):
        """Get online/offline status of contacts."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", TL_METHODS["contacts.getStatuses"])
        return await self._send_api_request(body, "contacts.getStatuses")

    async def get_contact_ids(self, hash_val=0):
        """Get list of contact user ids."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["contacts.getContactIDs"]) +
            struct.pack("<q", hash_val)
        )
        return await self._send_api_request(body, "contacts.getContactIDs")

    async def get_located_contacts(self, lat, long, accuracy_radius=500,
                                     self_expires=0):
        """
        Get contacts nearby a location.

        Args:
            lat: latitude (float).
            long: longitude (float).
            accuracy_radius: radius in meters.
            self_expires: seconds until self-broadcast expires.
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        # inputGeoPoint#48222faf flags:# lat:double long:double
        #   accuracy_radius:flags.0?int
        geo_flags = 0x1 if accuracy_radius else 0
        geo = (
            struct.pack("<I", 0x48222FAF) +
            struct.pack("<I", geo_flags) +
            struct.pack("<d", lat) +
            struct.pack("<d", long)
        )
        if accuracy_radius:
            geo += struct.pack("<i", accuracy_radius)

        flags = 0
        extra = b""
        if self_expires:
            flags |= 0x1
            extra = struct.pack("<i", self_expires)

        body = (
            struct.pack("<I", TL_METHODS["contacts.getLocated"]) +
            struct.pack("<I", flags) +
            geo +
            extra
        )
        return await self._send_api_request(body, "contacts.getLocated")

    async def update_contact_note(self, user_id, note_text,
                                    user_access_hash=0):
        """Set a private note for a contact."""
        if not self._is_running:
            raise JetraError("Client not started.")

        input_user = (
            struct.pack("<I", 0xF21158C6) +
            struct.pack("<q", user_id) +
            struct.pack("<q", user_access_hash)
        )

        # textWithEntities#751f3146 text:string entities:Vector<MessageEntity>
        note = (
            struct.pack("<I", 0x751F3146) +
            self._tl_string(note_text) +
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", 0)
        )

        body = (
            struct.pack("<I", TL_METHODS["contacts.updateContactNote"]) +
            input_user +
            note
        )
        return await self._send_api_request(body, "contacts.updateContactNote")

    async def accept_contact_request(self, user_id, user_access_hash=0):
        """Accept a contact request."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_user = (
            struct.pack("<I", 0xF21158C6) +
            struct.pack("<q", user_id) +
            struct.pack("<q", user_access_hash)
        )
        body = (
            struct.pack("<I", TL_METHODS["contacts.acceptContact"]) +
            input_user
        )
        return await self._send_api_request(body, "contacts.acceptContact")

    async def block_from_replies(self, msg_id, delete_message=False,
                                   delete_history=False, report_spam=False):
        """Block user who replied to a message."""
        if not self._is_running:
            raise JetraError("Client not started.")
        flags = 0
        if delete_message: flags |= 0x1
        if delete_history: flags |= 0x2
        if report_spam: flags |= 0x4
        body = (
            struct.pack("<I", TL_METHODS["contacts.blockFromReplies"]) +
            struct.pack("<I", flags) +
            struct.pack("<i", msg_id)
        )
        return await self._send_api_request(body, "contacts.blockFromReplies")

    async def delete_contacts_by_phones(self, phones):
        """Delete contacts by their phone numbers."""
        if not self._is_running:
            raise JetraError("Client not started.")
        items = b"".join(self._tl_string(p) for p in phones)
        vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(phones)) +
            items
        )
        body = (
            struct.pack("<I", TL_METHODS["contacts.deleteByPhones"]) +
            vec
        )
        return await self._send_api_request(body, "contacts.deleteByPhones")

    async def get_saved_contacts(self):
        """Get saved (starred) contacts."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", TL_METHODS["contacts.getSaved"])
        return await self._send_api_request(body, "contacts.getSaved")

    async def reset_top_peer_rating(self, peer_id, category_ctor,
                                     peer_type=None):
        """
        Reset top peer rating for a specific peer.

        category_ctor: 0xB3134D9D (correspondents), 0x6F02F748 (bots_pm),
                       0xA0051AB8 (bots_inline), 0xAB7EC0A0 (groups),
                       0x3C2E5D9D (channels), 0x1CB56A5D (phone_calls),
                       0x4529F2A8 (forward_users), 0x4A8D8B4 (forward_chats)
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        body = (
            struct.pack("<I", TL_METHODS["contacts.resetTopPeerRating"]) +
            struct.pack("<I", category_ctor) +
            input_peer
        )
        return await self._send_api_request(body, "contacts.resetTopPeerRating")

    # ------------------------------------------------------------------
    #  Stickers (create/edit)
    # ------------------------------------------------------------------

    async def create_sticker_set(self, user_id, title, short_name, stickers,
                                   user_access_hash=0, masks=False, emojis=False):
        """
        Create a new sticker set.

        Args:
            user_id: creator user id (usually self).
            title: sticker set title.
            short_name: short name (alphanumeric).
            stickers: list of (doc_id, doc_ah, file_ref, emoji) tuples.
            masks: True for mask set.
            emojis: True for custom emoji set.
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        input_user = (
            struct.pack("<I", 0xF21158C6) +
            struct.pack("<q", user_id) +
            struct.pack("<q", user_access_hash)
        )

        flags = 0
        if masks: flags |= 0x1
        if emojis: flags |= 0x20

        items = b""
        for doc_id, doc_ah, file_ref, emoji in stickers:
            input_doc = (
                struct.pack("<I", 0x1ABFB575) +
                struct.pack("<q", doc_id) +
                struct.pack("<q", doc_ah) +
                self._tl_bytes(file_ref)
            )
            # inputStickerSetItem#3282a1a flags:#
            #   document:InputDocument emoji:string mask_coords:flags.0?MaskCoords
            items += (
                struct.pack("<I", 0x0328A21A) +
                struct.pack("<I", 0) +
                input_doc +
                self._tl_string(emoji)
            )
        vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(stickers)) +
            items
        )

        body = (
            struct.pack("<I", TL_METHODS["stickers.createStickerSet"]) +
            struct.pack("<I", flags) +
            input_user +
            self._tl_string(title) +
            self._tl_string(short_name) +
            vec
        )
        return await self._send_api_request(body, "stickers.createStickerSet")

    async def add_sticker_to_set(self, set_id, set_ah, doc_id, doc_ah,
                                    file_ref, emoji):
        """Add a sticker to existing set."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_set = (
            struct.pack("<I", 0xFFB62B5E) +
            struct.pack("<q", set_id) +
            struct.pack("<q", set_ah)
        )
        input_doc = (
            struct.pack("<I", 0x1ABFB575) +
            struct.pack("<q", doc_id) +
            struct.pack("<q", doc_ah) +
            self._tl_bytes(file_ref)
        )
        sticker_item = (
            struct.pack("<I", 0x0328A21A) +
            struct.pack("<I", 0) +
            input_doc +
            self._tl_string(emoji)
        )
        body = (
            struct.pack("<I", TL_METHODS["stickers.addStickerToSet"]) +
            input_set +
            sticker_item
        )
        return await self._send_api_request(body, "stickers.addStickerToSet")

    async def change_sticker(self, doc_id, doc_ah, file_ref, emoji=None):
        """Change a sticker's emoji."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_doc = (
            struct.pack("<I", 0x1ABFB575) +
            struct.pack("<q", doc_id) +
            struct.pack("<q", doc_ah) +
            self._tl_bytes(file_ref)
        )
        flags = 0
        extra = b""
        if emoji:
            flags |= 0x1
            extra += self._tl_string(emoji)
        body = (
            struct.pack("<I", TL_METHODS["stickers.changeSticker"]) +
            struct.pack("<I", flags) +
            input_doc +
            extra
        )
        return await self._send_api_request(body, "stickers.changeSticker")

    async def replace_sticker(self, old_doc_id, old_doc_ah, old_file_ref,
                               new_doc_id, new_doc_ah, new_file_ref, emoji):
        """Replace a sticker in set with another."""
        if not self._is_running:
            raise JetraError("Client not started.")
        old_doc = (
            struct.pack("<I", 0x1ABFB575) +
            struct.pack("<q", old_doc_id) +
            struct.pack("<q", old_doc_ah) +
            self._tl_bytes(old_file_ref)
        )
        new_doc = (
            struct.pack("<I", 0x1ABFB575) +
            struct.pack("<q", new_doc_id) +
            struct.pack("<q", new_doc_ah) +
            self._tl_bytes(new_file_ref)
        )
        new_item = (
            struct.pack("<I", 0x0328A21A) +
            struct.pack("<I", 0) +
            new_doc +
            self._tl_string(emoji)
        )
        body = (
            struct.pack("<I", TL_METHODS["stickers.replaceSticker"]) +
            old_doc +
            new_item
        )
        return await self._send_api_request(body, "stickers.replaceSticker")

    async def set_sticker_set_thumb(self, set_id, set_ah, thumb_doc_id=0):
        """Set the thumbnail of a sticker set."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_set = (
            struct.pack("<I", 0xFFB62B5E) +
            struct.pack("<q", set_id) +
            struct.pack("<q", set_ah)
        )
        flags = 0x2 if thumb_doc_id else 0
        body = (
            struct.pack("<I", TL_METHODS["stickers.setStickerSetThumb"]) +
            struct.pack("<I", flags) +
            input_set +
            (struct.pack("<q", thumb_doc_id) if thumb_doc_id else b"")
        )
        return await self._send_api_request(body, "stickers.setStickerSetThumb")

    # ------------------------------------------------------------------
    #  Premium
    # ------------------------------------------------------------------

    async def apply_boost(self, peer_id, slots=None, peer_type=None):
        """Apply boost to a channel."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        flags = 0
        extra = b""
        if slots:
            flags |= 0x1
            slot_items = b"".join(struct.pack("<i", s) for s in slots)
            extra = (
                struct.pack("<I", VECTOR_CTOR) +
                struct.pack("<i", len(slots)) +
                slot_items
            )
        body = (
            struct.pack("<I", TL_METHODS["premium.applyBoost"]) +
            struct.pack("<I", flags) +
            extra +
            input_peer
        )
        return await self._send_api_request(body, "premium.applyBoost")

    async def get_boosts_list(self, peer_id, offset="", limit=100,
                                peer_type=None, gifts=False):
        """Get list of boosts for a channel."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        flags = 0x1 if gifts else 0
        body = (
            struct.pack("<I", TL_METHODS["premium.getBoostsList"]) +
            struct.pack("<I", flags) +
            input_peer +
            self._tl_string(offset) +
            struct.pack("<i", limit)
        )
        return await self._send_api_request(body, "premium.getBoostsList")

    async def get_user_boosts(self, peer_id, user_id, user_access_hash=0,
                                peer_type=None):
        """Get boosts a specific user applied to a peer."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        input_user = (
            struct.pack("<I", 0xF21158C6) +
            struct.pack("<q", user_id) +
            struct.pack("<q", user_access_hash)
        )
        body = (
            struct.pack("<I", TL_METHODS["premium.getUserBoosts"]) +
            input_peer +
            input_user
        )
        return await self._send_api_request(body, "premium.getUserBoosts")

    # ------------------------------------------------------------------
    #  Help extras
    # ------------------------------------------------------------------

    async def get_app_update(self, source=""):
        """Get app update info."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["help.getAppUpdate"]) +
            self._tl_string(source)
        )
        return await self._send_api_request(body, "help.getAppUpdate")

    async def get_countries_list(self, lang_code="en", hash_val=0):
        """Get list of countries."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["help.getCountriesList"]) +
            self._tl_string(lang_code) +
            struct.pack("<i", hash_val)
        )
        return await self._send_api_request(body, "help.getCountriesList")

    async def get_peer_colors(self, hash_val=0):
        """Get available peer colors."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["help.getPeerColors"]) +
            struct.pack("<i", hash_val)
        )
        return await self._send_api_request(body, "help.getPeerColors")

    async def get_peer_profile_colors(self, hash_val=0):
        """Get available peer profile colors."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["help.getPeerProfileColors"]) +
            struct.pack("<i", hash_val)
        )
        return await self._send_api_request(body, "help.getPeerProfileColors")

    async def get_timezones_list(self, hash_val=0):
        """Get list of timezones."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["help.getTimezonesList"]) +
            struct.pack("<i", hash_val)
        )
        return await self._send_api_request(body, "help.getTimezonesList")

    async def get_premium_promo(self):
        """Get premium promo info."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", TL_METHODS["help.getPremiumPromo"])
        return await self._send_api_request(body, "help.getPremiumPromo")

    async def get_promo_data(self):
        """Get promo data."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", TL_METHODS["help.getPromoData"])
        return await self._send_api_request(body, "help.getPromoData")

    async def get_invite_text(self):
        """Get invite text for app."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", TL_METHODS["help.getInviteText"])
        return await self._send_api_request(body, "help.getInviteText")

    async def get_user_info(self, user_id, user_access_hash=0):
        """Get info about a user (auth-required)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_user = (
            struct.pack("<I", 0xF21158C6) +
            struct.pack("<q", user_id) +
            struct.pack("<q", user_access_hash)
        )
        body = (
            struct.pack("<I", TL_METHODS["help.getUserInfo"]) +
            input_user
        )
        return await self._send_api_request(body, "help.getUserInfo")

    async def get_deep_link_info(self, path):
        """Get deep link info."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["help.getDeepLinkInfo"]) +
            self._tl_string(path)
        )
        return await self._send_api_request(body, "help.getDeepLinkInfo")

    # ------------------------------------------------------------------
    #  Account extras
    # ------------------------------------------------------------------

    async def get_chat_themes(self, hash_val=0):
        """Get chat themes."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["account.getChatThemes"]) +
            struct.pack("<q", hash_val)
        )
        return await self._send_api_request(body, "account.getChatThemes")

    async def get_channel_default_emoji_statuses(self, hash_val=0):
        """Get default channel emoji statuses."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["account.getChannelDefaultEmojiStatuses"]) +
            struct.pack("<q", hash_val)
        )
        return await self._send_api_request(body, "account.getChannelDefaultEmojiStatuses")

    async def get_channel_restricted_status_emojis(self, hash_val=0):
        """Get restricted channel status emojis."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["account.getChannelRestrictedStatusEmojis"]) +
            struct.pack("<q", hash_val)
        )
        return await self._send_api_request(body, "account.getChannelRestrictedStatusEmojis")

    async def get_collectible_emoji_statuses(self, hash_val=0):
        """Get collectible emoji statuses."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["account.getCollectibleEmojiStatuses"]) +
            struct.pack("<q", hash_val)
        )
        return await self._send_api_request(body, "account.getCollectibleEmojiStatuses")

    async def get_default_profile_photo_emojis(self, hash_val=0):
        """Get default profile photo emojis."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["account.getDefaultProfilePhotoEmojis"]) +
            struct.pack("<q", hash_val)
        )
        return await self._send_api_request(body, "account.getDefaultProfilePhotoEmojis")

    async def get_default_group_photo_emojis(self, hash_val=0):
        """Get default group photo emojis."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["account.getDefaultGroupPhotoEmojis"]) +
            struct.pack("<q", hash_val)
        )
        return await self._send_api_request(body, "account.getDefaultGroupPhotoEmojis")

    async def get_contact_signup_notification(self):
        """Get whether contact sign-up notifications are enabled."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", TL_METHODS["account.getContactSignUpNotification"])
        return await self._send_api_request(body, "account.getContactSignUpNotification")

    async def set_contact_signup_notification(self, silent=True):
        """Enable/disable contact sign-up notifications."""
        if not self._is_running:
            raise JetraError("Client not started.")
        bool_true = 0x997275B5
        bool_false = 0xBC799737
        body = (
            struct.pack("<I", TL_METHODS["account.setContactSignUpNotification"]) +
            struct.pack("<I", bool_true if silent else bool_false)
        )
        return await self._send_api_request(body, "account.setContactSignUpNotification")

    async def get_auto_download_settings(self):
        """Get auto-download settings."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", TL_METHODS["account.getAutoDownloadSettings"])
        return await self._send_api_request(body, "account.getAutoDownloadSettings")

    # ------------------------------------------------------------------
    #  Messages extras (scheduled, chat admin)
    # ------------------------------------------------------------------

    async def delete_scheduled_messages(self, peer_id, message_ids, peer_type=None):
        """Delete scheduled messages."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        ids_vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(message_ids)) +
            b"".join(struct.pack("<i", mid) for mid in message_ids)
        )
        body = (
            struct.pack("<I", TL_METHODS["messages.deleteScheduledMessages"]) +
            input_peer +
            ids_vec
        )
        return await self._send_api_request(body, "messages.deleteScheduledMessages")

    async def get_scheduled_messages(self, peer_id, message_ids, peer_type=None):
        """Get scheduled messages by ids."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        ids_vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(message_ids)) +
            b"".join(struct.pack("<i", mid) for mid in message_ids)
        )
        body = (
            struct.pack("<I", TL_METHODS["messages.getScheduledMessages"]) +
            input_peer +
            ids_vec
        )
        return await self._send_api_request(body, "messages.getScheduledMessages")

    async def get_scheduled_history(self, peer_id, hash_val=0, peer_type=None):
        """Get all scheduled messages in a chat."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        body = (
            struct.pack("<I", TL_METHODS["messages.getScheduledHistory"]) +
            input_peer +
            struct.pack("<q", hash_val)
        )
        return await self._send_api_request(body, "messages.getScheduledHistory")

    async def edit_chat_about(self, peer_id, about, peer_type=None):
        """Edit chat description."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        body = (
            struct.pack("<I", TL_METHODS["messages.editChatAbout"]) +
            input_peer +
            self._tl_string(about)
        )
        return await self._send_api_request(body, "messages.editChatAbout")

    async def edit_chat_admin(self, chat_id, user_id, is_admin,
                                user_access_hash=0):
        """Promote/demote a user in a basic group."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_user = (
            struct.pack("<I", 0xF21158C6) +
            struct.pack("<q", user_id) +
            struct.pack("<q", user_access_hash)
        )
        bool_true = 0x997275B5
        bool_false = 0xBC799737
        body = (
            struct.pack("<I", TL_METHODS["messages.editChatAdmin"]) +
            struct.pack("<q", chat_id) +
            input_user +
            struct.pack("<I", bool_true if is_admin else bool_false)
        )
        return await self._send_api_request(body, "messages.editChatAdmin")

    async def delete_basic_chat(self, chat_id):
        """Delete a basic group."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["messages.deleteChat"]) +
            struct.pack("<q", chat_id)
        )
        return await self._send_api_request(body, "messages.deleteChat")

    async def delete_revoked_chat_invites(self, peer_id, admin_id=None,
                                            admin_access_hash=0, peer_type=None):
        """Delete all revoked invite links for a chat."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        if admin_id is None:
            admin_id = self.session.user_id
        input_user = (
            struct.pack("<I", 0xF21158C6) +
            struct.pack("<q", admin_id) +
            struct.pack("<q", admin_access_hash)
        )
        body = (
            struct.pack("<I", TL_METHODS["messages.deleteRevokedExportedChatInvites"]) +
            input_peer +
            input_user
        )
        return await self._send_api_request(body, "messages.deleteRevokedExportedChatInvites")

    async def get_admins_with_invites(self, peer_id, peer_type=None):
        """Get admins who have invite links."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        body = (
            struct.pack("<I", TL_METHODS["messages.getAdminsWithInvites"]) +
            input_peer
        )
        return await self._send_api_request(body, "messages.getAdminsWithInvites")

    async def get_chat_invite_importers(self, peer_id, link="", q="",
                                          limit=100, requested=False,
                                          peer_type=None):
        """Get list of users who imported via invite link."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        flags = 0
        extra = b""
        if requested: flags |= 0x1
        if link:
            flags |= 0x2
            extra += self._tl_string(link)
        if q:
            flags |= 0x4
            extra += self._tl_string(q)

        # offset_user (inputUserEmpty#b98886cf)
        empty_user = struct.pack("<I", 0xB98886CF)

        body = (
            struct.pack("<I", TL_METHODS["messages.getChatInviteImporters"]) +
            struct.pack("<I", flags) +
            input_peer +
            extra +
            struct.pack("<i", 0) +  # offset_date
            empty_user +
            struct.pack("<i", limit)
        )
        return await self._send_api_request(body, "messages.getChatInviteImporters")

    async def toggle_no_forwards(self, peer_id, enabled=True,
                                   request_msg_id=0, peer_type=None):
        """Enable/disable content protection (no forwarding)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        flags = 0
        extra = b""
        if request_msg_id:
            flags |= 0x1
            extra = struct.pack("<i", request_msg_id)
        bool_true = 0x997275B5
        bool_false = 0xBC799737
        body = (
            struct.pack("<I", TL_METHODS["messages.toggleNoForwards"]) +
            struct.pack("<I", flags) +
            input_peer +
            struct.pack("<I", bool_true if enabled else bool_false) +
            extra
        )
        return await self._send_api_request(body, "messages.toggleNoForwards")

    async def get_recent_locations(self, peer_id, limit=50, hash_val=0,
                                     peer_type=None):
        """Get recent shared locations in a chat."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        body = (
            struct.pack("<I", TL_METHODS["messages.getRecentLocations"]) +
            input_peer +
            struct.pack("<i", limit) +
            struct.pack("<q", hash_val)
        )
        return await self._send_api_request(body, "messages.getRecentLocations")

    async def get_split_ranges(self):
        """Get available split ranges (sponsored messages info)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", TL_METHODS["messages.getSplitRanges"])
        return await self._send_api_request(body, "messages.getSplitRanges")

    async def get_sponsored_messages(self, peer_id, msg_id=0, peer_type=None):
        """Get sponsored messages for a channel."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        flags = 0
        extra = b""
        if msg_id:
            flags |= 0x1
            extra = struct.pack("<i", msg_id)
        body = (
            struct.pack("<I", TL_METHODS["messages.getSponsoredMessages"]) +
            struct.pack("<I", flags) +
            input_peer +
            extra
        )
        return await self._send_api_request(body, "messages.getSponsoredMessages")

    # ------------------------------------------------------------------
    #  Contacts: token-based export/import + close friends
    # ------------------------------------------------------------------

    async def export_contact_token(self):
        """Export contacts as a shareable token."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", TL_METHODS["contacts.exportContactToken"])
        return await self._send_api_request(body, "contacts.exportContactToken")

    async def import_contact_token(self, token):
        """Import contacts from a token."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["contacts.importContactToken"]) +
            self._tl_string(token)
        )
        return await self._send_api_request(body, "contacts.importContactToken")

    async def edit_close_friends(self, user_ids):
        """
        Set the list of close friends (used for story privacy).

        Args:
            user_ids: list of user ids to set as close friends.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        items = b"".join(struct.pack("<q", uid) for uid in user_ids)
        vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(user_ids)) +
            items
        )
        body = (
            struct.pack("<I", TL_METHODS["contacts.editCloseFriends"]) +
            vec
        )
        return await self._send_api_request(body, "contacts.editCloseFriends")

    # ------------------------------------------------------------------
    #  Advanced search and participants
    # ------------------------------------------------------------------

    def _messages_filter_ctor(self, filter_type):
        """Map a filter name to its MessagesFilter ctor id."""
        filters = {
            "empty": 0x57E2F66C,
            "photo": 0x9609A51C,
            "video": 0x9FC00E65,
            "photo_video": 0x56E9F0E4,
            "document": 0x9EDDF188,
            "url": 0x7EF0DD87,
            "gif": 0xFFC86587,
            "voice": 0x50F5C392,
            "music": 0x3751B49E,
            "chat_photos": 0x3A20ECB8,
            "phone_calls": 0x80C99768,
            "round_video": 0xB549DA53,
            "round_voice": 0x7A7C17A4,
            "my_mentions": 0xC1F8E69A,
            "geo": 0xE7026D0D,
            "contacts": 0xE062DB83,
            "poll": 0xFA2BC90A,
            "pinned": 0x1BB00451,
        }
        if filter_type not in filters:
            raise ValueError(f"Unknown filter: {filter_type}. Valid: {list(filters.keys())}")
        return filters[filter_type]

    async def search_messages_filtered(self, peer_id, query="", filter_type="empty",
                                        limit=20, peer_type=None):
        """
        Search messages in a chat with filter.

        Args:
            peer_id:     target chat.
            query:       text query (can be empty for filter-only).
            filter_type: "photo", "video", "document", "url", "gif",
                         "voice", "music", "link", "phone_calls", "round_video",
                         "round_voice", "my_mentions", "geo", "contacts", "poll".
            limit:       max results.
            peer_type:   "user" or "group".

        Returns:
            Raw messages.messages response.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)
        filter_ctor = self._messages_filter_ctor(filter_type)

        body = (
            struct.pack("<I", TL_METHODS["messages.search"]) +
            struct.pack("<I", 0) +  # flags
            input_peer +
            self._tl_string(query) +
            struct.pack("<I", filter_ctor) +
            struct.pack("<i", 0) +  # min_date
            struct.pack("<i", 0) +  # max_date
            struct.pack("<i", 0) +  # offset_id
            struct.pack("<i", 0) +  # add_offset
            struct.pack("<i", limit) +
            struct.pack("<i", 0) +  # max_id
            struct.pack("<i", 0) +  # min_id
            struct.pack("<q", 0)    # hash
        )
        return await self._send_api_request(body, "messages.search")

    async def get_participants_filtered(self, channel_id, filter_type="recent",
                                          query="", limit=200):
        """
        Get participants of a group with filter.

        Args:
            channel_id: group id.
            filter_type: "recent", "admin", "kicked", "banned",
                         "bots", "contacts", "non_contacts", "mentions", "search"
            query:      search query (for "search" filter).
            limit:      max results.

        Returns:
            Raw channels.ChannelParticipants response.
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        # ChannelParticipantsFilter ctors
        filters = {
            "recent": 0xDE3F3C79,
            "admin": 0xB4608969,
            "kicked": 0xA3B54985,
            "banned": 0xBB6AE88D,
            "bots": 0xB0D1865B,
            "contacts": 0xAB1F2D1B,
            "non_contacts": 0x2BA7D2FD,
            "mentions": 0x96137A6E,
            "search": 0xF0176E0E,
        }
        if filter_type not in filters:
            raise ValueError(f"Unknown filter: {filter_type}. Valid: {list(filters.keys())}")
        filter_ctor = filters[filter_type]

        # Build filter object
        if filter_type == "search":
            filter_obj = struct.pack("<I", filter_ctor) + self._tl_string(query)
        else:
            filter_obj = struct.pack("<I", filter_ctor)

        channel_input = self._get_channel_input(channel_id)
        body = (
            struct.pack("<I", TL_METHODS["channels.getParticipants"]) +
            channel_input +
            filter_obj +
            struct.pack("<i", 0) +  # offset
            struct.pack("<i", limit) +
            struct.pack("<q", 0)   # hash
        )
        return await self._send_api_request(body, "channels.getParticipants")

    # ------------------------------------------------------------------
    #  High-level helpers
    # ------------------------------------------------------------------

    async def wait_for_message(self, peer_id=None, timeout=30,
                                peer_type=None, predicate=None):
        """
        Wait for the next incoming message.

        Args:
            peer_id:   if given, only wait for messages from this peer.
            timeout:   max seconds to wait.
            peer_type: "user" or "group".
            predicate: optional callable(message) -> bool filter.

        Returns:
            Message object or None if timeout.
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        future = asyncio.get_event_loop().create_future()

        async def _handler(message):
            if future.done():
                return
            try:
                if peer_id is not None and message.peer_id != peer_id:
                    return
                if peer_type is not None and message.peer_type != peer_type:
                    return
                if predicate is not None and not predicate(message):
                    return
                if not future.done():
                    future.set_result(message)
            except Exception as e:
                print(f"[wait_for_message] handler error: {e}")

        # Register as tuple matching _trigger_message_handlers signature
        entry = (_handler, None, None)
        self._message_handlers.append(entry)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            if entry in self._message_handlers:
                self._message_handlers.remove(entry)

    async def wait_for_reply(self, message, timeout=30):
        """Wait for a reply to a specific message."""
        return await self.wait_for_message(
            peer_id=message.peer_id,
            timeout=timeout,
            predicate=lambda m: m.reply_to_msg_id == message.id
        )

    # ------------------------------------------------------------------
    #  Advanced media: poll, location, dice, contact, voice, round video
    # ------------------------------------------------------------------

    async def send_poll(self, peer_id, question, options, peer_type=None,
                        multiple_choice=False, quiz=False, anonymous=True,
                        correct_answers=None):
        """
        Send a poll.

        Args:
            peer_id:         target peer.
            question:        poll question text.
            options:         list of answer strings (Telegram limit 2-10; Jetra limit unverified).
            peer_type:       "user" or "group".
            multiple_choice: allow multiple answers.
            quiz:            quiz mode; requires correct_answers.
            anonymous:       hide voter identities.
            correct_answers: 0-based option indexes that are correct (quiz only).

        Returns:
            parsed sent message, or dict with raw_len.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        if not (2 <= len(options) <= 10):
            raise JetraError("A poll needs between 2 and 10 options.")
        if quiz and not correct_answers:
            raise JetraError("Quiz mode requires correct_answers.")
        if quiz and any(not (0 <= int(i) < len(options)) for i in correct_answers):
            raise JetraError("correct_answers index out of range.")

        # poll flags per schema: bit1 public_voters, bit2 multiple_choice, bit3 quiz
        poll_flags = 0
        if not anonymous:
            poll_flags |= 0x2
        if multiple_choice:
            poll_flags |= 0x4
        if quiz:
            poll_flags |= 0x8

        question_obj = (
            struct.pack("<I", 0x751F3146) +  # textWithEntities
            self._tl_string(question) +
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", 0)
        )

        answers_items = b""
        for i, opt in enumerate(options):
            answer_text = (
                struct.pack("<I", 0x751F3146) +  # textWithEntities
                self._tl_string(opt) +
                struct.pack("<I", VECTOR_CTOR) +
                struct.pack("<i", 0)
            )
            answers_items += (
                struct.pack("<I", 0x4B7D786A) +   # pollAnswer
                struct.pack("<I", 0) +            # pollAnswer.flags
                answer_text +
                self._tl_bytes(bytes([i]))        # option: TL bytes, length-prefixed
            )
        answers_vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(options)) +
            answers_items
        )

        import random as _r
        poll = (
            struct.pack("<I", 0x966E2DBF) +                # poll
            struct.pack("<q", _r.getrandbits(63)) +        # id
            struct.pack("<I", poll_flags) +
            question_obj +
            answers_vec +
            struct.pack("<q", 0)                           # hash
        )

        # inputMediaPoll: flags.0 gates correct_answers, which comes after poll
        media_flags = 0x1 if quiz else 0
        input_media = (
            struct.pack("<I", 0x883A4108) +
            struct.pack("<I", media_flags) +
            poll
        )
        if quiz:
            input_media += (
                struct.pack("<I", VECTOR_CTOR) +
                struct.pack("<i", len(correct_answers)) +
                b"".join(struct.pack("<i", int(i)) for i in correct_answers)
            )

        import random
        input_peer = self._get_input_peer(peer_id, peer_type)
        body = (
            struct.pack("<I", TL_METHODS["messages.sendMedia"]) +
            struct.pack("<I", 0) +
            input_peer +
            input_media +
            self._tl_string("") +
            struct.pack("<q", random.getrandbits(63))
        )
        result = await self._send_api_request(body, "messages.sendMedia")
        parsed = parse_sent_message(result)
        return parsed or {"raw_len": len(result)}

    async def send_location(self, peer_id, lat, long, accuracy_radius=0,
                              peer_type=None):
        """
        Send a location.

        Args:
            peer_id:  target peer.
            lat:      latitude (float).
            long:     longitude (float).
            accuracy_radius: optional radius in meters.
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        geo_flags = 0
        geo_extra = b""
        if accuracy_radius:
            geo_flags |= 0x1
            geo_extra = struct.pack("<i", accuracy_radius)

        input_geo = (
            struct.pack("<I", 0x48222FAF) +
            struct.pack("<I", geo_flags) +
            struct.pack("<d", lat) +
            struct.pack("<d", long) +
            geo_extra
        )

        input_media = (
            struct.pack("<I", 0xF9C44144) +
            input_geo
        )

        input_peer = self._get_input_peer(peer_id, peer_type)
        import random
        random_id = random.getrandbits(63)
        body = (
            struct.pack("<I", TL_METHODS["messages.sendMedia"]) +
            struct.pack("<I", 0) +
            input_peer +
            input_media +
            self._tl_string("") +
            struct.pack("<q", random_id)
        )
        result = await self._send_api_request(body, "messages.sendMedia")
        parsed = parse_sent_message(result)
        return parsed or {"raw_len": len(result)}

    async def send_venue(self, peer_id, lat, long, title, address,
                          provider="", venue_id="", venue_type="",
                          peer_type=None):
        """Send a venue (place with location)."""
        if not self._is_running:
            raise JetraError("Client not started.")

        input_geo = (
            struct.pack("<I", 0x48222FAF) +
            struct.pack("<I", 0) +
            struct.pack("<d", lat) +
            struct.pack("<d", long)
        )

        input_media = (
            struct.pack("<I", 0xC13D1C11) +  # inputMediaVenue
            input_geo +
            self._tl_string(title) +
            self._tl_string(address) +
            self._tl_string(provider) +
            self._tl_string(venue_id) +
            self._tl_string(venue_type)
        )

        input_peer = self._get_input_peer(peer_id, peer_type)
        import random
        random_id = random.getrandbits(63)
        body = (
            struct.pack("<I", TL_METHODS["messages.sendMedia"]) +
            struct.pack("<I", 0) +
            input_peer +
            input_media +
            self._tl_string("") +
            struct.pack("<q", random_id)
        )
        result = await self._send_api_request(body, "messages.sendMedia")
        parsed = parse_sent_message(result)
        return parsed or {"raw_len": len(result)}

    async def send_dice(self, peer_id, emoticon="🎲", peer_type=None):
        """
        Send animated dice/emoji.

        Args:
            peer_id:  target peer.
            emoticon: "🎲" (dice), "🎯" (dart), "🏀" (basketball), "⚽" (football),
                      "🎰" (slot machine), "🎳" (bowling)
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        input_media = (
            struct.pack("<I", 0xE66FBF7B) +  # inputMediaDice
            self._tl_string(emoticon)
        )

        input_peer = self._get_input_peer(peer_id, peer_type)
        import random
        random_id = random.getrandbits(63)
        body = (
            struct.pack("<I", TL_METHODS["messages.sendMedia"]) +
            struct.pack("<I", 0) +
            input_peer +
            input_media +
            self._tl_string("") +
            struct.pack("<q", random_id)
        )
        result = await self._send_api_request(body, "messages.sendMedia")
        parsed = parse_sent_message(result)
        return parsed or {"raw_len": len(result)}

    async def send_contact_media(self, peer_id, phone, first_name, last_name="",
                                   vcard="", peer_type=None):
        """Send a contact card (share contact)."""
        if not self._is_running:
            raise JetraError("Client not started.")

        input_media = (
            struct.pack("<I", 0xF8AB7DFB) +
            self._tl_string(phone) +
            self._tl_string(first_name) +
            self._tl_string(last_name) +
            self._tl_string(vcard)
        )

        input_peer = self._get_input_peer(peer_id, peer_type)
        import random
        random_id = random.getrandbits(63)
        body = (
            struct.pack("<I", TL_METHODS["messages.sendMedia"]) +
            struct.pack("<I", 0) +
            input_peer +
            input_media +
            self._tl_string("") +
            struct.pack("<q", random_id)
        )
        result = await self._send_api_request(body, "messages.sendMedia")
        parsed = parse_sent_message(result)
        return parsed or {"raw_len": len(result)}

    async def send_voice(self, peer_id, audio_path, duration=0, peer_type=None):
        """
        Send a voice message.

        Args:
            peer_id:    target peer.
            audio_path: path to audio file (usually .ogg or .opus).
            duration:   audio duration in seconds (0 = auto-guess).
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        # Upload file
        upload = await self.upload_file(audio_path)
        input_file = upload["input_file"]

        # documentAttributeAudio with voice flag
        audio_attr = (
            struct.pack("<I", 0x9852F9C6) +
            struct.pack("<I", 0x400) +  # flags bit 10 = voice
            struct.pack("<i", duration)
        )

        attrs = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", 1) +
            audio_attr
        )

        input_media_uploaded = (
            struct.pack("<I", 0x037C9330) +
            struct.pack("<I", 0) +
            input_file +
            self._tl_string("audio/ogg") +
            attrs
        )

        # Register
        registered = await self._upload_media_register(
            peer_id, input_media_uploaded, peer_type
        )
        parsed = self._parse_message_media(registered)
        if not parsed:
            raise JetraError("Failed to register voice message")

        input_doc = (
            struct.pack("<I", 0x1ABFB575) +
            struct.pack("<q", parsed["id"]) +
            struct.pack("<q", parsed["access_hash"]) +
            self._tl_bytes(parsed["file_reference"])
        )
        final_media = (
            struct.pack("<I", 0xA8763AB5) +
            struct.pack("<I", 0) +
            input_doc
        )

        input_peer = self._get_input_peer(peer_id, peer_type)
        import random
        random_id = random.getrandbits(63)
        body = (
            struct.pack("<I", TL_METHODS["messages.sendMedia"]) +
            struct.pack("<I", 0) +
            input_peer +
            final_media +
            self._tl_string("") +
            struct.pack("<q", random_id)
        )
        result = await self._send_api_request(body, "messages.sendMedia")
        parsed_msg = parse_sent_message(result)
        return parsed_msg or {"raw_len": len(result)}

    async def send_round_video(self, peer_id, video_path, duration=0,
                                 width=240, height=240, peer_type=None):
        """Send a round video message."""
        if not self._is_running:
            raise JetraError("Client not started.")

        upload = await self.upload_file(video_path)
        input_file = upload["input_file"]

        video_attr = (
            struct.pack("<I", 0x43C57C48) +
            struct.pack("<I", 0x1) +  # flags: round_message
            struct.pack("<d", float(duration)) +
            struct.pack("<i", width) +
            struct.pack("<i", height)
        )

        attrs = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", 1) +
            video_attr
        )

        input_media_uploaded = (
            struct.pack("<I", 0x037C9330) +
            struct.pack("<I", 0) +
            input_file +
            self._tl_string("video/mp4") +
            attrs
        )

        registered = await self._upload_media_register(
            peer_id, input_media_uploaded, peer_type
        )
        parsed = self._parse_message_media(registered)
        if not parsed:
            raise JetraError("Failed to register round video")

        input_doc = (
            struct.pack("<I", 0x1ABFB575) +
            struct.pack("<q", parsed["id"]) +
            struct.pack("<q", parsed["access_hash"]) +
            self._tl_bytes(parsed["file_reference"])
        )
        final_media = (
            struct.pack("<I", 0xA8763AB5) +
            struct.pack("<I", 0) +
            input_doc
        )

        input_peer = self._get_input_peer(peer_id, peer_type)
        import random
        random_id = random.getrandbits(63)
        body = (
            struct.pack("<I", TL_METHODS["messages.sendMedia"]) +
            struct.pack("<I", 0) +
            input_peer +
            final_media +
            self._tl_string("") +
            struct.pack("<q", random_id)
        )
        result = await self._send_api_request(body, "messages.sendMedia")
        parsed_msg = parse_sent_message(result)
        return parsed_msg or {"raw_len": len(result)}

    # ------------------------------------------------------------------
    #  Block A: send from URL, send sticker/gif, bulk, helpers
    # ------------------------------------------------------------------

    async def send_photo_from_url(self, peer_id, url, caption="",
                                    peer_type=None, reply_to=None):
        """
        Send a photo from a URL without downloading it locally.

        Args:
            peer_id: target peer.
            url:     direct image URL.
            caption: optional caption.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)

        # inputMediaPhotoExternal#e5bbfe1a flags:# spoiler:flags.1?true url:string
        input_media = (
            struct.pack("<I", 0xE5BBFE1A) +
            struct.pack("<I", 0) +  # flags
            self._tl_string(url)
        )

        flags = 0
        reply_bytes = b""
        if reply_to is not None:
            reply_to_msg_id = reply_to.id if isinstance(reply_to, Message) else reply_to
            if reply_to_msg_id and reply_to_msg_id != 0:
                flags |= 0x1
                reply_bytes = (
                    struct.pack("<I", 0x3BD4B7C2) +
                    struct.pack("<I", 0) +
                    struct.pack("<i", reply_to_msg_id)
                )

        import random
        random_id = random.getrandbits(63)
        body = (
            struct.pack("<I", TL_METHODS["messages.sendMedia"]) +
            struct.pack("<I", flags) +
            input_peer +
            reply_bytes +
            input_media +
            self._tl_string(caption) +
            struct.pack("<q", random_id)
        )
        result = await self._send_api_request(body, "messages.sendMedia")
        parsed = parse_sent_message(result)
        return parsed or {"raw_len": len(result)}

    async def send_document_from_url(self, peer_id, url, caption="",
                                       mime_type="application/octet-stream",
                                       peer_type=None, reply_to=None):
        """Send a document from URL."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)

        # inputMediaDocumentExternal#779600f9 flags:# spoiler:flags.1?true url:string
        input_media = (
            struct.pack("<I", 0x779600F9) +
            struct.pack("<I", 0) +
            self._tl_string(url)
        )

        flags = 0
        reply_bytes = b""
        if reply_to is not None:
            reply_to_msg_id = reply_to.id if isinstance(reply_to, Message) else reply_to
            if reply_to_msg_id and reply_to_msg_id != 0:
                flags |= 0x1
                reply_bytes = (
                    struct.pack("<I", 0x3BD4B7C2) +
                    struct.pack("<I", 0) +
                    struct.pack("<i", reply_to_msg_id)
                )

        import random
        random_id = random.getrandbits(63)
        body = (
            struct.pack("<I", TL_METHODS["messages.sendMedia"]) +
            struct.pack("<I", flags) +
            input_peer +
            reply_bytes +
            input_media +
            self._tl_string(caption) +
            struct.pack("<q", random_id)
        )
        result = await self._send_api_request(body, "messages.sendMedia")
        parsed = parse_sent_message(result)
        return parsed or {"raw_len": len(result)}

    async def send_sticker(self, peer_id, sticker_doc_id, sticker_doc_ah,
                            sticker_file_ref=b"", peer_type=None, reply_to=None):
        """
        Send a sticker.

        Args:
            peer_id: target peer.
            sticker_doc_id: document id of the sticker.
            sticker_doc_ah: access_hash.
            sticker_file_ref: file_reference bytes.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)

        input_doc = (
            struct.pack("<I", 0x1ABFB575) +
            struct.pack("<q", sticker_doc_id) +
            struct.pack("<q", sticker_doc_ah) +
            self._tl_bytes(sticker_file_ref)
        )

        # inputMediaDocument#a8763ab5 flags:# id:InputDocument
        input_media = (
            struct.pack("<I", 0xA8763AB5) +
            struct.pack("<I", 0) +
            input_doc
        )

        flags = 0
        reply_bytes = b""
        if reply_to is not None:
            reply_to_msg_id = reply_to.id if isinstance(reply_to, Message) else reply_to
            if reply_to_msg_id and reply_to_msg_id != 0:
                flags |= 0x1
                reply_bytes = (
                    struct.pack("<I", 0x3BD4B7C2) +
                    struct.pack("<I", 0) +
                    struct.pack("<i", reply_to_msg_id)
                )

        import random
        random_id = random.getrandbits(63)
        body = (
            struct.pack("<I", TL_METHODS["messages.sendMedia"]) +
            struct.pack("<I", flags) +
            input_peer +
            reply_bytes +
            input_media +
            self._tl_string("") +
            struct.pack("<q", random_id)
        )
        result = await self._send_api_request(body, "messages.sendMedia")
        parsed = parse_sent_message(result)
        return parsed or {"raw_len": len(result)}

    async def send_gif(self, peer_id, gif_doc_id, gif_doc_ah,
                        gif_file_ref=b"", caption="", peer_type=None):
        """Send a GIF."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)

        input_doc = (
            struct.pack("<I", 0x1ABFB575) +
            struct.pack("<q", gif_doc_id) +
            struct.pack("<q", gif_doc_ah) +
            self._tl_bytes(gif_file_ref)
        )
        input_media = (
            struct.pack("<I", 0xA8763AB5) +
            struct.pack("<I", 0) +
            input_doc
        )

        import random
        random_id = random.getrandbits(63)
        body = (
            struct.pack("<I", TL_METHODS["messages.sendMedia"]) +
            struct.pack("<I", 0) +
            input_peer +
            input_media +
            self._tl_string(caption) +
            struct.pack("<q", random_id)
        )
        result = await self._send_api_request(body, "messages.sendMedia")
        parsed = parse_sent_message(result)
        return parsed or {"raw_len": len(result)}

    async def send_bulk(self, peer_ids, text, delay=0.5, peer_types=None):
        """
        Send the same text to multiple peers.

        Args:
            peer_ids: list of peer ids.
            text: message text.
            delay: seconds between sends (to avoid flood).
            peer_types: optional list of types (or None to auto-detect).

        Returns:
            list of msg_ids (or None for failures).
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        results = []
        for i, pid in enumerate(peer_ids):
            ptype = peer_types[i] if peer_types else None
            try:
                msg_id = await self.send_message(pid, text, peer_type=ptype)
                results.append(msg_id)
            except Exception as e:
                print(f"[send_bulk] failed for {pid}: {e}")
                results.append(None)
            if i < len(peer_ids) - 1 and delay > 0:
                await asyncio.sleep(delay)
        return results

    async def is_blocked(self, user_id):
        """Check if a user is blocked by us."""
        if not self._is_running:
            raise JetraError("Client not started.")
        result = await self.get_blocked(offset=0, limit=100)
        # Parse blocked list for user_id
        # contacts.blocked#ade1591 flags:# blocked:Vector<PeerBlocked>
        # peerBlocked#e8fd8014 peer:Peer date:int
        needle = struct.pack("<I", 0x59511722)  # peerUser
        offset = 0
        while True:
            offset = result.find(needle, offset)
            if offset == -1:
                break
            try:
                uid = struct.unpack("<q", result[offset+4:offset+12])[0]
                if uid == user_id:
                    return True
            except Exception:
                pass
            offset += 4
        return False

    def get_cached_message(self, peer_id, msg_id):
        """Get a message from local DB cache."""
        rows = self.db.get_messages(peer_id=peer_id, limit=1000)
        for r in rows:
            if r["id"] == msg_id:
                return Message.from_dict(r)
        return None

    async def get_history_paginated(self, peer_id, limit=100, page=0,
                                      peer_type=None):
        """
        Get history from server with pagination.

        Args:
            peer_id: target peer.
            limit:   items per page.
            page:    0-based page number.
        """
        offset_id = page * limit
        return await self.get_server_history(peer_id, limit=limit,
                                               offset_id=offset_id,
                                               peer_type=peer_type)

    # ------------------------------------------------------------------
    #  Block B: download, global search filters, inline bot, password recovery
    # ------------------------------------------------------------------

    async def get_file_hashes(self, location_bytes, offset=0):
        """Get hashes for a file location (for integrity check)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["upload.getFileHashes"]) +
            location_bytes +
            struct.pack("<q", offset)
        )
        return await self._send_api_request(body, "upload.getFileHashes")

    async def get_file_chunk(self, location_bytes, offset=0, limit=512 * 1024):
        """
        Download a single chunk of a file.

        Args:
            location_bytes: pre-serialized InputFileLocation.
            offset:         byte offset.
            limit:          bytes to download (max 512KB typically).

        Returns:
            raw upload.File bytes.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        body = (
            struct.pack("<I", TL_METHODS["upload.getFile"]) +
            struct.pack("<I", 0) +  # flags
            location_bytes +
            struct.pack("<q", offset) +
            struct.pack("<i", limit)
        )
        return await self._send_api_request(body, "upload.getFile")

    async def download_media(self, location_bytes, save_path, chunk_size=512 * 1024):
        """
        Download a file in chunks.

        Args:
            location_bytes: pre-serialized InputFileLocation.
            save_path:      local file path to save to.
            chunk_size:     bytes per chunk.

        Returns:
            total bytes downloaded.
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        total = 0
        offset = 0
        with open(save_path, "wb") as f:
            while True:
                chunk_data = await self.get_file_chunk(location_bytes, offset=offset, limit=chunk_size)
                # upload.file#096a18d5 type:storage.FileType mtime:int bytes:bytes
                # upload.fileCdnRedirect - skip for now
                if len(chunk_data) < 4:
                    break
                ctor = struct.unpack("<I", chunk_data[:4])[0]
                if ctor != 0x096A18D5:  # upload.file
                    # Not upload.file (maybe CdnRedirect or error)
                    break

                # Parse: ctor(4) + type(storage.FileType - variable) + mtime(4) + bytes(TL)
                # Skip type ctor
                offset_in_chunk = 4
                file_type_ctor = struct.unpack("<I", chunk_data[offset_in_chunk:offset_in_chunk+4])[0]
                offset_in_chunk += 4

                # mtime
                mtime = struct.unpack("<i", chunk_data[offset_in_chunk:offset_in_chunk+4])[0]
                offset_in_chunk += 4

                # bytes
                bytes_len_byte = chunk_data[offset_in_chunk]
                if bytes_len_byte < 0xFE:
                    data_len = bytes_len_byte
                    offset_in_chunk += 1
                else:
                    data_len = int.from_bytes(chunk_data[offset_in_chunk+1:offset_in_chunk+4], 'little')
                    offset_in_chunk += 4

                chunk = chunk_data[offset_in_chunk:offset_in_chunk+data_len]
                if len(chunk) == 0:
                    break

                f.write(chunk)
                total += len(chunk)
                offset += len(chunk)

                if len(chunk) < chunk_size:
                    break

        return total

    async def search_global_filtered(self, query="", filter_type="empty",
                                       folder_id=None, groups_only=False,
                                       users_only=False, broadcasts_only=False,
                                       limit=20):
        """
        Global search with filters.

        Args:
            query:      search text.
            filter_type: same as search_messages_filtered.
            folder_id:  optional folder id.
            groups_only, users_only, broadcasts_only: restrict by type.
            limit:      max results.
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        filter_ctor = self._messages_filter_ctor(filter_type)

        flags = 0
        folder_bytes = b""
        if folder_id is not None:
            flags |= 0x1
            folder_bytes = struct.pack("<i", folder_id)
        if broadcasts_only:
            flags |= 0x2
        if groups_only:
            flags |= 0x4
        if users_only:
            flags |= 0x8

        body = (
            struct.pack("<I", TL_METHODS["messages.searchGlobal"]) +
            struct.pack("<I", flags) +
            folder_bytes +
            self._tl_string(query) +
            struct.pack("<I", filter_ctor) +
            struct.pack("<i", 0) +  # min_date
            struct.pack("<i", 0) +  # max_date
            struct.pack("<i", 0) +  # offset_rate
            struct.pack("<I", 0x7DA07EC9) +  # inputPeerEmpty
            struct.pack("<i", 0) +  # offset_id
            struct.pack("<i", limit)
        )
        return await self._send_api_request(body, "messages.searchGlobal")

    async def send_inline_bot_result(self, peer_id, query_id, result_id,
                                       peer_type=None, reply_to=None):
        """Send an inline bot result."""
        if not self._is_running:
            raise JetraError("Client not started.")
        input_peer = self._get_input_peer(peer_id, peer_type)

        flags = 0
        reply_bytes = b""
        if reply_to is not None:
            reply_to_msg_id = reply_to.id if isinstance(reply_to, Message) else reply_to
            if reply_to_msg_id and reply_to_msg_id != 0:
                flags |= 0x1
                reply_bytes = (
                    struct.pack("<I", 0x3BD4B7C2) +
                    struct.pack("<I", 0) +
                    struct.pack("<i", reply_to_msg_id)
                )

        import random
        random_id = random.getrandbits(63)
        body = (
            struct.pack("<I", TL_METHODS["messages.sendInlineBotResult"]) +
            struct.pack("<I", flags) +
            input_peer +
            reply_bytes +
            struct.pack("<q", random_id) +
            struct.pack("<q", query_id) +
            self._tl_string(result_id)
        )
        return await self._send_api_request(body, "messages.sendInlineBotResult")

    async def request_password_recovery(self):
        """Request a password recovery email."""
        if not self._is_running:
            raise JetraError("Client not started.")
        body = struct.pack("<I", TL_METHODS["auth.requestPasswordRecovery"])
        return await self._send_api_request(body, "auth.requestPasswordRecovery")

    async def recover_password(self, code, new_password=None):
        """
        Recover password using email code.

        Args:
            code:         6-digit code from recovery email.
            new_password: optional new password (if None, only clears old).
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        flags = 0
        new_settings = b""
        if new_password:
            flags |= 0x1
            # For simplicity, just code without new_settings (which would need SRP)
            # New settings require complicated SRP flow
            raise NotImplementedError(
                "recover_password with new_password requires SRP; use code-only to clear"
            )

        body = (
            struct.pack("<I", TL_METHODS["auth.recoverPassword"]) +
            struct.pack("<I", flags) +
            self._tl_string(code)
        )
        return await self._send_api_request(body, "auth.recoverPassword")

    # ------------------------------------------------------------------
    #  Block C: bot commands, forum topics, stickers by file, chat themes
    # ------------------------------------------------------------------

    async def get_bot_commands(self, bot_id, scope_ctor=0x2F6CB2AB,
                                 lang_code=""):
        """
        Get bot commands.

        Args:
            bot_id: bot user id.
            scope_ctor: botCommandScopeDefault (0x2F6CB2AB) or
                        botCommandScopePeer (0x54404712)
            lang_code: language code (empty = default).
        """
        if not self._is_running:
            raise JetraError("Client not started.")
        bot_ah = 0
        for d in self.db.get_dialogs():
            if d["peer_id"] == bot_id:
                bot_ah = d["access_hash"] or 0
                break
        bot_input = (
            struct.pack("<I", 0xF21158C6) +
            struct.pack("<q", bot_id) +
            struct.pack("<q", bot_ah)
        )
        scope = struct.pack("<I", scope_ctor)
        body = (
            struct.pack("<I", TL_METHODS["bots.getBotCommands"]) +
            scope +
            self._tl_string(lang_code)
        )
        # bots.getBotCommands needs bot in scope? No, needs bot:InputUser
        # Actually: bots.getBotCommands#e34c0dd6 scope:BotCommandScope lang_code:string
        # (bot comes from scope for peer-scope, or default scope)
        return await self._send_api_request(body, "bots.getBotCommands")

    async def set_bot_commands(self, commands, scope_ctor=0x2F6CB2AB,
                                 lang_code=""):
        """
        Set bot commands (requires bot token - not for regular users).

        Args:
            commands: list of (command, description) tuples.
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        items = b""
        for cmd, desc in commands:
            # botCommand#9852d6d2 flags:# command:string description:string
            items += (
                struct.pack("<I", 0x9852D6D2) +
                struct.pack("<I", 0) +
                self._tl_string(cmd) +
                self._tl_string(desc)
            )
        vec = (
            struct.pack("<I", VECTOR_CTOR) +
            struct.pack("<i", len(commands)) +
            items
        )
        scope = struct.pack("<I", scope_ctor)
        body = (
            struct.pack("<I", TL_METHODS["bots.setBotCommands"]) +
            scope +
            self._tl_string(lang_code) +
            vec
        )
        return await self._send_api_request(body, "bots.setBotCommands")

    async def get_forum_topics(self, channel_id, limit=100, offset_date=0,
                                 offset_id=0, offset_topic=0, query=""):
        """Get forum topics in a group (if forum enabled)."""
        if not self._is_running:
            raise JetraError("Client not started.")
        channel_input = self._get_channel_input(channel_id)

        body = (
            struct.pack("<I", TL_METHODS["messages.getForumTopics"]) +
            channel_input +
            self._tl_string(query) +
            struct.pack("<i", offset_date) +
            struct.pack("<i", offset_id) +
            struct.pack("<i", offset_topic) +
            struct.pack("<i", limit)
        )
        return await self._send_api_request(body, "messages.getForumTopics")

    async def upload_sticker_file(self, user_id, sticker_path, user_access_hash=0):
        """
        Upload a sticker file (for creating sticker sets).

        Args:
            user_id: bot/owner user id.
            sticker_path: local path to sticker image.
        """
        if not self._is_running:
            raise JetraError("Client not started.")

        # Upload as document
        upload = await self.upload_file(sticker_path)
        input_file = upload["input_file"]

        input_user = (
            struct.pack("<I", 0xF21158C6) +
            struct.pack("<q", user_id) +
            struct.pack("<q", user_access_hash)
        )

        body = (
            struct.pack("<I", TL_METHODS["stickers.uploadStickerFile"]) +
            input_user +
            input_file
        )
        return await self._send_api_request(body, "stickers.uploadStickerFile")

    async def create_chat_theme(self, slug, title, emoticon="",
                                  document_id=0):
        """Create a chat theme."""
        if not self._is_running:
            raise JetraError("Client not started.")
        flags = 0
        emoticon_bytes = b""
        if emoticon:
            flags |= 0x4
            emoticon_bytes = self._tl_string(emoticon)

        # theme ctor (theme#a00e67d6)
        # For simplicity, only basic fields
        theme = (
            struct.pack("<I", 0xA00E67D6) +
            struct.pack("<I", flags) +
            self._tl_string(slug) +
            self._tl_string(title)
        )
        if emoticon:
            theme += emoticon_bytes

        body = (
            struct.pack("<I", TL_METHODS["account.createTheme"]) +
            struct.pack("<I", 0) +  # flags
            theme
        )
        return await self._send_api_request(body, "account.createTheme")

    async def install_chat_theme(self, theme_id, theme_access_hash,
                                    dark=False):
        """Install a chat theme."""
        if not self._is_running:
            raise JetraError("Client not started.")
        flags = 0
        if dark:
            flags |= 0x1

        # inputTheme#fcaafeb7 id:long access_hash:long
        input_theme = (
            struct.pack("<I", 0xFCAAFEB7) +
            struct.pack("<q", theme_id) +
            struct.pack("<q", theme_access_hash)
        )

        body = (
            struct.pack("<I", TL_METHODS["account.installTheme"]) +
            struct.pack("<I", flags) +
            input_theme
        )
        return await self._send_api_request(body, "account.installTheme")

    async def save_chat_theme(self, theme_id, theme_access_hash, unsave=False):
        """Save or unsave a chat theme."""
        if not self._is_running:
            raise JetraError("Client not started.")
        flags = 0
        if unsave:
            flags |= 0x1
        input_theme = (
            struct.pack("<I", 0xFCAAFEB7) +
            struct.pack("<q", theme_id) +
            struct.pack("<q", theme_access_hash)
        )
        body = (
            struct.pack("<I", TL_METHODS["account.saveTheme"]) +
            struct.pack("<I", flags) +
            input_theme
        )
        return await self._send_api_request(body, "account.saveTheme")

    async def update_chat_theme(self, theme_id, theme_access_hash,
                                  slug=None, title=None):
        """Update theme slug or title."""
        if not self._is_running:
            raise JetraError("Client not started.")
        flags = 0
        extra = b""
        if slug is not None:
            flags |= 0x1
            extra += self._tl_string(slug)
        if title is not None:
            flags |= 0x2
            extra += self._tl_string(title)

        input_theme = (
            struct.pack("<I", 0xFCAAFEB7) +
            struct.pack("<q", theme_id) +
            struct.pack("<q", theme_access_hash)
        )
        body = (
            struct.pack("<I", TL_METHODS["account.updateTheme"]) +
            struct.pack("<I", flags) +
            input_theme +
            extra
        )
        return await self._send_api_request(body, "account.updateTheme")

    def _unwrap_gzip(self, result):
        if len(result) < 4:
            return result
        if struct.unpack('<I', result[:4])[0] == GZIP_PACKED:
            offset = 4
            if result[offset] < 0xFE:
                length = result[offset]
                offset += 1
            else:
                length = int.from_bytes(result[offset + 1:offset + 4], 'little')
                offset += 4
            return gzip.decompress(result[offset:offset + length])
        return result

    def _parse_rpc_error(self, data):
        if len(data) < 8:
            return "unknown"
        err_data = data[4:]
        if len(err_data) < 1:
            return "unknown"
        s_len = err_data[0]
        return err_data[1:1 + s_len].decode('utf-8', errors='ignore')

    def _tl_string(self, s):
        """Deprecated: delegate to tl_builder.tl_string."""
        return tl_string(s)
