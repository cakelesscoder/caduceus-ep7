# Map your own body: reusing the E-P7 atlas on other Olympus/OM cameras

This guide is for people porting Caduceus-style work to another Olympus or OM SYSTEM body. The PEN E-P7 1.1
firmware has a public map, the [atlas](ATLAS.md): about 770 named functions, tables and data, plus about
3,000 more function names derived from the firmware's own log strings ([RE_AUTONAME.md](RE_AUTONAME.md)). Most
of the code base is shared across the 2019+ bodies, so much of that map carries over. The tools here move it
onto your body's firmware in about a minute, and give you a named Ghidra project in about 15 minutes.

You need only your own body's firmware file from OM, plus the E-P7 1.1 file, which OM also offers for free
download. Nothing from this repo contains firmware, and nothing you make here should be published except
names and addresses (§1).

Round R4 of [RE_ROUNDS.md](RE_ROUNDS.md). Validated on the E-M10 IV, E-M5 III and E-M1 III (§6).

| What | File |
|---|---|
| Signature finder: E-P7 names to your body's addresses | `tools/atlas/sigfind.py` |
| One-command bootstrap: decode, base, names, Ghidra project | `tools/atlas/bootstrap_body.sh` |
| Ghidra scripts: seed functions, apply names, mark for REA | `tools/atlas/SeedFunctions.java`, `ApplyNames.java`, `ReaMark.java` (`apply_names.py` for PyGhidra) |
| Fix for the MN103 processor module on Ghidra 12 | `tools/atlas/fix_mn103.py` |
| The names to transfer | `docs/atlas.json`, `docs/autonames.json` |

## 1. The legal boundary (read this first)

OM's firmware is copyrighted, and its licence forbids redistributing it. Code decompiled or disassembled from it
is a derivative of it. Facts about it, such as addresses, names, record layouts and how it behaves, written in
your own words, are yours to share. The rules this repo follows, and that we ask ports to follow:

| You may publish | Keep private |
|---|---|
| Names and addresses (`names.json`, `candidates.json`, an atlas for your body) | The firmware file and every decoded component |
| Record layouts, setting ids, your own prose | Ghidra projects (`*.gpr`, `*.rep`) |
| Your own scripts and patches | Decompiler output and long disassembly listings |
| Short instruction quotes needed to check a patch site | Signature caches (`sigfind.py --cache`): they hold firmware bytes |

- `bootstrap_body.sh` puts everything it makes under `~/caduceus-port/<tag>/` by default, outside any repo.
  Only `candidates.json`, `names.json`, `sites.json` and `check.txt` are fit to publish. They hold addresses,
  names, scores and string-free method notes, and nothing else.
- **No signature file ships with this repo.** `sigfind.py` builds its signatures at run time from your copy of
  the E-P7 file. The reason is in §8.
- The MN103 processor module is GPL-3.0 and isn't ours. We don't redistribute it or a diff of it.
  `fix_mn103.py` is our own script, and it edits your checkout (§2).
- Credit: Caduceus is Apache-2.0, so keep our `NOTICE` if you reuse our code, names or docs. Ports built on this groundwork are asked to say so in their README and About text: "Based on Caduceus for the Olympus PEN E-P7 by cakelesscoder" (see `AGENTS.md`).

## 2. Toolchain

Linux is what we test on. Everything installs into one folder in your home directory, with no root needed.
The bootstrap defaults to `~/ep7fw-toolchains/`. Point it elsewhere with the environment variables in §3.

| Tool | Needed for | Get it |
|---|---|---|
| Python 3.10+ | everything | your distribution |
| GNU binutils 2.45 for `mn10300-elf` (`objdump -m am33-2`) | steps 1–4 (sigfind) | `tools/setup_toolchain.sh` (downloads, checks the GNU signature, builds into `~/ep7fw-toolchains/mn10300/`) |
| Ghidra **12.1 or newer** | step 5 | [ghidra-sre.org](https://github.com/NationalSecurityAgency/ghidra/releases). Check the zip's SHA-256 against the release notes |
| JDK **21** (Temurin) | step 5 | [adoptium.net](https://adoptium.net/). Ghidra 12 won't start on an older Java |
| MN103/AM33-2 processor module | step 5 | [nsud-dev/ghidra-mn103](https://github.com/nsud-dev/ghidra-mn103) (GPL-3.0), plus our fix below |
| REA ([morluto/rea](https://github.com/morluto/rea)) | optional, for agents | [REA_SETUP.md](REA_SETUP.md) |

**Installing the MN103 module.** The published module lost every empty `()` somewhere on the way to GitHub.
Ghidra 12's SLEIGH compiler then refuses the spec, and none of its Java scripts compile. `fix_mn103.py` puts the
parentheses back. It changes no decoding and no semantics. We tested it on upstream commit `e07c0d0`, where
it reproduces our working module exactly.

```sh
G=~/ep7fw-toolchains/ghidra                      # your Ghidra install (unzipped ghidra_12.1.x_PUBLIC)
git clone https://github.com/nsud-dev/ghidra-mn103 ~/ep7fw-toolchains/src/ghidra-mn103
cp -a ~/ep7fw-toolchains/src/ghidra-mn103/MN103 $G/Ghidra/Processors/MN103
python3 tools/atlas/fix_mn103.py $G/Ghidra/Processors/MN103 --ghidra $G --javac ~/ep7fw-toolchains/jdk21/bin/javac
$G/support/sleigh $G/Ghidra/Processors/MN103/data/languages/mn103.slaspec   # writes mn103.sla
```

Expect `slaspec: 5 lines fixed` and `scripts compile`. Language id: `MN103:LE:32:AM33-2`. On AM33-2 the
decoder agrees with objdump instruction for instruction. The decompiler is a reading aid only, because Ghidra
can't model MN103's split between data and address registers. [REA_SETUP.md](REA_SETUP.md) "What works on AM33-2"
lists the weak spots.

**Licence note.** The module stays GPL-3.0 in your copy. `fix_mn103.py` is our code (Apache-2.0). It holds no
module source and edits your checkout in place. We don't ship the module or a diff of it.

## 3. Bootstrap

```sh
tools/atlas/bootstrap_body.sh ~/Downloads/OLY_E_140_1100_0000_0000.BIN em10iv            # all five steps
tools/atlas/bootstrap_body.sh BODY.BIN em5iii --no-ghidra                                # steps 1–4 only
tools/atlas/bootstrap_body.sh BODY.BIN em1iii --autonames --ep7 ~/fw/OLY_E_142_1100_0000_0000.BIN --rea
```

| Step | What it does | Output (under `~/caduceus-port/<tag>/`) | Time |
|---|---|---|---|
| 1 | Decodes your `.BIN` with `caduceus.py`'s container code. Refuses on a bad header or checksum, and checks the round trip is byte-identical | `decoded/NN_<kind>_<addr>.decoded.bin`, `manifest.json` | 5 s |
| 2 | Finds the main component's CPU base (`sigfind.py base`, below) | `base.txt` | 10 s |
| 3 | Gets the E-P7 1.1 main: `--ep7 FILE`, a copy in the usual places, or a download from OM's own server (the same request `caduceus.py build` makes). SHA-256 checked | `decoded_ep7/` | 0–60 s |
| 4 | `sigfind.py map`, then `check`, then `seeds` | `candidates.json`, `names.json`, `sites.json`, `check.txt`, `seeds.tsv` | 40–60 s (2–3 min with `--autonames`) |
| 5 | Headless Ghidra: import at the base, an uninitialised RAM block up to 0x63000000, the seeds, full auto-analysis, `MN103FixCallFrames`, then `ApplyNames` with the transferred names | `ghidra/<tag>.gpr`, `ghidra/build.log` | 12–15 min |

Options: `--base HEX` overrides step 2. `--autonames` also transfers the string-derived E-P7 names (medium and
high), which roughly quadruples the yield (§6). `--min-conf low|medium|high` sets what step 5 applies (default
`medium`). `--rea` marks the project for REA. Environment: `GHIDRA`, `JAVA_HOME`, `OBJDUMP`, `MEM` (memory cap
for the `systemd-run` scope, default 6G) and `HEAP` (JVM heap, default 4G). Peak JVM RSS on these images stays
under 3 GB.

**Tested end to end** on the E-M5 III 1.7 file (6 GB cap, 4 GB heap): 12.5 min in all. That is 8 min of
analysis plus 2 min of call-frame fixing and re-analysis. The 26,068 seeds made 26,001 functions, and
`ApplyNames` renamed all 354 transferred entries and labelled the 15 sites. Pass `--rea` and REA can open the
project in the same way as the E-P7 one (set `REA_GHIDRA_PROJECT_PATH`, [REA_SETUP.md](REA_SETUP.md)).

**The CPU base matters.** The address in the container header is *not* the CPU address, and the base differs
between bodies. `sigfind.py base` looks for the base at which `mov imm32,aN` operands land on the starts of C
strings. At the right base about 60% of them do, and at any wrong base under 6% do:

| Body | Container address | CPU base | Pointers on a string start |
|---|---|---|---|
| E-P7 1.1 | 0x406a0020 | **0x60020020** | 63.1% |
| E-M10 IV 1.1 | 0x406a0020 | **0x60020020** | 62.7% |
| E-M5 III 1.7 | 0x40780020 | **0x60021020** | 62.4% (agrees with [PORT_EM5III.md](PORT_EM5III.md)) |
| E-M1 III 1.6 | 0x40800020 | **0x60021020** | 56.5% (new: not the E-P7 base, despite what an earlier decode manifest assumed) |

## 4. How sigfind works

For each E-P7 name (the atlas `func` rows, plus `autonames.json` rows with `--autonames`):

1. **Extent.** objdump disassembles from the E-P7 address. The walk stops at a return, or at an unconditional
   jump, once it is past the furthest forward branch inside the function. It never runs past 4 KB.
2. **Mask.** These operands become wildcards, because they change from build to build:
   - call, jump and branch displacements whose target is outside the function;
   - immediates and absolute addresses that point into the image, RAM, flash or uncached RAM
     (0x4…, 0x6… and 0xa… ranges).
   Opcodes, registers, stack offsets, struct offsets, small constants, setting ids and MMIO addresses stay
   fixed. Those are what make two builds of one function look alike.
3. **Notes.** It records the C strings the function loads (its *anchors*) and its call list.

Then it tries three methods in turn on your image:

| Method | Rule | Base score |
|---|---|---|
| `sig` | The masked signature (the first 96 bytes, with at least 12 of them fixed) is unique in the E-P7 image **and** occurs exactly once in yours | 0.97 |
| `sig64`, `sig48`, `sig32` | Only a shorter prefix matches, with the same two uniqueness rules | 0.88 down to 0.80 |
| `anchor` | A string the function loads is in your image. Its references give a candidate entry at the same offset, or the nearest call target before the reference. Kept if at least 60% of the fixed bytes agree | 0.55–0.95 |
| `call` | A matched caller (score 0.75+) calls this function. The two callers' listings are aligned instruction by instruction, and the call at the aligned position gives the target. Kept if the bytes there look like the function, or if two callers agree | 0.45–0.94 |

Every candidate is then disassembled on your image, and its mnemonic sequence is compared with the E-P7 one
(`struct`, a difflib ratio from 0 to 1). The final `score` is the base score × (0.6 + 0.4 × struct). Two
penalties apply: × 0.8 when a call vote disagreed, and × 0.7 when two E-P7 names landed on one address.
Candidates with struct < 0.3 are dropped, because both misses in our samples were of that kind.
Confidence: **high** ≥ 0.9, **medium** ≥ 0.75, **low** otherwise.

**Entries and sites.** Some atlas `func` rows are mid-function sites (a patch point, a call site). A row
counts as an entry when it is a call target in the E-P7 image, a task entry, or sits right after a return,
an unconditional jump or padding. Against the E-P7 Ghidra project that rule gets 519 of 529 entries right and
29 of 60 sites. Entries go to `names.json`, which `ApplyNames` uses to rename functions. Sites go to
`sites.json`, which it uses for labels. `seeds.tsv` includes every entry address, so step 5 makes a function
at each transferred entry. `sigfind.py seeds` on the E-P7 itself reproduces the 24,765 seeds of our own project
exactly.

## 5. Reading and verifying the candidate map

`candidates.json` has one row per transferred name:

```json
{"ep7_addr": "0x60634fbc", "name": "fopen", "entry": true, "other_addr": "0x60634d6b", "score": 0.94,
 "method": "call", "confidence": "high", "struct": 1.0, "shift": -593, "origin": "atlas", "detail": "callers=3 sim=1.00"}
```

`shift` is `other_addr − ep7_addr`. Code keeps its order within a region, so neighbouring rows usually share a
shift. A row whose shift is far from its neighbours' deserves a look, though a reshuffled section can make true
rows do that too (on the E-M5 III, section 6 comes in two interleaved shift families). `detail` tells you
what the decision rested on: `fixed=` is the number of fixed bytes matched, `strings=` the number of anchor
strings, `sim=` the byte similarity, `conflict=` and `dup-target` the penalties.

**Three checks, in order of cost:**

1. **`sigfind.py check candidates.json --dst MAIN [--truth known.json]`** (the bootstrap saves it as
   `check.txt`). It runs three independent checks per method and confidence:
   - **strings**: the E-P7 function and yours load the same C string. Signatures mask string pointers, so
     this check doesn't depend on how the row was matched;
   - **shift**: the row's shift agrees with its neighbours' (a weak check);
   - **truth**: the row agrees with addresses you already trust. The file is a JSON object of
     `{ep7_addr: your_addr}` pairs.
2. **`sigfind.py show candidates.json --dst MAIN --sample 15`** (or `--name fopen`). It prints the two
   listings side by side, plus each side's anchor strings. A right row looks the same down the page, apart
   from masked operands. Ours had the same registers, the same stack frame size and the same struct offsets
   and constants. A wrong row diverges in the first few lines. Keep these listings on your screen: they are
   disassembly, so don't paste them into an issue.
3. **Before patching anything,** verify the exact bytes you will change with objdump at your base:
   `mn10300-elf-objdump -b binary -m am33-2 -D --adjust-vma=BASE --start-address=A --stop-address=B MAIN`.
   A name match says the code looks alike. It does not say an E-P7 patch is safe on your body
   ([FIRMWARE_GUIDE.md](FIRMWARE_GUIDE.md) §12, [BODIES.md](BODIES.md) for the test order on a camera).

What to trust: **high** rows are right in every check we ran. Treat **medium** rows as right but glance at
them, and treat **low** rows as hints (both sample misses were low, §6). `ApplyNames` applies transferred
names with source ANALYSIS, so any name you set yourself always wins, and rerunning it is safe.

## 6. Validation: what transfers and what doesn't

We tested on three bodies, using the E-P7 1.1 atlas (589 `func` names in the image) and, with `--autonames`, the
atlas plus the medium and high string-derived names (2,145 in all).

**Yield** (rows by confidence, high / medium / low):

| Body (base) | Atlas only | High + medium | With `--autonames` | High + medium | Run time |
|---|---|---|---|---|---|
| E-M10 IV 1.1 (0x60020020) | 393 / 67 / 19 | **460 (78%)** | 1,764 / 181 / 60 | **1,945 (91%)** | 30 s / 90 s |
| E-M5 III 1.7 (0x60021020) | 259 / 110 / 30 | **369 (63%)** | 1,151 / 443 / 125 | **1,594 (74%)** | 30 s / 155 s |
| E-M1 III 1.6 (0x60021020) | 206 / 73 / 17 | **279 (47%)** | 271 / 78 / 22 | **349 (16%)** | 30 s / 120 s |

35 atlas names (39 with autonames) have under 12 fixed bytes, mostly tiny stubs and thunks, and are skipped.

**Precision.**

- *Ground truth.* The E-M10 IV has 14 atlas functions whose addresses were already worked out by hand
  (`tools/port_em10iv_map.py`, [PORT_EM10IV.md](PORT_EM10IV.md)): malloc, free, fopen/fclose/fseek/ftell/fread,
  get_tid, the setting getter, the COLOR builder, the job callback, the TRIG tracker, the validator and the
  text setter. sigfind gets **14/14**, 13 by `sig` and fopen by `call`.
- *Manual sample*, 15 per body drawn at random across methods, with each pair read side by side. A row
  counts as right when the two listings agree in structure, and in their strings where there are any:

| Body | Right | Misses |
|---|---|---|
| E-M10 IV | 14/15 | `wdt_flashop`, a mid-function site matched by `anchor` at low confidence, landed 9 bytes off: the code before it differs |
| E-M5 III | 15/15 | none. Two (`task_PER_SLOPE`, `REC_VIEW_CPU2`) are right by structure only; they load no strings |
| E-M1 III | 14/15 | `task_PLAY_LOAD`, `anchor`, low (struct 0.03): the string was found but the entry wasn't |

  Both misses were low confidence with struct near 0, so the `--min-struct 0.3` filter now drops them.
- *String check* (`sigfind.py check`, every row whose E-P7 function loads a string). It's an independent test
  because signatures mask string pointers. High and medium rows that pass it, with autonames:
  E-M10 IV **1,603/1,605**, E-M5 III **1,318/1,321**, E-M1 III **143/144**. The few failures we read were the
  right function with changed log text (`gui_WinMain` on the E-M5 III), or a format string that our C-string
  test doesn't recognise. Low rows pass between 36% (E-M1 III) and 100% (E-M10 IV). That is why `low` is never applied by default.

**What transfers well:**

- **The C core**: RTOS and kernel wrappers, heap, file I/O, the settings store and its flash writers, the JPEG and
  EXIF writers, and most of the image pipeline. By subsystem, E-M10 IV 68–95% (high + medium), E-M5 III 60–85%, E-M1 III 55–80%.
  Struct offsets usually survive (the job offsets don't; see FIRMWARE_GUIDE §12).
- **Task entries** (`task_*`): distinctive frame setup and log strings. 97 of 123 on the E-M10 IV, 73 on the
  E-M5 III, 63 on the E-M1 III (the rest are missing, changed or compressed on those bodies).
- **The C++ GUI and app layers by name**: `Class::method` names carry their own strings, so `anchor` finds them
  even where the code was rebuilt (E-M10 IV 143, E-M5 III 501).

**What doesn't:**

- **Anything compressed.** On the E-M1 III, the UI (2/100), OSD (0/23) and updater (1/8) names don't transfer
  at all, because that code isn't in plain form in the image (§9).
- **Body-specific UI.** Menu pages, OSD tables and the COLOR profile editor transfer on the E-M10 IV (74% of UI
  names), and only half as well on the E-M5 III, which has a different UI generation. The menu *ids* and
  string ids behind them never transfer: re-derive them ([FIRMWARE_GUIDE.md](FIRMWARE_GUIDE.md) §12.4).
- **Lens, AE and capture glue** on the older bodies (E-M5 III and E-M1 III, about 40–55%): different sensors
  and lens protocols.
- **Mid-function sites** (patch points). They transfer only when the surrounding code is identical. Always
  re-find a patch site by its bytes, not by the name.
- **Data, tables and RAM addresses** aren't attempted: sigfind maps code. For a RAM word, map a function that
  uses it, then read the operand at the same instruction (the method in `tools/port_em10iv_map.py`).

## 7. Contributing names back

Use one atlas format for every body, so names, tools and the Control Panel stay shared ([AGENTS.md](../AGENTS.md)).

- **Your body's atlas** lives in your port's repo as `atlas.json`, in the same format as
  [atlas.json](atlas.json): a header with `firmware` and `cpu_base`, then `symbols` rows of
  `{addr, name, kind (func|table|data|struct|site), subsystem, confidence (V|C|I), sig, notes, source}`.
  Tags as in FIRMWARE_GUIDE: **V** checked in bytes or the emulator, **C** proven on a camera, **I** inference.
- **Keep the E-P7 name** for the same function, so a name means one thing on every body. Put the E-P7 address
  in `notes` (`= E-P7 0x60634fbc`). New functions get new names. If the E-P7 name turns out wrong, fix it here
  (issue or PR) rather than renaming on your side.
- **Promote transferred rows deliberately.** `names.json` rows are proposals. Move a row into your atlas once
  you have looked at it (`show`, or your own reading), and tag it `V` once you depend on its bytes.
- **Names you find on your body can come back to the E-P7.** sigfind isn't E-P7-specific: swap the roles with
  `sigfind.py map --src YOUR_MAIN --src-base YOUR_BASE --dst E-P7_MAIN --atlas your/atlas.json`. Open an issue or PR
  here with the resulting `names.json` (names and addresses only) and we merge what checks out, with credit in
  `NOTICE`.
- **Never attach** listings, decompiler output, signature caches or firmware bytes to an issue or PR, even
  short ones, except a patch site's few expected bytes.

## 8. Design decisions

**No precomputed signature file.** A masked signature is still a run of verbatim firmware bytes. Only operands
are blanked, and in the atlas signatures a median of 81% of the bytes stay fixed (71–90% for the middle half).
A file covering 2,000 functions at 96 bytes each would be about 150 KB of OM's code with holes in it.
Shortening the signatures until they are "not a copy" would cost exactly the uniqueness the method needs.
Measured on the E-P7 image itself, a signature cut to its first 8 fixed bytes is unique for 75% of functions,
16 bytes for 90%, and 32 bytes for 95%. Those are losses before any other body is even searched. Meanwhile, anyone can get the E-P7 1.1 file from OM for free, and the bootstrap fetches it
from OM's own server. So the conservative choice costs nobody anything. Signatures are built in memory at run
time. `--cache FILE` saves them for speed, and that file is private: never publish it.

**objdump, not our own decoder.** GNU binutils is the reference AM33-2 decoder, and everyone porting already needs it
for `tools/dis.sh`-style checks. A home-made length decoder would add a second source of error.

**A conservative score.** A row is only `high` when the signature is unique on *both* images, or when a string
anchor and the structure agree. The rest of the yield goes to `medium` and `low`. Unique-on-both is the
rule that made the E-M10 IV ground truth come out 14/14.

**Function seeds from a linear sweep**, the way the E-P7 project was built (call targets with two or more call
sites, plus every `calls imm` target), plus every transferred entry. Table-only code (task entries, menu
handlers, vtables) is still missing from such a project. The transferred names recover the parts of it that the
atlas knows.

## 9. Open items

- **E-M1 III compressed regions.** About a quarter of the E-M1 III main is high-entropy (7.4 bits per byte at
  offsets 8–10, 13–14 and 20–21 MB), and none of the GUI strings are in plain text (`GPIInitPlatform`,
  `SsMenuLv_*`, `IGui_Controler`: absent in every component). The GUI, OSD and updater layers are probably
  compressed and unpacked at boot. sigfind can't see into them. Finding the decompressor would be the next
  step for that body (not attempted here).
- **Speed with `--autonames`.** The search costs one regex scan of each image per signature and prefix
  length. On a body that shares less code (E-M5 III, E-M1 III), more signatures fall through to the shorter
  prefixes, and a run takes several minutes. Caching the E-P7-side uniqueness test would halve that.
- **Sites.** 31 of the 60 E-P7 mid-function sites look like entries to the heuristic in §4, so they are
  proposed as function names. ApplyNames then renames whatever function Ghidra put there, or skips the row.
  A site list kept in atlas.json (`kind: site`) would settle it.
- **`apply_names.py`** (PyGhidra) is still only syntax-checked. The bootstrap uses `ApplyNames.java`.
