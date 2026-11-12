# Bulk decompile and auto-naming (round R1.5)

Round R1.5 of [RE_ROUNDS.md](RE_ROUNDS.md). It does two things:

- Every function in the saved E-P7 1.1 Ghidra project is decompiled into a private, greppable corpus.
- Functions get names from the atlas, the task table and the firmware's own trace and log strings.

Only the **name map** ([autonames.json](autonames.json)) and **our scripts** are public. The corpus and the
named Ghidra project stay private ([RE_PRIVATE.md](RE_PRIVATE.md)).

| File | What | Public? |
|---|---|---|
| `tools/atlas/DecompileAll.java`, `decompile_all.sh` | Headless bulk decompile with index, strings and failure log | yes (our code) |
| `tools/atlas/autoname.py` | Name proposer (reads the private index, writes the public name map) | yes |
| `tools/atlas/apply_names.py` | Applies atlas.json and autonames.json to anyone's own import (PyGhidra, or Jython on older Ghidra) | yes |
| `tools/atlas/ApplyNames.java` | The same rules in Java, for headless runs without PyGhidra | yes |
| `docs/autonames.json` | `{addr, name, method, confidence}` rows only: no code, no strings | yes |
| `~/ep7fw-private/decomp/full/` | The corpus (see below) | **no** |
| `~/ep7fw-private/decomp/autoname/evidence.tsv` | The evidence behind each proposal, for review | **no** |
| `~/ep7fw-toolchains/projects/ep7_1100_named/` | Copy of the project with every name applied | **no** |

## 1. The corpus

`tools/atlas/decompile_all.sh [project_dir] [project_name] [outdir] [threads] [timeout_s]` opens the project
`-readOnly -noanalysis`, so nothing is saved. It runs under `systemd-run --user --scope -p MemoryMax=7G -p
MemoryHigh=6G` with a 5 GB heap, and it refuses to write anywhere outside `~/ep7fw-private/`.
`DecompileAll.java` makes one index pass and then decompiles on a pool of 4 workers. Each worker has its own
`DecompInterface`, which is recycled every 4,000 functions and after any timeout. The timeout is 30 s per
function.

Layout of `~/ep7fw-private/decomp/full/`:

- `c/<range>.c`: one file per 256 KB of address space (83 files). Functions appear in address order, each headed by
  `// ==== FUNC 0x<addr> <name> size=<n> callers=<n> callees=<n>`. To find one:
  `grep -n 'FUNC 0x600227b4' c/*.c`. To find a name anywhere, including call sites: `grep -n scheap_ c/*.c`.
- `index.tsv`: `addr size name ncallers ncallees callers callees strings`. One row per function. Callers and
  callees are comma-separated entry addresses. Strings are escaped and joined with ` ¦ `.
- `strings.tsv`: `func str_addr string`. One row per referenced C string, from explicit references plus
  32-bit scalar operands that land on a NUL-terminated printable string, because MN103 loads string addresses
  as `mov imm32,aN`. This is autoname's main input.
- `failures.tsv`: `addr name reason seconds`.
- `run.log`: progress per range, plus totals.

**Measured** (22-core machine, shared with two other REA agents):

| Run | Functions | OK | Failed | Wall time | Output |
|---|---:|---:|---:|---:|---:|
| Pass 1, unnamed project | 56,231 | 56,116 | 115 | 524 s (8.7 min) | 78 MB |
| Pass 2, after the atlas pass (+209 functions) | 56,440 | 56,325 | 115 | 555 s | 78 MB |
| Final, fully named project (`full/`, qualified `Class::method` names in headers and index) | 56,440 | 56,325 | 115 | 536 s | 79 MB |

- The index pass takes 17 s. JVM plus decompiler RSS stayed around 2–3.5 GB.
- Almost all the time goes on false functions in data, mainly the string region 0x60f40000–0x60f80000 (836
  "functions", about 3 minutes of timeouts there).
- Failures: 62 "Cannot properly adjust input varnodes", 27 "Flow exceeded maximum", 15 timeouts, 3 others. They
  are nearly all in data regions.
- 0.2% of functions fail. A failed function keeps its header plus a `// DECOMPILE FAILED: reason` line, so it
  can still be found with grep.

Earlier passes are kept as `full_pass1/` (unnamed) and `full_pass2/` (atlas only).

## 2. Auto-naming method

`tools/atlas/autoname.py` reads `index.tsv`, `strings.tsv`, `atlas.json` and, optionally, the decoded image for
the task tables. Each address gets at most one name, and each name goes to at most one address. A higher method
wins. When a lower method proposes a name that is already taken, it gets a `_2`, `_3`… suffix and `low`
confidence.

| Method | Rule | Confidence |
|---|---|---|
| `atlas` | `kind: func` symbols in atlas.json. Authoritative | high |
| `task` | Static task table: name table records `{char[24], u16 id}` joined to the 28-B descriptors (entry at +12) | high |
| `cppmethod` | `Class::method` in the function's strings (the C++ UI and app layers trace `Class::method start/end`, `@@@@…Class::method#`, `[GUI …] Class::method …`) | high: 2+ hits, one function, unambiguous; medium otherwise; low if 3+ functions share it |
| `prefix` | C log prefix `name: message` / `name : message` | medium: unique to one function; low if shared |
| `funcstr` | The only bare identifier string in a function, used by it alone, next to a `%s:` / `[%s]` format (the `__func__` pattern) | medium at most |
| `thunk` (`--thunks`) | Exactly one callee, that callee named, size ≤ 24 B: `thunk_<callee>` (≤ 12 B, a bare call and return) or `wrap_<callee>` (also sets a field or two) | low |
| `srcfile` (`--srcfile`, off) | `<module>.c` string: module tag `<module>_<addr>` | low |

Filters, each added after a false positive in the spot checks (§4):

- `Class::CONSTANT` (all-caps member), `x = Class::y` and `a::b()->c()` call chains don't count as a method.
- `foo() Error/failed/ret/arguments…` names a callee, so it is excluded from every method.
- A `DbgSup-function::x` tag gives `x`, not class `function`.
- A prefix needs an underscore or lowerCamel case: `MultiExpose:` was a feature tag.
- A prefix needs a message after the colon. `name:   %x` is a field label.
- A function that prints 3 or more different `word:` labels is a struct dump, so its prefixes are ignored.
- Generic words (`error`, `start`, `mode`, `size`…), ALL-CAPS words and hex-like words are never names.
- `funcstr` needs exactly one bare identifier. Functions with several are shell-command or state tables (round 1:
  0/3 correct).

Run (E-P7 1.1):

```sh
F=~/ep7fw-private/decomp/full
tools/atlas/autoname.py --index $F/index.tsv --strings $F/strings.tsv --atlas docs/atlas.json \
  --out docs/autonames.json --bin analysis/ep7_1100/00_0100_406a0020.decoded.bin --base 0x60020020 \
  --task-desc 0x600389d0 --task-names 0x613ff240 --thunks \
  --debug ~/ep7fw-private/decomp/autoname/evidence.tsv     # private: evidence per row
```

`autonames.json` puts one row per line, so it greps and diffs cleanly. `stats` holds the method/confidence
counts.

## 3. Coverage

The project has 56,440 functions after the atlas pass. Some of them are false functions in data, so the true
total is lower. 10,624 functions reference at least one string, which is the most that string methods can reach.
12,674 have no callers at all: they are reached through tables, or they are false.

| Method | high | medium | low | Total |
|---|---:|---:|---:|---:|
| atlas (function entries / all `func` rows) | 408 / 444 | | | 408 |
| cppmethod (260 classes) | 1,169 | 203 | 81 | 1,453 |
| prefix | | 186 | 23 | 209 |
| thunk / wrap | | | 1,370 | 1,370 |
| funcstr | | 0 | 0 | 0 |
| task | (all 137 already in atlas) | | | 0 |
| **Named** | **1,577** | **389** | **1,474** | **3,440 / 56,440 (6.1%)** |

Without thunks, 2,070 functions are named, and 1,662 of those come from strings. That is 15.6% of the functions
that reference any string. Coverage concentrates where OM's code logs its own name:

- the C++ playback, edit and GUI layers (`OlyHfwOpe*`, `Cmp*`, `CapImg_*`, `GCPnl_*`, `CAvfw*`);
- the album DB (`oldb_*`, `chls_oldb_*`);
- the heap (`scheap_*`);
- MTP (`tpc_mtp_*`).

The C core (image pipeline, AE and the RTOS) mostly logs fixed tags such as `[FLSH]` or `%s (%d):` with
`__FILE__`, not the function name, so it stays mostly unnamed. Those strings still sort functions by module
(`--srcfile`), but that's off by default because the names it makes are tags, not real names.

**Atlas fixes in the named project.** 231 atlas `func` addresses (mostly task entries, reached only through the
descriptor table) had no function in the saved project. The call-target seeding never reached them, so Ghidra
had folded them into a neighbour. `ApplyNames.java -create` made 209 of them into functions. The other 36
atlas func rows are mid-function sites (for example `bss_clear_call`, `wdt_off_on_example`) and got labels. 11
are outside the image (CPU-local RAM such as 0x8050).

## 4. Spot checks (false-positive rate)

The method: draw a stratified random sample from `evidence.tsv`, then judge each one by its strings, its size,
its callees and, for unclear cases, the decompiled body in the private corpus.

**Round 1 (first rules, 20 names): 14/20 correct.**

| Class | Result | Misses |
|---|---|---|
| cppmethod high | 6/6 | none |
| cppmethod medium | 2/3 | `IOlyApiCameraCommon::EV_MEDIA_WRITE_FINISHED` was an enum value in `status = …` |
| cppmethod low | 0/1 | `getInterface()->forwardFrame()` was a call chain |
| prefix medium | 3/4 | `MultiExpose:` was a feature tag in a touch-shooting check |
| prefix low | 1/1 | none |
| funcstr | 0/3 | state and command-table names in a `[%s][%d]` logger and a shell table |
| thunk | 2/2 | none (one is really a wrapper that sets two fields first, hence `wrap_`) |

Each miss became a filter in §2. After the fixes, all six of those addresses get no proposal.

**Round 2 (final rules, fresh sample of 20, no overlap with round 1): 19/20 correct.**

| Class | Result | Notes |
|---|---|---|
| cppmethod high | 7/7 | `…::canMovePage`, `…::setMesScaleOn`, `…::Update_Item`… |
| cppmethod medium | 3/3 | `CAvfwPathController::ForcedDeactivate` judged likely (two classes in its strings) |
| cppmethod low | 0/1 | `GCPnl_Play_WIZ::UpdateGuideItem_3`: right method, but the class is ambiguous (base vs derived trace) |
| prefix medium | 4/4 | `tpc_mtp_opl_put_jpeg_prop_value` checked in the body: it logs its own name in its default case |
| prefix low | 1/1 | none |
| thunk / wrap | 4/4 | correct by construction; chained names such as `thunk_wrap_…` are ugly but true |

**Automatic cross-check against the atlas.** I reran autoname without atlas.json and compared the string names
at the 10 addresses the atlas already names:

- 8 agree. `scheap_phyalloc` is `malloc`, `scheap_phyfree` is `free`, `scheap_alloc` is `alloc_class`,
  `appevent::Wait_Event` is `appevent_get`, and `api_event_check_release_notice` is `trig_tracker` (the
  atlas notes give that same name). `play_load_draw` is the `task_PLAY_LOAD_DRAW` entry, `rcu_serv_upload` is
  `task_BAS_RCU_SRV`, and `Initialize_picture_mode` is `pm_list_builder`.
- 1 was partial: `function::sys_dbg_sup_setting` for `busmon_cfg`. The pseudo-class `function` is now dropped.
- 1 is unclear: `Lv_Control_Mode_Viewer::lv_vertical_select_base` for `menu_label_lookup`. It comes from a
  numbered trace (`2.…`), which may mark a step inside a caller.

**Precision estimate (final rules):**

| Group | Estimate | Basis |
|---|---|---|
| high | ≈ 100% | 13/13 in samples |
| medium | ≈ 95% | 7/7 in round 2, plus the cross-check |
| low cppmethod / prefix | ≈ 50–70% | 1/2 in round 2 |
| low thunk | correct as relations | names are mechanical |

Treat `low` as a hint. `apply_names` applies auto names as source ANALYSIS, so your own names always win, and
`-min-conf medium` leaves the low ones out.

## 5. Named project for REA sessions

`~/ep7fw-toolchains/projects/ep7_1100_named/ep7_1100_named.gpr` is a copy of `ep7_1100` with these changes:

- 209 atlas function entries created;
- all 548 atlas symbols applied (functions renamed, and labels for tables, data and mid-function sites);
- atlas sig and notes as plate comments;
- 3,032 auto names (`Class::method` names inside class namespaces).

The original `ep7_1100` is untouched. Steps to rebuild it, or to refresh it after atlas.json changes (about
15 s plus the copy):

```sh
TC=~/ep7fw-toolchains P=$TC/projects R=~/projects/ep7-firmware
rm -rf $P/ep7_1100_named && mkdir $P/ep7_1100_named
cp -a $P/ep7_1100/ep7_1100.rep $P/ep7_1100_named/ep7_1100_named.rep
cp -a $P/ep7_1100/ep7_1100.gpr $P/ep7_1100_named/ep7_1100_named.gpr
export JAVA_HOME=$TC/jdk21 PATH=$TC/jdk21/bin:$PATH GHIDRA_HEADLESS_MAXMEM=5G
systemd-run --user --scope -p MemoryMax=7G -p MemoryHigh=6G -q $TC/ghidra/support/analyzeHeadless \
  $P/ep7_1100_named ep7_1100_named -process -noanalysis -scriptPath $R/tools/atlas \
  -postScript ApplyNames.java $R/docs/atlas.json $R/docs/autonames.json -create -comments
# then the corpus:  tools/atlas/decompile_all.sh   (defaults to the named project, ~9 min)
```

ApplyNames is idempotent, so you can re-run it on an existing named copy after atlas.json grows. New atlas
names replace the old ones.

To point REA at the named project, set one variable (`rea-ep7` keeps it if it is already set; the program name is
the same). Tested: REA's decompile of 0x6081e1a2 then shows `OlyHfwOpeRsvPrt::reservePrint`.

```sh
export REA_GHIDRA_PROJECT_PATH=~/ep7fw-toolchains/projects/ep7_1100_named/ep7_1100_named.gpr
~/ep7fw-toolchains/bin/rea-ep7 decompile ~/projects/ep7-firmware/analysis/ep7_1100/00_0100_406a0020.decoded.bin \
  --procedure 0x600227b4 --target-format raw-binary --architecture mn103 --entry-point 0x60020020 --provider ghidra --json
```

For the MCP server, add `"env": {"REA_GHIDRA_PROJECT_PATH": "…/ep7_1100_named.gpr"}` to the `rea` entry in
`.mcp.json`. The lead decides whether that becomes the default. As before, REA copies the project and opens the
copy read-only, so the named project is never written.

## 6. Reuse on another body

Nothing in the scripts is specific to the E-P7, except the defaults and the task-table addresses.

1. Build your own project from your own OM download, the way `build_project.sh` does (MN103/AM33-2 bodies), or
   use your existing import.
2. Run `tools/atlas/decompile_all.sh <proj_dir> <proj_name> ~/<private>/decomp/full`. Keep the output private.
   The outdir check expects `~/ep7fw-private/`, so edit the `case` line for another private root.
3. Find your task tables: the name table holds `[A-Z0-9_]` names in 26-B records, and the descriptor table
   holds 28-B records with the entry at +12 (see ATLAS §2.1). Then run:
   `autoname.py --index … --strings … --out <body>_autonames.json --bin <decoded main> --base <cpu base>
   --task-desc <addr> --task-names <addr> --thunks --firmware "<body> <version>"`.
   Leave out `--atlas` until you have your own atlas. **E-P7 atlas addresses don't carry to other bodies.**
4. Apply the names with `apply_names.py` (PyGhidra or Jython, GUI or `pyghidraRun -H`) or `ApplyNames.java`
   (any headless Ghidra). Pass `-` for a file you don't have.
5. The string rules carry over wherever the body shares OM's code base. The `Class::method` trace style and the
   `scheap_` / `oldb_` prefixes are common across the 2019+ bodies [I]. Spot-check about 20 names per body
   before relying on `medium`.

`apply_names.py` has only been syntax-checked here. This machine's Python 3.14 has no JPype wheel in the
Ghidra 12.1.4 bundle, so PyGhidra isn't installed. The named project was built with `ApplyNames.java`, which
follows the same rules line for line.

## 7. Open items

- **Missing entries.** There are still more true entry points missing than the 209 recovered. The same
  table-only reachability applies to the menu handlers and the C++ vtables. A pass over pointer tables
  (vtables near the `Class::` strings, and the display and command jump tables) would add both functions and
  names (round R4 or a follow-up).
- **Duplicate method names.** The 81 low cppmethods are mostly base/derived pairs that log the same
  `Class::method`. Linking them through vtables would settle which is which.
- **False functions.** False functions in the string region (0x60f4xxxx) inflate the function count and cause
  most of the decompile failures. Deleting functions that start inside defined strings would clean up both.
