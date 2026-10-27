"""Erzeugt künstliche .mcrec-Aufnahmen für Tests (keine echten Bildschirminhalte im Repo)."""
import io
import json
import struct

from PIL import Image


def _time_bytes(t_ms, style):
    if style == "browser":
        # agent-desktop-0.0.2.js: intToStr(now >> 32) + intToStr(now & 32)
        hi = ((t_ms + (1 << 31)) % (1 << 32)) - (1 << 31)  # int32(now)
        return struct.pack(">iI", hi, t_ms & 32)
    # meshrelay.js: header.writeIntBE(Date, 10, 6)
    return b"\0\0" + t_ms.to_bytes(6, "big")


def entry(typ, flags, data, t_ms=0, style="browser"):
    return struct.pack(">HHI", typ, flags, len(data)) + _time_bytes(t_ms, style) + data


def png(color, size, noise=False):
    img = Image.new("RGB", size, color)
    if noise:
        import random
        rnd = random.Random(1)
        img.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
                     for _ in range(size[0] * size[1])])
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def cmd(c, payload):
    return struct.pack(">HH", c, (4 + len(payload)) & 0xFFFF) + payload


def screen(w, h):
    return cmd(7, struct.pack(">HH", w, h))


def tile(x, y, img_bytes):
    view = cmd(3, struct.pack(">HH", x, y) + img_bytes)
    if len(view) > 65000:  # wie der Browser: Großpaket-Wrapper vor die echte Nachricht
        return struct.pack(">HHIHHHH", 27, 8, len(view), 3, 0, 0, 0) + view
    return view


def recording(events, meta=None, style="browser", t_base=1_761_552_000_000, end_ms=None):
    """events: Liste von (t_ms relativ, Desktop-Kommando-Bytes)."""
    meta = {"magic": "MeshCentralRelaySession", "ver": 1, "time": "27.10.2026, 09:12:38", "protocol": 2,
            **(meta or {})}
    out = entry(1, 0, json.dumps(meta).encode(), t_base, style)
    for t, data in events:
        out += entry(2, 1, data, t_base + t, style)
    end = end_ms if end_ms is not None else (events[-1][0] if events else 0)
    out += entry(3, 0, b"MeshCentralMCREC", t_base + end, style)
    return out
