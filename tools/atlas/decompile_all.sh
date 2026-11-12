#!/usr/bin/env bash
# Bulk-decompile a saved Ghidra project into a PRIVATE corpus (never publish the output: docs/RE_PRIVATE.md).
#   tools/atlas/decompile_all.sh [project_dir] [project_name] [outdir] [threads] [timeout_s] [limit]
# Defaults: the named E-P7 copy, ~/ep7fw-private/decomp/full, 4 threads, 30 s per function.
# Opens the project -readOnly, so nothing is saved. Memory-capped; run one heavy JVM at a time.
set -euo pipefail
TC=$HOME/ep7fw-toolchains
PDIR=${1:-$TC/projects/ep7_1100_named}
PNAME=${2:-ep7_1100_named}
OUT=${3:-$HOME/ep7fw-private/decomp/full}
THREADS=${4:-4}
TIMEOUT=${5:-30}
LIMIT=${6:-0}
HERE=$(cd "$(dirname "$0")" && pwd)
case "$OUT" in "$HOME"/ep7fw-private/*) ;; *) echo "refusing: outdir must be under ~/ep7fw-private/" >&2; exit 2;; esac
mkdir -p "$OUT"
export JAVA_HOME=$TC/jdk21 PATH=$TC/jdk21/bin:$PATH
export GHIDRA_HEADLESS_MAXMEM=${GHIDRA_HEADLESS_MAXMEM:-5G}
exec systemd-run --user --scope -p MemoryMax=7G -p MemoryHigh=6G -q \
  "$TC/ghidra/support/analyzeHeadless" "$PDIR" "$PNAME" -process -noanalysis -readOnly \
  -scriptPath "$HERE" -postScript DecompileAll.java "$OUT" "$THREADS" "$TIMEOUT" 0x40000 "$LIMIT"
