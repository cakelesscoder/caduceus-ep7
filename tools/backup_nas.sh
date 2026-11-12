#!/usr/bin/env bash
# Back up the working repo and the private RE material to the NAS.
#   tools/backup_nas.sh   (target: $NAS, or the path in ~/.config/caduceus/nas_path)
# Skips external/ (re-clone fishcu: git submodule update) and node_modules/ (npm ci).
# Copy-only: never deletes on the NAS, so a bad local state can't wipe the backup.
# Private material (firmware bytes, Ghidra projects, decompiled code) goes to
# private/ and must never be published; see docs/RE_PRIVATE.md.
set -uo pipefail   # no -e: one failed section must not skip the rest
# --inplace: the NAS (SMB, macOS-compat) rejects rsync temp names that start with "._"
NAS=${NAS:-$(cat "$HOME/.config/caduceus/nas_path" 2>/dev/null)}
[ -n "$NAS" ] || { echo "Set NAS=<backup dir> or write it to ~/.config/caduceus/nas_path" >&2; exit 1; }
REPO=$(cd "$(dirname "$0")/.." && pwd)
TC=$HOME/ep7fw-toolchains
[ -d "$NAS" ] || { echo "Backup target not reachable: $NAS" >&2; exit 1; }
R="rsync -rlt --inplace --info=stats1 --exclude=__pycache__/ --exclude=*.pyc --exclude=/external/ --exclude=node_modules/ --exclude=/.venv/"
echo "== repo (working tree + .git)"; $R "$REPO/" "$NAS/repo/caduceus-ep7/"
echo "== private: decompiled notes"; $R "$HOME/ep7fw-private/" "$NAS/private/ep7fw-private/"
echo "== private: Ghidra projects"; $R "$TC/projects/" "$NAS/private/ghidra-projects/"
echo "== private: toolchain recipe (patches, wrappers, scripts; not the downloads)"
mkdir -p "$NAS/private/toolchain"
$R "$TC/bin" "$TC/tools" "$TC/ghidra_scripts" "$TC/rea-env.sh" "$TC/src/rea-mn103-local.patch" "$NAS/private/toolchain/"
[ -d "$TC/src/ext" ] && $R --exclude=*.zip --exclude=*.tar.* "$TC/src/ext" "$NAS/private/toolchain/"
date -Is > "$NAS/LAST_BACKUP"; echo "done -> $NAS (check above for rsync errors)"
