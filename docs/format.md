# Das .mcrec-Format (MeshCentral-Desktop)

Zusammengetragen aus dem MeshCentral-Quellcode (`views/player.handlebars` → `processBlockEx`,
`public/scripts/agent-desktop-0.0.2.js` → `ProcessBinaryCommand`/`recordingEntry`, `meshrelay.js` →
`recordingEntry`, `views/default.handlebars` → `deskRecordSession`).

## Blöcke

Die Datei ist eine Folge von Blöcken: 16 Byte Kopf + Daten.

| Byte  | Inhalt                         |
|-------|--------------------------------|
| 0–1   | Typ (u16 BE)                   |
| 2–3   | Flags (u16 BE)                 |
| 4–7   | Datengröße (u32 BE)            |
| 8–15  | Zeit (siehe unten)             |

Typen: 1 = Metadaten (JSON), 2 = Netzwerkdaten, 3 = Ende/Index-Zeiger, 4 = Index-Metadaten.
Flags: `1` = binär, `2` = Benutzer → Gerät. Für das Bild zählen nur Typ-2-Blöcke mit `flags & 1` und
ohne `flags & 2` (Gerät → Benutzer).

## Zeitstempel

Der Player rechnet `(ReadInt(8) << 32) + ReadInt(12)`. In JavaScript ist `x << 32` dasselbe wie
`x << 0`, das Ergebnis ist also `int32(Bytes 8–11) + uint32(Bytes 12–15)`.

- **Browser-Aufnahme** (Aufnahme-Knopf in der Web-Oberfläche) schreibt `intToStr(now >> 32)` und
  `intToStr(now & 32)` – also die unteren 32 Bit der Millisekunden-Zeit und dazu 0 oder 32.
  Zeitabstände schwanken dadurch um bis zu 32 ms.
- **Server-Aufzeichnung** schreibt die Zeit korrekt als 48-Bit-Zahl in Bytes 10–15.

Beide Varianten laufen nach der Player-Formel alle 2³² ms (≈ 49,7 Tage) über. mcrec2mp4 entfaltet die
Zeit deshalb und nutzt nur Zeitabstände.

## Metadaten (Typ 1)

- Browser-Aufnahme: nur `magic`, `ver`, `time` (`toLocaleString()` des Browsers) und `protocol`.
  Den Gerätenamen gibt es nur im Dateinamen: `DesktopSession-<Gerät>-JJJJ-MM-TT-HH-MM.mcrec`
  (Zeit = Ende der Aufnahme).
- Server-Aufzeichnung: zusätzlich `userid`, `username`, `sessionid`, `ipaddr1`, `ipaddr2`, `nodeid`,
  `devicename` (und je nach Weg `devicegroup`).

`protocol`: 2 = MeshCentral-Desktop (unterstützt), 1/6/8/9 = Terminal, 101/102 = Intel AMT.

## Desktop-Kommandos

Daten = `cmd u16 | cmdsize u16 | …`

- `cmd 27, cmdsize 8`: Großpaket-Wrapper. Echte Größe = u32 @4, echtes Kommando @8, dann `v = v[8:]`.
- Ist danach `cmdsize + 8 == len(v)`, folgt ein doppelter Kopf: `v = v[8:]`.
- Passt `cmdsize` nicht zur Länge, verwirft der Player das Kommando.
- `cmd 7`: Bildschirmgröße, Breite = u16 @4, Höhe = u16 @6.
- `cmd 3`: Kachel, X = u16 @4, Y = u16 @6, Bild (PNG/JPEG/WebP) ab Byte 8.
- Alles andere (Maus, Displays, …) ist für das Video unerheblich.
