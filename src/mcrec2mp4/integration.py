"""Rechtsklick-Eintrag „In MP4 umwandeln“ / „Convert to MP4“ im Dateimanager ein- und austragen.

- Windows: Explorer (HKCU, keine Admin-Rechte nötig)
- Linux: Nautilus (GNOME Files), Nemo, Caja, Dolphin + MIME-Typ für *.mcrec
- macOS: noch nicht unterstützt (Kommandozeile funktioniert)
"""
import os
import shlex
import shutil
import subprocess
import sys

from .i18n import t

LABELS = ("In MP4 umwandeln", "Convert to MP4")  # Name des Eintrags (de, en)
MARKER = "mcrec2mp4-integration"
MIME = "application/x-meshcentral-recording"
WIN_KEY = r"Software\Classes\SystemFileAssociations\.mcrec\shell\mcrec2mp4"


def label():
    return t(*LABELS)


def launcher():
    """Befehl (Liste), mit dem der Dateimanager mcrec2mp4 startet."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    exe = shutil.which("mcrec2mp4")
    if exe:
        return [os.path.abspath(exe)]
    return [sys.executable, "-m", "mcrec2mp4"]


# ---------------------------------------------------------------- Linux

def _xdg(var, default):
    return os.environ.get(var) or os.path.join(os.path.expanduser("~"), default)


def _desktop_exec(cmd):
    """Exec-Zeile nach Desktop-Entry-Spezifikation quoten."""
    out = []
    for a in cmd:
        a = a.replace("%", "%%")
        if any(c in a for c in ' \t\n"\'\\><~|&;$*?#()`'):
            a = '"' + a.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$") + '"'
        out.append(a)
    return " ".join(out)


def _linux_targets(cmd, name=None):
    name = name or label()
    data = _xdg("XDG_DATA_HOME", ".local/share")
    config = _xdg("XDG_CONFIG_HOME", ".config")
    sh = shlex.join(cmd + ["--from-filemanager"])
    script = (f"#!/bin/sh\n# {MARKER}: {name} (mcrec2mp4 --uninstall)\n"
              f'exec {sh} "$@"\n')
    dexec = _desktop_exec(cmd + ["--from-filemanager"]) + " %F"
    comment = t("MeshCentral-Aufzeichnung in MP4 umwandeln", "Convert a MeshCentral recording to MP4")
    nemo = (f"[Nemo Action]\n# {MARKER}\nName={name}\nComment={comment}\n"
            f"Exec={dexec}\nIcon-Name=video-x-generic\nSelection=notnone\nExtensions=mcrec;\n")
    dolphin = (f"[Desktop Entry]\n# {MARKER}\nType=Service\nMimeType={MIME};\nActions=mcrec2mp4;\n"
               "X-KDE-ServiceTypes=KonqPopupMenu/Plugin\n\n"
               f"[Desktop Action mcrec2mp4]\nName={name}\nIcon=video-x-generic\nExec={dexec}\n")
    mime = (f'<?xml version="1.0" encoding="UTF-8"?>\n<!-- {MARKER} -->\n'
            '<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">\n'
            f'  <mime-type type="{MIME}">\n    <comment>MeshCentral-Aufzeichnung</comment>\n'
            '    <comment xml:lang="en">MeshCentral recording</comment>\n'
            '    <generic-icon name="video-x-generic"/>\n    <glob pattern="*.mcrec"/>\n'
            '  </mime-type>\n</mime-info>\n')
    # (Name, erkannt?, Pfad, Inhalt, ausführbar)
    return [
        (t("MIME-Typ *.mcrec", "MIME type *.mcrec"), True, os.path.join(data, "mime", "packages", "mcrec2mp4.xml"), mime, False),
        ("Nautilus", bool(shutil.which("nautilus")),
         os.path.join(data, "nautilus", "scripts", name), script, True),
        ("Nemo", bool(shutil.which("nemo")), os.path.join(data, "nemo", "actions", "mcrec2mp4.nemo_action"),
         nemo, False),
        ("Caja", bool(shutil.which("caja")), os.path.join(config, "caja", "scripts", name), script, True),
        ("Dolphin", bool(shutil.which("dolphin")),
         os.path.join(data, "kio", "servicemenus", "mcrec2mp4.desktop"), dolphin, True),
    ]


def _ours(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return MARKER in f.read()
    except OSError:
        return False


def _update_mime(data_dir):
    tool = shutil.which("update-mime-database")
    if tool:
        subprocess.run([tool, os.path.join(data_dir, "mime")], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _install_linux(cmd, everything=False):
    msgs = []
    for name, found, path, content, executable in _linux_targets(cmd):
        if not (found or everything):
            continue
        if os.path.exists(path) and not _ours(path):
            msgs.append(t(f"{name}: übersprungen, {path} existiert bereits (nicht von mcrec2mp4)",
                          f"{name}: skipped, {path} already exists (not created by mcrec2mp4)"))
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        if executable:
            os.chmod(path, 0o755)
        msgs.append(f"{name}: {path}")
    _update_mime(_xdg("XDG_DATA_HOME", ".local/share"))
    return msgs


def _uninstall_linux():
    msgs = []
    seen = set()
    for lbl in LABELS:  # Skripte heißen je nach Sprache bei der Installation anders
        for name, _found, path, _content, _x in _linux_targets(launcher(), lbl):
            if path not in seen and os.path.exists(path) and _ours(path):
                seen.add(path)
                os.unlink(path)
                msgs.append(t(f"{name}: entfernt", f"{name}: removed"))
    _update_mime(_xdg("XDG_DATA_HOME", ".local/share"))
    return msgs


# ---------------------------------------------------------------- Windows

def _win_install_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local")
    return os.path.join(base, "Programs", "mcrec2mp4")


def _install_windows(cmd):
    import winreg
    msgs = []
    if getattr(sys, "frozen", False):
        # Einzeldatei-Build an einen festen Ort kopieren, damit der Eintrag nicht von Downloads abhängt
        dest_dir = _win_install_dir()
        dest = os.path.join(dest_dir, "mcrec2mp4.exe")
        if os.path.normcase(os.path.abspath(sys.executable)) != os.path.normcase(dest):
            os.makedirs(dest_dir, exist_ok=True)
            shutil.copy2(sys.executable, dest)
            try:  # Download-Markierung nicht mitkopieren, sonst warnt SmartScreen bei jedem Start
                os.remove(dest + ":Zone.Identifier")
            except OSError:
                pass
            msgs.append(t(f"Programm kopiert nach {dest}", f"Program copied to {dest}"))
        cmd = [dest]
    command = subprocess.list2cmdline(cmd + ["--from-filemanager"]) + ' "%1"'
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, WIN_KEY) as k:
        winreg.SetValueEx(k, None, 0, winreg.REG_SZ, label())
        winreg.SetValueEx(k, "MUIVerb", 0, winreg.REG_SZ, label())
        winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, cmd[0])
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, WIN_KEY + r"\command") as k:
        winreg.SetValueEx(k, None, 0, winreg.REG_SZ, command)
    msgs.append(t("Explorer: Rechtsklick auf .mcrec → „In MP4 umwandeln“ "
                  "(Windows 11: unter „Weitere Optionen anzeigen“)",
                  "Explorer: right-click a .mcrec file → \"Convert to MP4\" "
                  "(Windows 11: under \"Show more options\")"))
    return msgs


def _uninstall_windows():
    import winreg
    msgs = []
    for sub in (WIN_KEY + r"\command", WIN_KEY):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
        except FileNotFoundError:
            pass
    msgs.append(t("Explorer: Eintrag entfernt", "Explorer: entry removed"))
    dest = os.path.join(_win_install_dir(), "mcrec2mp4.exe")
    if os.path.exists(dest):
        if os.path.normcase(os.path.abspath(sys.executable)) == os.path.normcase(dest):
            msgs.append(t(f"{dest} läuft gerade – bitte von Hand löschen",
                          f"{dest} is running – please delete it manually"))
        else:
            try:
                os.unlink(dest)
                msgs.append(t(f"{dest} gelöscht", f"{dest} deleted"))
            except OSError:
                msgs.append(t(f"{dest} konnte nicht gelöscht werden", f"{dest} could not be deleted"))
            try:
                os.rmdir(os.path.dirname(dest))
            except OSError:
                pass
    return msgs


def win_registered_command():
    """Für Tests: registrierter Befehl oder None."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WIN_KEY + r"\command") as k:
            return winreg.QueryValueEx(k, None)[0]
    except FileNotFoundError:
        return None


# ---------------------------------------------------------------- öffentlich

def install(everything=False):
    cmd = launcher()
    if sys.platform == "win32":
        return _install_windows(cmd)
    if sys.platform == "darwin":
        return [t("macOS: Finder-Einbindung wird noch nicht unterstützt – bitte die Kommandozeile nutzen.",
                  "macOS: Finder integration is not supported yet – please use the command line.")]
    msgs = _install_linux(cmd, everything)
    if len(msgs) <= 1:
        msgs.append(t("Kein unterstützter Dateimanager gefunden (Nautilus, Nemo, Caja, Dolphin). "
                      "Mit --install-all trotzdem für alle einrichten.",
                      "No supported file manager found (Nautilus, Nemo, Caja, Dolphin). "
                      "Use --install-all to set it up for all of them anyway."))
    return msgs


def uninstall():
    if sys.platform == "win32":
        return _uninstall_windows()
    if sys.platform == "darwin":
        return [t("macOS: nichts zu entfernen.", "macOS: nothing to remove.")]
    return _uninstall_linux() or [t("Nichts zu entfernen.", "Nothing to remove.")]
