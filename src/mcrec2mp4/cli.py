"""Kommandozeile."""
import argparse
import os
import shutil
import subprocess
import sys
import time

from . import __version__
from .convert import convert
from .i18n import t
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
        description=t("MeshCentral-Desktop-Aufzeichnungen (.mcrec) in MP4 umwandeln. "
                      "Aufzeichnungen unter einer Sekunde (ein Bild) werden als PNG gespeichert.",
                      "Convert MeshCentral desktop recordings (.mcrec) to MP4. "
                      "Recordings shorter than one second (a single image) are saved as PNG."),
        epilog=t("Sprache: MCREC2MP4_LANG=de|en", "Language: MCREC2MP4_LANG=de|en"))
    ap.add_argument("files", nargs="*", metavar=t("DATEI", "FILE"), help=t(".mcrec-Datei(en)", ".mcrec file(s)"))
    ap.add_argument("-o", "--output", help=t("Ausgabedatei (nur bei einer Eingabedatei)",
                                             "output file (only with a single input file)"))
    ap.add_argument("--fps", type=float, default=10, help=t("Bildrate (Standard: 10)", "frame rate (default: 10)"))
    ap.add_argument("--max-idle", type=float, default=0, metavar="S",
                    help=t("Pausen länger als S Sekunden auf S Sekunden kürzen (Standard: 0 = aus)",
                           "shorten pauses longer than S seconds to S seconds (default: 0 = off)"))
    ap.add_argument("--crf", type=int, default=23, help=t("x264-Qualität, kleiner = besser (Standard: 23)",
                                                          "x264 quality, lower = better (default: 23)"))
    ap.add_argument("-n", "--no-overwrite", action="store_true",
                    help=t("vorhandene Ausgabedateien nicht überschreiben", "don't overwrite existing output files"))
    ap.add_argument("-i", "--info", action="store_true",
                    help=t("nur Angaben zur Aufzeichnung anzeigen", "only show details about the recording"))
    ap.add_argument("--notify", action="store_true",
                    help=t("Ergebnis per Desktop-Benachrichtigung melden", "report the result as a desktop notification"))
    ap.add_argument("--install", action="store_true",
                    help=t("Rechtsklick-Eintrag im Dateimanager einrichten", "set up the right-click entry in the file manager"))
    ap.add_argument("--install-all", action="store_true",
                    help=t("wie --install, aber für alle unterstützten Linux-Dateimanager",
                           "like --install, but for all supported Linux file managers"))
    ap.add_argument("--uninstall", action="store_true",
                    help=t("Rechtsklick-Eintrag wieder entfernen", "remove the right-click entry"))
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
            info_box("mcrec2mp4", t(f"Fehler: {e}", f"Error: {e}"))
            return 1
        info_box("mcrec2mp4", "\n".join(msgs))
        return 0

    files = a.files
    if a.from_filemanager:
        a.notify = True
        files = [os.path.abspath(f) for f in files if f.lower().endswith(".mcrec")]
        if not files:
            notify(t("Keine .mcrec-Datei ausgewählt", "No .mcrec file selected"), error=True)
            return 1
        if sys.platform != "win32":
            notify(t("Umwandlung läuft …", "Converting …"), t(f"{len(files)} Aufzeichnung(en)", f"{len(files)} recording(s)"))
    if not files:
        ap.print_usage(sys.stderr)
        print(t("mcrec2mp4: keine Datei angegeben (Hilfe: mcrec2mp4 -h)",
                "mcrec2mp4: no file given (help: mcrec2mp4 -h)"), file=sys.stderr)
        return 2
    if a.output and len(files) > 1:
        ap.error(t("-o geht nur mit einer einzigen Eingabedatei", "-o only works with a single input file"))
    if a.fps <= 0:
        ap.error(t("--fps muss größer als 0 sein", "--fps must be greater than 0"))

    ok, failed = [], []
    for fn in files:
        try:
            res = convert(fn, a.output, a.fps, a.max_idle, a.crf, not a.no_overwrite, a.info)
            if res:
                ok.append(res)
        except KeyboardInterrupt:
            print(t("\nAbgebrochen.", "\nCancelled."), file=sys.stderr)
            return 130
        except (McrecError, OSError) as e:
            print(f"{os.path.basename(fn)}: " + t(f"Fehler: {e}", f"Error: {e}"), file=sys.stderr)
            failed.append((fn, str(e)))
        except Exception as e:  # unerwartet: Meldung statt Traceback (wichtig beim Rechtsklick)
            print(f"{os.path.basename(fn)}: " + t(f"unerwarteter Fehler: {e!r}", f"unexpected error: {e!r}"),
                  file=sys.stderr)
            failed.append((fn, t(f"unerwarteter Fehler: {e}", f"unexpected error: {e}")))

    if a.notify and not a.info:
        if failed:
            notify(t(f"{len(ok)} umgewandelt, {len(failed)} fehlgeschlagen", f"{len(ok)} converted, {len(failed)} failed"),
                   "\n".join(f"{os.path.basename(f)}: {e}" for f, e in failed), error=True)
        else:
            notify(t("Umwandlung fertig", "Conversion finished") if len(ok) == 1 else
                   t(f"{len(ok)} Aufzeichnungen umgewandelt", f"{len(ok)} recordings converted"),
                   "\n".join(os.path.basename(p) for p in ok))
    if a.from_filemanager and sys.platform == "win32" and not failed:
        print(t("\nFertig – das Fenster schließt sich gleich.", "\nDone – this window will close shortly."))
        time.sleep(4)
    return 1 if failed else 0
