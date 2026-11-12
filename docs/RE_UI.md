# UI framework: state machine, screens, menus, key routing (E-P7 1.1)

Round R3b (docs/RE_ROUNDS.md). Static analysis of the stock main image only: no build, no camera, no patch.

- **[V]** = read from bytes (`tools/dis.sh`, table dumps) or a decompile of the function named. **[I]** = inference.
- Addresses are E-P7 1.1 main CPU addresses. RAM .data words have a flash init image at RAM − 0x01d67d40.
- Decompiler output and dumps behind this note: `~/ep7fw-private/decomp/ui/` (`d*.c`, `pages_all.md`,
  `act_kinds.txt`, `view_kinds.txt`, `tools/`). Nothing decompiled is copied here.
- New symbols: `tools/atlas/new_ui.py`. Builds on ATLAS §4 and RE_DRAW_PLUGIN (not repeated).

## 1. Short answers

| Question | Answer |
|---|---|
| Screen stack? | **No generic screen stack.** Navigation is a two-level **hierarchical state machine** (HSM: 19 sub-machines "Ss…", each with its own states). A state's **entry** function creates its screen(s), its **exit** destroys them. Menus add two private stacks: the 10-deep menu history (`userGuiDbMenu`) and the 2CNL actuator's own column depth (1 or 2). [V] |
| What is a "screen"? | An `IGui_Controler` (228 B): one **actuator** (input + model) and one **viewer** (drawing), picked by kind from factory tables. Screens are found by **(group, key)** in a 13-group table. [V] |
| Menu tree | Main menu = screen (15, 0): a tab column + a `Cursor_2CNL` actuator per tab (2CNL kinds 62–68). Every sub-page is another 2CNL record (156 × 36 B at 0x6114b2e0) whose rows come from a column-mode list. Rows link onward through 24-B transition entries `{depth, item, sub, fn, group, key, fn2}`. [V] |
| Item kinds | Not a field: a row's behaviour is set by which table names it. Inline value column (list A), open another screen (group 8 popup, 14 sub-page, 15 Custom Menu, 18 editor, 29 wizard…), or call a function (fn in the transition). §4.5. [V] |
| Binding to sids | The row id **is** the sid for setting rows. Ids ≥ 3000 / 5000 / 10000 are virtual rows (submenus, actions, Reset 10003). Values, counts and allowed values come through the facade (ATLAS §4). [V] |
| Grey-out | Each row id → CANEXEC (0x607b3c32 → 0x6082686f → `app_check_mode` 0x608290c8): 611-row condition table + predicate table, else the rule engine. Hidden rows are simply absent from the per-model row list. [V] |
| Key routing | Input layer posts 0x90xx messages → GUI queue (500 × 32 B) → `gui_WinMain` → HSM dispatch (current Ss/state × event → handler) → handler calls `screen_event` on the screen it owns → actuator vtable slot by key → per-instance handler words. Return codes go back up. §5. [V] |
| SCP / Live Control | Both are states of **SsMenuLv** (Ss 4): state 2 = Live Control (screen (20, 0)), state 3 = SCP (controller kind 10 → `Func_Scp_Actuator`). A cell's OK goes to state 7, which opens the group-18 editor keyed by the cell's sid. §6. [V] |
| New "Caduceus" page? | **Feasible, mostly data, risk M.** Add one virtual row to a tab, one transition to a new (14, key) screen, reuse a 2CNL record, a column-mode slot and an item-info slot that the E-P7 never shows. Value pickers reuse stock kinds on real sids; a custom action is one fn word in a transition. Several table bounds are hard-coded, so **repurpose, don't append**. §7. |

## 2. The state machine (HSM)

### 2.1 Engine [V]

- Context (32 B, RAM **0x6246684c**, pointer in 0x61fb2564): `+0 u8 ss`, `+1 u8 state`, `+2 u8 n_ss` (19),
  `+4 ss table`, `+8 u16 current handler index` (0xffff idle), `+0x10/+0x14/+0x18` engine fn pointers.
  Init 0x60d113d1 (called from 0x60dd4b19 with ss 1, state 2, table 0x611317c4) runs the first state's entry.
- Ss table **0x611317c4**: 19 × u32 descriptor pointer, indexed ss − 1.
- Descriptor (32 B): `+0 u8 n_states`, `+2 u16 n_events`, `+4 u16 n_handlers`, `+6 s16 n_map`, `+8 matrix`,
  `+0xc handler words`, `+0x10 event map {u32 code, u32 index}`, `+0x14 entry fn[n_states]`,
  `+0x18 exit fn[n_states]`, `+0x1c u8 wide` (0 = u8 matrix, else u16).
- Dispatch **0x60d1144d** (call-site entry; prologue at 0x60d11448 = atlas `ssmenulv_dispatch`): event → index
  through the map (0x60d1158b, linear) → `handler = words[matrix[index·n_states + state − 1]]` →
  `rc = handler(event, lparam, ctx, uparam)`. **rc = (new_ss << 8) | new_state**; 0 = stay. On a change:
  old state's exit, store ss/state, new state's entry (looked up in the *new* ss's descriptor).
- Every descriptor's default handler (matrix byte 1 in all states) is 0x60dd4b47, a no-op. So an event a
  state doesn't list is dropped, not forwarded [V tables, I for "no-op" from its 4-byte body].
- `gui_WinMain` 0x60cfd311 logs every transition through 0x60e9e771 ("Event 0x%04x: [ss][state]-->[ss][state]").

### 2.2 Sub-machines [V descriptor + strings in their handlers]

| ss | Descriptor | States | Events | Name (from handler strings) |
|---|---|---|---|---|
| 1 | 0x611992c4 | 14 | 89 | SsCommon (power, black screen, battery, scene select) |
| 2 | 0x611ada58 | 5 | 47 | SsRec (shooting, direct-key value set) |
| 3 | 0x611a6410 | 13 | 77 | **SsMenuMain** (state 1 menu, 2 StWizardMenu, …) |
| 4 | 0x611a3bc8 | 29 | 112 | **SsMenuLv** (2 Live Control, 3 SCP, 7 setting screen, 15–28 ART/SCN/movie-mode pickers) |
| 5 | 0x611a7738 | 2 | 2 | ? |
| 6 | 0x611abc5c | 43 | 109 | SsPlaySingle |
| 7 | 0x611a9d44 | 30 | 81 | SsPlayMovieSlide |
| 8 | 0x611a82f4 | 18 | 88 | SsPlayIndex |
| 9 | 0x611ae24c | 9 | 14 | ? |
| 10 | 0x611a0198 | 4 | 10 | SsDebugMenuColor |
| 11 | 0x611af2b4 | 6 | 24 | SsUsbConnect |
| 12, 13 | 0x611a7780, 0x61196490 | 2, 1 | 2, 26 | ? |
| 14 | 0x611a0ac4 | 26 | 33 | ? |
| 15 | 0x61198904 | 35 | 24 | SsBtSend |
| 16 | 0x61196a78 | 19 | 36 | SsBtReceive [I: its entry strings sit just before the descriptor] |
| 17 | 0x611a22ac | 3 | 66 | SsMenu (MENU key entry, initial-settings sequence) |
| 18 | 0x611a1f48 | 9 | 67 | SsEdit |
| 19 | 0x611aecd8 | 7 | 84 | SsShortMovie |

Full per-state handler lists: `~/ep7fw-private/decomp/ui/tools/ssdump.py <ss> v`.

### 2.3 Messages and the GUI task [V]

- Queue: ring of **500 × 32 B** at 0x62466870 (`+0 u8 used`, `+4` message: 7 words), head/tail u16
  0x6246a6f0/0x6246a6f2. Get 0x60d10133 serves 0x1002 and 0x1100 first. Purge-by-code 0x60d1050a.
- Post **0x60d0ffb4** (code, lparam, …, a 28-B message, sender 0xfffe); 61 callers, most in the input layer
  0x60d1d9ec–0x60d25a02 [I: that range converts key/dial input].
- `gui_WinMain` loop: code < 0x8000 = system message (handled outside the HSM); code ≥ 0x8000 → event trace
  ring 0x60e9eb89 (not for 0x9b02; it records, it doesn't filter) → 0x60e9fa88 (returns 1 to skip dispatch;
  "MODE_HDMI_INFO" log, [I] HDMI-info mode) → HSM dispatch with (code, lparam, ctx, uparam).
- A handler that wants another key later posts it (0x60d0ffb4) or arms a GUI timer (0x60ea15a3 id, ticks;
  cancel 0x60ea15ca) [I: from call patterns, e.g. 2CNL OK arms timer 0x20a].

## 3. Screens: controller, actuator, viewer

### 3.1 The screen object `IGui_Controler` (228 B) [V: 0x60e4cb5a, 0x60e4c9a0, 0x60e4d032]

| Off | Field |
|---|---|
| +0 | actuator* (0 = none) |
| +4 | viewer* |
| +8 | actuator kind (0x35 = none) |
| +12 | viewer kind (0x87 = none) |
| +16 | layout id (0x2d default) |
| +20 | 8-B binding `{actuator*, u16 viewer param}` handed to the viewer |
| +24 | optional descriptor hook (word 5 of the screen descriptor) |
| +28/+32 | optional pre-event callback (pointer-to-member pair) |

Ways to make one:

| Function | Use |
|---|---|
| **`screen_open` 0x60e4cea8** (group, key) | 64 call sites. Finds the group in **0x6119fadc** (13 × 12 B `{u32 group, u32 list, u16 n}`), the key in the group's 24-B descriptors, allocs 228 B, builds via 0x60e4cb5a |
| 0x60e4cf21 (group, key, arg, arg) | Same with extra args (build 0x60e4cc53, alt factories) |
| 0x60e4cfa8 | Same, key read through a pointer (build 0x60e4cd2d) |
| **`IGui_Controler::IGui_Controler` 0x60e4c9a0** (controller kind, args) | Controller kind → layout id (0x6119a0b0 `{kind, layout}` until 0x20, or a RAM resolver pair at 0x61fc4198 + 8·kind) → **layout table 0x6119a100** (45 × 12 B `{layout, actuator kind, viewer kind}`). Wrapper with alloc: 0x60e4ce8b |
| `screen_close` 0x60e4ce26 (61 callers) | Frees binding, calls actuator vtbl +0x28 (dtor) and viewer vtbl +4 (dtor) |
| `screen_event` **0x60e4d032** (event, lparam, screen) | 179 callers. See §5 |
| 0x60e4d144 / 0x60e4d157 | Actuator vtbl +4 (current item id) / +0x10 (id of item n) |
| `screen_next` 0x60e4d16c (&key, &type, screen) | Pending open request (0x60dd5110 → 0x61fc1bb0/0x61fc1bb2); type 0x20 = none |

**Screen descriptor (24 B):** `{u32 key, u32 actuator kind, u32 actuator param, u32 viewer kind, u32 viewer param, u32 hook fn}` [V].

| Group | List | n | Content (actuator kind / viewer kind) [V counts, I roles] |
|---|---|---|---|
| 3 | 0x6119d7fc | 17 | viewer only (53 / 8) |
| **8** | 0x6119a31c | 429 | **popups**: value pickers (5 / 25, 30, 56, 122: 164), 4 / 54, 55 (78), 6 / 72, 32 / 30, 13 / 36, 101, 51 / 129 (Select_Shooting_Menu) |
| **14** | 0x6119cb54 | 132 | **menu sub-pages**: `Cursor_2CNL` (21 / 49, a few 80, 52, 60, 123); actuator param = 2CNL kind, viewer param = item-info key (§4.4) |
| 15 | 0x6119d7b4 | 3 | key 0 **main menu** (24 / 57 Menu_Viewer); keys 1, 2 Custom Menu (25 / 58) |
| 16, 17 | 0x6119d994, 0x6119d9c4 | 2, 13 | viewer only |
| **18** | 0x6119dafc | 257 | **setting editors, key = sid** (26 `Plural_Direct` / 63, 131, 36, 120, 89 (Color Profile view), 96 …). Opened from SCP/LC (§6) |
| 20 | 0x6119f314 | 1 | **Live Control** (27 `Plural_Lv_Control` / 64 `Lv_Control_Mode_Viewer`) |
| 21 | 0x6119f32c | 1 | 28 / 67 |
| 26–29 | 0x6119f344.. | 11, 3, 7, 60 | wizards, play, misc (34–48 / 90–118) |

### 3.2 Actuators [V]

- Factory `act_create` **0x60dd5146** (kind): table **0x611401f4**, 45 × `{u32 kind, fn create}`. After create it
  sends **0xf805** (init) to the new actuator. Alt factories: 0x60dd51cb (table 0x611403bc, 4), **column
  factory** 0x60dd518e (table 0x6114035c, 12) and 0x60dd520c (table 0x611403dc, 5), used for actuators that live
  inside another actuator.
- Base (0x60dd5083 ctor, size per class): vtable `[0]` **0x60dd5250** (shared event entry), `[1]` current id,
  `[2..9]` getters (defaults return 0 / 1), `[10]` (+0x28) dtor, `[11]` +44 Up, `[12]` +48 Down, `[13]` +52 Left,
  `[14]` +56 Right, `[15]` +60 dial 0x9032, `[16]` +64 dial 0x9031, `[17]` **+68 everything else**.
- Base event entry 0x60dd5250: stores event at +24, lparam at +28; hashes `event − 0x9003` in **0x6114040c**
  (16 × `{key, stub}`) to a stub that calls the per-key slot above, or slot +68. A key grab word **0x61fc1bac**
  (non-zero = only that event gets through) supports press/release pairs; odd codes (releases 0x9005..0x9017)
  clear it and post 0xf802.

| Kind | Create | Vtable | Class (from method strings) |
|---|---|---|---|
| 3 | 0x60df002e | 0x61159ea8 | `Direct_Actuator` |
| 4 | 0x60dde1b4 | 0x6114f7e4 | ? (also column kind 1: the main-menu tab column) |
| **5** | 0x60de33a7 | **0x61155a7c** | **`Cursor_Move_Set_Mode_Actuator`** (one setting's value list; = ATLAS "property child") |
| 8 / 9 | 0x60df0591 / 0x60df05c1 | 0x6115ba70 | `Func_Scp_Actuator` (Detail SCP / RC SCP) |
| 15 | 0x60dd5923 | 0x611431a4 | `AF_Target_Actuator` |
| **21** | 0x60dda3fd | **0x6114d1a8** | **`Cursor_2CNL_Actuator`** (two-column list page) |
| **24** | 0x60e0e7b4 | 0x61179560 | main-menu actuator [I name]: tab column + one 2CNL per tab |
| 25 | 0x60ded5f4 | 0x61158274 | `Custom_Menu_Actuator` |
| **26** | 0x60e2054e | **0x61187534** | **`Plural_Direct_Actuator`** (= ATLAS editor parent; COLOR1–4 wheels) |
| 27 | 0x60e23b98 | 0x611875f4 | `Plural_Lv_Control_Actuator` |
| 29 / 30 | 0x60e24ea3 / 0x60e243c4 | 0x61188248 / 0x61187d04 | `Plural_Photo_Session(_Detail)_Actuator` |
| 43 | 0x60e42c35 | 0x61195d90 | `Short_Movie_Index_Actuator` |
| 45 | 0x60e2808f | 0x6118a390 | `Progress_Bar_Actuator` |
| 51 | 0x60e3eb72 | 0x611928f8 | `Select_Shooting_Menu_Actuator` |

Others (0, 2, 6, 12–14, 16, 20, 23, 28, 31–42, 44, 46–50, 52) are listed with create/vtable in
`~/ep7fw-private/decomp/ui/act_kinds.txt`; names unknown.

Column kinds (0x60dd518e): 0 `Cursor_Move_Set_Mode`, 1 kind-4 class, 2 ?, 3 / 4 `Cursor_Move` column
(0x5c B, vtable 0x61150e0c; 3 = plain mode list, 4 = per-model list, see §4.3), 5 / 6 `Cursor_2CNL`,
7 `Plural_Direct`, 8 `AF_Target`, 9 kind-6 class, 10 kind-13 class, 14 `Direct` [V table, I names via the
matching main factory entries].

### 3.3 Viewers [V]

- Factory `view_create` **0x60df249e** (kind): table **0x6115c724**, 126 × `{u32 kind, fn create}`.
  Vtable `[0]` update/draw (called after any actuator rc 1), `[1]` dtor. Drawing itself: RE_DRAW_PLUGIN.
- Known: 57 `Menu_Viewer` (vtable 0x6117efc8, reads root 0x6117b410), 58 Custom Menu viewer (0x611613fc),
  64 `Lv_Control_Mode_Viewer` (0x611773d0), 89 Color Profile view (0x61155e14, ATLAS), 129
  `Select_Shooting_Menu_Viewer`. Kind 49 (0x60e8c4a2, vtables 0x611d2ec8/0x611d1e54) draws the 2CNL pages and reads
  the item-info index (§4.4) [I: by the 0x60e89a28 reader in that class's range].
- Full list: `~/ep7fw-private/decomp/ui/view_kinds.txt`.

## 4. Menu tree

### 4.1 Main menu (screen (15, 0)) [V]

- **Actuator kind 24** (68 B, vtable 0x61179560): `+0x34` tab column (column kind 1, mode 22), `+0x38` item
  column = a **`Cursor_2CNL` actuator for the current tab** (0x60e0f2cb: column kind 5, 2CNL kind from
  **0x611794a8**, 7 × `{u16 tab, u32 2CNL kind}` = 62..68), `+0x3e` focus (0 tabs, 1 items). Up/Down go to the
  focused column (and skip rows whose id is −1); Right/OK on a tab moves focus in; a child rc 3 moves it back.
  Dials (vtbl +60/+64) become Left/Right after reading sid 170 (0xaa). Other events: table 0x611794e0, else the
  focused column.
- **Viewer kind 57 `Menu_Viewer`** (ctor 0x60e0f9e3) reads the root **0x6117b410** (`{u16 0, u16 n_tabs 7}` then):

| Root off | Content |
|---|---|
| +4 | tab titles 0x6117b308: 7 × `{u32 tab, label}` (Shooting Menu 1, Shooting Menu 2, Video, Playback, Custom, Accessory Port, Setup) |
| +8 | Custom Menu sub-menu titles 0x6117b278: 12 × `{u32 row id 3324.., label}` |
| +12 | tab help texts 0x6117b35c: 7 × `{u32 tab, label}` |
| +16 | **pages 0x6117b1b4**: 7 × 28 B `{u16 tab, u16 n, items, helps, ndesc, desc[], n2, x}` (LOOK_MENUS §2 #5) |
| +20 | guide-bar labels 0x6117b3b0: 12 × 8-B label source |
| +24.. | 7 × `{s32 −7..−1, label}` [I: tab icons] |

- The **rows** a tab shows come from its 2CNL kind's column (§4.3), not from the page record. The page record
  supplies each row's label, help and value-column descriptor by id. A row in the column but not in the page
  record has no label [I]; a page entry with no column row is never shown [I: Shooting Menu 1's page record has
  10 ids, column mode 80 lists 5; see §8.1].

### 4.2 `Cursor_2CNL` page records (156 × 36 B at **0x6114b2e0**) [V]

`{u32 kind, u32 column kind, u32 column mode, u32 listA, u16 nA, u32 listB, u16 nB, u32 listC, u16 nC}`
(u16 counts in u32 slots). Lookup is linear by `kind` with a **hard-coded bound 0x9c (156)** in 0x60dda6a0 and
0x60dda760.

Actuator object (0x88 B, ctor 0x60dda522 / 0x60dda561): `+0x30..+0x48` per-instance handler words, `+0x4c`
kind, `+0x50` depth (1 = first column, 2 = second column open), `+0x54` second-column kind, `+0x58` column 1,
`+0x5c` column 2, `+0x60/+0x64` listA/nA, `+0x68/+0x6c` listB/nB, `+0x70/+0x74` listC/nC, `+0x7c/+0x80` last
transition fns, `+0x84` arg.

- `Cursor_2CNL_Actuator::Initialize` 0x60dda5cf: copies 7 handler words from **RAM 0x61fc1c00** (flash image
  0x60259ec0: Up 0x60ddab47, Down 0x60ddac5f, Left 0x60ddad77, Right 0x60ddaee9, dial 0x60ddb06d,
  dial 0x60ddb0de, other 0x60ddb14e → `invidual_act_base` 0x60ddb150), then runs a per-kind init from
  **0x6114569c** (35 × `{u16 kind, fn}`; kinds 62–94 → 0x60dda760, which also sets `+0x48` = 0x60ddb908) or the
  default 0x60dda6a0. Both build column 1 with the column factory from `{column kind, column mode}`.
- **Right** (0x60ddaee9): listB transition (below); if none and depth 1, a **listA** entry for the row opens
  column 2 inline (depth 2). **OK** (`invidual_act_base` → table 0x6114d028 → 0x60ddb1c2): listC transition;
  if none, OK goes to the active column and the page returns 2. **Left / MENU** (0x60ddad77 / 0x60ddb3c1): at
  depth 2 close column 2 (rc 1); at depth 1 return 3 (back to the parent).

**Transition entry (listB / listC, 24 B)** [V: 0x60ddc1f1]:

| Off | Field |
|---|---|
| +0 | u32 depth (1 or 2) |
| +4 | u16 row id (column 1 current id) |
| +6 | u16 sub id (column 2 current id, 0 at depth 1) |
| +8 | fn pre (optional): `rc = fn(fn, row id, actuator)`; rc ≠ 4 ends here with that rc |
| +12 | u16 open **group** (8, 14, 15, 29, …) |
| +16 | u16 open **key** |
| +20 | fn post (optional): computes `(group, key)` into two u16 outs instead of +12/+16 |

A match with an open sets the request (0x60dd5125 → 0x61fc1bb0 group, 0x61fc1bb2 key) and returns **4**; the
owning state reads it with `screen_next` and opens that screen. Groups used: 8 (691 entries), 14 (241),
15 (30), 29 (6), 19 (2), 16, 3, 0 (1 each).

**listA entry (12 B):** `{u32 column kind (0: 263 entries, 1: 53), u16 row id, u16 param, fn (optional)}` →
second column built by the column factory; column kind 0 = `Cursor_Move_Set_Mode` on the row's sid, i.e. the
inline value list [V layout, I for "param" = column mode].

### 4.3 Where a column's rows come from [V]

`Cursor_Move` column init 0x60de2134: per-mode init table **0x61150c2c** (41 × `{u16 mode, fn}`), else the
default 0x60de21b0 (150 × 12 B `{u32 mode, u32 u16-list, u16 n}` at **0x61150328**, bound 0x96).

| Modes | Init | Row source |
|---|---|---|
| 80–86 (the 7 tabs) | 0x60de2628 | **0x61150af4**: 7 × `{u16 mode, u16 n, ptr}` → records `{u16 key, u16 n, u32 list}`; the **key 0** record is used. Flash lists 0x61150a30.. |
| 87–116 (Custom Menu pages) | 0x60de276f | **0x61150bb4**: 15 × 8 B, same shape; lists are in **RAM .data** (0x61fc1dcc..), see MIN_SHUTTER §2b |
| 9–24 | 0x60de2878 | 0x6114ff04 (12 × 32 B; reads a sid to pick) else 0x61150328 |
| 8, 29, 138 | 0x60de2461 / 0x60de258e / 0x60de2abe | special |
| others | 0x60de21b0 | 0x61150328 |

Then per row: id remap **0x61150d74** (`{u16 id, fn}` until 3200; 10 → 0x60de2e70, 111 → 0x60de2e9b), then
**CANEXEC** (`0x607b3c32()->vtbl[0](id) == 1` → enabled, else grey flag). The column keeps `+0x48` n, `+0x4a`
first enabled, `+0x4c` grey flags, `+0x50` ids, `+0x54/+0x56` first/last enabled. Mode 42 (Button Function)
special case for 2CNL-kind sub-modes 9–13 in the default init.

### 4.4 Labels and value lists of 2CNL rows (item-info) [V]

- Index **0x611c2c78**: 129 × 24 B `{u32 key, u32 records, u32 n, u32 0, u32 ?, u32 ?}`, scanned by the kind-49
  viewer (0x60e89a28, bound 129). **key = the screen descriptor's viewer param** (e.g. Button Function screen
  (14, 46): viewer param 33 → index key 0x21 → records 0x611bf6ec, 17 rows 47, 49, 48, 571 …).
- Record (36 B): `{u32 row id, label title (8 B), u32 row value list, u16 n, u32 0, u32 text, u32 popup value
  list, u16 n}`. Value lists are the usual 12-B `{u32 value, label}` (ATLAS §4). A second tree with the same
  shape (0x611cce58.., e.g. 0x611cc96c for sid 267) exists; live_nd edited both (CODE_SPACE_MAP). Which tree the
  E-P7 reads is [I: both edited and the camera result held].

### 4.5 Item kinds (what a row does) [V tables, I names]

| Kind | How it is declared | What happens | Stock example |
|---|---|---|---|
| Setting, inline value column | listA `{0, sid, …}` | Right opens column 2 = `Cursor_Move_Set_Mode` on the sid (count / value-by-index / available through the facade); OK sets | Shooting Menu 1: 34 Digital Tele, 685 Keystone, 1, 1038 AF Illuminator |
| Setting, popup picker | listB/C `{1, sid, 0, 0, 8, key}` | opens group-8 screen `key` (usually actuator 5 + a list viewer) | 270 Image Aspect → (8, 26); Button Function rows → (8, 199..) |
| Sub-page | `{1, id, 0, 0, 14, key}` | opens another 2CNL page | 10 quality → (14, 29); 5010 → (14, 78) |
| Conditional sub-page | `fn pre` + `{…, 14, key}` | fn decides (rc 4 = go) | 111 Picture Mode → fn 0x60ddc529, (14, 5) or (14, 103) |
| Custom Menu letter | fn 0x60ddc3c1 + (15, 1) | fn picks the letter's page, (15, 1) = `Custom_Menu_Actuator` | rows 3324.. on tab 66 |
| Action / special screen | fn and/or group 8 / 29 / 16 / 19 / 3 | runs code, or opens a wizard / confirm screen | 10003 Reset → (8, 133) |
| Direct editor | group-18 screen keyed by sid | `Plural_Direct` children (wheel, sliders) | COLOR1–4 wheels (ATLAS §4) |

Row ids: real sids (< 1769) bind to the settings store; virtual ids 3000+ / 5000+ / 10003 have no storage and
exist only in these tables, CANEXEC rows and labels [V for ids, I for "no storage" beyond sid 1768].

## 5. Key and dial routing

```
input layer (0x60d1d9ec..0x60d25a02) --post 0x60d0ffb4--> GUI queue 0x62466870 (500 x 32 B)
  gui_WinMain 0x60cfd311: get 0x60d10133 -> trace 0x60e9eb89 -> skip? 0x60e9fa88
    HSM dispatch 0x60d1144d: map event -> matrix[ss][state] -> state handler (rc = new ss<<8 | state)
      state handler: screen_event 0x60e4d032(event, lparam, screen it owns)   (screen pointer in a state global)
        IGui_Controler pre-callback (+28/+32), then actuator vtbl[0] = 0x60dd5250
          key grab 0x61fc1bac; hash 0x6114040c -> vtbl +44 Up .. +64 dial, else +68
            class method -> per-instance handler words (editors: record words in parent +48..+88;
                                                       2CNL: +0x30..+0x48 from RAM 0x61fc1c00)
              composite actuators forward to their child / column (2CNL depth, main menu focus)
        actuator rc 1 -> viewer vtbl[0] redraw (not for touch codes 0xaf00..0xaf03)
        screen_event returns: actuator rc 2 -> 1 (decide), 3 -> 2 (back), 4 -> 3 (open request pending), else 0
```

- **Consuming vs passing** [V]: an actuator "consumes" a key by returning non-zero; rc 0 means nothing
  happened and the state handler may act on the key itself. A key a state never maps in its matrix row is
  dropped at the HSM (default handler 0x60dd4b47 returns 0) and **never reaches the screen**. That is why only
  INFO reaches the COLOR editor on camera (ATLAS §4) and why AP_CUSTOM had to retarget matrix bytes.
- Event codes (from the SsMenuMain / SsMenuLv maps) [V codes, I meanings beyond ATLAS]: 0x9004 Up, 0x9006 Down,
  0x9008 Left, 0x900a Right, 0x900c OK, 0x900e MENU, 0x9010 Play, 0x9012 Movie, 0x9014 INFO, 0x9016 Delete,
  odd code = release of the even one, 0x9031 / 0x9032 dial steps, 0x9030 / 0x9033 other dial / power [I],
  0x903e held OK, 0x9300.. 0x9308 lever/state changes [I], 0x9a.., 0x9b.., 0xa30a, 0xf8xx internal (0xf802
  release done, 0xf805 actuator init, 0xf823 HDMI fallback).
- Dials on lists are converted: the main-menu actuator turns +60/+64 into Left/Right (0x60e0eb8b/0x60e0ec27);
  `userGuiDbMenu::MoveDial` 0x60ea7e3b handles dial steps in wizard menus.
- State globals that hold the screen a state talks to [V]: **0x61fc4328 SCP**, **0x61fc432c Live Control**,
  **0x61fc4330 last group-18 editor**, 0x61fc4370 key for state 7's open, 0x61fc5060 current wizard-menu
  screen (SsMenuMain).

### 5.1 Menu history (wizard menus) [V: 0x60ea7c10..0x60ea7e01]

- Stack of **10 × 6 B** at 0x61fc4ffc `{u16 item, u8 cursor, u8 ?, u16 x}`, depth byte 0x61fc5038.
  Push 0x60ea7dcc, pop 0x60ea7d42 (returns the popped entry) / 0x60ea7da4 (drop), peek 0x60ea7c89,
  peek n back 0x60ea7cd4, clear 0x60ea7c6d. SsMenuMain StWizardMenu entry 0x60e5db2e restores the cursor from
  it on re-entry.
- GUI "DB" records: `gui_db_get` 0x60cfec91(id, size, buf) / `gui_db_set` 0x60cfeca9(id, size, buf, flag)
  (244 / 198 callers) hold menu position (id 0x10, 12 B), shared UI state (id 0, 0x26 B), etc. [V calls,
  I semantics].

## 6. Super Control Panel and Live Control (SsMenuLv, ss 4) [V]

- Matrix is event-major (AP_CUSTOM b7 correction): handler = `words[matrix[event_index·29 + state − 1]]`,
  descriptor 0x611a3bc8, matrix 0x611a2e30, handlers 0x611a2c08 (138), event map 0x611a2888 (112),
  entry table 0x611a3ae0, exit table 0x611a3b54.

| State | Entry / exit | Screen |
|---|---|---|
| 1 | 0x60e5788e / 0x60e57a7c | ? |
| **2 Live Control** | 0x60e56973 / 0x60e569a2 | `screen_open(20, 0)` → 0x61fc432c: `Plural_Lv_Control_Actuator` + `Lv_Control_Mode_Viewer`. Rows: `lv_control_select` 0x61177140 (ATLAS). All keys → 0x60e593be |
| **3 SCP** | 0x60e56ea0 / 0x60e57a89 | `IGui_Controler(10, 0x62472e44)` → layout 13 → **`Func_Scp_Actuator` (kind 8) + viewer 15** → 0x61fc4328. RC-mode SCP: controller 11 → layout 14 → kind 9 + viewer 16 |
| 7 setting screen | 0x60e590bd / 0x60e591ba | helper 0x60e59198: `screen_open(18, key 0x61fc4370)` → 0x61fc4330, then sends 0x9749 |
| 15–28 | strings | ART / SCN / movie-mode / ADV pickers (group 8 keys 417, 436, 437, 447) |

**SCP cells** [V]: `Func_Scp_Actuator::initActModeDetail` 0x60df1429 copies 39 cell sids from **0x61159f08**
(39 × 14 B; +0 u16 sid, then 6 u16 [I: neighbour cells for the 4-way cursor + position]) into actuator
+0x5c (u16[39]), count +0xaa. `updateActModeDetail` 0x60df149c swaps per-mode cell sids from small
`{mode, sid}` tables (0x6115a358.., 0x6115a6f8..; mode = sid 16 [I]). Cell sids in order: 6, 16, 17, 157, 826,
9, 39, 132, 3281, 1, 290, 85, 10, 270, 111, 7, 8, 59, 105, 307, 131, 241, 60, 1439, 383, 1390, 24, 218, 228, 219,
229, 220, 230, 221, 231, 217, 233, 232, 24.

**Opening a cell** [V: 0x60e56a7f]: the SCP OK handler forwards the event to the SCP screen; on screen rc 1 it
reads the cell sid (actuator vtbl +4) into 0x61fc4370, runs CANEXEC on it (special cases 0x452, 0x362, 0x473,
0x55, 0x6f, 0x56e/0x56f, 0x269, 0x17f), and returns (4, 7) by default, (4, 8) for a list of WB/flash-type cells, (4, 9) / (4, 0x15) / (4, 0x16) for
0x56e / 0x56f / 0x473, and (1, 8) plus a camera-app event for 0x269 / 0x17f. State 7 opens the group-18 editor whose key is that sid. Caduceus' `ap_sc` / `mv_lc`
hooks sit exactly on this path (AP_CUSTOM, MOVIE_COLOUR).

## 7. Recipe: a brand-new "Caduceus" page (design only)

Goal: Setup Menu gets a row **"Caduceus"** → a 2CNL page with (a) stock-setting rows with inline value pickers,
(b) one value-picker row in a popup, (c) one custom action row. Existing kinds only.

**Constraints found** [V]: 2CNL records are a fixed 156-slot table (bound 0x9c hard-coded twice), column-mode
lists a fixed 150 (0x96), the item-info index a fixed 129, the tab tables a fixed 7. The screen-group lists,
row lists and transition lists carry their own counts (data). So: **relocate** the lists that carry a count,
**repurpose** slots in the fixed tables.

| Step | Record / site | Change | Kind |
|---|---|---|---|
| R1 row | Setup tab rows: record **0x61150aec** `{0, 7, 0x61150aa6}` (mode 86) | → `{0, 8, new list}`: stock 7 ids + **X** (new virtual id, e.g. 5200: no 2CNL list, column list, item-info record or cond row uses 5132..5299 [V scan of those tables]; other readers not checked) | data, 6 B + 16 B |
| R2 label | Menu_Viewer page 6 **0x6117b25c** (items 0x6117a30c × 7, helps 0x6117a4f8) | relocate items (+1 × 12 B: `{X, kind 5, 0, "Caduceus"}`) and helps (+1); n 7 → 8 | data |
| R3 link | 2CNL 68 (Setup tab) **0x6114c15c**: listB 0x61147d64 ×6, listC 0x61147df4 ×6 | relocate both +1 entry `{1, X, 0, 0, 14, K, 0}` (Right and OK) | data, 2 × 168 B |
| R4 screen | group 14: list **0x6119cb54** ×132, count u16 at **0x6119faf0** | relocate +1 descriptor `{K, 21, KIND, 49, VP, 0}`; K = 135 (keys go to 134) | data, 3.2 KB |
| R5 page | 2CNL slot to repurpose: **43** (0x6114bc28, mode 31) or **96** (0x6114bd6c, mode 38): no group-14 screen opens either | rewrite `{KIND, 3, M, listA, nA, listB, nB, listC, nC}` | data, 36 B |
| R6 rows | column-mode entry of M (31 or 38) in **0x61150328** | point it at our u16 list `[sid1, sid2, sidP, Y]` | data |
| R7 labels | item-info index entry with a key no screen uses (**30, 45, 70, 71, 72**) → VP | point it at our 36-B records: `{id, kind-5 title, value list, n, 0, text, popup list, n}`; reuse the stock value lists of the sids | data |
| R8 inline pickers | listA of our page | `{0, sid1, 0, 0}`, `{0, sid2, 0, 0}`: Right/OK opens column 2 = `Cursor_Move_Set_Mode` on the sid (stock facade, validator, labels) | data |
| R9 popup picker | listC `{1, sidP, 0, 0, 8, key}` | reuse the stock group-8 popup of sidP (its key from any stock transition naming sidP) | data |
| R10 action | listC `{1, Y, cad_action, 0, 0, 0}` | `cad_action(a0 = 2CNL actuator)`: do the work, return **1** (stay, redraw) or 3 (leave). Must not return 4 (that opens group/key 0) | **code**, ~20 B + body |
| R11 grey | CANEXEC for X and Y | unknown ids fall to `set_available(id, 2, 3200)` in `app_check_mode` 0x608290c8; result for an unknown id is **unverified**. Either give X/Y cond-table rows by repurposing two unused 12-B rows of 0x60adf518, or front `0x6082686f` with a 10-B check that returns "enabled" for X/Y | data or code |

Hook points: none for R1–R9 (pure data). R10 is a function pointer in data. R11 maybe one small hook.

**Values that only Caduceus has** (no stock sid): the row must name a host id and the facade words
(+0/+8/+24/+28/+20, 0x60acb0dc, plus the setter call 0x607fa355) must answer it from the heap, exactly as
LOOK_MENUS route V1. Without that, keep the page to real sids and actions.

**Risk: M.**
- Unknown ids X/Y reaching stock getters: Menu_Viewer's value column for X (0x60e8af1c, by item id) and the
  2CNL viewer's per-row value read. Give X/Y no desc / no value list and check those readers skip them [open].
- Repurposed slots 43/96 and mode 31/38 must be truly unused: audit every reader of those kinds/modes
  (listA column kinds can build columns from modes too) before writing [open].
- Viewer layout: row count per screen and label width are not decoded (FIRMWARE_GUIDE §4 "keep text short").
- Emulation cannot run the screen stack; navigation must be camera-tested.

**Smallest camera slice (ship-minimal):** R1–R4 only, with KIND = an existing stock page (e.g. 97, the
Wi-Fi/Bluetooth page). Data only. Pass = Setup Menu shows an extra row (label from R2) and OK/Right opens that
page, MENU returns. Then R5–R9 with real sids, then R10.

**Verdict: feasible, mostly data (~4 KB relocated tables + < 0.2 KB new records), one function word for the
action; confidence M** (layouts [V]; viewer behaviour for unknown ids and the free-slot audits [open]).

## 8. Stock menu pages

### 8.1 Main menu tabs [V]

Root **0x6117b410**, Menu_Viewer page records 0x6117b1b4 + 28·tab, 2CNL kind from 0x611794a8, rows from
0x61150af4 (key-0 record).

| Tab | Title | Page record | 2CNL kind / record | Row list (ids) |
|---|---|---|---|---|
| 0 | Shooting Menu 1 | 0x6117b1b4 | 62 / 0x6114c084 | 0x61150a30: 10003, 111, 34, 1, 1038 |
| 1 | Shooting Menu 2 | 0x6117b1d0 | 63 / 0x6114c0a8 | 0x61150a3a: 157, 650, 17, 267, 478, 5011, 180 |
| 2 | Video Menu | 0x6117b1ec | 64 / 0x6114c0cc | 0x61150a48: 102, 652, 291, 826, 651, 1441, 1442 |
| 3 | Playback Menu | 0x6117b208 | 65 / 0x6114c0f0 | 0x61150a56: 3270, 89, 3252, 3239, 3321, 3554, 3551 |
| 4 | Custom Menu | 0x6117b224 | 66 / 0x6114c114 | 0x61150a64: 3324, 3325, 3326, 5067, 3327, 5068, 3328, 3329, 3330, 3332 (a key-11 record of 20 also exists) |
| 5 | Accessory Port Menu | 0x6117b240 | 67 / 0x6114c138 | 0x61150aa0: 3493, 3494, 3495 |
| 6 | Setup Menu | 0x6117b25c | 68 / 0x6114c15c | 0x61150aa6: 5099, 20, 3009, 31, 19, 5008, 3290 |

The column lists are shorter than the page records (Shooting Menu 1's page record lists 10 ids, its column 5).
The rows drawn come from the column list (0x60de2628 reads it [V]). The page records and tab 62's transitions
(10 quality, 270 Image Aspect, 5010 drive) are the superset shared with other bodies [I]. ASPECT.md never
camera-checked a main-menu Image Aspect row. One look at the E-P7's Shooting Menu 1 (expect 5 rows: Reset /
Custom Modes, Picture Mode, Digital Tele-converter, sid 1, AF Illuminator) confirms this cheaply **[open]**.

Custom Menu letters (rows 3324.. on tab 66) all run fn 0x60ddc3c1 and open screen (15, 1)
(`Custom_Menu_Actuator`); the letter pages are 2CNL kinds 69–94 (column kind 4, modes 87–116, rows in RAM .data:
MIN_SHUTTER §2b).

### 8.2 Every 2CNL page record

Columns: 2CNL kind | record | screen (group/key) that opens it | rows source | opened from (row label [row id]
(source page)) or tab | rows (ids, with the label from that page's item-info entry where one exists) |
nA/nB/nC. "values of sid N" = the page is a single value list of that sid. Generated by
`~/ep7fw-private/decomp/ui/tools/pages.py` [V tables; labels are the OSD English strings by id].

| Kind | Record | Screen | Rows | Opened from | Rows (ids / labels) | A/B/C |
|---|---|---|---|---|---|---|
|0|`0x6114c378`|14/66|values of sid 0|||0/0/0|
|2|`0x6114b3b8`|14/3|col 3 mode 0|Assign to Custom Mode [5093] (2CNL 128)|3000 Custom Mode C1, 3001 Custom Mode C2, 3002 Custom Mode C3|0/3/3|
|3|`0x6114b3dc`|14/4|col 3 mode 1|Recall from Custom Mode [5094] (2CNL 128)|3000 Custom Mode C1, 3001 Custom Mode C2, 3002 Custom Mode C3|0/3/3|
|4|`0x6114b424`|14/5|values of sid 111|Picture Mode [111] (2CNL 62)||0/58/0|
|5|`0x6114b448`|14/6|col 3 mode 2|value 7 of sid 111 (2CNL 4)|297 Sharpness, 296 Contrast, 298 Saturation, 311 Gradation, 299 Effect|5/0/0|
|6|`0x6114b46c`|14/7|col 3 mode 3|value 0 of sid 111 (2CNL 4)|118 Sharpness, 117 Contrast, 119 Saturation, 312 Gradation|4/0/0|
|7|`0x6114b490`|14/8|col 3 mode 4|value 1 of sid 111 (2CNL 4)|121 Sharpness, 120 Contrast, 122 Saturation, 313 Gradation|4/0/0|
|8|`0x6114b4b4`|14/9|col 3 mode 5|value 2 of sid 111 (2CNL 4)|124 Sharpness, 123 Contrast, 125 Saturation, 314 Gradation|4/0/0|
|9|`0x6114b4d8`|14/10|col 3 mode 6|value 5 of sid 111 (2CNL 4)|182 Sharpness, 181 Contrast, 183 Saturation, 315 Gradation|4/0/0|
|10|`0x6114b4fc`|14/11|col 3 mode 7|value 3 of sid 111 (2CNL 4)|127 Sharpness, 126 Contrast, 128 Color Filter, 129 Monochrome Color, 316 Gradation|3/2/0|
|11|`0x6114b520`|14/12|col 3 mode 8|value 6 of sid 111 (2CNL 4)||6/2/0|
|12|`0x6114b568`|14/13|col 3 mode 9|value 8 of sid 111 (2CNL 4)|363 Filter Type, 370 Add Effects|0/3/0|
|13|`0x6114b58c`|14/14|col 3 mode 10|value 9 of sid 111 (2CNL 4)|374 Add Effects|0/1/0|
|14|`0x6114b5b0`|14/15|col 3 mode 11|value 10 of sid 111 (2CNL 4)|366 Filter Type, 375 Add Effects|0/3/0|
|15|`0x6114b5d4`|14/16|col 3 mode 12|value 11 of sid 111 (2CNL 4)|378 Add Effects|0/1/0|
|16|`0x6114b5f8`|14/17|col 3 mode 13|value 12 of sid 111 (2CNL 4)|364 Filter Type, 371 Add Effects, 461 Color Filter, 463 Monochrome Color|0/7/0|
|17|`0x6114b61c`|14/18|col 3 mode 14|value 13 of sid 111 (2CNL 4)|365 Filter Type, 372 Add Effects|0/4/0|
|18|`0x6114b640`|14/19|col 3 mode 15|value 14 of sid 111 (2CNL 4)|595 Filter Type, 379 Add Effects|0/3/0|
|19|`0x6114b664`|14/20|col 3 mode 16|value 15 of sid 111 (2CNL 4)|367 Filter Type, 376 Add Effects|0/3/0|
|20|`0x6114b688`|14/21|col 3 mode 17|value 16 of sid 111 (2CNL 4)|377 Add Effects|0/1/0|
|21|`0x6114b6ac`|14/22|col 3 mode 18|value 17 of sid 111 (2CNL 4)|368 Filter Type, 373 Add Effects|0/5/0|
|22|`0x6114b6d0`|14/23|col 3 mode 19|value 18 of sid 111 (2CNL 4)|369 Filter Type, 380 Add Effects|0/3/0|
|23|`0x6114b6f4`|14/24|col 3 mode 20|value 19 of sid 111 (2CNL 4)|468 Filter Type, 467 Add Effects|0/3/0|
|24|`0x6114b718`|14/25|col 3 mode 21|value 26 of sid 111 (2CNL 4)|661 Filter Type, 662 Add Effects|0/4/0|
|25|`0x6114b73c`|14/26|col 3 mode 22|value 27 of sid 111 (2CNL 4)|663 Filter Type, 664 Add Effects|0/4/0|
|26|`0x6114b760`|14/27|col 3 mode 23|value 60 of sid 111 (2CNL 4)|1454 Filter Type, 1455 Add Effects|0/3/0|
|27|`0x6114b784`|14/28|col 3 mode 24|value 63 of sid 111 (2CNL 4)|1461|0/1/0|
|28|`0x6114bb74`|14/29|col 3 mode 25|@A02E@ [10] (2CNL 62)|866, 10 Still Picture, 699 Movie|2/6/0|
|29|`0x6114bb98`|14/30|col 3 mode 26|@A014@/@A015@ [3281] (2CNL 63)|469 Number of Frames, 471 @A03F@ Timer, 470 Interval Length|3/1/0|
|30|`0x6114bbbc`|14/31|col 3 mode 27|Bracketing [605] (2CNL 63)|476 AE BKT, 608 WB BKT, 614 FL BKT, 606 ISO BKT, 616 ART BKT, 860 Focus BKT|4/9/0|
|31|`0x6114bcdc`|14/32|col 3 mode 36||5025 Recording Volume, 657 @A01D@Volume Limiter, 433 Wind Noise Reduction, 774 @A01D@Plug-in Power, 5080 PCM Recorder @A01D@ Link, 785 Headphone Volume|5/3/0|
|32|`0x6114bd24`|14/33|col 3 mode 39|PCM Recorder @A01D@ Link [5080] (2CNL 31)|773 Camera Rec. Volume, 1335 Slate Tone, 1336 Synchronized @A01C@Rec.|0/3/0|
|33|`0x6114bdfc`|14/50|col 3 mode 46|@A006@Button Function [5100] (2CNL 111)|1246 @A00C@Function, 1248 @A03B@Function, 1247 @A013@Function, 1250 @A03A@Function, 1251 @A05C@Function, 1249 @A02B@Function, 1252 @A056@Function …(+9)|0/16/0|
|34|`0x6114be44`|14/34|col 3 mode 45| [3452] (2CNL 73)|1469 bmp7289, 1466 P/A/S/M/B, 1467 ART, 1468 SCN/@A0A9@|4/0/0|
|35|`0x6114b2e0`|14/35|col 3 mode 108||429 Max fps, 1171 Frame Count Limiter|2/4/0|
|36|`0x6114b304`|14/36|col 3 mode 109||430 Max fps, 1173 Frame Count Limiter|2/4/0|
|37|`0x6114b328`|14/37|col 3 mode 110||769 Max fps, 1169 Frame Count Limiter|2/4/0|
|38|`0x6114b34c`|14/38|col 3 mode 111||768 Max fps, 1167 Frame Count Limiter|2/4/0|
|39|`0x6114b370`|14/39|col 3 mode 112||1159 Max fps, 1165 Pre-shutter Frames, 1161 Frame Count Limiter|3/2/0|
|40|`0x6114b394`|14/40|col 3 mode 113||1160 Max fps, 1166 Pre-shutter Frames, 1163 Frame Count Limiter|3/2/0|
|41|`0x6114bbe0`|14/41|col 3 mode 29|Multiple Exposure [267] (2CNL 63)|267 Number of Frames, 268 Auto Gain, 269 Overlay|3/0/1|
|42|`0x6114bc04`|14/42|col 3 mode 30|Intrvl. Sh./Time Lapse [478] (2CNL 63)|479 Number of Frames, 480 Start Waiting Time, 481 Interval Length, 482 Time Lapse Movie, 5042 Movie Settings|1/5/0|
|43|`0x6114bc28`|-|col 3 mode 31||157, 826|2/2/0|
|44|`0x6114bd48`|14/44|col 3 mode 37||290 Still Picture, 291 Movie|1/0/0|
|45|`0x6114bd90`|14/134,14/45|col 3 mode 40||70 P, 74 A, 72 S, 76 M|5/0/0|
|47|`0x6114bdb4`|14/46|col 3 mode 42| [3476] (2CNL 72)|47 @A03A@Function, 48 @A013@Function|0/16/0|
|48|`0x6114be20`|14/47|col 3 mode 43| [3549] (2CNL 72)|1041, 1042|2/0/0|
|49|`0x6114be68`|14/48|col 3 mode 44| [3447] (2CNL 73)|289 Output Size, 305 HDMI Control|3/0/0|
|50|`0x6114be8c`|14/52|col 3 mode 50| [5112] (2CNL 73)|681 @A063@Lock, 1426 Live View Boost|2/1/0|
|51|`0x6114beb0`|14/51|col 3 mode 51| [5111] (2CNL 73)|343 LV Close Up Mode, 1425 Live View Boost|0/2/0|
|52|`0x6114bd00`|14/49|col 3 mode 47|@A006@HDMI Output [1276] (2CNL 64)|1276 Output Mode, 1421 REC Bit, 1422 Time Code|2/1/0|
|53|`0x6114bed4`|14/58|values of sid 9| [9] (2CNL 82)||1/12/0|
|54|`0x6114bef8`|14/59|col 3 mode 65| [175] (2CNL 82)|176 @A04C@iddle, 177 @A04D@mall|2/0/0|
|55|`0x6114bf64`|14/60|col 3 mode 66| [3478] (2CNL 83)|361 Copyright Info., 3487 Artist Name, 3488 Copyright Name|1/2/0|
|56|`0x6114bf88`|14/61|col 3 mode 67| [273] (2CNL 75)|273 bmp663, 274 bmp654, 275 bmp655|3/0/0|
|57|`0x6114bfac`|14/62|col 3 mode 68| [3500] (2CNL 92)|3501 Address List, 398 Search Timer, 3502 New Pairing|1/2/2|
|58|`0x6114bfd0`|14/63|col 1 mode 20|Address List [3501] (2CNL 57)|468, 467|14/28/28|
|59|`0x6114bff4`|14/64|col 3 mode 76||282 @A00A@ Menu Display, 393 @A000@ Menu Display|0/2/0|
|60|`0x6114c018`|14/53|col 3 mode 78||647 Composite Mode, 648 Base Exposure Time|0/2/0|
|61|`0x6114c03c`|14/57|col 3 mode 79| [5035] (2CNL 87)|650 Still Picture, 651 Movie|2/0/0|
|62|`0x6114c084`|-|col 4 mode 80|TAB Shooting Menu 1|10003 Reset, 111 Picture Mode, 34 Digital Tele-converter, 1 Metering, 1038 AF Illuminator|4/6/6|
|63|`0x6114c0a8`|-|col 4 mode 81|TAB Shooting Menu 2|157 @A002@Image Stabilizer, 650 @A002@Elec. Zoom Speed, 17 @A00A@, 267 Multiple Exposure, 478 Intrvl. Sh./Time Lapse, 5011 Anti-Shock@A04D@/Silent@A0, 180 @A00B@ RC Mode|8/10/7|
|64|`0x6114c0cc`|-|col 4 mode 82|TAB Video Menu|102 Movie @A014@, 652 Recording Volume, 291 @A04E@AF Mode, 826 @A04E@Image Stabilizer, 651 @A04E@Elec. Zoom Speed, 1441 Video Frame Rate, 1442 Video Bit Rate|4/8/8|
|65|`0x6114c0f0`|-|col 4 mode 83|TAB Playback Menu|3270 @A028@, 89 @A023@, 3252 Edit, 3239 Print Order, 3321 Reset Protect, 3554 Reset share Order, 3551 Device Connection|1/6/6|
|66|`0x6114c114`|-|col 4 mode 84|TAB Custom Menu|3324 A1. AF/MF, 3325 Button/Dial/Lever, 3326 C1. Release/@A018@/Image S, 5067 C2. Release/@A018@/Image S, 3327 D1. Disp/@A002@/PC, 5068 D2. Disp/@A002@/PC, 3328 E1. Exp/ISO/BULB/@A0A7@ …(+3)|0/12/12|
|67|`0x6114c138`|-|col 4 mode 85|TAB Accessory Port Menu|3493 OLYMPUS PENPAL Share, 3494 OLYMPUS PENPAL Album, 3495 Electronic Viewfinder|0/3/3|
|68|`0x6114c15c`|-|col 4 mode 86|TAB Setup Menu|5099 Card Setup, 20 @A01F@, 3009 @A0A5@, 31 @A012@, 19 Rec View, 5008 @A089@/Bluetooth Settings, 3290 Firmware|1/6/6|
|69|`0x6114c1ec`|-|col 4 mode 87||65, 241, 5009, 81|11/14/11|
|72|`0x6114c210`|-|col 4 mode 90||3476, 1465, 37|5/11/11|
|73|`0x6114c234`|-|col 4 mode 91||3452, 3390, 36, 460, 155, 566|7/17/17|
|74|`0x6114c258`|-|col 4 mode 92||1043, 3447, 82|7/17/17|
|75|`0x6114c27c`|-|col 4 mode 93||273, 112, 143, 35|10/8/7|
|76|`0x6114c2a0`|-|col 4 mode 94||173, 435, 436, 648|10/8/7|
|79|`0x6114c2c4`|-|col 4 mode 97||114, 174, 113, 317|4/0/0|
|82|`0x6114c2e8`|-|col 4 mode 100||234, 9, 428, 60|4/6/6|
|83|`0x6114c30c`|-|col 4 mode 101||21, 3320, 3478|2/5/5|
|85|`0x6114c330`|-|col 4 mode 102||591, 3565|0/6/6|
|87|`0x6114c354`|-|col 4 mode 104||3254, 3420, 426, 32, 5060|4/12/10|
|92|`0x6114c180`|-|col 4 mode 114||3499, 3500, 3503, 399|0/4/4|
|93|`0x6114c1a4`|-|col 4 mode 115||3508, 3507, 3506, 3505, 400|0/5/5|
|94|`0x6114c1c8`|-|col 4 mode 116||58, 448|0/2/2|
|95|`0x6114c39c`|14/65|col 4 mode 117|@A028@ [3270] (2CNL 65)|3270 Start, 110 BGM, 101 Slide, 288 Slide Interval, 283 Movie Interval|4/1/1|
|96|`0x6114bd6c`|-|col 3 mode 38||537, 540|2/0/0|
|97|`0x6114c3c0`|14/68|col 3 mode 69|@A089@/Bluetooth Settings [5008] (2CNL 68)|564 Wireless Functions, 1642 Bluetooth, 1688 Auto Share Order, 1463 Power-off Standby, 5029 Connection Password, 5030 Reset Settings|0/7/0|
|98|`0x6114c3e4`|14/69|col 3 mode 70| [5009] (2CNL 69)|284 Magnify, 567 Peaking|0/2/0|
|99|`0x6114c408`|14/70|col 3 mode 71| [5109] (2CNL 72)|535 @A004@Fn Lever Function, 597 Switch@A0A9@ Function|0/2/0|
|101|`0x6114c450`|14/71|col 3 mode 74| [243] (2CNL 72)|243 Exposure, 596 Ps|0/2/0|
|102|`0x6114c42c`|14/72|col 3 mode 73|Recording Volume [5025] (2CNL 31)|652 Built-In @A01D@, 654 MIC @A01D@|3/0/0|
|103|`0x6114c474`|14/73|col 3 mode 75| [3565] (2CNL 85)|589 EVF Auto Luminance, 3559 EVF Adjust|0/2/0|
|106|`0x6114c498`|14/76|col 3 mode 42||47 @A03A@Function, 48 @A013@Function|0/16/0|
|107|`0x6114c4bc`|14/77|col 1 mode 99| [578] (2CNL 69)||20/41/41|
|108|`0x6114c528`|14/78|col 3 mode 118|@A018@/@A019@/@A0D4@ [5010] (2CNL 62)|3281 @A014@/@A015@, 478 Intrvl. Sh./Time Lapse/|2/4/0|
|109|`0x6114bc4c`|14/80|col 3 mode 32|@A006@Specification Settings [5014] (2CNL 64)|699 @A04E@@A021@, 1334 @A006@Noise Filter, 1337 @A006@Picture Mode|3/6/0|
|110|`0x6114bc70`|14/81|col 3 mode 33||291 @A04E@AF Mode, 826 @A04E@Image Stabilizer|2/1/0|
|111|`0x6114bc94`|14/82|col 3 mode 34|@A006@Button/Dial/Lever [5090] (2CNL 64)|5100 @A006@Button Function, 5108 @A006@Dial Function, 1302 @A006@Fn Lever Function, 789 @A006@Shutter Function, 651 @A04E@Elec. Zoom Speed|3/6/4|
|112|`0x6114bcb8`|14/83|col 3 mode 35|@A006@Display Settings [5091] (2CNL 64)|5104 @A006@Control Settings, 5105 @A006@Info Settings, 5013 Time Code Settings, 1103 @A0B4@Display Pattern|3/4/0|
|113|`0x6114c570`|14/79|col 3 mode 122|Anti-Shock@A04D@/Silent@A047@ [5011] (2CNL 63)|167 Anti-Shock@A04D@, 765 Silent@A047@, 766 Noise Reduction@A047@, 5052 Silent@A047@Mode Settings|3/4/0|
|114|`0x6114c594`|14/84|col 3 mode 123||566 Peaking Color, 756 Highlight Intensity, 757 Image Brightness Adj.|0/3/0|
|115|`0x6114c5b8`|14/85|col 3 mode 124|High Res Shot [775] (2CNL 63)|775 High Res Shot, 760 @A011@Charge Time|1/2/0|
|116|`0x6114c5dc`|14/86|col 3 mode 125||782 Manual Shooting, 783 Bulb/Time, 784 Live Composite, 781 Others|0/4/0|
|117|`0x6114c600`|14/87|col 3 mode 126|Time Code Settings [5013] (2CNL 112)|786 Time Code Mode, 787 Count Up, 788 Starting Time|0/3/0|
|118|`0x6114c624`|14/88|col 3 mode 127||1121 End LV@A0AE@, 1122 Reset LV@A0AE@ Frame, 1123 End @A05B@, 1124 Reset @A05B@ Frame, 1125 Reset @A00E@, 1126 Reset @A010@, 1127 Reset @A0B1@ …(+10)|0/18/0|
|119|`0x6114b400`|14/90|col 3 mode 128||451 Battery Priority, 5096 Battery Status|0/2/0|
|120|`0x6114c648`|14/89|col 3 mode 129| [778] (2CNL 87)|779 Backlit LCD, 780 Sleep|2/0/0|
|121|`0x6114c66c`|-|col 3 mode 138|||4/1/1|
|122|`0x6114c690`|-|col 3 mode 138|||4/1/1|
|123|`0x6114c6b4`|-|col 3 mode 138|||4/1/1|
|124|`0x6114c6d8`|8/365|col 3 mode 139|Focus BKT [860] (2CNL 30)|1332 Focus Stacking, 862 Set number of shots, 865 Set focus differential, 1086 @A011@Charge Time|4/3/0|
|125|`0x6114c6fc`|8/46|col 3 mode 140| [5082] (2CNL 69)|1319 AF Mode, 1320 bmp6572, 1321 bmp6573|3/1/0|
|126|`0x6114bf1c`|14/54|col 3 mode 119| [5110] (2CNL 85)|1119 Display Color, 447 Displayed Grid|2/2/0|
|127|`0x6114bf40`|14/56|col 3 mode 120||1118 Display Color, 155 Displayed Grid, 1120 Apply Settings to EVF|2/3/0|
|128|`0x6114c54c`|14/2|col 3 mode 121||10003 Reset, 5093 Assign to Custom Mode, 5094 Recall from Custom Mode|0/3/3|
|129|`0x6114c060`|14/91|col 3 mode 142|Silent@A047@Mode Settings [5052] (2CNL 113)|1027 @A001@, 1028 AF Illuminator, 1029 Flash Mode|3/0/0|
|130|`0x6114c720`|14/99|col 3 mode 143|value 54 of sid 111 (2CNL 4)|909 Sharpness, 912 Contrast|2/0/0|
|131|`0x6114c744`|14/100|col 3 mode 144|value 55 of sid 111 (2CNL 4)|910 Sharpness, 913 Contrast|2/0/0|
|132|`0x6114c768`|14/101|col 3 mode 145|value 56 of sid 111 (2CNL 4)|911 Sharpness, 914 Contrast|2/0/0|
|133|`0x6114c78c`|14/102|col 3 mode 146|value 64 of sid 111 (2CNL 4)|1651 Sharpness, 1653 Contrast|2/0/0|
|134|`0x6114c4e0`|14/94,14/93|col 3 mode 147| [1] (2CNL 135)|5054 Lens Name, 5055 Focal Length, 5056 Aperture Value, 5057 Set|4/4/4|
|135|`0x6114c504`|14/92,18/1078|col 1 mode 145| [5053] (2CNL 83)|911, 914|10/21/21|
|136|`0x6114c7b0`|14/95|col 3 mode 148|value 57 of sid 111 (2CNL 4)|974 Sharpness, 977 Contrast, 981 Film Grain Effect, 984 Monochrome Color|3/1/0|
|137|`0x6114c7d4`|14/96|col 3 mode 149|value 58 of sid 111 (2CNL 4)|975 Sharpness, 978 Contrast, 982 Film Grain Effect, 985 Monochrome Color|3/1/0|
|138|`0x6114c7f8`|14/97|col 3 mode 150|value 59 of sid 111 (2CNL 4)|976 Sharpness, 979 Contrast, 983 Film Grain Effect, 986 Monochrome Color|3/1/0|
|139|`0x6114c81c`|14/98|col 3 mode 151|value 65 of sid 111 (2CNL 4)|1652 Sharpness, 1654 Contrast, 1678 Film Grain Effect, 1679 Monochrome Color|3/1/0|
|140|`0x6114b544`|14/103|values of sid 111|Picture Mode [111] (2CNL 62)||0/58/0|
|141|`0x6114b7a8`|14/104|col 3 mode 152|value 2049 of sid 111 (2CNL 4)|370 Add Effects|0/1/0|
|142|`0x6114b7cc`|14/105|col 3 mode 153|value 2050 of sid 111 (2CNL 4)|873 Add Effects|0/1/0|
|143|`0x6114b7f0`|14/106|col 3 mode 154|value 2561 of sid 111 (2CNL 4)|375 Add Effects|0/1/0|
|144|`0x6114b814`|14/107|col 3 mode 155|value 2562 of sid 111 (2CNL 4)|874 Add Effects|0/1/0|
|145|`0x6114b838`|14/108|col 3 mode 156|value 3073 of sid 111 (2CNL 4)|371 Add Effects, 461 Color Filter, 463 Monochrome Color|0/3/0|
|146|`0x6114b85c`|14/109|col 3 mode 157|value 3074 of sid 111 (2CNL 4)|875 Add Effects, 887 Color Filter, 889 Monochrome Color|0/3/0|
|147|`0x6114b880`|14/110|col 3 mode 158|value 3329 of sid 111 (2CNL 4)|372 Add Effects|0/1/0|
|148|`0x6114b8a4`|14/111|col 3 mode 159|value 3330 of sid 111 (2CNL 4)|876 Add Effects|0/1/0|
|149|`0x6114b8c8`|14/112|col 3 mode 160|value 3331 of sid 111 (2CNL 4)|877 Add Effects|0/1/0|
|150|`0x6114b8ec`|14/113|col 3 mode 161|value 3585 of sid 111 (2CNL 4)|379 Add Effects|0/1/0|
|151|`0x6114b910`|14/114|col 3 mode 162|value 3586 of sid 111 (2CNL 4)|878 Add Effects|0/1/0|
|152|`0x6114b934`|14/115|col 3 mode 163|value 3841 of sid 111 (2CNL 4)|376 Add Effects|0/1/0|
|153|`0x6114b958`|14/116|col 3 mode 164|value 3842 of sid 111 (2CNL 4)|879 Add Effects|0/1/0|
|154|`0x6114b97c`|14/117|col 3 mode 165|value 4353 of sid 111 (2CNL 4)|373 Add Effects|0/1/0|
|155|`0x6114b9a0`|14/118|col 3 mode 166|value 4354 of sid 111 (2CNL 4)|880 Add Effects, 888 Color Filter, 890 Monochrome Color|0/3/0|
|156|`0x6114b9c4`|14/119|col 3 mode 167|value 4609 of sid 111 (2CNL 4)|380 Add Effects|0/1/0|
|157|`0x6114b9e8`|14/120|col 3 mode 168|value 4610 of sid 111 (2CNL 4)|881 Add Effects|0/1/0|
|158|`0x6114ba0c`|14/121|col 3 mode 169|value 4865 of sid 111 (2CNL 4)|467 Add Effects|0/1/0|
|159|`0x6114ba30`|14/122|col 3 mode 170|value 4866 of sid 111 (2CNL 4)|882 Add Effects|0/1/0|
|160|`0x6114ba54`|14/123|col 3 mode 171|value 6657 of sid 111 (2CNL 4)|662 Add Effects|0/1/0|
|161|`0x6114ba78`|14/124|col 3 mode 172|value 6658 of sid 111 (2CNL 4)|883 Add Effects|0/1/0|
|162|`0x6114ba9c`|14/125|col 3 mode 173|value 6659 of sid 111 (2CNL 4)|884 Add Effects|0/1/0|
|163|`0x6114bac0`|14/126|col 3 mode 174|value 6913 of sid 111 (2CNL 4)|664 Add Effects|0/1/0|
|164|`0x6114bae4`|14/127|col 3 mode 175|value 6914 of sid 111 (2CNL 4)|885 Add Effects|0/1/0|
|165|`0x6114bb08`|14/128|col 3 mode 176|value 6915 of sid 111 (2CNL 4)|886 Add Effects|0/1/0|
|166|`0x6114bb2c`|14/129|col 3 mode 177|value 15361 of sid 111 (2CNL 4)|1455 Add Effects|0/1/0|
|167|`0x6114bb50`|14/130|col 3 mode 178|value 15362 of sid 111 (2CNL 4)|1456 Add Effects|0/1/0|
|168|`0x6114c840`|14/131|col 3 mode 179||112 Upper Limit / Default, 1146 Lowest S/S Setting|1/2/0|
|169|`0x6114c864`|14/132|col 3 mode 180| [1149] (2CNL 69)|1150 Distance settings, 1157 Pri. Rls|2/4/0|
|171|`0x6114c888`|14/0|col 3 mode 182||1323 bmp6899, 1325 bmp6898, 1327 bmp3406, 1329 bmp2642|8/0/0|
|172|`0x6114c8ac`|14/1|col 3 mode 183||1324 bmp6899, 1326 bmp6898, 1328 bmp3406, 1330 bmp2642|8/0/0|
|173|`0x6114bdd8`|14/133|col 3 mode 42| [3476] (2CNL 72)|47 @A03A@Function, 48 @A013@Function|0/16/0|

Other screens that act as pages but are not 2CNL: the main menu (15, 0), Custom Menu (15, 1/2), group-8
popups (429, mostly `Cursor_Move_Set_Mode` value lists keyed by a popup id), group-18 editors (257, keyed by
sid), Live Control (20, 0), SCP (controller 10). Their descriptors are in the lists of §3.1.

## 9. Open questions

1. Viewer behaviour for unknown row ids (value column 0x60e8af1c, 2CNL viewer kind 49) and CANEXEC's answer
   for an id with no cond row and no rule. Both gate the recipe (§7 R11). Cheapest check: emulate
   `app_check_mode` (0x608290c8) for id 5200 with the rule hash initialised.
2. Whether 2CNL kinds 43 / 96 and modes 31 / 38 are reachable some other way (listA column kinds, per-kind
   init functions) before repurposing them.
3. The tab column (column kind 1, mode 22) and whether the Accessory Port tab is hidden on the E-P7, and how.
4. Which item-info tree (0x611bee58.. vs 0x611cce58..) the E-P7 reads; live_nd edited both.
5. Names of ss 5, 9, 12, 13, 14 and of the unnamed actuator / viewer kinds; the state-name tables used by
   the transition logger 0x60e9e771 would give them.
6. The SCP cell record's six u16 after the sid (assumed navigation neighbours).
7. Who opens the main menu screen (15, 0): not via `screen_open` call sites with a constant group 15 [V scan];
   probably the user-menu process objects (0x60edef64, `userCommon*Wizard::initMenu`) [I].
