import asyncio
import websockets
import os
import struct
import time
import math
import random
import hashlib
from Crypto.Cipher import AES
from Crypto.Util import Counter

from pyjetra.userapi.tl_builder import tl_string, tl_bytes

RSA_MODULUS_HEX = (
    "a1d79eb1ffcc0edd282c52215e60491200cc4d5f907e6d5ceb759958282d389e9c"
    "9443b0a8e4505a608bfe2f14a157c3e24b553017cb8d310d0c48fd8a63340cd556f"
    "83bc4cd48400cd582dd881dc7c52b14d6b7f469f0e889444734f65736ad6ace97d5"
    "7ef551a572414272760e2bffcca018e5c9951488cfbbcd0e87dc33a9242b2f71eca"
    "049a4050df82f3e630a2725887f8b1498146fc9d0f253d0746b690655e6ac65485c"
    "e8d257e22f7a95d75f24d8efa7a679deb794dc66bd888155ae5f3334a40861b4afa"
    "c807843cc253df4595b7ef709c8395663b38f37db18778f7ae1ca4b7f30cbe714bc"
    "e8de57ab54610273fd685c11dad77e3ad26031bda32f"
)
RSA_MODULUS = int(RSA_MODULUS_HEX, 16)
RSA_EXPONENT = 65537

JETRA_DH_PRIME = int("c71caeb9c6b1c9048e6c522f70f13f73980d40238e3e21c14934d037563d930f48198a0aa7c14058229493d22530f4dbfa336f6e0ac925139543aed44cce7c3720fd51f69458705ac68cd4fe6b6b13abdc9746512969328454f18faf8c595f642477fe96bb2a941d5bcd1d4ac8cc49880708fa9b378e3c4f3a9060bee67cf9a4a4a695811051907e162753b56b0f6b410dba74d8a84b2a14b3144e0ef1284754fd17ed950d5965b4b9dd46582db1178d169c6bc465b0d6ff9ca3928fef5b9ae4e418fc15e83ebea0f87fa9ff5eed70050ded2849f47bf959d956850ce929851f0d8115f635b105ee2e4e15d04b2454bf6f4fadf034b10403119cd8e3b92fcc5b", 16)

def tl_store_bytes(data):
    n = len(data)
    if n <= 253:
        buf = bytes([n]) + data
    else:
        buf = b'\xfe' + n.to_bytes(3, 'little') + data
    return buf + b'\x00' * ((4 - len(buf) % 4) % 4)

def aes_ige_encrypt(plaintext, key, iv):
    cipher = AES.new(key, AES.MODE_ECB)
    n = len(plaintext)
    out = bytearray(n)
    prev_c = iv[:16]
    prev_p = iv[16:]
    for i in range(0, n, 16):
        block = plaintext[i:i+16]
        x = bytes(a ^ b for a, b in zip(block, prev_c))
        y = cipher.encrypt(x)
        c = bytes(a ^ b for a, b in zip(y, prev_p))
        out[i:i+16] = c
        prev_c = c
        prev_p = block
    return bytes(out)

def aes_ige_decrypt(ciphertext, key, iv):
    cipher = AES.new(key, AES.MODE_ECB)
    n = len(ciphertext)
    out = bytearray(n)
    prev_c = iv[:16]
    prev_p = iv[16:]
    for i in range(0, n, 16):
        block = ciphertext[i:i+16]
        x = bytes(a ^ b for a, b in zip(block, prev_p))
        y = cipher.decrypt(x)
        c = bytes(a ^ b for a, b in zip(y, prev_c))
        out[i:i+16] = c
        prev_c = block
        prev_p = c
    return bytes(out)

def rsa_pad(inner_data):
    n = RSA_MODULUS
    for _ in range(100):
        padded = inner_data + os.urandom(192 - len(inner_data))
        rev = padded[::-1]
        tk = os.urandom(32)
        dwh = rev + hashlib.sha256(tk + padded).digest()
        ige = aes_ige_encrypt(dwh, tk, b'\x00' * 32)
        xored = bytes(a ^ b for a, b in zip(tk, hashlib.sha256(ige).digest()))
        blob = xored + ige
        if int.from_bytes(blob, 'big') < n:
            c = pow(int.from_bytes(blob, 'big'), RSA_EXPONENT, n)
            return c.to_bytes(256, 'big')
    raise RuntimeError("RSA pad failed")

def wrap_init_connection(inner_query):
    API_ID = 3893396
    LAYER = 228
    init_body = (
        struct.pack("<I", 0xC1CD5EA9) +
        struct.pack("<I", 0) +
        struct.pack("<I", API_ID) +
        tl_string("Samsung SM-G973F") +
        tl_string("Android 12") +
        tl_string("0.1.0 K voiceotp=1") +
        tl_string("fa") +
        tl_string("webk") +
        tl_string("fa") +
        inner_query
    )
    return (
        struct.pack("<I", 0xDA9B0D0D) +
        struct.pack("<i", LAYER) +
        init_body
    )

class JetraClient:
    def __init__(self, ws_url="wss://web.jetra.ir/apiws", session=None):
        self.ws_url = ws_url
        self.ws = None
        self.enc_cipher = None
        self.dec_cipher = None
        self.new_nonce = None
        self.b = None
        self.auth_key = None
        self.auth_key_id = None
        
        if session:
            self.server_salt = session.server_salt
            self.session_id = session.session_id
            self.auth_key = session.auth_key
            self.auth_key_id = session.auth_key_id
        else:
            self.server_salt = b'\x00' * 8
            self.session_id = os.urandom(8)
            
        self.seq_no = 0

    def _pack_msg_id(self):
        return struct.pack("<Q", (int(time.time()) << 32) | 4)

    def _abridged_frame(self, data):
        length = len(data)
        if length < 127:
            return struct.pack("<B", length >> 2) + data
        else:
            return b'\x7f' + struct.pack("<I", length >> 2)[:3] + data

    async def connect(self):
        print(f"Connecting to {self.ws_url}...")
        self.ws = await websockets.connect(self.ws_url)
        print("WebSocket connected!")

        while True:
            header = bytearray(os.urandom(64))
            if header[0] == 0xEF:
                continue
            if struct.unpack("<I", header[0:4])[0] in (0x44414548, 0x54534F50, 0x20544745, 0x4954504F, 0xEEEEEEEE, 0xDDDDDDDD):
                continue
            if struct.unpack("<I", header[4:8])[0] == 0:
                continue
            break

        header[56:60] = b'\xEF\xEF\xEF\xEF'
        header_rev = header[::-1]
        
        enc_key = bytes(header[8:40])
        enc_iv = bytes(header[40:56])
        dec_key = bytes(header_rev[8:40])
        dec_iv = bytes(header_rev[40:56])

        self.enc_cipher = AES.new(enc_key, AES.MODE_CTR, counter=Counter.new(128, initial_value=int.from_bytes(enc_iv, 'big')))
        self.dec_cipher = AES.new(dec_key, AES.MODE_CTR, counter=Counter.new(128, initial_value=int.from_bytes(dec_iv, 'big')))

        encrypted_tail = self.enc_cipher.encrypt(bytes(header))[56:64]
        header[56:64] = encrypted_tail

        print("Sending header...")
        await self.ws.send(bytes(header))

    async def send_req_pq(self):
        self.new_nonce = os.urandom(32)
        print(f"Generated new_nonce: {self.new_nonce.hex()}")
        
        nonce = os.urandom(16)
        msg_id = self._pack_msg_id()
        method_buf = struct.pack("<I", 0xBE7E8EF1) + nonce
        packet = b"\x00"*8 + msg_id + struct.pack("<I", len(method_buf)) + method_buf

        framed = self._abridged_frame(packet)
        encrypted = self.enc_cipher.encrypt(framed)

        print(f"Sending req_pq_multi (encrypted)...")
        await self.ws.send(encrypted)
        return nonce

    async def recv(self):
        """
        Receive one message and return the TL body (after stripping envelope).

        Handles three layers:
          1. Transport frame (abridged length prefix) - stripped
          2. Envelope (auth_key_id:8, msg_id:8, msg_len:4) - stripped
          3. TL body (ctor + params) - returned to caller

        Envelope stripping is done even when auth_key_id=0 (pre-auth).
        """
        response = await self.ws.recv()
        decrypted = self.dec_cipher.decrypt(response)

        if len(decrypted) < 1:
            return b""

        first_byte = decrypted[0]
        if first_byte < 0x7F:
            frame_len = first_byte << 2
            payload = decrypted[1:1+frame_len]
        elif first_byte == 0x7F:
            if len(decrypted) < 4:
                return b""
            frame_len = int.from_bytes(decrypted[1:4], "little") << 2
            payload = decrypted[4:4+frame_len]
        else:
            payload = decrypted

        # Strip envelope: auth_key_id(8) + msg_id(8) + msg_len(4) + body
        if len(payload) >= 20:
            msg_len = struct.unpack("<I", payload[16:20])[0]
            if msg_len > 0 and msg_len <= len(payload) - 20:
                return payload[20:20 + msg_len]

        # If envelope parse fails, return full payload (edge case)
        return payload

    def parse_res_pq(self, data):
        # recv() strips transport + envelope; body starts at offset 0.
        offset = 0

        res_pq_ctor = struct.unpack("<I", data[offset:offset+4])[0]
        offset += 4
        
        if res_pq_ctor != 0x05162463:
            raise ValueError(f"Invalid resPQ constructor: {hex(res_pq_ctor)}")
        
        nonce = data[offset:offset+16]
        offset += 16
        server_nonce = data[offset:offset+16]
        offset += 16
        pq_len = data[offset]
        offset += 1
        pq = data[offset:offset+pq_len]
        offset += pq_len
        offset = (offset + 3) & ~3
        
        vector_ctor = struct.unpack("<I", data[offset:offset+4])[0]
        offset += 4
        
        fp_count = struct.unpack("<I", data[offset:offset+4])[0]
        offset += 4
        
        fingerprints = []
        for _ in range(fp_count):
            fp = struct.unpack("<Q", data[offset:offset+8])[0]
            fingerprints.append(fp)
            offset += 8
        
        return {
            'nonce': nonce,
            'server_nonce': server_nonce,
            'pq': pq,
            'fingerprints': fingerprints
        }

    def factorize_pq(self, pq):
        pq_int = int.from_bytes(pq, 'big')
        if pq_int % 2 == 0:
            return 2, pq_int // 2
        
        def pollard_rho(n):
            if n % 2 == 0:
                return 2
            x = random.randint(2, n-1)
            y = x
            c = random.randint(1, n-1)
            d = 1
            while d == 1:
                x = (x*x + c) % n
                y = (y*y + c) % n
                y = (y*y + c) % n
                d = math.gcd(abs(x-y), n)
            return d
        
        p = pollard_rho(pq_int)
        q = pq_int // p
        return p, q

    async def send_req_dh_params(self, parsed_respq):
        nonce = parsed_respq['nonce']
        server_nonce = parsed_respq['server_nonce']
        pq = parsed_respq['pq']
        fingerprints = parsed_respq['fingerprints']
        
        fingerprint = fingerprints[0]
        
        p, q = self.factorize_pq(pq)
        if p > q:
            p, q = q, p
        
        p_bytes = p.to_bytes((p.bit_length() + 7) // 8, 'big')
        q_bytes = q.to_bytes((q.bit_length() + 7) // 8, 'big')
        
        pq_tl = tl_store_bytes(pq)
        p_tl = tl_store_bytes(p_bytes)
        q_tl = tl_store_bytes(q_bytes)
        
        inner = (
            struct.pack("<I", 0xA9F55F95) +
            pq_tl +
            p_tl +
            q_tl +
            nonce +
            server_nonce +
            self.new_nonce +
            struct.pack("<i", 2)
        )
        
        encrypted_data = rsa_pad(inner)
        
        req_body = (
            struct.pack("<I", 0xD712E4BE) +
            nonce +
            server_nonce +
            p_tl +
            q_tl +
            struct.pack("<Q", fingerprint) +
            tl_store_bytes(encrypted_data)
        )
        
        msg_id = self._pack_msg_id()
        packet = b"\x00"*8 + msg_id + struct.pack("<I", len(req_body)) + req_body
        
        framed = self._abridged_frame(packet)
        encrypted = self.enc_cipher.encrypt(framed)
        
        await self.ws.send(encrypted)

    def parse_server_dh_params_ok(self, data):
        # recv() strips transport + envelope.
        # data layout (TL body):
        #   ctor: 4 (server_DH_params_ok = 0xD0E8075C)
        #   nonce: 16
        #   server_nonce: 16
        #   encrypted_answer: bytes (length prefix + content)
        offset = 0

        ctor = struct.unpack("<I", data[offset:offset+4])[0]
        offset += 4
        if ctor != 0xD0E8075C:
            raise ValueError(f"Invalid server_DH_params_ok ctor: 0x{ctor:08X}")

        nonce = data[offset:offset+16]
        offset += 16
        server_nonce = data[offset:offset+16]
        offset += 16

        enc_len_byte = data[offset]
        if enc_len_byte < 0xFE:
            enc_len = enc_len_byte
            offset += 1
        else:
            enc_len = int.from_bytes(data[offset+1:offset+4], "little")
            offset += 4

        encrypted_answer = data[offset:offset+enc_len]

        return {
            "nonce": nonce,
            "server_nonce": server_nonce,
            "encrypted_answer": encrypted_answer,
        }

    async def complete_auth(self, parsed_respq, decrypted_answer):
        nonce = parsed_respq['nonce']
        server_nonce = parsed_respq['server_nonce']
        
        inner_ctor = struct.pack("<I", 0xB5890DBA)
        pos = decrypted_answer.find(inner_ctor)
        if pos == -1:
            raise ValueError("server_DH_inner_data not found")
        
        server_dh_inner = decrypted_answer[pos:]
        
        offset = 4 + 16 + 16 + 4
        dh_prime_len = server_dh_inner[offset]
        if dh_prime_len < 0xFE:
            offset += 1 + dh_prime_len
        else:
            dh_prime_len = int.from_bytes(server_dh_inner[offset+1:offset+4], 'little')
            offset += 4 + dh_prime_len
        offset = (offset + 3) & ~3
        
        g_a_len = server_dh_inner[offset]
        if g_a_len < 0xFE:
            g_a = server_dh_inner[offset+1:offset+1+g_a_len]
            offset += 1 + g_a_len
        else:
            g_a_len = int.from_bytes(server_dh_inner[offset+1:offset+4], 'little')
            g_a = server_dh_inner[offset+4:offset+4+g_a_len]
            offset += 4 + g_a_len
        
        self.server_salt = bytes(a ^ b for a, b in zip(self.new_nonce[:8], server_nonce[:8]))
        
        self.b = os.urandom(256)
        b_int = int.from_bytes(self.b, 'big')
        
        g = 3
        g_b_int = pow(g, b_int, JETRA_DH_PRIME)
        g_b_bytes = g_b_int.to_bytes(256, 'big')
        
        g_a_int = int.from_bytes(g_a, 'big')
        auth_key_int = pow(g_a_int, b_int, JETRA_DH_PRIME)
        self.auth_key = auth_key_int.to_bytes(256, 'big')
        self.auth_key_id = hashlib.sha1(self.auth_key).digest()[-8:]
        
        client_inner = (
            struct.pack("<I", 0x6643B654) +
            nonce +
            server_nonce +
            struct.pack("<Q", 0) +
            tl_store_bytes(g_b_bytes)
        )
        
        inner_hash = hashlib.sha1(client_inner).digest()
        inner_with_hash = inner_hash + client_inner
        
        sha1_a = hashlib.sha1(self.new_nonce + server_nonce).digest()
        sha1_b = hashlib.sha1(server_nonce + self.new_nonce).digest()
        sha1_c = hashlib.sha1(self.new_nonce + self.new_nonce).digest()
        
        tmp_aes_key = sha1_a + sha1_b[:12]
        tmp_aes_iv = sha1_b[12:] + sha1_c + self.new_nonce[:4]
        
        padding_len = 16 - (len(inner_with_hash) % 16)
        if padding_len < 16:
            inner_with_hash = inner_with_hash + os.urandom(padding_len)
        
        encrypted_inner = aes_ige_encrypt(inner_with_hash, tmp_aes_key, tmp_aes_iv)
        
        req_body = (
            struct.pack("<I", 0xF5045F1F) +
            nonce +
            server_nonce +
            tl_store_bytes(encrypted_inner)
        )
        
        msg_id = self._pack_msg_id()
        packet = b"\x00"*8 + msg_id + struct.pack("<I", len(req_body)) + req_body
        
        framed = self._abridged_frame(packet)
        encrypted = self.enc_cipher.encrypt(framed)
        
        await self.ws.send(encrypted)

    def decrypt_response(self, response):
        if len(response) < 24:
            return None
        
        auth_key_id = response[0:8]
        msg_key_received = response[8:24]
        encrypted_data = response[24:]
        
        if len(encrypted_data) % 16 != 0:
            encrypted_data = encrypted_data[:len(encrypted_data) - (len(encrypted_data) % 16)]
        
        if len(encrypted_data) == 0:
            return None
        
        i = 8
        
        a = bytearray(52)
        a[0:16] = msg_key_received
        a[16:52] = self.auth_key[i:i+36]
        s0 = hashlib.sha256(bytes(a)).digest()
        
        o = bytearray(52)
        o[0:36] = self.auth_key[40+i:40+i+36]
        o[36:52] = msg_key_received
        s1 = hashlib.sha256(bytes(o)).digest()
        
        aes_key = s0[0:8] + s1[8:24] + s0[24:32]
        aes_iv = s1[0:8] + s0[8:24] + s1[24:32]
        
        decrypted = aes_ige_decrypt(encrypted_data, aes_key, aes_iv)
        
        offset = 0
        salt = decrypted[offset:offset+8]; offset += 8
        session_id = decrypted[offset:offset+8]; offset += 8
        msg_id = struct.unpack("<Q", decrypted[offset:offset+8])[0]; offset += 8
        seq_no = struct.unpack("<I", decrypted[offset:offset+4])[0]; offset += 4
        msg_len = struct.unpack("<I", decrypted[offset:offset+4])[0]; offset += 4
        msg_data = decrypted[offset:offset+msg_len]
        
        return msg_data

    async def send_request(self, method_bytes):
        # Pre-auth requests (e.g. auth.sendCode) have no auth_key yet.
        # Use zero salt and unencrypted transport for those calls.
        if not self.auth_key:
            return await self._send_request_unencrypted(method_bytes)

        msg_id_bytes = self._pack_msg_id()
        msg_id_int = struct.unpack("<Q", msg_id_bytes)[0]
        
        self.seq_no += 1
        seq_no = struct.pack("<I", self.seq_no * 2 - 1)
        msg_len = struct.pack("<I", len(method_bytes))
        
        salt = self.server_salt if self.server_salt is not None else b'\x00' * 8
        buffer_without_padding = salt + self.session_id + msg_id_bytes + seq_no + msg_len + method_bytes
        offset = len(buffer_without_padding)
        padding_len = 16 - (offset % 16) + 16 * (1 + random.randint(0, 4))
        padding = os.urandom(padding_len)
        
        payload = buffer_without_padding + padding
        
        msg_key = hashlib.sha256(self.auth_key[88:120] + payload).digest()[8:24]
        
        a = bytearray(52)
        a[0:16] = msg_key
        a[16:52] = self.auth_key[0:36]
        s0 = hashlib.sha256(bytes(a)).digest()
        
        o = bytearray(52)
        o[0:36] = self.auth_key[40:76]
        o[36:52] = msg_key
        s1 = hashlib.sha256(bytes(o)).digest()
        
        aes_key = s0[0:8] + s1[8:24] + s0[24:32]
        aes_iv = s1[0:8] + s0[8:24] + s1[24:32]
        
        encrypted_data = aes_ige_encrypt(payload, aes_key, aes_iv)
        
        packet = self.auth_key_id + msg_key + encrypted_data
        framed = self._abridged_frame(packet)
        encrypted = self.enc_cipher.encrypt(framed)
        
        await self.ws.send(encrypted)
        print(f"Request sent (msg_id: {msg_id_int})")
        
        for _ in range(10):
            response = await asyncio.wait_for(self.recv(), timeout=10.0)
            msg_data = self.decrypt_response(response)
            
            if msg_data and len(msg_data) >= 4:
                ctor = struct.unpack("<I", msg_data[:4])[0]
                if ctor == 0xF35C6D01:
                    req_msg_id = struct.unpack("<Q", msg_data[4:12])[0]
                    if req_msg_id == msg_id_int:
                        result_data = msg_data[12:]
                        return result_data
        return None

    async def invoke(self, method_id: int, *args):
        """
        Generic invoke method for any TL method.
        Usage:
            await client.invoke(0xFEF48F62, peer, message, random_id)
        """
        body = struct.pack("<I", method_id)
        for arg in args:
            if isinstance(arg, bytes):
                body += arg
            elif isinstance(arg, int):
                body += struct.pack("<i", arg)
            elif isinstance(arg, str):
                body += tl_string(arg)
            else:
                raise ValueError(f"Unsupported arg type: {type(arg)}")
        
        return await self.send_request(wrap_init_connection(body))

    async def _send_request_unencrypted(self, method_bytes):
        """
        Send a request without auth_key (used for auth.sendCode, auth.signIn).

        In this mode, messages are plain TL payloads wrapped in the
        abridged frame, not encrypted with auth_key.
        """
        msg_id_bytes = self._pack_msg_id()
        msg_id_int = struct.unpack("<Q", msg_id_bytes)[0]

        self.seq_no += 1
        seq_no = struct.pack("<I", self.seq_no * 2 - 1)
        msg_len = struct.pack("<I", len(method_bytes))

        # Unencrypted messages: auth_key_id = 0, msg_id, msg_len, body
        packet = (
            b'\x00' * 8 +      # auth_key_id = 0
            msg_id_bytes +
            msg_len +
            method_bytes
        )

        framed = self._abridged_frame(packet)
        encrypted = self.enc_cipher.encrypt(framed)

        await self.ws.send(encrypted)
        print(f"Unencrypted request sent (msg_id: {msg_id_int})")

        for _ in range(10):
            response = await asyncio.wait_for(self.recv(), timeout=10.0)
            # Response is unencrypted now (not through decrypt_response)
            # The recv() decrypts with dec_cipher, so the response IS still
            # in the encrypted stream but with auth_key_id = 0.
            if not response or len(response) < 24:
                continue
            auth_key_id = response[0:8]
            if auth_key_id != b'\x00' * 8:
                continue
            # Extract msg_data from unencrypted envelope
            # The response after decrypt should already be the raw body
            # Format: auth_key_id(8) + msg_id(8) + msg_len(4) + body
            body_len = struct.unpack("<I", response[16:20])[0]
            body = response[20:20 + body_len]
            if len(body) < 4:
                continue
            ctor = struct.unpack("<I", body[:4])[0]
            if ctor == 0xF35C6D01:  # rpc_result
                req_msg_id = struct.unpack("<Q", body[4:12])[0]
                if req_msg_id == msg_id_int:
                    return body[12:]
        return None

    async def close(self):
        if self.ws:
            await self.ws.close()
