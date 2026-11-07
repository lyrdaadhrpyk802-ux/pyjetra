# ============================================
#  jetrauserapi/srp.py - SRP for Telegram 2FA
#  All code and comments are English. No emojis.
#
#  Reference: https://core.telegram.org/api/srp
# ============================================

import hashlib
import os

from Crypto.Hash import SHA512 as _SHA512
from Crypto.Protocol.KDF import PBKDF2


def H(data: bytes) -> bytes:
    """SHA256 hash function."""
    return hashlib.sha256(data).digest()


def SH(data: bytes, salt: bytes) -> bytes:
    """Salted hash: SHA256(salt | data | salt)."""
    return hashlib.sha256(salt + data + salt).digest()


def xor_bytes(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def pad_2048(n: int) -> bytes:
    """Serialize integer as big-endian, padded to 2048 bits (256 bytes)."""
    return n.to_bytes(256, "big")


def compute_x(password: bytes, salt1: bytes, salt2: bytes) -> int:
    """
    Compute x = PH2(password, salt1, salt2):
        PH1 = SH(SH(password, salt1), salt2)
        PH2 = SH(pbkdf2_sha512(PH1, salt1, 100000), salt2)
    """
    # PH1 = SH(SH(password, salt1), salt2)
    ph1 = SH(SH(password, salt1), salt2)

    # pbkdf2_sha512(ph1, salt1, 100000, 64)
    pbkdf2_result = PBKDF2(
        password=ph1,
        salt=salt1,
        dkLen=64,
        count=100000,
        hmac_hash_module=_SHA512,
    )

    # PH2 = SH(pbkdf2_result, salt2)
    ph2 = SH(pbkdf2_result, salt2)

    return int.from_bytes(ph2, "big")


def compute_srp(algo, srp_B_bytes: bytes, srp_id: int, password: bytes):
    """
    Compute SRP proof per Telegram spec.

    Returns dict with 'srp_id', 'A', 'M1'.
    """
    salt1 = algo["salt1"]
    salt2 = algo["salt2"]
    p_bytes = algo["p"]
    g = algo["g"]

    p = int.from_bytes(p_bytes, "big")
    g_b = int.from_bytes(srp_B_bytes, "big")

    # Validate B
    if g_b % p == 0:
        raise ValueError("Invalid SRP B (0 mod p)")

    # x := PH2(password, salt1, salt2)
    x = compute_x(password, salt1, salt2)

    # k := H(p | g)  (with 2048-bit padding for both)
    k = int.from_bytes(H(pad_2048(p) + pad_2048(g)), "big")

    # v := g^x mod p
    v = pow(g, x, p)

    # k_v := (k * v) mod p
    k_v = (k * v) % p

    # t := (g_b - k_v) mod p  (positive modulo)
    t = (g_b - k_v) % p

    # a := random 2048-bit number
    a = int.from_bytes(os.urandom(256), "big")

    # g_a := g^a mod p
    g_a = pow(g, a, p)

    # u := H(g_a | g_b)  (with 2048-bit padding)
    u = int.from_bytes(H(pad_2048(g_a) + pad_2048(g_b)), "big")

    # s_a := t^(a + u*x) mod p
    s_a = pow(t, a + u * x, p)

    # k_a := H(s_a)  (padded to 2048 bits)
    k_a = H(pad_2048(s_a))

    # M1 := H(H(p) xor H(g) | H(salt1) | H(salt2) | g_a | g_b | k_a)
    h_p = H(pad_2048(p))
    h_g = H(pad_2048(g))
    h_xor = xor_bytes(h_p, h_g)
    h_salt1 = H(salt1)
    h_salt2 = H(salt2)
    M1 = H(
        h_xor +
        h_salt1 +
        h_salt2 +
        pad_2048(g_a) +
        pad_2048(g_b) +
        k_a
    )

    return {
        "srp_id": srp_id,
        "A": pad_2048(g_a),
        "M1": M1,
    }
