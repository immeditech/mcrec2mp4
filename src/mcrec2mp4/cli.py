"""Kommandozeile."""
import argparse
import os
import shutil
import subprocess
import sys
import time

from . import __version__
from .convert import convert
from .recording import McrecError


def notify(title, body="", error=False):
    """Desktop-Benachrichtigung, so gut es die Plattform ohne Zusatzpakete hergibt."""
    try:
        if sys.platform == "win32":
            if error:  # Erfolg sieht man im Konsolenfenster; Fehler sollen nicht untergehen
                import ctypes
                ctypes.windll.user32.MessageBoxW(None, body, f"mcrec2mp4 – {title}", 0x10)
        elif sys.platform == "darwin":
            def q(s):
                return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
            subprocess.run(["osascript", "-e", f"display notification {q(body)} with title {q(title)}"],
                           check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif shutil.which("notify-send"):
            subprocess.run(["notify-send", "-a", "mcrec2mp4", "-i", "dialog-error" if error else "video-x-generic",
                            title, body], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def info_box(title, body):
    """Meldung für den Doppelklick auf die .exe (Windows) bzw. Ausgabe auf der Konsole."""
    print(body)
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, body, title, 0x40)
        except Exception:
            pass


def _parser():
    ap = argparse.ArgumentParser(
        prog="mcrec2mp4",
        description="MeshCentral-Desktop-Aufzeichnungen (.mcrec) in MP4 umwandeln. "
                    "Aufzeichnungen mit nur einem Bild werden als PNG gespeichert.")
    ap.add_argument("files", nargs="*", metavar="DATEI", help=".mcrec-Datei(en)")
    ap.add_argument("-o", "--output", help="Ausgabedatei (nur bei einer Eingabedatei)")
    ap.add_argument("--fps", type=float, default=10, help="Bildrate (Standard: 10)")
    ap.add_argument("--max-idle", type=float, default=0, metavar="S",
                    help="Pausen länger als S Sekunden auf S Sekunden kürzen (Standard: 0 = aus)")
    ap.add_argument("--crf", type=int, default=23, help="x264-Qualität, kleiner = besser (Standard: 23)")
    ap.add_argument("-n", "--no-overwrite", action="store_true", help="vorhandene Ausgabedateien nicht überschreiben")
    ap.add_argument("-i", "--info", action="store_true", help="nur Angaben zur Aufzeichnung anzeigen")
    ap.add_argument("--notify", action="store_true", help="Ergebnis per Desktop-Benachrichtigung melden")
    ap.add_argument("--install", action="store_true",
                    help="Rechtsklick-Eintrag „In MP4 umwandeln“ im Dateimanager einrichten")
    ap.add_argument("--install-all", action="store_true",
                    help="wie --install, aber für alle unterstützten Linux-Dateimanager")
    ap.add_argument("--uninstall", action="store_true", help="Rechtsklick-Eintrag wieder entfernen")
    ap.add_argument("--from-filemanager", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    return ap


def main(argv=None):
    for s in (sys.stdout, sys.stderr):  # z. B. Windows-Konsole mit cp1252: nie an „→“ scheitern
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass
    argv = sys.argv[1:] if argv is None else argv

    # Doppelklick auf die Windows-.exe: Rechtsklick-Eintrag einrichten
    if not argv and getattr(sys, "frozen", False) and sys.platform == "win32":
        argv = ["--install"]

    ap = _parser()
    a = ap.parse_args(argv)

    if a.install or a.install_all or a.uninstall:
        from . import integration
        try:
            msgs = integration.uninstall() if a.uninstall else integration.install(a.install_all)
        except OSError as e:
            info_box("mcrec2mp4", f"Fehler: {e}")
            return 1
        info_box("mcrec2mp4", "\n".join(msgs))
        return 0

    files = a.files
    if a.from_filemanager:
        a.notify = True
        files = [os.path.abspath(f) for f in files if f.lower().endswith(".mcrec")]
        if not files:
            notify("Keine .mcrec-Datei ausgewählt", error=True)
            return 1
        if sys.platform != "win32":
            notify("Umwandlung läuft …", f"{len(files)} Aufzeichnung(en)")
    if not files:
        ap.print_usage(sys.stderr)
        print("mcrec2mp4: keine Datei angegeben (Hilfe: mcrec2mp4 -h)", file=sys.stderr)
        return 2
    if a.output and len(files) > 1:
        ap.error("-o geht nur mit einer einzigen Eingabedatei")
    if a.fps <= 0:
        ap.error("--fps muss größer als 0 sein")

    ok, failed = [], []
    for fn in files:
        try:
            res = convert(fn, a.output, a.fps, a.max_idle, a.crf, not a.no_overwrite, a.info)
            if res:
                ok.append(res)
        except KeyboardInterrupt:
            print("\nAbgebrochen.", file=sys.stderr)
            return 130
        except (McrecError, OSError) as e:
            print(f"{os.path.basename(fn)}: Fehler: {e}", file=sys.stderr)
            failed.append((fn, str(e)))
        except Exception as e:  # unerwartet: Meldung statt Traceback (wichtig beim Rechtsklick)
            print(f"{os.path.basename(fn)}: unerwarteter Fehler: {e!r}", file=sys.stderr)
            failed.append((fn, f"unerwarteter Fehler: {e}"))

    if a.notify and not a.info:
        if failed:
            notify(f"{len(ok)} umgewandelt, {len(failed)} fehlgeschlagen",
                   "\n".join(f"{os.path.basename(f)}: {e}" for f, e in failed), error=True)
        else:
            notify("Umwandlung fertig" if len(ok) == 1 else f"{len(ok)} Aufzeichnungen umgewandelt",
                   "\n".join(os.path.basename(p) for p in ok))
    if a.from_filemanager and sys.platform == "win32" and not failed:
        print("\nFertig – das Fenster schließt sich gleich.")
        time.sleep(4)
    return 1 if failed else 0
