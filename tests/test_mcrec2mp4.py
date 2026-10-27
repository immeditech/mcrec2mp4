import struct
import subprocess
import sys

import pytest
from PIL import Image

from mcrec2mp4 import cli, integration
from mcrec2mp4.convert import convert, find_ffmpeg
from mcrec2mp4.recording import McrecError, blocks, describe, desktop_commands, parse_time

import sample

RED, GREEN = (220, 20, 20), (20, 200, 20)


def write(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)


def decode(mp4, w, h):
    """Alle Frames als rohe RGB-Bytes."""
    raw = subprocess.run([find_ffmpeg(), "-v", "error", "-i", mp4, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    n = w * h * 3
    return [raw[i:i + n] for i in range(0, len(raw), n)]


def px(frame, w, x, y):
    i = (y * w + x) * 3
    return tuple(frame[i:i + 3])


# ------------------------------------------------------------------ Zeitstempel

@pytest.mark.parametrize("style", ["browser", "server"])
@pytest.mark.parametrize("base", [1_761_552_000_000, (1 << 31) - 1000, (1 << 32) - 1000])
def test_time_monotonic_over_wrap(style, base):
    data = sample.recording([(0, b"x"), (1500, b"y"), (3000, b"z")], style=style, t_base=base)
    ts = [t for typ, _f, t, _v in blocks(data) if typ == 2]
    d = [b - a for a, b in zip(ts, ts[1:])]
    assert all(1400 <= x <= 1600 for x in d), (ts, d)


def test_parse_time_formats():
    assert parse_time("27.10.2026, 09:12:38").hour == 9
    assert parse_time("10/27/2026, 9:12:38 PM").hour == 21
    assert parse_time("2026-10-27 09:12:38").minute == 12
    assert parse_time("Unsinn") is None


# ------------------------------------------------------------------ Parser

def test_wrapper_and_big_tile():
    big = sample.png(RED, (200, 200), noise=True)
    assert len(big) > 65000
    data = sample.recording([(0, sample.screen(200, 200)), (10, sample.tile(0, 0, big))])
    cmds = [(c, len(v)) for _t, c, v in desktop_commands(data)]
    assert cmds == [(7, 8), (3, 8 + len(big))]


def test_describe_device_from_filename():
    rows, start = describe("/x/DesktopSession-PC-01-2026-10-27-09-21 (1).mcrec", {}, 60, (800, 600))
    info = dict(rows)
    assert info["Gerät"] == "PC-01"
    assert start.strftime("%H:%M") == "09:20"
    assert info["Aufnahme"].startswith("Browser")


def test_describe_server_meta():
    meta = {"devicename": "Srv", "username": "Anna", "userid": "user//anna", "ipaddr1": "10.0.0.1",
            "time": "10/27/2026, 9:00:00 AM", "sessionid": "s1"}
    info = dict(describe("a.mcrec", meta, 5, None)[0])
    assert info["Benutzer"] == "Anna" and info["IP-Adressen"] == "10.0.0.1"
    assert info["Aufnahme"] == "MeshCentral-Server" and info["Beginn"] == "27.10.2026 09:00:00"


# ------------------------------------------------------------------ Umwandlung

def test_single_frame_becomes_png(tmp_path):
    data = sample.recording([(0, sample.screen(64, 48)), (5, sample.tile(0, 0, sample.png(RED, (64, 48))))])
    src = write(tmp_path, "DesktopSession-Kasse-2026-10-27-09-12.mcrec", data)
    out = convert(src)
    assert out.endswith(".png")
    with Image.open(out) as img:
        assert img.size == (64, 48) and img.getpixel((10, 10)) == RED
        assert "Kasse" in img.text["Title"] and "Gerät: Kasse" in img.text["Comment"]


@pytest.mark.parametrize("style", ["browser", "server"])
def test_video(tmp_path, style):
    w, h = 64, 48
    data = sample.recording([
        (0, sample.screen(w, h)),
        (0, sample.tile(0, 0, sample.png(RED, (w, h)))),
        (2000, sample.tile(0, 0, sample.png(GREEN, (32, 24)))),
        (4000, sample.cmd(88, b"\0\0\0\0")),  # unbekanntes Kommando → ignoriert, setzt nur das Ende
    ], meta={"username": "Tester"}, style=style)
    src = write(tmp_path, "rec.mcrec", data)
    out = convert(src, fps=10)
    assert out.endswith(".mp4")
    frames = decode(out, w, h)
    assert 40 <= len(frames) <= 42  # Browser-Zeitstempel schwanken um bis zu 32 ms
    r, g, _b = px(frames[10], w, 5, 5)
    assert r > 150 and g < 80  # vor 2 s rot
    r, g, _b = px(frames[-1], w, 5, 5)
    assert g > 150 and r < 80  # danach grün
    r, g, _b = px(frames[-1], w, 60, 44)
    assert r > 150 and g < 80  # Rest bleibt rot
    tags = subprocess.run([find_ffmpeg(), "-hide_banner", "-i", out], capture_output=True,
                          text=True, encoding="utf-8", errors="replace").stderr
    assert "Tester" in tags and "creation_time" in tags and "MeshCentral-Sitzung" in tags


def test_max_idle(tmp_path):
    data = sample.recording([
        (0, sample.screen(32, 32)),
        (0, sample.tile(0, 0, sample.png(RED, (32, 32)))),
        (20000, sample.tile(0, 0, sample.png(GREEN, (32, 32)))),
        (21000, sample.cmd(88, b"")),
    ])
    out = convert(write(tmp_path, "idle.mcrec", data), fps=10, max_idle=2)
    assert 30 <= len(decode(out, 32, 32)) <= 32  # 21 s → 3 s


def test_odd_size_and_resize(tmp_path):
    data = sample.recording([
        (0, sample.screen(65, 49)),
        (0, sample.tile(0, 0, sample.png(RED, (65, 49)))),
        (1000, sample.screen(130, 98)),
        (1000, sample.tile(0, 0, sample.png(GREEN, (130, 98)))),
        (2000, sample.cmd(88, b"")),
    ])
    out = convert(write(tmp_path, "odd.mcrec", data), fps=5)
    frames = decode(out, 64, 48)
    r, g, _b = px(frames[-1], 64, 30, 20)
    assert g > 150 and r < 80


def test_static_screen_until_end_block(tmp_path):
    # nur ein Bild, aber die Aufnahme läuft 3 s weiter → Standbild-Video statt PNG
    data = sample.recording([(0, sample.screen(32, 32)), (0, sample.tile(0, 0, sample.png(RED, (32, 32))))],
                            end_ms=3000)
    out = convert(write(tmp_path, "still.mcrec", data), fps=10)
    assert out.endswith(".mp4")
    assert 30 <= len(decode(out, 32, 32)) <= 32


def test_tile_before_screen_size(tmp_path):
    # Kachel kommt vor der Größenangabe → Video trotzdem in Bildschirmgröße
    data = sample.recording([
        (0, sample.tile(0, 0, sample.png(RED, (16, 16)))),
        (0, sample.screen(64, 48)),
        (0, sample.tile(16, 0, sample.png(GREEN, (48, 48)))),
        (2000, sample.cmd(88, b"")),
    ])
    out = convert(write(tmp_path, "early.mcrec", data), fps=5)
    frames = decode(out, 64, 48)
    r, g, _b = px(frames[-1], 64, 40, 40)
    assert g > 150 and r < 80


def test_last_command_reaches_video(tmp_path):
    # letzte Änderung kurz vor dem Ende darf nicht verloren gehen
    data = sample.recording([
        (0, sample.screen(32, 32)),
        (0, sample.tile(0, 0, sample.png(RED, (32, 32)))),
        (1000, sample.cmd(88, b"")),
        (2150, sample.tile(0, 0, sample.png(GREEN, (32, 32)))),
    ], style="server")
    out = convert(write(tmp_path, "end.mcrec", data), fps=2)
    r, g, _b = px(decode(out, 32, 32)[-1], 32, 5, 5)
    assert g > 150 and r < 80


def test_unreadable_tiles(tmp_path):
    data = sample.recording([(0, sample.tile(0, 0, b"kein Bild")), (2000, sample.cmd(88, b""))])
    with pytest.raises(McrecError, match="lesbare"):
        convert(write(tmp_path, "kaputt.mcrec", data))


def test_wrong_protocol(tmp_path):
    data = sample.recording([(0, b"ls\r\n")], meta={"protocol": 1})
    with pytest.raises(McrecError, match="Protokoll 1"):
        convert(write(tmp_path, "term.mcrec", data))


def test_garbage(tmp_path):
    with pytest.raises(McrecError):
        convert(write(tmp_path, "x.mcrec", b"hallo"))


def test_no_overwrite(tmp_path):
    data = sample.recording([(0, sample.screen(8, 8)), (0, sample.tile(0, 0, sample.png(RED, (8, 8))))])
    src = write(tmp_path, "a.mcrec", data)
    convert(src)
    with pytest.raises(McrecError, match="existiert bereits"):
        convert(src, overwrite=False)


# ------------------------------------------------------------------ Kommandozeile

def test_cli_filemanager_filters(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "notify", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(cli.time, "sleep", lambda s: None)
    data = sample.recording([(0, sample.screen(8, 8)), (0, sample.tile(0, 0, sample.png(RED, (8, 8))))])
    src = write(tmp_path, "a.mcrec", data)
    other = write(tmp_path, "b.txt", b"x")
    assert cli.main(["--from-filemanager", other]) == 1
    assert cli.main(["--from-filemanager", src, other]) == 0
    assert (tmp_path / "a.png").exists()
    assert any("fertig" in c[0] for c in calls)


def test_cli_info(tmp_path, capsys):
    data = sample.recording([(0, sample.screen(8, 8)), (0, sample.tile(0, 0, sample.png(RED, (8, 8))))])
    assert cli.main(["--info", write(tmp_path, "a.mcrec", data)]) == 0
    assert "Auflösung: 8×8" in capsys.readouterr().err
    assert not (tmp_path / "a.png").exists()


# ------------------------------------------------------------------ Dateimanager

@pytest.mark.skipif(sys.platform in ("win32", "darwin"), reason="Linux-Einbindung")
def test_linux_integration(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(integration.shutil, "which", lambda n: f"/usr/bin/{n}" if n != "update-mime-database" else None)
    foreign = tmp_path / "data" / "nemo" / "actions" / "mcrec2mp4.nemo_action"
    foreign.parent.mkdir(parents=True)
    foreign.write_text("eigene Datei")
    msgs = integration.install()
    script = tmp_path / "data" / "nautilus" / "scripts" / integration.LABEL
    assert script.exists() and script.stat().st_mode & 0o111
    assert "--from-filemanager" in script.read_text()
    assert (tmp_path / "config" / "caja" / "scripts" / integration.LABEL).exists()
    assert (tmp_path / "data" / "kio" / "servicemenus" / "mcrec2mp4.desktop").exists()
    assert (tmp_path / "data" / "mime" / "packages" / "mcrec2mp4.xml").exists()
    assert foreign.read_text() == "eigene Datei" and any("übersprungen" in m for m in msgs)
    integration.uninstall()
    assert not script.exists() and foreign.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-Explorer")
def test_windows_integration():
    integration.install()
    cmd = integration.win_registered_command()
    assert cmd and "--from-filemanager" in cmd and cmd.endswith('"%1"')
    integration.uninstall()
    assert integration.win_registered_command() is None
