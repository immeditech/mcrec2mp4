# The .mcrec format (MeshCentral desktop)

Compiled from the MeshCentral source code (`views/player.handlebars` → `processBlockEx`,
`public/scripts/agent-desktop-0.0.2.js` → `ProcessBinaryCommand`/`recordingEntry`, `meshrelay.js` →
`recordingEntry`, `views/default.handlebars` → `deskRecordSession`).

## Blocks

The file is a sequence of blocks: a 16-byte header followed by the data.

| Bytes | Content                        |
|-------|--------------------------------|
| 0–1   | type (u16 BE)                  |
| 2–3   | flags (u16 BE)                 |
| 4–7   | data size (u32 BE)             |
| 8–15  | time (see below)               |

Types: 1 = metadata (JSON), 2 = network data, 3 = end/index pointer, 4 = index metadata.
The end block (type 3) carries the end of the recording: if the screen doesn't change, no more data
arrives, but the recording keeps running (the player shows a still image). The server backdates the
end block by 5 s, so the end is the later of the last data block and the end block.

Flags: `1` = binary, `2` = user → device. Only type-2 blocks with `flags & 1` and without `flags & 2`
(device → user) matter for the picture.

## Timestamps

The player computes `(ReadInt(8) << 32) + ReadInt(12)`. In JavaScript `x << 32` is the same as
`x << 0`, so the result is `int32(bytes 8–11) + uint32(bytes 12–15)`.

- **Browser recording** (record button in the web UI) writes `intToStr(now >> 32)` and
  `intToStr(now & 32)` – i.e. the lower 32 bits of the millisecond time plus 0 or 32.
  Time intervals therefore jitter by up to 32 ms.
- **Server recording** writes the time correctly as a 48-bit number in bytes 10–15.

With the player's formula, both variants wrap around every 2³² ms (≈ 49.7 days). mcrec2mp4 therefore
unwraps the time and only uses time differences.

## Metadata (type 1)

- Browser recording: only `magic`, `ver`, `time` (the browser's `toLocaleString()`) and `protocol`.
  The device name is only in the file name: `DesktopSession-<device>-YYYY-MM-DD-HH-MM.mcrec`
  (time = end of the recording).
- Server recording: additionally `userid`, `username`, `sessionid`, `ipaddr1`, `ipaddr2`, `nodeid`,
  `devicename` (and, depending on the code path, `devicegroup`).

`protocol`: 2 = MeshCentral desktop (supported), 1/6/8/9 = terminal, 101/102 = Intel AMT.

## Desktop commands

Data = `cmd u16 | cmdsize u16 | …`

- `cmd 27, cmdsize 8`: jumbo-packet wrapper. Real size = u32 @4, real command @8, then `v = v[8:]`.
- If `cmdsize + 8 == len(v)` afterwards, a duplicate header follows: `v = v[8:]`.
- If `cmdsize` doesn't match the length, the player discards the command.
- `cmd 7`: screen size, width = u16 @4, height = u16 @6.
- `cmd 3`: tile, X = u16 @4, Y = u16 @6, image (PNG/JPEG/WebP) from byte 8.
- Everything else (mouse, displays, …) is irrelevant for the video.
