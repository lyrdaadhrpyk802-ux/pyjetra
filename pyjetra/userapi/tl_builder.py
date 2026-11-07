import struct

def tl_bytes(data: bytes) -> bytes:
    """Serialize bytes with TL length prefix"""
    n = len(data)
    if n <= 253:
        buf = bytes([n]) + data
    else:
        buf = b'\xfe' + n.to_bytes(3, 'little') + data
    return buf + b'\x00' * ((4 - len(buf) % 4) % 4)

def tl_string(s: str) -> bytes:
    """Serialize a string as TL bytes"""
    return tl_bytes(s.encode('utf-8'))

def tl_int(n: int) -> bytes:
    """Serialize a 32-bit signed integer"""
    return struct.pack("<i", n)

def tl_uint(n: int) -> bytes:
    """Serialize a 32-bit unsigned integer"""
    return struct.pack("<I", n)

def tl_long(n: int) -> bytes:
    """Serialize a 64-bit signed integer"""
    return struct.pack("<q", n)

def tl_ulong(n: int) -> bytes:
    """Serialize a 64-bit unsigned integer"""
    return struct.pack("<Q", n)

def tl_double(d: float) -> bytes:
    """Serialize a 64-bit float"""
    return struct.pack("<d", d)

def tl_bool(b: bool) -> bytes:
    """Serialize a boolean (boolTrue or boolFalse)"""
    return struct.pack("<I", 0x997275B5 if b else 0xBC799737)

def tl_vector(items: list) -> bytes:
    """Serialize a vector of already-serialized items"""
    result = struct.pack("<I", 0x1CB5C415) + struct.pack("<i", len(items))
    for item in items:
        result += item
    return result

def tl_vector_int(items: list) -> bytes:
    """Serialize a vector of 32-bit integers"""
    return tl_vector([tl_int(x) for x in items])

def tl_vector_long(items: list) -> bytes:
    """Serialize a vector of 64-bit integers"""
    return tl_vector([tl_long(x) for x in items])

def tl_vector_string(items: list) -> bytes:
    """Serialize a vector of strings"""
    return tl_vector([tl_string(x) for x in items])

def tl_read_bytes(data: bytes, offset: int):
    """Read TL bytes from data at offset. Returns (value, new_offset)"""
    n = data[offset]
    if n < 0xFE:
        val = data[offset+1:offset+1+n]
        new_offset = offset + 1 + n
    else:
        n = int.from_bytes(data[offset+1:offset+4], 'little')
        val = data[offset+4:offset+4+n]
        new_offset = offset + 4 + n
    new_offset = (new_offset + 3) & ~3
    return val, new_offset

def tl_read_string(data: bytes, offset: int):
    """Read TL string from data at offset. Returns (string, new_offset)"""
    val, new_offset = tl_read_bytes(data, offset)
    return val.decode('utf-8', errors='ignore'), new_offset

def tl_read_int(data: bytes, offset: int):
    """Read 32-bit signed integer"""
    return struct.unpack("<i", data[offset:offset+4])[0], offset + 4

def tl_read_uint(data: bytes, offset: int):
    """Read 32-bit unsigned integer"""
    return struct.unpack("<I", data[offset:offset+4])[0], offset + 4

def tl_read_long(data: bytes, offset: int):
    """Read 64-bit signed integer"""
    return struct.unpack("<q", data[offset:offset+8])[0], offset + 8

def tl_read_ulong(data: bytes, offset: int):
    """Read 64-bit unsigned integer"""
    return struct.unpack("<Q", data[offset:offset+8])[0], offset + 8

def tl_read_double(data: bytes, offset: int):
    """Read 64-bit float"""
    return struct.unpack("<d", data[offset:offset+8])[0], offset + 8

def tl_read_vector_header(data: bytes, offset: int):
    """Read vector constructor and count. Returns (count, new_offset) or (None, offset) if not a vector"""
    if offset + 8 > len(data):
        return None, offset
    ctor = struct.unpack("<I", data[offset:offset+4])[0]
    if ctor != 0x1CB5C415:
        return None, offset
    count = struct.unpack("<i", data[offset+4:offset+8])[0]
    return count, offset + 8
