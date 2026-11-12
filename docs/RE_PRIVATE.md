# What stays private, and where it lives

The reverse-engineering work produces two kinds of material. Only one of them may ever be published.

| Public (repo, GitHub, handoff to other ports) | Private (never published) |
|---|---|
| Addresses, names, signatures, record layouts (`docs/ATLAS.md`, `atlas.json`) | OM firmware files and decoded components (`stock_firmware/`, `analysis/`) |
| Our own prose and our own paraphrased pseudocode (`docs/RE_*.md`) | Ghidra projects (`~/ep7fw-toolchains/projects/`) |
| Our scripts: label appliers, signature finders, verifiers, patches | Decompiler output and long disassembly listings (`~/ep7fw-private/decomp/`) |
| Short instruction quotes needed to check a patch site | Built packages (`generated/`, `out/`, `cache/`) |

**Why.** Decompiled or disassembled OM code is a derivative of their copyrighted firmware, and the OM EULA forbids
redistributing the firmware (FIRMWARE_GUIDE §13). Facts about it, such as addresses, layouts and how it behaves,
written in our own words, are ours to share. Anyone can rebuild the Ghidra project from their own OM download
(`~/ep7fw-toolchains/projects/ep7_1100/build_project.sh`, about 12 min) and apply our labels, so other ports lose
nothing.

## Where things are kept

| Material | Local (working copy) | NAS backup (path in `~/.config/caduceus/nas_path`, not in the repo) |
|---|---|---|
| Repo, including `.git` and the git-ignored firmware/analysis | `~/projects/ep7-firmware` | `repo/caduceus-ep7/` |
| Decompiled code and RE scratch notes | `~/ep7fw-private/` (`decomp/<topic>/<addr>_<name>.c`) | `private/ep7fw-private/` |
| Ghidra projects | `~/ep7fw-toolchains/projects/` | `private/ghidra-projects/` |
| Toolchain recipe (REA/MN103 patches, wrappers, fix scripts) | `~/ep7fw-toolchains/{bin,tools,ghidra_scripts,src/ext,src/*.patch}` | `private/toolchain/` |

Downloads (Ghidra, JDK, binutils source) aren't backed up because they can be fetched again. `REA_SETUP.md` lists them.

- **Back up:** `tools/backup_nas.sh`. It only copies and never deletes on the NAS. `LAST_BACKUP` holds the date.
- **Why we work locally:** Ghidra, git and builds run on the local disk. The SMB share is too slow for them, and
  Ghidra project locks are unreliable over SMB.

## Guard rails

- **Commit hook:** `tools/hooks/pre-commit` (enabled with `git config core.hooksPath tools/hooks`). It refuses
  private paths, and files with 8 or more Ghidra auto-names (`undefined4`, `uVar3`, `unaff_`, `extraout_` and so on).
  If it fires, rewrite the content in your own words. Use `--no-verify` only when you are sure it's a false
  positive.
- **Agent rule** (every RE brief): decompiler output goes to `~/ep7fw-private/decomp/`. Docs carry only our own
  prose, plus a pointer to the private file.
- **Handoff to other ports** (round R4 in `RE_ROUNDS.md`): ship `atlas.json`, the label-apply script and the
  signature finder. Never ship a project file or exported C.
