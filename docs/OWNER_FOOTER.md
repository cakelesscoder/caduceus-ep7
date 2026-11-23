# Owner footer (E-P7 1.1, `patches/owner_footer`)

The owner types a name and phone number when building the firmware (`caduceus.py`, double-click launchers or
`caduceus.py build --owner-name NAME --owner-phone PHONE`; `--no-owner` skips the questions). The camera then shows them
as one line at the bottom of every main-menu page. Nothing on the camera or the card can change it: changing it means
rebuilding and reflashing. Status: **emulator-verified; on the camera the footer doesn't show yet (v0.35c test, 2026-11-23).** v0.35 ships the
layer with an empty block and doesn't offer the owner questions (its spec has no `owner_footer` key) until that's fixed. `[V]` bytes / emulator, `[I]` inferred.

## Build side

- Limits (caduceus.py `owner_text`): printable ASCII; name ≤ 24, phone ≤ 20 of digits, space, `+ - ( )`; the line is
  `name  phone`; its estimated width (ASCII glyph widths of the camera font + 3 px) ≤ 620 px. Both empty = no footer.
- The release image carries a zero **owner block** (104 B at `owner_footer.block` in the spec): `u32 'EP7O'`, `u16 n`
  (1..46), `u16 0`, `wchar text[n]`, `u16 0`, zero padding. caduceus.py first builds the release package and checks
  its hashes as before, then writes the block into the edit list and builds again; it refuses unless the two packages
  differ only inside the block (`owner_unpatch`). The output folder gets an `OWNER_FOOTER` marker (no personal data);
  `caduceus.py verify` accepts such a firmware file when it equals the release with the block zeroed.
- Releases without the layer refuse `--owner-*` and ask nothing.

## Camera side [V code, I camera]

- Hook: the GE window paint's only vtbl +160 call (0x60d005fb). +160 (0x60d00692) **is the children paint** (per layer,
  per dirty rect); the +164 slot used by the shelved overlay runs *before* it, which is why text drawn there was painted
  over (ATLAS §15 #13). of_paint replays +160 and then draws.
- Gate: valid owner block; `0x61fb828c` != 0 (set by the 2CNL menu-page panel's show / data-notify methods, cleared by
  its destructor, no stock reader); painted window == current window `*0x61fb3138`; painter ≥ 2 layers; multi-layer window.
- Draw, as stock paints a label part: painter_set_layer(2) (GUI layer 1), text style 1 (the only one; menu labels use
  it) via 0x60d0fce0, gc+0x34 = 2, then for each layer-2 dirty rect (window+1464, ≤ 3) clip 0x60d0618c and draw with
  0x60d075a7: style `{25, 15, 15, centred}` (colour 25 = normal menu text), rect `{40, 434, 680, 474}` (below the page
  frame, which ends at y 425). Release the font, restore the layer, put gc clip / font / mode back.
- Empty or bad block: the stub replays the call and returns; registers, stack and objects as stock (verify E).

## Checks (`patches/owner_footer/verify.py BASE NEW [PKGDIR]`)

S static, E empty block == stock, C dummy block with the menu closed == stock, D one draw (2 dirty rects: layers 2 then
the old one, style 1, one draw per rect with that clip, text / style / rect, font released, gc and painter as found),
P package anti-brick + the caduceus.py personalisation path. All pass on `generated/v034a_owner`.

## For the camera test

Footer visible and legible on every tab (Shooting 1/2, Video, Playback, Custom, Setup) and on sub-pages and Custom
letter pages; position (no overlap with the page frame, the scroll bar or a second-level popup); not on live view,
playback or screens opened from a menu row (date/time, Wi-Fi, colour editor) — if it shows there, the alive word is
too coarse; no ghost text after leaving the menu; menu keys and navigation unchanged; HDMI out (if tried).
