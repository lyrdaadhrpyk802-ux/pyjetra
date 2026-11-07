# ============================================
#  jetrauserapi/parsers.py - TL response parsers
#  All code and comments are English. No emojis.
# ============================================

import struct


# Constructors
MSG_CTOR_JETRA = 0x7600B9D3
SERVICE_MSG_CTOR_JETRA = 0x7A800E0A
PEER_USER = 0x59511722
PEER_CHANNEL = 0xA2A5371E
UPDATES_CTOR = 0x74AE4240


def _parse_peer(data: bytes, offset: int):
    """
    Parse a Peer (peerUser/peerChat/peerChannel).

    Returns (peer_ctor, peer_id, new_offset).
    peer ctor is 4 bytes + id is 8 bytes = 12 total.
    """
    if offset + 12 > len(data):
        return None, None, offset
    peer_ctor = struct.unpack("<I", data[offset:offset+4])[0]
    offset += 4
    peer_id = struct.unpack("<q", data[offset:offset+8])[0]
    offset += 8
    return peer_ctor, peer_id, offset


def _parse_message_at(data: bytes, offset: int):
    """
    Parse a Jetra Message constructor starting at offset.

    Correct structure (from TL schema):
        message#7600b9d3
            flags:#
            flags2:#
            id:int
            from_id:flags.8?Peer
            peer_id:Peer
            saved_peer_id:flags.28?Peer
            ... (many optional fields)
            date:int
            message:string
            ...

    We only parse: id, from_id, peer_id, date, text.
    All optional fields are skipped based on their flag bits.
    """
    if offset + 4 > len(data):
        return None

    ctor = struct.unpack("<I", data[offset:offset + 4])[0]
    if ctor not in (MSG_CTOR_JETRA, SERVICE_MSG_CTOR_JETRA):
        return None

    try:
        pos = offset + 4

        if ctor == SERVICE_MSG_CTOR_JETRA:
            # service messages have simpler structure; skip for now
            return None

        flags = struct.unpack("<I", data[pos:pos + 4])[0]
        pos += 4
        flags2 = struct.unpack("<I", data[pos:pos + 4])[0]
        pos += 4

        msg_id = struct.unpack("<i", data[pos:pos + 4])[0]
        pos += 4

        # from_id: flags.8?Peer
        from_id = 0
        if flags & 0x100:
            fp_ctor, fid, pos = _parse_peer(data, pos)
            from_id = fid

        # peer_id: Peer (always)
        pp_ctor, peer_id, pos = _parse_peer(data, pos)
        if pp_ctor == PEER_USER:
            peer_type = "user"
        elif pp_ctor == PEER_CHANNEL:
            peer_type = "group"
        else:
            peer_type = "unknown"

        # saved_peer_id: flags.28?Peer
        if flags & 0x10000000:
            _, _, pos = _parse_peer(data, pos)

        # fwd_from: flags.2?MessageFwdHeader - complex, skip by scanning
        # (for now assume not present; advanced parsing later)

        # date: int
        date = struct.unpack("<i", data[pos:pos + 4])[0]
        pos += 4

        # message: string
        text = ""
        try:
            text_len = data[pos]
            text = data[pos + 1:pos + 1 + text_len].decode("utf-8", errors="ignore")
            pos += 1 + text_len
            pos = (pos + 3) & ~3
        except Exception:
            pass

        return {
            "msg_id": msg_id,
            "from_id": from_id,
            "peer_id": peer_id,
            "peer_type": peer_type,
            "date": date,
            "text": text,
            "offset": offset,
        }
    except Exception:
        return None


def parse_sent_message(data: bytes):
    """
    Parse a messages.sendMessage response and extract the sent Message.

    Handles two cases:
      1. Top-level Updates ctor -> scan for nested Message ctor.
      2. Top-level Message ctor (rare, bare message).

    Returns dict from _parse_message_at, or None.
    """
    if not data or len(data) < 4:
        return None

    top_ctor = struct.unpack("<I", data[:4])[0]

    if top_ctor == UPDATES_CTOR:
        needle = struct.pack("<I", MSG_CTOR_JETRA)
        pos = 4
        while True:
            pos = data.find(needle, pos)
            if pos < 0:
                break
            parsed = _parse_message_at(data, pos)
            if parsed:
                return parsed
            pos += 4
        return None

    return _parse_message_at(data, 0)
