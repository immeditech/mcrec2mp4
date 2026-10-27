"""Lesen von MeshCentral-Aufzeichnungen (.mcrec).

Format siehe docs/format.md. Quelle: MeshCentral (views/player.handlebars,
public/scripts/agent-desktop-0.0.2.js, meshrelay.js).
"""
import datetime
import json
import os
import re
import struct

PROTO_NAMES = {1: "Terminal", 2: "Desktop", 6: "Terminal", 8: "Terminal", 9: "Terminal",
               101: "Intel-AMT-Desktop", 102: "Intel-AMT-Terminal"}

# Blocktypen
T_META, T_DATA, T_END = 1, 2, 3
# Desktop-Kommandos
CMD_TILE, CMD_SCREEN, CMD_WRAPPER = 3, 7, 27

_WRAP = 1 << 32


class McrecError(Exception):
    pass


def blocks(data):
    """Liefert (type, flags, t_ms, payload) für jeden Block.

    Die Zeit wird wie im MeshCentral-Player berechnet: ``int32(Bytes 8–11) + uint32(Bytes 12–15)``
    (in JS ist ``x << 32 == x``). Browser- und Server-Aufnahmen schreiben die Zeit unterschiedlich,
    beide laufen modulo 2³² über – deshalb wird die Zeit hier zusätzlich entfaltet, sodass sie
    über die ganze Aufnahme monoton bleibt. Nur Zeitabstände sind aussagekräftig.
    """
    p, n = 0, len(data)
    prev = None
    t = 0
    while p + 16 <= n:
        typ, flags, size = struct.unpack_from(">HHI", data, p)
        hi, lo = struct.unpack_from(">iI", data, p + 8)
        raw = (hi + lo) % _WRAP
        if prev is not None:
            delta = (raw - prev) % _WRAP
            if delta >= _WRAP // 2:  # kleiner Rücksprung statt Überlauf
                delta -= _WRAP
            t += delta
        prev = raw
        if p + 16 + size > n:
            break  # abgeschnittener letzter Block
        yield typ, flags, t, data[p + 16:p + 16 + size]
        p += 16 + size


def desktop_commands(data):
    """Liefert (t_ms, cmd, view) für alle Desktop-Kommandos Gerät → Benutzer."""
    for typ, flags, t, v in blocks(data):
        if typ != T_DATA or not (flags & 1) or (flags & 2) or len(v) < 4:
            continue
        cmd, cmdsize = struct.unpack_from(">HH", v)
        if cmd == CMD_WRAPPER and cmdsize == 8 and len(v) >= 10:  # Großpaket-Wrapper
            cmdsize = struct.unpack_from(">I", v, 4)[0]
            cmd = struct.unpack_from(">H", v, 8)[0]
            v = v[8:]
        if cmdsize + 8 == len(v):  # doppelter Kopf
            v = v[8:]
        if cmdsize != len(v):
            continue  # der Player verwirft das ebenso ("Bad command size")
        yield t, cmd, v


def read_meta(data):
    for typ, _flags, _t, v in blocks(data):
        if typ == T_META:
            try:
                meta = json.loads(v)
            except ValueError:
                return {}
            return meta if isinstance(meta, dict) else {}
    return {}


def time_range(data):
    t0 = t1 = None
    for typ, _f, t, _v in blocks(data):
        if typ == T_DATA:
            if t0 is None:
                t0 = t
            t1 = t
    return t0, t1


# Dateiname der Browser-Aufnahme: DesktopSession-<Gerät>-JJJJ-MM-TT-HH-MM[ (n)].mcrec
# (views/default.handlebars → deskRecordSession; die Zeit ist das Aufnahme-Ende)
FILENAME_RE = re.compile(r"^DesktopSession-(?P<dev>.+)-(?P<ts>\d{4}-\d{2}-\d{2}-\d{2}-\d{2})(?: ?\(\d+\))?$")

# meta.time stammt aus toLocaleString() des Browsers bzw. Servers → gängige Formate
TIME_FORMATS = ("%d.%m.%Y, %H:%M:%S", "%d.%m.%Y %H:%M:%S", "%m/%d/%Y, %I:%M:%S %p",
                "%m/%d/%Y %I:%M:%S %p", "%d/%m/%Y, %H:%M:%S", "%d/%m/%Y %H:%M:%S",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d, %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d, %H:%M:%S")


def parse_time(txt):
    """Ortszeit aus meta.time (naives datetime) oder None."""
    if not isinstance(txt, str):
        return None
    txt = re.sub(r"[  ]", " ", txt).strip()
    for f in TIME_FORMATS:
        try:
            return datetime.datetime.strptime(txt, f)
        except ValueError:
            pass
    return None


def fmt_dur(s):
    s = int(round(s))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def describe(path, meta, raw_dur, size):
    """Sammelt alle verfügbaren Angaben.

    Rückgabe: (Liste von (Bezeichnung, Wert), Beginn als naives datetime in Ortszeit oder None).
    """
    stem = os.path.splitext(os.path.basename(path))[0]
    m = FILENAME_RE.match(stem)
    device = meta.get("devicename") or (m.group("dev") if m else None)
    start = parse_time(meta.get("time"))
    if start is None and m:  # nur minutengenau, und das ist das Ende der Aufnahme
        end = datetime.datetime.strptime(m.group("ts"), "%Y-%m-%d-%H-%M")
        start = end - datetime.timedelta(seconds=raw_dur)
    server = any(k in meta for k in ("userid", "sessionid", "ipaddr1", "ipaddr2"))
    ips = ", ".join(str(x) for x in (meta.get("ipaddr1"), meta.get("ipaddr2")) if x)
    single = raw_dur < 1
    rows = [
        ("Gerät", device),
        ("Gerätegruppe", meta.get("devicegroup")),
        ("Benutzer", meta.get("username")),
        ("Benutzer-ID", meta.get("userid")),
        ("IP-Adressen", ips),
        ("Beginn", start.strftime("%d.%m.%Y %H:%M:%S") if start else meta.get("time")),
        ("Ende", None if single or not start else
         (start + datetime.timedelta(seconds=raw_dur)).strftime("%d.%m.%Y %H:%M:%S")),
        ("Dauer", "Einzelbild" if single else fmt_dur(raw_dur)),
        ("Auflösung", f"{size[0]}×{size[1]}" if size else None),
        ("Aufnahme", "MeshCentral-Server" if server else "Browser (Aufnahme-Knopf)"),
        ("Sitzungs-ID", meta.get("sessionid")),
        ("Geräte-ID", meta.get("nodeid")),
        ("Originaldatei", os.path.basename(path)),
    ]
    return [(k, str(v)) for k, v in rows if v], start
