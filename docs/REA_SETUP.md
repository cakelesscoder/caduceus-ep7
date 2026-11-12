# REA setup for the E-P7 1.1 main image

REA ([morluto/rea](https://github.com/morluto/rea), 6.8.0) is set up as an MCP server for this repo, backed by
Ghidra 12.1.4 and a community MN103/AM33-2 processor module. Agents can list, decompile, xref and search the
E-P7 main image (`analysis/ep7_1100/00_0100_406a0020.decoded.bin`, CPU base 0x60020020) through it. Use
`tools/dis.sh` to check the bytes that matter. The decoder matches objdump, but the decompiler is a reading aid.

## What is installed where

Everything lives under `~/ep7fw-toolchains/`: no sudo, no system-wide installs, no global config.

| Path | What |
|---|---|
| `ghidra_12.1.4_PUBLIC/` (`ghidra` symlink) | Official Ghidra 12.1.4 (zip SHA-256 checked against the release notes) |
| `jdk-21.0.13+9/` (`jdk21` symlink) | Temurin JDK 21. The system Java is 11, which Ghidra 12 can't use |
| `ghidra/Ghidra/Processors/MN103/` | [nsud-dev/ghidra-mn103](https://github.com/nsud-dev/ghidra-mn103) (GPL-3.0), language `MN103:LE:32:AM33-2`, plus local fixes (below). Clean clone in `src/ext/ghidra-mn103/` |
| `src/ext/ghidra-mn103-ghidra12.patch` | Diff of the installed module against upstream |
| `src/rea/` | REA clone, built locally (`npm ci && npm run build:cached`), with a small local patch |
| `src/rea-mn103-local.patch` | That patch: adds raw-binary architecture `mn103` and lets saved projects be reused for it |
| `ghidra_scripts/EP7Seeds.java`, `EP7ReaMark.java` | Project-build helpers (seed functions; mark the import the way REA's raw lane expects) |
| `projects/ep7_1100/` | Saved, fully analysed Ghidra project `ep7_1100.gpr`, plus `build_project.sh`, `seeds.tsv` and `build.log` |
| `bin/rea-ep7` | Wrapper: sets Ghidra/JDK/project env vars and runs REA under a 9 GB memory cap |

Local fixes to the MN103 module: the published repo has every empty `()` stripped. In the SLEIGH spec this broke
4 pcodeop calls (`trap;` and others), which Ghidra 12 refuses to compile. In the Java scripts it broke every
no-argument call. `~/ep7fw-toolchains/tools/fix_mn103_parens.py` and `fix_mn103_javac.py` restored them, and all 11 scripts now
compile. No decoding or semantics were changed.

## MCP registration

The registration is project-scoped, in `.mcp.json` at the repo root:

```json
{ "mcpServers": { "rea": { "type": "stdio", "command": "${HOME}/ep7fw-toolchains/bin/rea-ep7", "args": ["mcp"] } } }
```

Claude Code asks once for approval of project servers (`claude mcp get rea` shows "Pending approval" until then).
REA exposes about 255 tools. On first use, the server copies the saved project into a private temp directory and
opens it read-only. The original is never written. Session edits (renames, comments) are discarded on close.

## Querying the E-P7 image

Every call opens the target with the same raw-binary selection:

```json
{"name": "open_binary", "arguments": {
  "path": "<repo>/analysis/ep7_1100/00_0100_406a0020.decoded.bin",
  "format": "raw-binary", "architecture": "mn103", "entry_point": "0x60020020", "provider_id": "ghidra"}}
```

Then use `analyze_function` / `procedure_pseudo_code` (by address, such as `0x600227b4`), `xrefs`,
`list_procedures`, `search_procedures`, `read_bytes` and string search. The same through the CLI:

```sh
T="--target-format raw-binary --architecture mn103 --entry-point 0x60020020 --provider ghidra --json"
M=~/projects/ep7-firmware/analysis/ep7_1100/00_0100_406a0020.decoded.bin
~/ep7fw-toolchains/bin/rea-ep7 decompile $M --procedure 0x600227b4 $T
~/ep7fw-toolchains/bin/rea-ep7 function  $M 0x60022782 $T     # asm + pseudocode + callers/callees + xrefs
```

The first query in a session takes about 5 s to copy and open the project (416 MB). After that, queries return
within a second. Each CLI call is a new session, so it costs about 7 s. With `REA_EP7_FRESH=1`, REA does its own ephemeral import from the entry point alone, which finds far
less code. Don't use it for the full image.

**Rebuilding the project** (when the module or seeds change): `~/ep7fw-toolchains/projects/ep7_1100/build_project.sh`.
It runs under `systemd-run … MemoryMax=9G` with a 7 GB heap and takes **about 12 min**: 1 min import + seeding, 8.5 min auto-analysis (Decompiler
Switch Analysis alone 3.7 min), 2.5 min call-frame fix + re-analysis. Peak JVM RSS stays under 3 GB. The steps:

1. Import with BinaryLoader at 0x60020020.
2. Add an uninitialised RAM block 0x61920020–0x63000000, for labels and xrefs on statics and .bss.
3. Seed functions at 24,765 `call` targets from an objdump sweep (targets with 2 or more call sites, plus every
   `calls imm` target).
4. Run full auto-analysis.
5. Run `MN103FixCallFrames` (callee frames set at the call site) and `EP7ReaMark`.

## What works on AM33-2, and what doesn't

Checked on the full image with REA (project mode), against `tools/dis.sh` and FIRMWARE_GUIDE §2:

- **Decoding: good.** Instruction boundaries match objdump exactly (loader 0x600457e7: 43/43 instructions at the
  same addresses). The module's own test claims 14M instructions identical to binutils 2.42.
- **Functions: 56,232** after analysis. Bodies look right: malloc 0x60022782 is 50 B and ends at `ret [],4`.
  free 0x600227b4 is 80 B. The loader is 133 B. Call-site frames (`call f,[regs],N`) are modelled as callee entry
  code, so stack frames come out right.
- **Xrefs: good for direct calls.** malloc has 428 callers and free 407. The loader 0x600457e7 shows 0 callers
  because it is reached indirectly. Computed calls (`calls (aN)`) and function-pointer tables don't make edges
  unless Ghidra resolves the table.
- **Decompiler: usable.**
  - malloc shows the ≤128 / ≤2048 / ≤16384 class split and the "scheap_phyalloc: Size Over" string.
  - free shows the pool ranges 0xa1f8d800–0xa1f98540 and 0xa1dd8d40–0xa1e85800, as in §2.
  - The loader reads descriptor table 0x60027068 (12-byte entries) and ORs bit (id−1) into 0xa272e420.
  - The end getter 0x60045786 comes out as a clean `switch` returning every section end in §2's table.
  - Strings resolve (`s_UserSub_FlashReadErr…`).
- **Known weak spots:**
  - Ghidra can't express MN103's "integers in d0/d1, pointers in a0/a1" split. Pointer arguments show as extra
    `param_N`: free's pointer shows as `param_3`, malloc's result as `a0`. Fix hot signatures by hand.
  - Uncached `0xa…` addresses aren't mapped, so they appear as raw `_DAT_a…` constants.
  - Decompiler warnings about flows into unmapped memory come from false seeds or data decoded as code.
  - FPU semantics are untested upstream.
- **REA's `assembly` text drops memory-operand syntax**: `mov d0,(4,sp)` is shown as `mov d0, 0x4`. Ghidra's
  listing has it right. Use `tools/dis.sh` for exact operands. Treat REA's asm lines as addresses and mnemonics
  only.
- **Coverage:** seeds come from a linear sweep, so some false functions exist in data, and code reached only
  through pointer tables may still be missing. `list_procedures` absence doesn't prove absence. A session can add
  names and comments, but they are discarded on close. To keep annotations, rebuild the project or edit it in
  the Ghidra GUI (`~/ep7fw-toolchains/ghidra/ghidraRun`, project `projects/ep7_1100/ep7_1100.gpr`).
- CLI gotcha (zsh): `$T` in the example above doesn't word-split in zsh. Use `${=T}` or write the flags out.

## Not set up

- **IDA:** REA's IDA provider needs a current, licensed IDA with idalib. IDA Free has no MN103. fishcu's
  IDA 4.9 + MN103 under Wine (`external/oly_fw_analysis/tools/ida`) needs a commercial IDA 4.9 licence we don't
  have. The MN10300 module for IDA 9 (`AndThePickles/MN10300-IDA-9`) is Windows/SDK-only and covers base MN10300
  only, without AM33.
- **binwalk/unblob:** not installed. Ghidra handles AM33, so the fallback wasn't needed, and the container is
  already decoded by `tools/decode_stock.sh`.
- The REA patch is local to the clone. `npm`/`npx rea-agents` releases don't know `mn103`. Re-apply
  `src/rea-mn103-local.patch` after updating the clone.

**Default project (2026-11-12):** `rea-ep7` now opens `ep7_1100_named` (atlas + auto names applied, [RE_AUTONAME.md](RE_AUTONAME.md)). Set `REA_GHIDRA_PROJECT_PATH` to `.../ep7_1100/ep7_1100.gpr` for the unnamed original.
