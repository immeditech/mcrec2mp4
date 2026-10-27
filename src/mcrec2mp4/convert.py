"""Umwandlung einer Aufzeichnung in MP4 (bzw. PNG bei Einzelbildern)."""
import datetime
import errno
import io
import math
import os
import shutil
import struct
import subprocess
import sys
import time

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from .recording import (CMD_SCREEN, CMD_TILE, McrecError, PROTO_NAMES, describe, desktop_commands,
                        fmt_dur, read_meta, time_range)


def find_ffmpeg():
    """ffmpeg suchen: $MCREC2MP4_FFMPEG, im PATH, sonst das von imageio-ffmpeg mitgelieferte."""
    env = os.environ.get("MCREC2MP4_FFMPEG")
    if env:
        return env
    bundled = None
    try:
        import imageio_ffmpeg  # optional
        bundled = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    if getattr(sys, "frozen", False) and bundled:  # Einzeldatei-Build: eigenes ffmpeg bevorzugen
        return bundled
    return shutil.which("ffmpeg") or bundled


class Screen:
    def __init__(self, out_size=None):
        self.canvas = None
        self.out_size = out_size  # Videogröße; ohne Vorgabe die erste Bildschirmgröße

    def resize(self, w, h):
        if w <= 0 or h <= 0:
            return
        old = self.canvas
        self.canvas = Image.new("RGB", (w, h))
        if old is not None:
            self.canvas.paste(old, (0, 0))
        if self.out_size is None:
            self.out_size = (w, h)

    def tile(self, x, y, img_bytes):
        try:
            img = Image.open(io.BytesIO(img_bytes))
            img.load()
        except Exception:
            return False
        if self.canvas is None:  # Kachel vor der Größenangabe: Leinwand aus der Kachel ableiten
            self.resize(x + img.width, y + img.height)
        if img.mode != "RGB":
            img = img.convert("RGB")
        self.canvas.paste(img, (x, y))
        return True

    def frame(self):
        """Aktuelles Bild in Videogröße (nach einem Größenwechsel eingepasst)."""
        if self.canvas is None:
            return Image.new("RGB", self.out_size)
        if self.canvas.size == self.out_size:
            return self.canvas
        W, H = self.out_size
        w, h = self.canvas.size
        s = min(W / w, H / h)
        nw, nh = max(1, round(w * s)), max(1, round(h * s))
        out = Image.new("RGB", (W, H))
        out.paste(self.canvas.resize((nw, nh), Image.BILINEAR), ((W - nw) // 2, (H - nh) // 2))
        return out

    def apply(self, cmd, v):
        if cmd == CMD_SCREEN and len(v) >= 8:
            self.resize(*struct.unpack_from(">HH", v, 4))
        elif cmd == CMD_TILE and len(v) > 8:
            x, y = struct.unpack_from(">HH", v, 4)
            self.tile(x, y, v[8:])


def video_size(cmds):
    """Videogröße: erste Bildschirmgröße (cmd 7), sonst aus der ersten lesbaren Kachel."""
    for _t, c, v in cmds:
        if c == CMD_SCREEN and len(v) >= 8:
            w, h = struct.unpack_from(">HH", v, 4)
            if w > 0 and h > 0:
                return w, h
    probe = Screen()
    for _t, c, v in cmds:
        probe.apply(c, v)
        if probe.out_size:
            return probe.out_size
    return None


def idle_mapper(max_idle_ms):
    """Funktion, die (monotone) Zeitstempel auf eine Zeitachse mit gekürzten Pausen abbildet."""
    state = {"last": None, "shift": 0}

    def remap(t):
        last = state["last"]
        if last is not None and max_idle_ms > 0 and t - last > max_idle_ms:
            state["shift"] += (t - last) - max_idle_ms
        if last is None or t > last:
            state["last"] = t
        return t - state["shift"]
    return remap


class Progress:
    def __init__(self, stream):
        self.stream = stream
        self.tty = hasattr(stream, "isatty") and stream.isatty()
        self.width = 0

    def update(self, msg):
        if self.tty:  # ohne ANSI-Codes, damit es auch in der alten Windows-Konsole geht
            self.stream.write("\r" + msg.ljust(self.width))
            self.stream.flush()
            self.width = len(msg)

    def done(self, msg):
        if self.tty and self.width:
            self.stream.write("\r" + " " * self.width + "\r")
        print(msg, file=self.stream)
        self.width = 0


def _unlink(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def convert(path, out=None, fps=10, max_idle=0.0, crf=23, overwrite=True, info_only=False,
            ffmpeg=None, log=None):
    """Wandelt eine .mcrec-Datei um. Gibt den Pfad der Ausgabedatei zurück (None bei info_only)."""
    log = log or sys.stderr
    with open(path, "rb") as f:
        data = f.read()

    meta = read_meta(data)
    if meta.get("magic") not in (None, "MeshCentralRelaySession"):
        raise McrecError("Keine MeshCentral-Aufzeichnung.")
    proto = meta.get("protocol")
    if proto is not None and str(proto) != "2":
        raise McrecError(f"Protokoll {proto} ({PROTO_NAMES.get(proto, 'unbekannt')}) wird nicht "
                         "unterstützt – nur MeshCentral-Desktop-Aufzeichnungen.")

    t0, t1 = time_range(data)
    if t0 is None:
        raise McrecError("Keine Aufzeichnungsdaten gefunden.")

    remap = idle_mapper(int(max_idle * 1000))
    remap(t0)  # auch eine lange Lücke vor dem ersten Bild kürzen
    cmds = [(remap(t), c, v) for t, c, v in desktop_commands(data)]
    if not any(c == CMD_TILE for _t, c, _v in cmds):
        raise McrecError("Keine Bildkacheln in der Aufzeichnung.")
    start = t0
    dur = (max(remap(t1), cmds[-1][0]) - start) / 1000
    raw_dur = (t1 - t0) / 1000

    size = video_size(cmds)
    if size is None:
        raise McrecError("Keine lesbare Bildkachel in der Aufzeichnung.")
    rows, rec_start = describe(path, meta, raw_dur, size)
    if dur < raw_dur - 0.5:
        rows = [(k, f"{v} (Video gekürzt auf {fmt_dur(dur)})" if k == "Dauer" else v) for k, v in rows]
    print(os.path.basename(path) + ":", file=log)
    shown = [(k, v) for k, v in rows if k != "Originaldatei"]
    width = max(len(k) for k, _v in shown)
    for k, v in shown:
        print(f"  {k + ':':<{width + 1}} {v}", file=log)
    if info_only:
        return None

    info = dict(rows)
    title = "MeshCentral-Sitzung" + (f" {info['Gerät']}" if "Gerät" in info else "") + \
        (f" – {rec_start:%d.%m.%Y %H:%M}" if rec_start else "")
    comment = "\n".join(f"{k}: {v}" for k, v in rows)
    base = os.path.splitext(path)[0]
    screen = Screen(size)

    # Einzelbild-Aufzeichnung → PNG (an der echten Dauer gemessen, nicht an der gekürzten)
    if raw_dur < 1.0:
        for _t, c, v in cmds:
            screen.apply(c, v)
        target = out or base + ".png"
        if not overwrite and os.path.exists(target):
            raise McrecError(f"{target} existiert bereits.")
        png = PngInfo()
        png.add_itxt("Title", title)
        png.add_itxt("Comment", comment)
        png.add_text("Software", "mcrec2mp4")
        if meta.get("username"):
            png.add_itxt("Author", str(meta["username"]))
        if rec_start:
            png.add_text("Creation Time", rec_start.astimezone().strftime("%a, %d %b %Y %H:%M:%S %z"))
        tmp = target + ".part"
        try:
            screen.frame().save(tmp, "PNG", pnginfo=png)
            os.replace(tmp, target)
        except BaseException:
            _unlink(tmp)
            raise
        print(f"  → Einzelbild gespeichert: {target}", file=log)
        return target

    ffmpeg = ffmpeg or find_ffmpeg()
    if not ffmpeg:
        raise McrecError("ffmpeg wurde nicht gefunden (installieren oder `pip install imageio-ffmpeg`).")
    W, H = size
    W2, H2 = W - W % 2, H - H % 2  # yuv420p braucht gerade Maße
    target = out or base + ".mp4"
    if not overwrite and os.path.exists(target):
        raise McrecError(f"{target} existiert bereits.")
    tmp = target + ".part"
    ff = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
          "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
          "-vf", f"crop={W2}:{H2}:0:0",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-tune", "stillimage",
          "-pix_fmt", "yuv420p", "-movflags", "+faststart",
          "-metadata", f"title={title}", "-metadata", f"comment={comment}",
          "-metadata", f"description={comment}"]
    if meta.get("username"):
        ff += ["-metadata", f"artist={meta['username']}"]
    if rec_start:  # naives datetime = Ortszeit
        utc = rec_start.astimezone(datetime.timezone.utc)
        ff += ["-metadata", f"creation_time={utc:%Y-%m-%dT%H:%M:%S.000000Z}",
               "-metadata", f"date={rec_start:%Y-%m-%d}"]
    ff += ["-f", "mp4", tmp]
    proc = subprocess.Popen(ff, stdin=subprocess.PIPE)

    nframes = math.ceil(dur * fps - 1e-9) + 1  # letzter Frame liegt bei/nach dem Ende
    i = 0
    started = time.monotonic()
    frame_bytes = None
    dirty = True
    prog = Progress(log)
    try:
        for n in range(nframes):
            ft = start + n * 1000 / fps
            while i < len(cmds) and cmds[i][0] <= ft:
                screen.apply(cmds[i][1], cmds[i][2])
                i += 1
                dirty = True
            if dirty or frame_bytes is None:
                frame_bytes = screen.frame().tobytes()
                dirty = False
            proc.stdin.write(frame_bytes)
            if n % 50 == 0 or n == nframes - 1:
                prog.update(f"  {n / fps:6.0f} s / {dur:.0f} s  ({100 * (n + 1) / nframes:3.0f} %, "
                            f"{time.monotonic() - started:.0f} s vergangen)")
        proc.stdin.close()
    except OSError as e:
        # ffmpeg ist ausgestiegen (Windows meldet das als EINVAL statt BrokenPipe) → Fehlercode unten
        if not (isinstance(e, BrokenPipeError) or e.errno == errno.EINVAL) or proc.poll() is None:
            proc.kill()
            proc.wait()
            _unlink(tmp)
            raise
    except BaseException:
        proc.kill()
        proc.wait()
        _unlink(tmp)
        raise
    if proc.wait() != 0:
        _unlink(tmp)
        raise McrecError("ffmpeg ist fehlgeschlagen.")
    os.replace(tmp, target)
    prog.done(f"  → Video gespeichert: {target} ({W2}×{H2}, {fmt_dur(dur)}, "
              f"in {time.monotonic() - started:.0f} s umgewandelt)")
    return target
