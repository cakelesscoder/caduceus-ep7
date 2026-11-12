#!/usr/bin/env bash
# Map your own Olympus/OM body from the E-P7 atlas: decode, find the CPU base, transfer names, build a named
# Ghidra project. Our own script (Caduceus, Apache-2.0). Read-only on your inputs; offline except the optional
# E-P7 download from OM's server. Never talks to a camera. Guide: docs/RE_HANDOFF.md.
#
#   tools/atlas/bootstrap_body.sh BODY.BIN TAG [options]
#     BODY.BIN       your body's stock firmware file from OM (e.g. OLY_E_140_1100_0000_0000.BIN)
#     TAG            short name for the work folder and project, e.g. em10iv
#   options:
#     --ep7 FILE     E-P7 1.1 stock file (OLY_E_142_1100_0000_0000.BIN) or its decoded main
#                    (default: analysis/ep7_1100/…, stock_firmware/…, ./cache/…, ~/Downloads/…, else download from OM)
#     --work DIR     work folder (default ~/caduceus-port/TAG). PRIVATE: it holds firmware and, later, a project
#     --base HEX     CPU base of the main image (default: found by `sigfind.py base`)
#     --autonames    also transfer docs/autonames.json names (string-derived, medium+), not only the atlas
#     --min-conf C   lowest confidence applied in Ghidra: low|medium|high (default medium)
#     --no-ghidra    stop after the name map (steps 1-4); no Ghidra needed
#     --rea          also mark the project for REA (ReaMark.java)
#   environment: GHIDRA (install dir, default ~/ep7fw-toolchains/ghidra), JAVA_HOME (JDK 21),
#                OBJDUMP (mn10300-elf-objdump), MEM (systemd-run MemoryMax, default 6G), HEAP (default 4G)
#
# Steps: 1 decode BODY.BIN (caduceus.py's container code; byte-exact round trip checked)
#        2 CPU base of the main component     3 decode the E-P7 1.1 main (SHA-256 checked)
#        4 sigfind map -> candidates.json, names.json, sites.json; seeds.tsv
#        5 Ghidra: import at the base, RAM block, seeds, auto-analysis, call frames, ApplyNames (needs Ghidra 12.1+
#          and the MN103 module fixed with tools/atlas/fix_mn103.py)
set -euo pipefail
R=$(cd "$(dirname "$0")/../.." && pwd)
A=$R/tools/atlas
die() { echo "bootstrap: $*" >&2; exit 1; }
[ $# -ge 2 ] || { sed -n '2,27p' "$0"; exit 2; }
BIN=$(realpath "$1"); TAG=$2; shift 2
EP7= WORK= BASE= AUTO= MINCONF=medium GH=1 REA=
while [ $# -gt 0 ]; do
  case $1 in
    --ep7) EP7=$(realpath "$2"); shift ;;
    --work) WORK=$2; shift ;;
    --base) BASE=$2; shift ;;
    --autonames) AUTO=1 ;;
    --min-conf) MINCONF=$2; shift ;;
    --no-ghidra) GH= ;;
    --rea) REA=1 ;;
    *) die "unknown option $1" ;;
  esac; shift
done
[[ $TAG =~ ^[A-Za-z0-9_-]+$ ]] || die "TAG must be letters, digits, _ or -"
[ -f "$BIN" ] || die "no such file: $BIN"
WORK=${WORK:-$HOME/caduceus-port/$TAG}
mkdir -p "$WORK/decoded"
case $(realpath "$WORK")/ in "$R"/*) echo "note: $WORK is inside the repo; keep it git-ignored (firmware and projects never go in git)" >&2 ;; esac
export OBJDUMP=${OBJDUMP:-$HOME/ep7fw-toolchains/mn10300/bin/mn10300-elf-objdump}
[ -x "$OBJDUMP" ] || die "objdump not found ($OBJDUMP): build binutils for mn10300-elf (tools/setup_toolchain.sh) or set OBJDUMP"

echo "== 1. decode $(basename "$BIN") -> $WORK/decoded"
python3 -I - "$R" "$BIN" "$WORK/decoded" <<'PY'
import sys, json, hashlib, struct
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import caduceus as C
data = Path(sys.argv[2]).read_bytes()
out = Path(sys.argv[3])
blocks = C.parse(data)                      # refuses on a bad header, trailer or checksum
rt = b''.join(h + C.encode(p) + t for _, h, p, t in blocks)
assert rt == data, 'container round trip is not byte-identical'
man = dict(source=Path(sys.argv[2]).name, source_sha256=hashlib.sha256(data).hexdigest(), roundtrip_identical=True, blocks=[])
for i, (off, h, p, t) in enumerate(blocks):
    k, addr = C.kind(h), struct.unpack_from('<I', h, 8)[0] + 0x20
    name = f'{i:02d}_{k:04x}_{addr:08x}.decoded.bin'
    (out / name).write_bytes(p)
    man['blocks'].append(dict(index=i, kind=hex(k), model=h[2:4].hex(), size=len(p), file=name,
                              sha256=hashlib.sha256(p).hexdigest()))
    print(f'  block {i}: kind {k:#06x} size {len(p):>9d}  {name}')
(out / 'manifest.json').write_text(json.dumps(man, indent=1) + '\n')
PY
MAIN=$(ls "$WORK"/decoded/*_0100_*.decoded.bin | head -1)
[ -f "$MAIN" ] || die "no main component (kind 0x100) in $BIN"

echo "== 2. CPU base of $(basename "$MAIN")"
if [ -z "$BASE" ]; then
  python3 "$A/sigfind.py" base "$MAIN" | tee "$WORK/base.txt"
  BASE=$(sed -n 's/^best bases by scan: \(0x[0-9a-f]*\).*/\1/p' "$WORK/base.txt")
  PCT=$(grep "^base $BASE" "$WORK/base.txt" | sed 's/.*(\([0-9.]*\)%).*/\1/')
  awk -v p="$PCT" 'BEGIN{exit !(p >= 30)}' || die "no base makes string pointers line up (best $BASE at $PCT%); pass --base"
fi
echo "  base $BASE"

echo "== 3. E-P7 1.1 main (the signature source)"
EP7MAIN=$WORK/decoded_ep7/00_0100_406a0020.decoded.bin
if [ ! -f "$EP7MAIN" ]; then
  mkdir -p "$WORK/decoded_ep7"
  for c in "$EP7" "$R/analysis/ep7_1100/00_0100_406a0020.decoded.bin" "$R/stock_firmware/OLY_E_142_1100_0000_0000.BIN" \
           "$R/cache/OLY_E_142_1100_0000_0000.BIN" "$HOME/Downloads/OLY_E_142_1100_0000_0000.BIN" download; do
    [ -n "$c" ] || continue
    [ "$c" = download ] || [ -f "$c" ] || continue
    python3 -I - "$R" "$c" "$EP7MAIN" <<'PY' && break
import sys, hashlib
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import caduceus as C
src, dst = sys.argv[2], Path(sys.argv[3])
if src == 'download':
    data = C.fetch_stock()                     # OM's own server, the same request caduceus.py build makes
else:
    data = Path(src).read_bytes()
if hashlib.sha256(data).hexdigest() == C.STOCK_SHA:
    data = next(p for _, h, p, _ in C.parse(data) if C.kind(h) == 0x100)
if not hashlib.sha256(data).hexdigest().startswith('5dd9af16'):
    sys.exit(f'{src}: not the E-P7 1.1 stock file or its decoded main')
dst.write_bytes(data)
print(f'  E-P7 main from {src}')
PY
  done
fi
[ -f "$EP7MAIN" ] || die "no E-P7 1.1 main; pass --ep7 OLY_E_142_1100_0000_0000.BIN"

echo "== 4. transfer names (sigfind)"
AUTOARG=()
[ -n "$AUTO" ] && AUTOARG=(--autonames "$R/docs/autonames.json" --auto-conf medium)
python3 "$A/sigfind.py" map --src "$EP7MAIN" --dst "$MAIN" --dst-base "$BASE" --atlas "$R/docs/atlas.json" "${AUTOARG[@]}" \
  --out "$WORK/candidates.json" --names-out "$WORK/names.json" --sites-out "$WORK/sites.json" \
  --min-conf "$MINCONF" --firmware "$TAG $(basename "$BIN")"
python3 "$A/sigfind.py" check "$WORK/candidates.json" --src "$EP7MAIN" --dst "$MAIN" | tee "$WORK/check.txt"
python3 "$A/sigfind.py" seeds "$MAIN" --base "$BASE" --extra "$WORK/names.json" --out "$WORK/seeds.tsv"
echo "  map: $WORK/candidates.json   (review with: sigfind.py show $WORK/candidates.json --src $EP7MAIN --dst $MAIN --sample 15)"

[ -n "$GH" ] || { echo "== done (--no-ghidra)"; exit 0; }

echo "== 5. Ghidra project $WORK/ghidra/$TAG.gpr"
GHIDRA=${GHIDRA:-$HOME/ep7fw-toolchains/ghidra}
[ -x "$GHIDRA/support/analyzeHeadless" ] || die "Ghidra not found at $GHIDRA (set GHIDRA); the name map is ready in $WORK"
MN=$GHIDRA/Ghidra/Processors/MN103
[ -d "$MN" ] || die "MN103 module not installed in $GHIDRA (see docs/RE_HANDOFF.md §2)"
export JAVA_HOME=${JAVA_HOME:-$HOME/ep7fw-toolchains/jdk21}
export PATH=$JAVA_HOME/bin:$PATH GHIDRA_HEADLESS_MAXMEM=${HEAP:-4G}
SIZE=$(stat -c %s "$MAIN")
RAM=$(python3 -c "b=int('$BASE',16)+$SIZE; b=(b+15)&~15; print(hex(b), hex(0x63000000-b))")
mkdir -p "$WORK/ghidra"
REAARG=()
[ -n "$REA" ] && REAARG=(-postScript ReaMark.java "$BASE")
RUN=()
command -v systemd-run >/dev/null && RUN=(systemd-run --user --scope -p "MemoryMax=${MEM:-6G}" -q)
"${RUN[@]}" "$GHIDRA/support/analyzeHeadless" "$WORK/ghidra" "$TAG" -import "$MAIN" -overwrite \
  -processor MN103:LE:32:AM33-2 -cspec default -loader BinaryLoader -loader-baseAddr "$BASE" \
  -scriptPath "$MN/ghidra_scripts;$A" \
  -preScript MN103AddRamBlock.java $RAM \
  -preScript SeedFunctions.java "$WORK/seeds.tsv" \
  -postScript MN103FixCallFrames.java \
  -postScript ApplyNames.java "$WORK/sites.json" "$WORK/names.json" -min-conf "$MINCONF" \
  "${REAARG[@]}" -max-cpu 6 2>&1 | tee "$WORK/ghidra/build.log" | grep -E 'SeedFunctions|ApplyNames|atlas:|auto:|REPORT|ERROR' || true
echo "== done: open $WORK/ghidra/$TAG.gpr in Ghidra (ghidraRun). Names from sigfind are proposals: docs/RE_HANDOFF.md §5"
