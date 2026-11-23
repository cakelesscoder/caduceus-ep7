# Dial Function: ISO and flash comp on the front dial (issue #60)

Layer `patches/dial_func` (data only, no code). First built in the v0.35c test build; camera-tested by the owner
and released in v0.35.

## What it adds

Custom Menu B > Dial Function > P / A / S / M now has four choices per mode instead of two. The first two are unchanged
(in M they are the ones mdial gives). Both new choices keep the rear dial as it is and put something new on the front dial:

| Mode | Stock / existing | New |
|---|---|---|
| P | {EC, Ps}, {Ps, EC} | {Ps, ISO}, {Ps, flash comp} |
| A | {EC, FNo.}, {FNo., EC} | {FNo., ISO}, {FNo., flash comp} |
| S | {EC, Shutter}, {Shutter, EC} | {Shutter, ISO}, {Shutter, flash comp} |
| M | {Shutter, EC}, {Shutter, FNo.} (mdial) | {Shutter, ISO}, {Shutter, flash comp} |

Each pair is written {rear (main, sid 70/74/72/76), front (sub, sid 71/75/73/77)}, using the column order the popup
already has. The labels are stock strings: "ISO" (153) and the flash-comp icon `@A00A@` (525, from Shooting Menu 2).

## How it works [V code]

- The popup (screens 8/152..155, `Cursor_Move_Set_Mode_Actuator` on sid 70/74/72/76) walks the sid's validator record.
  The record is type 6, with 64-B elements `{u32 rear fn, u32 front fn, 0 x 14}` and an alt list of GUI codes
  (0x604ade64: P {11, 1}, A {12, 5}, S {13, 9}, M {4, 8}). Setting a value maps code → index through the alt list
  (0x602b9deb → 0x602b9f26; an unknown code falls back to index 0). Reading a value maps the element back to its index
  with memcmp (0x602b9e7e). Both work for any count (bytes / elem).
- The popup view (create 0x60e95999) has one 20-B record per mode in 0x611d714c: `{u16 param, u16 count, title, rear
  labels, front labels, guide}`. Labels are looked up by code (0x60df250b). The same view class has stock 7–9-entry
  records (params 6–9, the other bodies' per-dial lists), so longer lists are within its design.
- The dial routine 0x60cdc82c (via `ca_dial_function` 0x60cc8b23) treats the function value as a target sid.
  **ISO (6)** has its own branches for both dials (0x60cdc976 main, 0x60cdca2c sub). mdial's M-mode ISO runs through
  these, and phocean tested that on a camera. **Flash comp (17)** is in the dial rule table 0x60f38dd4
  `{86:68, 2:69, 4:70, 3:71, 17:72}` and takes the generic step path (rule check 0x60cce3dc, then step 0x60cddaec /
  0x60cdda80 of sid 17).
- Edits: one 1472-B data block in a dead sec-5 claim (0x607deb00–0x607df100). For each mode: the validator record's
  list, alt and byte count (128 → 256), and the view record's count (2 → 4) and two label-list pointers. There are no
  hooks, and mdial's bytes are untouched. For M, the layer copies the two elements and labels as the image has them, so
  it works with or without mdial.

## Not done, and why

- **EC in M with a contact lens.** mdial's stub turns front-dial EC into FNo. whenever a contact lens is fitted, and the
  E-P7 has two dials, so one of shutter or aperture would have to go. Doing this would need a change to mdial's rule
  (for example a separate code for "EC even with a lens"). That is left to a later round.
- **Manual flash power.** The E-P7 has no built-in flash (the pop-up flash in the request is an E-M10 feature). Manual
  power for a hot-shoe flash is not a dial function in the rule table.
- **ISO / flash comp on the rear dial, or WB / CWB Kelvin (fn 9 / 107)** on the dials: these are possible with the same
  mechanism but are not in this slice.

## Checks

`patches/dial_func/verify.py NEW.json [PKGDIR]`:
- S: the bytes that differ are all inside the 13 edits.
- E: in the emulator, the stock settings manager (hash build, count, code → element, element → index) runs 28 times
  over every code of the four sids, on both images.
- P: the package is stock plus the edits, and restore equals stock.

## Risks

- **UI.** The 4-row popup layout is not tested on the E-P7 (only 2-row lists are). A clipped or overlapping row would
  be a cosmetic problem only.
- **Flash comp on the dial** is not camera-proven. The rule engine may refuse sid 17 without a flash fitted. In that
  case the dial does nothing.
- **New stored values.** A new choice stores {rear, 6} or {rear, 17} in the dial setting. Firmware that doesn't know
  this pair (stock, or older Caduceus) shows the first choice in the menu, but the dial still follows the stored
  value until the Dial Function is set again.

## Camera test

1. Custom Menu B > Dial Function > P: the list shows 4 rows (Ps/EC rows plus Ps+ISO and Ps+flash-comp icon) and is
   drawn cleanly.
2. Pick Ps+ISO. In P, turn the front dial: ISO changes (the ISO display or overlay appears), and the rear dial still
   does program shift. Then pick Ps+flash comp: the front dial changes flash comp (check Shooting Menu 2's flash comp
   value), with and without a flash on the shoe.
3. Repeat for A, S and M. In M, test with a contact lens and with a lens without contacts (mdial: FNo. → ISO, EC → FNo.
   are unchanged).
4. Leave and re-enter the menu, and power-cycle: the choice sticks and the right row is highlighted.
5. Set each mode back to a stock choice. The dials return to stock behaviour.
