# Split toning on the E-P7 (scope, 2026-11-12)

Source: Caduceus for OM-3 v0.26 (`st_run` in `firmware/src/editor.s`, `docs/DEVELOPER_NOTES.md` "v0.26 release"),
Apache-2.0. Shared look field: `split {sh_color 0..11, sh -5..5, hl_color 0..11, hl -5..5}` (`webapp/src/split.ts`,
already in packs and `pk1_` links; the E-P7 export ignores it today). Nothing built. [V] = read in code or docs, [I] = inference.

## What the OM-3 does [V]
At the tone hook's exit it bends the job's R/G/B gamma tables in place:
t' = t + ((Ks·ws + Kh·wh) >> 8), ws = ((t·s>>12)·s)>>12, wh = ((t·t>>12)·s)>>12, s = 4095 − t, with a running max so
each curve keeps rising. K = `st_k`[colour] × strength (12 colours). Only for COLOR (key 11); stills and live view.

## E-P7 differences
- **Gamma is ROM, not a job table [V]:** the selector writes one ROM pointer to all three slots, O+2596 / 2600 / 2604
  (`0x603ae7d3`, docs/VIDEO_LOG.md bank A, 256 × u16, 12-bit). So we copy the ROM curve into three 512-B RAM
  buffers, bend each one and point the three slots at them. This takes 1.5 KB of RAM per context (live view and capture), and
  the curve has to be rebuilt when the pointer changes (the same idempotence rule as tone_ends v0.19b).
- **Hook:** the tone_ends hook `0x603b14ff` runs after the gamma pointer is set, with the same gates (key 11, profile
  from job+15488 / getter 0xF6B1) [V for the hook, I for the order]. Code size is about 250 B [I]. It needs new free space (CODE_SPACE_MAP).
- **Look bytes: the LOOKS.BIN record is full [V]:** +0..44 bundle, +45 class, +46 mask, +47 bloom tint, +48..63
  name. Split needs 2 bytes (4 nibbles). Options:
  1. LOOKS.BIN v4 with a larger record, which needs loader and panel changes. Old firmware rejects it (size % 64).
  2. Names cut to 13 characters to free +61..62. This truncates existing names.
  3. Use the free bundle bytes 46..63, which needs a layout.json change.
  The slot entry has space (+45..63 are written on a pick).
- **Camera editor:** the OM-3 adds wheel pages 5 / 6. Leave these out of the first slice: the look is set in the Control Panel only.

## Plan (smallest testable slice)
1. Decide the record format (above). This is a format question, so agree it in this repo first (AGENTS.md).
2. Firmware: RAM curves + bend at the tone hook, COLOR stills and LV. Port `st_k` and the formula unchanged.
3. Control Panel: E-P7 export writes the split bytes; the preview already has `bendSplit`.
4. Camera test: one look with Gold-200-style warm highlights / cool shadows against the panel preview; grey card stays neutral at 0.

Estimate: 1–2 agent sessions after the format decision. Risk: low–medium (it edits a table like tone_ends, but it is a new RAM
buffer in the live view path).
