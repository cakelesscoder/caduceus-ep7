# Extras overlay: text rows over the Colour Profile editor (E-P7 1.1)

Goal: replace the colour-wheel-style Extras pages with a plain **text overlay** on the Colour Profile editor live
view — a list of rows, each `name  value`, redrawn live, driven by today's keys (no key changes), writing today's
fields. Room to grow past 12 sectors (split toning folds in next as Shadows/Highlights rows). Design background:
[EXTRAS_MENU_V2.md](EXTRAS_MENU_V2.md) (its Effects/Colour/Tone/Profile grouping still applies; its "stay on the
wheel" line is superseded). Draw API: [RE_DRAW_PLUGIN.md](RE_DRAW_PLUGIN.md). Keys and fields:
[LOOK_EXTRAS.md](LOOK_EXTRAS.md), [LOOK_EDITOR.md](LOOK_EDITOR.md), [HALATION_RED.md](HALATION_RED.md).

`[V]` = read from the bytes (private decompile under `~/ep7fw-private/decomp/`, nothing copied here). `[I]` =
inference. `[C]` = camera. **Nothing here is camera-tested.** Base: the v0.32 test build.

Private RE (disassembly, decompiler output) stays in `~/ep7fw-private/decomp/`; this file carries addresses and the
recipe only ([RE_PRIVATE.md](RE_PRIVATE.md)).

## 1. Status

> **Superseded hook (v0.32 diag layer, docs/PLUGINS.md §10).** The camera drew nothing. The two window +164 words
> covered only two of about 400 window classes, and the flag was consumed on the first paint after each update. The
> diag layer draws the same four rows from the GE paint site 0x60d005ef with a "view alive" flag (set by view +0,
> cleared by view +4), cached alias. §2.2 and §4 below describe the original probe.
> **Invisible text (camera `7/3`, PLUGINS.md §11):** ge_draw_text takes the text colour from style +0 and overwrites
> the gc colour, so the zeroed style drew in palette entry 0 (transparent). §2.1's "colour is set on the gc" and its
> style offsets are wrong; §11 has the corrected layout. The diag layer now puts the colour in the style.
> Also wrong: `*(window+72)` and the +164 argument are the **painter**; the gc is `*(painter+8)` (0x60d060e3), and
> stock selects a text style (0x60d0fce0) before every draw (camera `7/4`, PLUGINS.md §11).

- **Stage A (this build): a probe.** It answers, in one camera look, the three questions that block a real overlay:
  live palette/colour, the layer and clipping of the hook, and whether the area is cleared each frame (ghosting).
  It draws four short text rows on the Colour Profile editor while the Extras page is open, in four colours, each row
  printing the colour value it was drawn with and a live number that moves with the dial. The stock wheel, labels
  and every field stay exactly as today; nothing is removed.
- **Stage B (after the probe): the real overlay.** Rows for every Extras field with live values, selection and value
  change on today's keys, writing the same slot bytes the wheel editor writes, split toning folded in. Not built:
  it needs the probe's answers first.

The probe ships **inside the v0.32 test build** next to the key-hook layer (one flash). With no looks (no card
table) the overlay is off and the stock path is byte-for-byte unchanged.

## 2. The text-draw recipe (as traced; `[V]` unless noted)

Three ways to put glyphs on an OSD layer were considered (RE_DRAW_PLUGIN §2.3): the per-glyph gpi char call
(`gpi_dc_char` 0x60d1216c, DC fn +28), the one-character `gpiDrawCharactor` 0x60d12d57, and the **high-level string
drawer 0x60d075a7**. The probe uses the string drawer, because it takes a whole wide string, a rect and the window's
own graphics context, and it is the routine the stock menus and value lists already use (callers 0x60d0758f,
0x60d455bf, 0x60d4728a, 0x60d473db) — so geometry and font come for free.

### 2.1 draw_text(gc, style, string, rect)

```
call 0x60d075a7, [d2,d3,a2,a3], 252
  d0 = style*   : pointer to a 24-byte style record (below)
  d1 = string*  : NUL-terminated UTF-16LE (wide) string; res-35 glyphs cover ASCII 0x20..0x7e
  a0 = gc       : a graphics context ("gc", 0x2ac bytes). The window's own gc = *(window + 72)
  a1 = rect*    : four s16 {x0, y0, x1, y1}, clip/area of the text, 800x600 canvas
```

- The routine returns early (no draw) if `string == 0` or `gc+0x4c == 0`, so a bad pointer is a no-op, not a fault.
- **Colour is set on the gc, not in the style:** `call 0x60d0fc05, a0 = gc, d0 = colour` writes gc+0x24 and
  gc+0x280. On the glyph path the four palette indices of a character come out as `{0, c+2, c+1, c}` from the gc
  colour (OSD.md "Glyph levels"); `[I]` the colour word the gc wants and the exact index it yields is the open
  question the probe settles. Stock also calls `0x60d0fd83, a0 = gc, d0 = 2` (a mode byte at gc+0x34) before a list
  draw; the probe replays it.
- **Style record (24 B)** `[V fields used by 0x60d075a7, I of the rest]`: +3 h-align (0 left, 1 centre, 2 right),
  +0xd v-align, +4/+5 margins (shrink the rect), +0xe/+0x12 x/y offset inside the rect. The probe uses a zeroed
  record (left/top, no margin) so text starts at the rect's top-left. A nonzero unknown field would shift or scale
  the text, never fault.
- **Font:** the one registered font is id 1; `call 0x60d0fce0, a0 = gc, d0 = 1` selects it. The window's gc is
  already set to it by stock, so the probe does not re-select.

### 2.2 The hook: window vtable +164 (post-paint, data only)

The GE screen paint routine 0x60d00506 draws the child widgets (loop through 0x60d0f3aa / 0x60d06530 / 0x60d0642a),
then calls the window's vtable **+164** and **+160**, then presents (RE_DRAW_PLUGIN §2.4). **+164 is an empty
`retf [],0`** (0x60cfe263) in both window classes — their vtable words at **0x60f94820** and **0x60fac3f0** both hold
0x60cfe263 `[V]`. Repointing those two data words at `ov_post` adds one post-paint call per window paint and changes
nothing else. a0 = the window; the gc is `*(a0 + 72)`.

- **Off path = exactly stock.** `ov_post` reads only scratch registers (d0, d1, a0, a1), leaves d2/d3/a2/a3/sp/mdr
  untouched, and on any miss does `retf [],0` — the same bytes 0x60cfe263 ran. The emulator test drives the hook on
  windows that are not the editor and compares against stock +164 (§4, test E-off).
- **When to draw:** only when the heap editor state says the Extras page is open — P valid, `EP7B`, editor marker
  `EP7E` at P+680, axis P+684 == 4 (the extras axis, `ed_cfg_x`). This is the same trusted read `ed_poly` and
  `ex_guide` use. With no card table the handle word 0x622cbcc2 is 0 at power-on, so the check misses and the stock
  path runs.
- **Close:** the Colour Profile view's own vtable +4 (close, 0x60dec697) is hooked to clear the overlay flag and
  request a repaint, so the rows don't linger after the editor closes (the axis byte persists until the editor
  reopens — the known `ed_poly` limitation). The flag is one boot-cleared .bss byte (§3).

## 3. State byte

The hook runs in GUI_TASK; the close hook in GUI_TASK too. The probe needs one flag byte they share. **P+816..823 is
not confirmed free in P2/P3** (P2's MOVIE.BIN file buffer spans +800..895 while a movie look loads), so the probe
does **not** use a P word. It uses the boot-cleared .bss pad **0x622ab792** (`[V]`, AUTOLOAD.md §Progress: padding
between a `movhu`-only u16 at 0x622ab790 and u32s at 0x622ab794/798; no abs32 reference; shelved auto-load freed it).
Accessed through the uncached alias 0xa22ab792. 0x622ab793 stays the auto-load/plugin reserve.

## 4. As built (probe, emulator-verified, not camera-tested)

`patches/overlay_probe/` (`build.py`, `ov.s.in`, `verify.py`); atlas symbols `tools/atlas/new_overlay.py`. Layered
into v0.32 after keyhook (`patches/v032/build.py`). 604 B of code at **0x607b8430** (claim 0x607b8420–0x607c8420,
sec 5 dead sdk-api handlers).

**What it draws.** While the Colour Profile editor is on the Extras page (heap `EP7E`, axis 4), four text rows over
the live view, through the stock string drawer 0x60d075a7 into the window's own gc:

| Row | Text | Colour value | Rect `{x0,y0,x1,y1}` | Tests |
|---|---|---|---|---|
| A | `c1 Clarity +2` | 1 | 40, 40, 380, 96 | top-left; colour 1 |
| B | `c2 Halo Red 3` | 2 | 40, 110, 380, 166 | colour 2 |
| C | `c4 Shadow Teal` | 4 | 44, 470, 460, 526 | **near the bottom edge** (clipping); colour 4 |
| D | `c6 #NN` | 6 | 400, 40, 796, 96 | **near the right edge** (clipping); `NN` = a rolling hex counter (**ghosting**) |

The rows are fixed text (the colour-index probe matters more than live values at this stage); row D's `#NN`
increments every repaint, so stale digits under fresh ones show ghosting at a glance. The colour value is passed to
0x60d0fc05 and printed as `c<n>`, so the camera shows which value yields which on-screen colour — settling the live
palette. Rows at the edges settle clipping and which layer the gc targets. The stock wheel, labels and every field
are untouched.

**Hooks (data words only).** View +0 word 0x61155e14 (0x60dec790 → ov_upd): runs the stock update, then sets the
flag. Window +164 words 0x60f94820 / 0x60fac3f0 (0x60cfe263 → ov_post): post-paint; flag 0 → the stock empty method
byte-for-byte; flag 1 → clear it and draw. The flag is set each editor-paint frame and consumed+cleared each
post-paint, so it self-clears on editor close (no close hook, no stale axis). State: .bss 0x622ab792 (flag) /
0x622ab793 (counter).

**Text-draw recipe status: works in the emulator.** `draw_text(gc, style, string, rect)` = `call 0x60d075a7,
[d2,d3,a2,a3],252` with d0 = style (a zeroed 24-B record, left/top), d1 = wide string, a0 = the window gc
(`*(window+72)` / the painter a1), a1 = a 4×s16 rect; colour set first with `call 0x60d0fc05,[d2,d3,a2,a3],16`
(d0 = colour value, a0 = gc) and mode byte gc+0x34 = 2. The emulator DRAW test confirms ov_post calls the colour
setter 4× (values 1,2,4,6) and the drawer 4× (gc = the window gc, the four row strings, style/rect in-frame), clears
the flag, restores mdr and writes nothing into the loaded image. **Open on the camera:** the live palette (what
colour each value produces), which layer the gc draws to, whether the editor repaints behind the overlay (ghosting),
and the font cell size vs the 32-px rows.

**Emulator checks** (`patches/overlay_probe/verify.py`, ALL PASS): OFF (flag 0 == stock `retf [],0`: d2/d3/a2/a3/sp/
mdr and the stack identical), UPD (ov_upd runs the body, sets the flag, returns the body's frame), DRAW (4 colour +
4 text calls with the right args, flag cleared, counter stepped, no image store), MISS (flag 1 but not the Extras
page → no draw, flag cleared), P (package 0x100 == the image DRAW ran, restore == stock, the only changed bytes are
the code + the three words). Reference safety: a delta scan proves no new reference lands in the claim beyond the
three vtable words and the code's own internal branches (the shell range is survey-cleared).

**Risks.**
- Text drawing is traced and emulator-proven for register/frame discipline, but the **rendered result is unverified**
  — the colour mapping and layer are exactly what the probe is for. If a value renders near-black (gc colour is ARGB,
  not an index), rows C/D may be hard to read; the camera report tells us.
- ov_post runs on every window paint from boot; the off path is byte-exact stock (OFF test) and the flag is 0 until
  the editor paints, so with no looks the overlay never draws. A valid-but-wrong draw can at worst fault in GUI_TASK
  when the editor is open — recoverable by reflashing, never a bootloop (boot never runs this code's draw path).
- The flag enables drawing on any window while the editor is the active viewer; a popup over the editor could take an
  overlay frame. Cosmetic, and informative for the probe.
- `mov sp,Dn` is not a valid form (it faulted in the emulator); the code routes sp→a-reg→d-reg. Noted so stage B
  avoids it.

**Package:** `patched.pkg.bin` sha256 `1b14cae58364e494664a2e9a531644c6b8ef989a264c94cb25b54f3c3073760d`
(restore `963f4dfe…`), built from `generated/v032/edits.json`.

**What to look at on the camera (one flash).** Open a COLOR profile editor, step to the Extras page. Expect four
text rows over the live view: `c1 Clarity +2` (top-left), `c2 Halo Red 3` below it, `c4 Shadow Teal` low on the left,
`c6 #NN` top-right with `NN` changing. Report: which rows are visible and readable; the colour of each (does `c1`/`c2`/
`c4`/`c6` differ, and how); whether row C (bottom) and row D (right) are clipped or complete; whether `#NN` updates
cleanly or leaves ghost digits; and roughly where the rows sit relative to the wheel. With no card (no looks), nothing
new should appear and the editor must be exactly as today.

