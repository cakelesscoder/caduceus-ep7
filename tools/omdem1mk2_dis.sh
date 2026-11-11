#!/usr/bin/env bash
# Disassemble E-M1 Mark II (v3.70) Partition 0 by CPU address.
#   scripts/dis.sh 0x603e9bc0 0x603e9c60 [image]
# Image defaults to the stock decoded partition. Requires mn10300-elf binutils
# (build with caduceus-ep7/tools/setup_toolchain.sh).
set -euo pipefail
cd "$(dirname "$0")/.."
OBJDUMP=${OBJDUMP:-$HOME/ep7fw-toolchains/mn10300/bin/mn10300-elf-objdump}
IMG=${3:-em1mk2/extracted/00_0100_40560020.decoded.bin}
"$OBJDUMP" -b binary -m am33-2 -D --adjust-vma=0x60021020 \
  --start-address="$1" --stop-address="$2" "$IMG" | tail -n +8

