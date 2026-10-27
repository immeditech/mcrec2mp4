# mcrec2mp4

Wandelt **MeshCentral-Desktop-Aufzeichnungen (`.mcrec`)** in MP4-Videos um. Eine Aufnahme mit 8 Minuten
in Full HD dauert rund 25 Sekunden statt Echtzeit wie beim Export im Browser-Player.

- Setzt die Bildkacheln wie der MeshCentral-Player zusammen und übernimmt die Zeitabstände.
- Aufnahmen, die kürzer als eine Sekunde sind (nur ein Bild), werden als **PNG** gespeichert. Bleibt der
  Bildschirm unverändert, entsteht ein Standbild-Video über die ganze Aufnahmedauer.
- Übernimmt die Angaben der Aufnahme (Gerät, Benutzer, Beginn, Dauer …) als Titel, Kommentar und
  Aufnahmedatum in die MP4/PNG.
- Lange Pausen lassen sich kürzen (`--max-idle`).
- **Rechtsklick „In MP4 umwandeln“** im Dateimanager: Windows-Explorer, Nautilus (GNOME Files), Nemo,
  Caja und Dolphin. Mehrere Dateien auf einmal gehen auch (unter Windows je Datei ein Fenster, bis 15
  Dateien).

Die Ausgabedatei landet neben der Aufnahme (`Aufnahme.mcrec` → `Aufnahme.mp4`).

## Installation

### Windows

1. `mcrec2mp4-windows-x64.exe` von den [Releases](https://github.com/immeditech/mcrec2mp4/releases/latest)
   herunterladen.
2. Doppelklicken. Das Programm kopiert sich nach `%LOCALAPPDATA%\Programs\mcrec2mp4` und richtet den
   Rechtsklick-Eintrag ein – ohne Admin-Rechte. ffmpeg ist eingebaut.
3. Rechtsklick auf eine `.mcrec`-Datei → **In MP4 umwandeln** (Windows 11: unter „Weitere Optionen
   anzeigen“).

Windows SmartScreen kann beim ersten Start warnen, weil die Datei nicht signiert ist
(„Weitere Informationen“ → „Trotzdem ausführen“).

### Linux / macOS

Mit Python ≥ 3.9 und [pipx](https://pipx.pypa.io) oder [uv](https://docs.astral.sh/uv/):

```sh
pipx install "git+https://github.com/immeditech/mcrec2mp4"     # oder: uv tool install git+https://…
mcrec2mp4 --install                                            # Rechtsklick-Eintrag einrichten
```

ffmpeg mit libx264 wird vorausgesetzt (Paket `ffmpeg` der Distribution). Ohne System-ffmpeg:
`pipx install "mcrec2mp4[ffmpeg] @ git+https://github.com/immeditech/mcrec2mp4"`.

Alternativ gibt es fertige Einzeldateien (`mcrec2mp4-linux-x64`, `mcrec2mp4-macos-arm64`) mit
eingebautem ffmpeg bei den Releases. Nach dem Herunterladen `chmod +x` setzen; macOS blockiert die
unsignierte Datei zunächst, freigeben mit `xattr -d com.apple.quarantine mcrec2mp4-macos-arm64`.

`mcrec2mp4 --install` erkennt die installierten Dateimanager (Nautilus, Nemo, Caja, Dolphin) und legt
dazu den MIME-Typ für `*.mcrec` an. Vorhandene eigene Dateien gleichen Namens werden nicht
überschrieben. Entfernen: `mcrec2mp4 --uninstall`.
Im macOS-Finder gibt es den Rechtsklick-Eintrag noch nicht, dort geht nur die Kommandozeile.

## Kommandozeile

```text
mcrec2mp4 [Optionen] DATEI…

  -o, --output DATEI   Ausgabedatei (nur bei einer Eingabedatei)
  --fps N              Bildrate (Standard: 10)
  --max-idle S         Pausen länger als S Sekunden auf S Sekunden kürzen
  --crf N              Qualität, kleiner = besser (Standard: 23)
  -n, --no-overwrite   vorhandene Dateien nicht überschreiben
  -i, --info           nur Angaben zur Aufnahme anzeigen
  --notify             Ergebnis als Desktop-Benachrichtigung
  --install            Rechtsklick-Eintrag einrichten (--install-all: für alle Linux-Dateimanager)
  --uninstall          Rechtsklick-Eintrag entfernen
```

Beispiel:

```text
$ mcrec2mp4 --max-idle 5 DesktopSession-PC01-2026-10-27-09-21.mcrec
DesktopSession-PC01-2026-10-27-09-21.mcrec:
  Gerät:     PC01
  Beginn:    27.10.2026 09:12:38
  Ende:      27.10.2026 09:21:00
  Dauer:     8:22 (Video gekürzt auf 7:04)
  Auflösung: 1920×1080
  Aufnahme:  Browser (Aufnahme-Knopf)
  → Video gespeichert: DesktopSession-PC01-2026-10-27-09-21.mp4 (1920×1080, 7:04, in 23 s umgewandelt)
```

## Welche Angaben gibt es?

Das hängt davon ab, wie aufgenommen wurde:

- **Aufnahme-Knopf im Browser:** Die Datei enthält nur die Startzeit. Den Gerätenamen liest mcrec2mp4
  aus dem Dateinamen (`DesktopSession-<Gerät>-<Datum>`).
- **Aufzeichnung durch den MeshCentral-Server** (Richtlinie „Sitzungen aufzeichnen“): zusätzlich
  Benutzer, Benutzer-ID, IP-Adressen, Sitzungs- und Geräte-ID.

Unterstützt werden MeshCentral-Desktop-Sitzungen. Terminal- und Intel-AMT-Aufnahmen werden mit einer
Meldung abgelehnt. Details zum Dateiformat: [docs/format.md](docs/format.md).

## Entwicklung

```sh
python -m venv .venv && .venv/bin/pip install -e ".[test]"
.venv/bin/pytest
```

Die Tests erzeugen künstliche Aufnahmen (`tests/sample.py`). **Echte Aufnahmen gehören nicht ins Repo**,
sie zeigen Bildschirminhalte.

Release: Version in `src/mcrec2mp4/__init__.py` anheben, Tag `vX.Y.Z` pushen. GitHub Actions baut dann
die Einzeldateien für Windows, Linux und macOS und hängt sie an das Release.

## Lizenz

Der Quellcode steht unter der MIT-Lizenz. Kein Code aus MeshCentral übernommen, nur das Dateiformat
nachgebaut.

Die fertigen Einzeldateien bei den Releases enthalten zusätzlich ein ffmpeg mit libx264 aus
[imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg). Dieses ffmpeg steht unter der GPL; Quellen
und Lizenztexte: [ffmpeg.org](https://ffmpeg.org/legal.html) und
[imageio-binaries](https://github.com/imageio/imageio-binaries).
