# mcrec2mp4

Converts **MeshCentral desktop recordings (`.mcrec`)** to MP4 videos. An 8½-minute Full HD session
takes about 25 seconds, instead of real time as with the export in the browser player.

- Assembles the screen tiles the same way the MeshCentral player does and keeps the original timing.
- Recordings shorter than one second (a single image) are saved as **PNG**. If the screen doesn't
  change, you get a still-image video for the full length of the recording.
- Writes the recording details (device, user, start, duration …) into the MP4/PNG as title, comment
  and creation date.
- Long pauses can be shortened (`--max-idle`).
- Recordings from a crashed server (missing end block or truncated last block) are converted up to
  the last complete block.
- **Right-click "In MP4 umwandeln"** ("Convert to MP4") in the file manager: Windows Explorer,
  Nautilus (GNOME Files), Nemo, Caja and Dolphin. Multiple files work too (on Windows one window per
  file, up to 15 files).

The output file is placed next to the recording (`recording.mcrec` → `recording.mp4`).

> **Note:** The program's messages and the context-menu label are currently in German.

## Installation

### Windows

1. Download `mcrec2mp4-windows-x64.exe` from the
   [releases](https://github.com/immeditech/mcrec2mp4/releases/latest).
2. Double-click it. The program copies itself to `%LOCALAPPDATA%\Programs\mcrec2mp4` and sets up the
   right-click entry – no admin rights needed. ffmpeg is bundled.
3. Right-click a `.mcrec` file → **In MP4 umwandeln** (Windows 11: under "Show more options").

Windows SmartScreen may warn on first start because the file isn't signed
("More info" → "Run anyway").

To remove it, run `mcrec2mp4.exe --uninstall` from a command prompt.

### Linux / macOS

With Python ≥ 3.9 and [pipx](https://pipx.pypa.io) or [uv](https://docs.astral.sh/uv/):

```sh
pipx install "git+https://github.com/immeditech/mcrec2mp4"     # or: uv tool install git+https://…
mcrec2mp4 --install                                            # set up the right-click entry
```

Requires ffmpeg with libx264 (your distribution's `ffmpeg` package). Without a system ffmpeg:
`pipx install "mcrec2mp4[ffmpeg] @ git+https://github.com/immeditech/mcrec2mp4"`.

Alternatively, the releases contain standalone binaries (`mcrec2mp4-linux-x64`,
`mcrec2mp4-macos-arm64`) with ffmpeg bundled. After downloading, run `chmod +x`. macOS blocks the
unsigned file at first; allow it with `xattr -d com.apple.quarantine mcrec2mp4-macos-arm64`.

`mcrec2mp4 --install` detects the installed file managers (Nautilus, Nemo, Caja, Dolphin) and also
registers the MIME type for `*.mcrec`. Existing files with the same name that weren't created by
mcrec2mp4 are left untouched. Remove with `mcrec2mp4 --uninstall`.
There is no Finder integration on macOS yet; use the command line there.

## Command line

```text
mcrec2mp4 [options] FILE…

  -o, --output FILE    output file (only with a single input file)
  --fps N              frame rate (default: 10)
  --max-idle S         shorten pauses longer than S seconds to S seconds
  --crf N              quality, lower = better (default: 23)
  -n, --no-overwrite   don't overwrite existing files
  -i, --info           only show details about the recording
  --notify             report the result as a desktop notification
  --install            set up the right-click entry (--install-all: for all Linux file managers)
  --uninstall          remove the right-click entry
```

Example (output is in German):

```text
$ mcrec2mp4 DesktopSession-PC01-2026-10-27-09-21.mcrec
DesktopSession-PC01-2026-10-27-09-21.mcrec:
  Gerät:     PC01
  Beginn:    27.10.2026 09:12:38
  Ende:      27.10.2026 09:21:11
  Dauer:     8:33
  Auflösung: 1920×1080
  Aufnahme:  Browser (Aufnahme-Knopf)
  → Video gespeichert: DesktopSession-PC01-2026-10-27-09-21.mp4 (1920×1080, 8:33, in 24 s umgewandelt)
```

## Which details are available?

That depends on how the session was recorded:

- **Record button in the browser:** The file only contains the start time. mcrec2mp4 reads the
  device name from the file name (`DesktopSession-<device>-<date>`).
- **Recorded by the MeshCentral server** (session recording policy): additionally user, user ID,
  IP addresses, session ID and node ID.

MeshCentral desktop sessions are supported. Terminal and Intel AMT recordings are rejected with a
message. Details on the file format: [docs/format.md](docs/format.md).

## Development

```sh
python -m venv .venv && .venv/bin/pip install -e ".[test]"
.venv/bin/pytest
```

The tests generate synthetic recordings (`tests/sample.py`). **Never commit real recordings** – they
contain screen contents.

Test build without a release: Actions → "Release" → "Run workflow"; the standalone binaries are then
attached to the run as artifacts.

Release: bump the version in `src/mcrec2mp4/__init__.py` and push a `vX.Y.Z` tag. GitHub Actions
builds the standalone binaries for Windows, Linux and macOS and attaches them to the release.

## License

The source code is licensed under the MIT license. No code was taken from MeshCentral; only the file
format was reimplemented.

The standalone binaries in the releases additionally bundle an ffmpeg with libx264 from
[imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg). That ffmpeg is licensed under the GPL;
sources and license texts: [ffmpeg.org](https://ffmpeg.org/legal.html) and
[imageio-binaries](https://github.com/imageio/imageio-binaries).
