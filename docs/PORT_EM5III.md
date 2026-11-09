# Porting Caduceus to the E-M5 Mark III: first-glance feasibility

> **Needs someone with an E-M5 III to try this.** Nothing here has been run on a camera, and nothing here has been built.
> This is a static read (2026-11-04) plus a byte-signature match. The author has no E-M5 III. A port should be done by a
> person who owns one and can test every change on the body, keeping a way back to stock firmware. A signature match
> only shows the surrounding bytes look alike; it does not show an edit is correct or safe on this body.

Companion to [PORT_EM10IV.md](PORT_EM10IV.md), which did the full edit-by-edit signature match for the E-M10 IV.

## Sources

- E-M5 III `OLY_E_137_1700_0000_0000.BIN` (1.7, latest in OM's catalog, dated 2023/1/19). It is kept in
  `stock_firmware/em5iii/`, never committed. The catalog request and response are saved beside it.
- E-P7 1.1 (`OLY_E_142_1100_0000_0000.BIN`).
- The decoded components are in `analysis/em5iii/` and `analysis/ep7_1100/`.

## What was checked

| Check | E-P7 1.1 | E-M5 III 1.7 |
|---|---|---|
| Whole image | 111 017 984 B | 118 620 160 B |
| Main (0x100) decoded | 26 214 336 B | 25 034 688 B |
| OSD resource (0x101) decoded | 26 214 336 B | 31 457 216 B |
| 0x106 decoded | 45 219 776 B | 52 428 736 B |
| 0x102 decoded | 13 107 136 B | 9 437 120 B |
| `PROFILE` strings in main | 21 | **0** |
| `COLORTONE` strings in main | 213 | **64** |

- The component kinds are the same (0x100/101/106/10e/102) and the load addresses are close but not equal
  (main `0x40780020` against `0x406a0020`). The sizes all differ, so unlike the E-M10 IV this is **not** a same-layout container.
  The container still decodes and round-trips byte-identically (`analysis/em5iii/manifest.json`, `roundtrip_identical: true`,
  see the E-M5 III-specific analysis mapping below; the E-P7 base must not be reused).
- The E-M5 III main has Color Creator (`setColorCreatorScpEvent`, `VARIOUS_DRAW_COLOR_CREATOR`, `COLORTONE_COLOR_CREATOR`)
  and no Color/Mono Profile strings.
- Earlier docs already note: the same TruePic VIII generation as the E-P7; the same C4K sensor drive modes
  ([VIDEO_HIDDEN.md](VIDEO_HIDDEN.md)); the three lens-button records, with longer lists ([LENS_BUTTONS.md](LENS_BUTTONS.md));
  and an older settings layout without the E-P7's 20-byte validator table.

## E-M5 III 1.7 main address mapping (static correction)

For the exact inputs below, decoded main offset zero corresponds to CPU analysis
address **`0x60021020`**, not the E-P7's `0x60020020`. Using the latter labels
E-M5 III addresses `0x1000` too low. This matters when locating port hooks or
translating a matched file offset into a CPU address; it does not validate a patch.

| Input | Bytes | SHA-256 |
|---|---:|---|
| `OLY_E_137_1700_0000_0000.BIN` | 118620160 | `939260fc22b4217fce64274eb5a6707d307a499804d8a316b6b39019c4afded2` |
| Decoded main `00_0100_40780020.decoded.bin` | 25034688 | `4097f57751ac30c24589448865b2824891a754744eae63ab14359fd46c1cf4be` |

Keep three different quantities separate:

- Main payload begins at **container byte offset** `0x20`.
- `0x40780020` is its **container/header logical payload address**, not a file offset or CPU base.
- The ten 12-byte section records begin at **decoded main offset** `0x6284`,
  corresponding to **CPU analysis address** `0x600272a4`.

Read each little-endian record as `(destination, logical_source, duplicate_destination)`.
All ten satisfy `destination - (logical_source - 0x40780020) == 0x60021020`;
first record: destination `0x600de000`, source `0x4083d000`.
The existing static loader analysis at `0x60045e2e` also contains the absolute table
address `0x600272a4` at instruction `0x60045e40` (decoded offset `0x24e20`).
It accesses record fields, calls the address-conversion helper `0x600645f0`, and
passes a section length to `0x6005a177`. This is supporting disassembly, not an
executed loader or proof that every section is resident. GNU binutils labels an
instruction in this window `udfu01`; no execution semantics are assigned to it here.

To reproduce the table calculation on an already decoded, locally held main
component, run from the repository root (Python 3 standard library only):

```sh
python3 - <<'PY'
from pathlib import Path
import hashlib, struct
p = Path('analysis/em5iii/00_0100_40780020.decoded.bin')
b = p.read_bytes()
assert len(b) == 25034688
assert hashlib.sha256(b).hexdigest() == '4097f57751ac30c24589448865b2824891a754744eae63ab14359fd46c1cf4be'
for i in range(10):
    offset = 0x6284 + 12 * i
    dst, src, duplicate = struct.unpack_from('<III', b, offset)
    base = dst - (src - 0x40780020)
    assert duplicate == dst and base == 0x60021020
    print(i + 1, hex(offset), hex(dst), hex(src), hex(base))
PY
```

For independent instruction review, use GNU MN10300/AM33 binutils (the check used
2.45) with `--adjust-vma=0x60021020` on this main component and the reviewed window
`--start-address=0x60045dc5 --stop-address=0x60045ea0`, with `-b binary -m mn10300 -D`.
Do not use the E-P7-only `tools/dis.sh` unchanged. These are read-only checks;
firmware and disassembly are not included in this contribution.

This corrects the address interpretation, not the historical byte-search counts
elsewhere in this note: those counts were not rerun here. It does not establish code-space
availability, section lifetime, settings synchronization, modified-image acceptance
or independent recovery. No instruction-model result or camera test is claimed
for this correction. Prepared by Roy Kittrell with AI assistance, building on the
Caduceus port assessment and the fishcu/community container/tooling research.

## Signature match (E-P7 v0.20 edits → E-M5 III 1.7 main)

Script: `tools/port_sigmatch.py` (read-only). For each of the 294 main-image edits in `releases/v0.20/edits.json` it looks for
the same E-P7 bytes, plus 32/16/8 bytes of context each side, in the E-M5 III main. PC-relative operands are not masked, so
shifted matches are undercounted. The same script on the E-M10 IV gives 47 % (137 of 294), consistent with the 48 % in
[PORT_EM10IV.md](PORT_EM10IV.md).

| Result | E-M5 III | E-M10 IV (same script) |
|---|---:|---:|
| Same address | 0 | 21 |
| Found once, shifted | 106 | 116 |
| Found more than once (ambiguous) | 13 | 13 |
| Not found | 175 | 144 |
| **Auto (same + shifted)** | **106 / 294 = 36 %** | 137 / 294 = 47 % |

Nothing sits at its E-P7 address, so this is a different build from the E-P7, further away than the E-M10 IV.

Features, by keyword in each edit's reason (counts of edits):

| Feature | Found | Not found / ambiguous | Note |
|---|---:|---:|---|
| Recording-length limit (the `1740` and `7200` operands) | 2 | 0 | both operand sites found once |
| LCD tint | 4 | 0 | |
| Tone hook | 2 | 7 | mostly ambiguous |
| Aspect | 2 | 4 | |
| Film page / looks / editor | 1 of 47 film, 1 of 5 look | the rest | depends on profile slots |
| SD loader | 0 | 1 + 2 ambiguous | not found |
| Log video (`925` hook) | 0 | 1 | not found |

The recording-length limit and LCD tint are the only encouraging groups. The SD loader and log-video hook, which matched
fully on the E-M10 IV, did **not** match here, so they need locating by hand.

## Assessment

**A small port (rec limit, LCD tint) looks plausible. The SD loader, log hook and aspect tables need real work. A full port is a redesign.**

**Main blocker: no Color/Mono Profile system.** Every look, editor, film-page and bundle feature in Caduceus hangs off the
E-P7's profile slots. The E-M5 III would need a different host (Color Creator, Art Filters or picture mode), and the
look-applying code would have to be redesigned around that host rather than relocated.

**Other blockers**
- The settings/validator layout is older, so the settings ids and tables must be re-derived.
- The OSD resource (0x101) differs a lot in size, so all menu, wheel and string ids must be re-derived.
- It has a mode dial and an EVF, so the LCD and EVF panel tables need checking.
- None of the emulator baselines or camera-JPEG comparisons exist for it.

## Suggested path for whoever takes this

1. Re-run `tools/port_sigmatch.py` after any change to the edit set, and read the matched sites in a disassembly before trusting them.
2. Start with the two best groups (recording limit, LCD tint), build one change at a time, and test each on the body before adding the next.
3. Work out the SD loader by hand, since it is needed to load anything else from a card.
4. Decide on a host for the looks (Color Creator is the likeliest) only after the above works.
5. Keep the stock image and a recovery route to hand throughout. The project's anti-brick checks should be passed before any
   image goes on a card.

## Status

Not started. Waiting for an owner of an E-M5 III who is willing to validate changes on the camera.
