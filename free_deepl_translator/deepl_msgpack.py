import msgpack

def msgpackPack(messages: list[bytes]) -> bytes:
    def encode_varint(value: int) -> bytes:
        parts = []
        while True:
            byte = value & 0x7F
            value >>= 7
            if value:
                parts.append(byte | 0x80)
            else:
                parts.append(byte)
                break
        return bytes(parts)
    output = bytearray()
    for msg in messages:
        msgb = msgpack.packb(msg)
        output += encode_varint(len(msgb))
        output += msgb
    return bytes(output)

def msgpackUnpack(data: bytes) -> list[bytes]:
    messages = []
    n = data
    o = [0, 7, 14, 21, 28]
    r = 0
    while r < len(n):
        size = 0
        i = 0
        while True:
            if r + i >= len(n):
                raise ValueError("Message size varint incomplete")
            s = n[r + i]
            size |= (s & 0x7F) << o[i]
            i += 1
            if (s & 0x80) == 0 or i >= 5:
                break
        if (s & 0x80) != 0 and i < 5:
            raise ValueError("Cannot read message size.")
        if i == 5 and s > 7:
            raise ValueError("Messages bigger than 2GB are not supported.")
        start = r + i
        end = start + size
        if end > len(n):
            raise ValueError("Incomplete message.")
        messages.append(msgpack.unpackb(n[start:end]))
        r = end
    return messages

