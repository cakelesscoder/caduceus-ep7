# Minimum shutter speed (ISO-Auto "Lowest S/S Setting") on the E-P7 1.1

Research 2026-11-09. m1 and m2 failed on camera; m3 showed the row but its value column overflowed. **Test m4 (`0.30m4`,
for 0.30b9)** is built and emulator-verified, not camera-tested, not committed.
Main CPU addresses (base `0x60020020`). [V] = read from code or bytes. [E] = run in the emulator. [I] = inference.
Our own analysis. Nothing from azqeurio's om-c-firmware is used ([OMC_FEATURES.md](OMC_FEATURES.md)).

## Verdict

**Stock has the feature, hidden.** The E-P7 1.1 keeps the whole OM "Lowest S/S Setting": the AE logic, two stock
settings, the "ISO-Auto Set" submenu and its speed picker. The Custom Menu row skips the submenu. This corrects
OMC_FEATURES ("no string or setting for it exists").

- **m1** pointed ISO-Auto Set at the OM submenu. **Camera: unusable.** "I ain't got no set button, and I can't get to
  that submenu." The OM submenu expects a SET key, and the E-P7 has only OK, the arrow pad and the dials.
- **m2** (0.30b7): **no row appeared.** It patched the page's row-info records, but not the list of rows the E-P7
  draws (§2b).
- **m3** (0.30b8) = m2 + the E1 row list. **The row appears**, but its 40-entry inline column runs off the screen.
- **m4** = m3, but OK opens the **stock Lowest S/S picker screen** (§2c) instead of the inline column.
- **m2** leaves ISO-Auto Set stock and adds **its own Custom Menu row, "Lowest S/S Setting", under ISO-Auto Set**,
  edited inline the same way ISO Step is. One setting (sid 1147): Auto, 1/1.3 … 1/8000. Data plus one in-place
  rewrite of the AE record builder; no new code path, no new setting.

## 1. What stock does

**Settings** [V]:

| Sid | Key | Validator | Initial | Meaning |
|---|---|---|---|---|
| 1146 | 0x5351 (u8) | record 1060 `0x604d1c5c`, {0, 1} | 0 | 0 = Auto, 1 = use 1147 |
| 1147 | 0x536a (s16) | record 1061 `0x604d1c70`, 55 values | 0 | Tv as APEX × 256: −1280 (30 s) to 3328 (1/8000), 1/3 EV steps |

Initial values are from the property init table at `0x600973dc` [V]. Both are ordinary registered properties, so they
are saved like other settings [I].

**AE** [V]:
- The AE settings record builder `0x6042777c` (called from `0x60427689`, record of 84 B) writes
  `+30 = (sid 1146 == 0) ? 0x7eee : sid 1147` (`0x604279c9..f5`). 0x7eee is the AE's general "unset" value.
- The predicate `0x603fe925` is true when the exposure mode byte +2 is 3, 4, 36 or 37 (P/A types; the help string 3068
  says "Valid in P or A mode"), the second struct's +2 is 0, +30 != 0x7eee, and `0x60420199(+38, +46)` is 0.
- Where it is true, the slow limit becomes `0x6020cf8a(+30, step)` instead of the stock hand-holding rule `0x603fc5d3`
  (`0x603fcca3`, `0x603fccc1`, `0x603fcd61`, `0x603fc64a`, `0x603fc7c0`, `0x603fea75`). `0x6020cf8a` snaps the value to
  the 1/3, 1/2 or 1 EV speed table.
- The stock rule `0x603fc5d3` gives a computed limit, adds 3 EV (+768) or 2 EV (+512) in some states, and never
  goes slower than Tv 5 (1280, about 1/30 s) [V code; reading of the inputs I]. One path (`0x603fcd5c`, a jump-table
  case) also caps the user value at Tv 5 [V], for a mode not identified [I].

**UI** [V]:
- Strings exist in every OSD language table: 3065 "Detailed settings for when ISO sensitivity is set to AUTO.",
  3066 "Upper Limit / Default", 3067 "Lowest S/S Setting", 3068 (help).
- Item-info page `0x7e` "ISO-Auto Set" (both trees, `0x611bd674` / `0x611cade0`): rows 112 (string 3066, no list) and
  1146 (string 3067, 56-entry list "Auto" + 55 speeds `0x611b9a10`).
- Cursor_2CNL kind **0xa8** (`0x6114c840`), rows from Cursor_Move mode 179 `0x6114fc7a` = **[112, 1146]**. Its OK table
  `0x6114585c`: row 112 → (8, `0x49`) and (1146, sub 1) → (8, `0x1aa`).
- Group 8 (state table `0x6119a31c`, 429 × 24 B `{state, type, param, viewer, sub, 0}`):
  - **0x18e** = type 4 (2CNL), kind 0xa8: the submenu;
  - 0x49 = type 0xd wizard 2: the stock High Limit / Default screen;
  - 0x1aa = type 5 list on sid 1147, with its own init `0x60de4f46` (Cursor_Move per-mode table `0x611517bc`).
- Value labels: the wizard viewers' page-0x7e functions (`0x60e8abc9`, `0x60e8da58`) show "Auto" for 1146 = 0, else
  the 1147 speed through the combined index `0x60ded18d` (list `0x611560a8`: {1146 = 0}, {1147 = −1280} …).
- Stock routes into 0x18e exist (kind 0x94 row 876, kind 0x11), but no E-P7 screen reaches them [V/I].
- **The gap:** the Custom Menu pages that hold ISO-Auto Set are 2CNL type-4 kinds 0x4b and 0x4c (items include ISO
  Step 141; OK rows 112, 239, 648, 273 …). Both OK tables (`0x6114882c`, 8 entries; `0x611488ec`, 7) send row 112
  to state **0x49**, so the submenu is skipped.
- Grey-out: 1146 has no condition entry (`0x60adf518`) and no rule-DB record (`0x6045e5fc`); CANEXEC `0x608290c8`
  then returns 0, not greyed [V]. Sids 51/53 took the same path and are camera-proven visible (v0.29).

## 2. Route (m2)

| Option | Verdict |
|---|---|
| OM submenu (m1) | Failed on camera: no SET key |
| OK on a new row → stock picker state 0x1aa | Not used: the picker sets 1147 only, and its label source is unknown |
| **New D1 row on sid 1147 with an inline value column**, the same mechanism as ISO Step / Noise Filter / Bulb Timer | **Chosen** |

**How a Custom Menu page works** [V]:
- Page entries are 20 B `{label, label ptr, rows, …, u16 page id, u16 count}`, in two trees: `0x6117ea4c` with rows
  `0x6117df2c`, and `0x61160fb0` with rows `0x61160430`.
- D1 "Exp/ISO/BULB" (id 0x13cc) has 7 rows in both trees, ending with ISO-Auto Set.
- A row is a 36-B record: `{u16 sid, u16 n, u32 n2, label, help, list, 0, list2}`.
- The page's 2CNL kind comes from `{kind, fn, page}` at `0x61158190`: D1 = 0x4b, D2 = 0x4c.
- The kind's **items** list (`0x6114ae6c`, shared by both kinds, 10 entries) names the rows that open an inline value
  column (64, 141, 143, 173, 35 …). Its OK table names the rows that open a screen.

**Storage, and making a speed "on":** a single setting, sid 1147. The builder at `0x604279c9` used to read
`1146 ? 1147 : 0x7eee`. It now reads `1147 == 0 ? 0x7eee : 1147`, so Auto = value 0 (Tv 0 = 1 s, which is dropped from
the list) and any speed is on. 1147 starts at 0, so a fresh flash behaves as stock. Stock firmware still gates on 1146,
which is still 0, so a downgrade behaves as stock.

## 2b. Which rows the E-P7 draws (found after m2)

Custom Menu pages are Cursor_2CNL type-4 kinds. A page's rows come from its **column** [V]:
- Column mode → init table `0x61150c2c` (`{u16 mode, fn}`): modes 87..116 → **0x60de276f**.
- That reads `0x61150bb4` (`{u16 mode, u16 n, ptr}`) → a record `{u16 key 0, u16 count, u32 list}`. It copies the u16
  list (`0x47001052`), then CANEXEC only greys rows. There is **no per-model hide.**
- The lists are in RAM .data. The init image is RAM − 0x01d67d40: per LOOK_EDITOR, 0x61fc27d0 ← **0x6025aa90**. The
  guide's word 0x6025aa98 is part 3, +8. Using +8 by mistake gives plausible but wrong lists. That was the m2
  mistake [V: the stock readers below return the right lists only with this delta].
- E-P7 lists [V, E]:

  | Mode | Kind | Page rows |
  |---|---|---|
  | 87 | | AEL/AFL, Face Priority, MF Assist, Reset Lens |
  | 90 | | Button Function, 1465, Dial Function |
  | 91 | | Control / Info Settings, LV Boost, Flicker, Grid, Peaking |
  | **93** | **0x4b** | **[273 Exposure Shift, 112 ISO-Auto Set, 143 Noise Filter, 35 Noise Reduct.]** = E1 |
  | 94 | 0x4c | [173, 435, 436, 648] (Bulb / Composite) |

- Row info (label, help, value list) for a row id comes from the 36-B records of page 0x13cc (kind 0x4b's page,
  `0x61158190`). These records are a superset (273, 64, 143, 173, 35, 141, 112), which is where m2 put 1147. The
  `0x6117a240` / `0x6117b278` label sets are per model and don't decide the rows.

**m3:** record `0x61150b7c` count 4 → 5, list → a read-only copy `[273, 112, 1147, 143, 35]` (`0x601deef4`). The
builder only copies from it, and the other readers (`0x60de2ef0`, `0x60de2eb8`, the all-grey check `0x60ddc451`) only
read.

**Fallback, not built:** repoint an existing E1 row instead of adding one. Change one u16 in the .data init list
(e.g. `0x6025a1fe` 273 Exposure Shift → 1147), keep everything else from m2, and leave the count unchanged. That
costs the replaced row.

## 2c. The stock picker screen (m4)

- Group-8 state **0x1aa** = type 5 (a set-mode list), sid 1147, viewer 0x19. That is the generic scrolling list viewer
  ISO-Auto's picker (0x4a) also uses, as do 118 states. Field 4 = 0x75 indexes the viewer label table `0x611dc8c4`
  (120 × 24 B `{idx, title, n, labels, help, …}`). Entry 0x75 (`0x611dd314`) [V]:
  - title {4, 3067 "Lowest S/S Setting"};
  - **55 stock labels** `0x611d8b24` keyed by Tv (30'' … 1/8000, kind 5);
  - help 3068.
  Cursor_Move mode 426 init `0x60de4f46` = the default list init (facade count/values, our 40) + a commit refresh.
- m4 edits:
  - both OK tables of kinds 0x4b / 0x4c → copies with `{1, 1147, 0, 8, 0x1aa, 0}` appended;
  - the items lists are stock again;
  - the picker's value-0 label "1''" → {4, 71 "Auto"} (`0x611d8bdc`).
- m4 tests [E]:
  - **K**: the native router gives row 1147 → (8, 0x1aa), and all 23 stock entries are unchanged. All 40 values have a
    picker label: Auto, then "1/x".
  - R, B, A, V, D and P as m3.

## 3. As built: m2 parts (kept in m3, `patches/min_ss`)

`build.py` `apply(spec, version)`. `patches/v030/build.py` applies it right after v0.29a, and it composes there with
ap_custom and live_nd. It checks every stock source, then edits:
- **Data, 1188 B at `0x601dea50`** (dead EVF tables, [CODE_SPACE_MAP.md](CODE_SPACE_MAP.md) "min_ss"):
  - the 1147 label list: 40 × `{value, label}`, with 0 = string 71 "Auto" and the speeds as kind-5 texts reused from the
    stock flash Slow Limit list (1/1.3..1/400) and the item-info list (1/500..1/8000);
  - the items list + 1147;
  - both trees' D1 rows (7 stock records + `{1147, 40, 40, "Lowest S/S Setting" 3067, help 3068, list, 0, list}`).
- **Page entries:** rows pointer → the copy, and count 7 → 8 (both trees).
- **Kinds 0x4b / 0x4c:** items pointer → the copy, count 10 → 11.
- **Validator record 1061:** list `0x604cc34c` → `0x604cc36a` (the stock list from value 0), 110 → 80 bytes.
- **Builder `0x604279c9..f5`:** 19 nops, then `mov 0x536a,d0; mov (0x622a0ba4),a0; clr d1; call 0x6005e971,[d2,d3],12;
  exthu d0; cmp 0,d0; bne +5; mov 0x7eee,d0`, falling through into the stock `movhu d0,(30,a3)`. There are no branches
  into the range from outside (xref).
- The fw_version label.

`verify.py` [E], on the image decoded from the package:
- **B:** the patched builder (getter stubbed) gives +30 = 0x7eee for 1147 = 0 and the speed otherwise, whatever 1146
  holds. The stock builder with 1146 = 0 also gives 0x7eee, so Auto == stock.
- **A:** the predicate is 0 for 0x7eee and 1 for a speed.
- **V:** the native validator for 1147 lists [0, 85 … 3328] (40 values); 1140–1150, 174, 112 and 239 are unchanged.
- **D:** pages, rows, items, labels and alignment.
- **R** (m3): the native readers `0x60de2ef0` / `0x60de2eb8` for mode 93 give stock [273, 112, 143, 35] (RAM seeded
  from the init image) and patched [273, 112, 1147, 143, 35]; the other page modes are unchanged.
- **L** label; **P** anti-brick: decoded == stock + edits, restore == stock, only our 1256 B differ from v0.29a.
  45/45 + 30 checks.

Output m4: `generated/min_ss/m4/edits.json`, package `generated/min_ss/m4/rel/` (`patched.pkg.bin` SHA-256
`a550bc66f60fe59635fb393aef220f3fd7d587387719ba7fc466ac622569d505`, restore
`963f4dfe560e29216862c96284c92225f49977fd831a2ed60fa3ebbddf6d2327`). m1–m3 (`generated/min_ss/rel/`, `m2/`, `m3/`) are withdrawn.

## 4. Camera test (m4)

1. It boots, and the Firmware screen shows the version.
2. Custom Menu D1 (Exp/ISO/BULB): "Lowest S/S Setting" appears under ISO-Auto Set and reads Auto. ISO-Auto Set still opens its wizard.
3. OK on the row opens a full "Lowest S/S Setting" picker screen that scrolls with up/down (Auto, 1/1.3 … 1/8000).
   OK on 1/250 returns to E1, and the row reads 1/250. Check that 1/8000 and Auto are reachable, and that MENU / back
   leaves the picker.
4. In P and A with ISO-Auto in a dim scene: Auto behaves as stock. With 1/250 the shutter stays at 1/250 or faster and
   ISO rises first; with 1/8 the shutter goes slower before ISO rises. S and M are unaffected.
5. The value survives a power cycle. D2 and the rest of the Custom Menu are unchanged.

## 5. Open risks

- **The inline column isn't emulated** (the emulator doesn't run the screen stack). It is the same mechanism as the
  D1 rows next to it, but a 40-entry column is longer than theirs (Slow Limit has 42 in D2, through its own path).
- **Which row-info tree is live is unknown**, so both are patched. If the row appears without its label or list, the
  row-info lookup is somewhere else.
- **The stock picker (0x1aa) has never been drawn on an E-P7.** Its viewer and init are shared with ISO-Auto's picker,
  but its OK/back routing and the commit refresh (`0x60de9834`) are untested. Worst case is a stuck screen, recoverable
  by power cycle. Fallback: option (c), a short inline list of about 8 values (validator sub-list + labels).
- **The AE rewrite runs on every exposure update.** It is emulated for every value, and the stock-shaped call keeps
  the same frame.
- One AE path caps the user value at about 1/30 s, for a mode not identified (§1).
