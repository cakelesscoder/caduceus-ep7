# Down on the film select screen crashes (issue #48, v0.32a, 2026-11-14)

**Report (codefist, v0.32a):** power on, half-press (looks load), press the Shortcut button (top, beside REC),
d-pad over to change the film look, press Down: the camera crashes, reboots, and needs a battery pull. Follow-up:
pressing Down "right away" on that screen also crashes, sometimes.

**Result: no cause found.** Every v0.32 code path that this key sequence can reach runs clean in the emulator on the
real v0.32a image. What's left is either a stock path the emulator stubs, or code outside the GUI. No fix was built.
[V] = bytes, code or emulator. [I] = inference.

## Which screen

- [I] The Shortcut button opens the **full Colour Profile page** (Profile view, vtable 0x61189ba8). That is the
  page from #41 ("the screen with the left COLOR 1 badge and the four small icons"). The #41 reporter could switch
  looks there on v0.31c with no crash.
- [V] On that page, page 1 (the COLOR wheel) is drawn by `0x60e27289`. Since v0.32 its guide-label write at
  0x60e2757d jumps to `sn_gd` (patches/scp_name, #41). sn_gd runs the whole guide chain on a fake view, so the page
  now shows `Film: <name>`. That is likely why the reporter calls it the "film select screen" [I].
- So, as reported, Down is either the Film page's look step (`fm_down`) or the page change that draws page 1.

## What changed on this path from v0.31d to v0.32a [V]

Diff of `releases/v0.31d/edits.json` against `releases/v0.32a/edits.json`. Only these edits are new or changed on
the GUI side of this path:
- **Film step:** sl_pick's tail goes to `ls_pick` (slot +62/+63). The rest (fm_down → u_apply → lt_post → sl_pick →
  fm_post → ed_poke) is byte-identical to v0.31d.
- **Profile view page 1:** `sn_gd` (new). The guide word chain now starts with i18n_gd → xp_guide (both new), then
  ap_gd → ex_guide → ed_guide → stock 0x60decbfc as before.
- **Facade:** xp_get / xp_def / xp_cnt / xp_val / xp_av / xp_set (new). All of them pass straight through unless
  the editor is on the Extras page (axis 4).
- **Outside the GUI:**
  - split_tone in the LV/capture stage list. In v0.32a, S lives at L+2688, which is not camera-tested.
  - lv_grid OSD bitmaps, drawn only with Displayed Grid on.

## Ruled out (emulator, real v0.32a image, whole image mapped)

Scratch harnesses: `sn_chain.py` and `fm_step.py`/`fm_real.py`, not in the tree. The only stubs are the stock end of
the facade (GetValue 0x607f9549, GetDefault 0x607f964a, SetValue 0x607fa129), the facade getter 0x607f9062, the
manager 0x60827440 and the stock part's leaf calls (0x607af9ce, 0x60d17e22, 0x60d1be47, 0x60ea3a8d). `.data` is
mapped from its init image.

1. **sn_gd and the real guide chain** run from the site 0x60e2757d to 0x60e27589. Cases: axis 0–5, no editor
   marker, no LOOKS.BIN, ALL on and off, both Extras sub-pages with and without a stale cursor override, and
   COLOR1/3/4 (42 runs).
   - No fault in any run.
   - d0 = 2. d1, d2, d3, a1, a2, a3, sp and mdr are as at entry. The caller's frame is untouched apart from the
     74-B label.
   - Labels are as designed (`Film: Kodachrome`, `Saturation - All`, `1 Grain Off`, ...).
   - With a zeroed view and +128 = 1, the stock part reads only the facade and globals. It never reads a view
     pointer.
   - Stack use is 544 B below the writer. GUI_TASK has a 16 KB stack (ATLAS 0x60dd5067), so an overflow is
     implausible [I].
2. **The Film step, Up and Down**, from the COLOR record +12/+16 words through fm_up/fm_down → u_apply → sl_pick
   → ls_pick → fm_post → ed_poke. Full wraps in both directions on all four slots, with library_v2 (17 looks) and
   the release `LOOKS.BIN` (32 looks, 23 with split; L built as ls_chk leaves it).
   - No fault in any step.
   - The order is as designed: Down from Own goes to Stock (33), then skips the mono looks.
   - Slot +62/+63 always equals the look's stash bytes.
   - sp is back at its entry value after every step.
3. **Branches into the 12 hooked bytes [V]:** the only one is `bra 0x60e2757d` at 0x60e27567. Nothing lands inside
   the jmp.

## Not covered (where the cause must be, if v0.32 caused it)

- The stock work after `SetValue` in ed_poke, which is the view refresh. On this page it now redraws through
  sn_gd while the key handler is still running.
- The real stock facade and the leaf calls named above.
- The LV pipeline reacting to the new slot. A pick changes +62/+63 and st rebuilds S in the LOOKS block tail.
  That code is new in v0.32a and not camera-tested.
- lv_grid's bitmaps under an overlay, if Displayed Grid is on.

## Cheapest camera test (owner, E-P7 on v0.32a)

1. Reproduce codefist's steps exactly. Photograph the screen right after the Shortcut press, and note whether
   Displayed Grid is on.
2. If it crashes, repeat with **Up** instead of Down, and once with Displayed Grid **Off**. That separates the
   look step from a page redraw, and rules out lv_grid.
3. Move `EP7MOD/LOOKS.BIN` off the card, power-cycle, half-press and repeat. That removes the Film page, ls_pick
   and split tone; sn_gd still runs.
4. If it still crashes, rename `EP7MOD` and repeat. Now every hook only replays stock.
5. If step 3 or 4 still crashes, flash v0.31d and repeat. That tells whether v0.32 introduced it.

How to read it:
- **Step 3 stops the crash:** the look step or split tone is the cause.
- **Only step 4 stops it:** sn_gd or the other card-table layers.
- **v0.31d crashes too:** the cause is older than v0.32.
