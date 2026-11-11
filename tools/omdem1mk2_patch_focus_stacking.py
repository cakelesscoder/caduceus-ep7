#!/usr/bin/env python3
"""
Olympus OM-D E-M1 Mark II (v3.70 / Model 125) Focus Stacking Limit Removal Tool.

This script patches the in-camera Focus Stacking compatibility check routine
(fcs_check_focus_stacking_enable) in Partition 0 (0x100 Main RTOS code).
By replacing the allowlist-rejection conditional branch at offset 0x635a2a
(0x60656a4a) with NOP instructions (0xcbcb), in-camera focus stacking is
unlocked for ALL autofocus lenses (Olympus non-PRO lenses, Panasonic, Sigma, etc.).
"""

import argparse
import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List

DECODE_ORDER = (1, 3, 0, 2, 6, 4, 7, 5, 11, 10, 9, 8, 13, 14, 12, 15)
INVERT = bytes(i ^ 0xFF for i in range(256))

BASE_VMA = 0x60021020

# Partition 0 Focus Stacking check location in v3.70
STACKING_PATCH_OFFSET = 0x635a2a
STOCK_BYTES = bytes.fromhex("c904")   # BNE +4 (skips stacking enable flag assignment)
PATCH_BYTES = bytes.fromhex("cbcb")   # NOP NOP (falls through to mov 1, d0)


@dataclass
class ContainerBlock:
    offset: int
    header: bytes
    payload: bytes
    trailer: bytes
    kind: int
    address: int
    version: int


def decode(data: bytes) -> bytes:
    if len(data) % 16:
        raise ValueError("payload is not a multiple of 16 bytes")
    result = bytearray(len(data))
    for output_index, input_index in enumerate(DECODE_ORDER):
        result[output_index::16] = data[input_index::16].translate(INVERT)
    return bytes(result)


def encode(data: bytes) -> bytes:
    if len(data) % 16:
        raise ValueError("payload is not a multiple of 16 bytes")
    result = bytearray(len(data))
    for input_index, output_index in enumerate(DECODE_ORDER):
        result[output_index::16] = data[input_index::16].translate(INVERT)
    return bytes(result)


from array import array

def sum32(data: bytes) -> int:
    if len(data) % 4:
        raise ValueError("checksum data is not a multiple of 4 bytes")
    words = array("I")
    words.frombytes(data)
    if sys.byteorder != "little":
        words.byteswap()
    return sum(words) & 0xFFFFFFFF


def parse_container(raw: bytes) -> List[ContainerBlock]:
    if not raw:
        raise ValueError("empty image")
    blocks = []
    offset = 0
    model = None
    while offset < len(raw):
        if len(raw) - offset < 64:
            raise ValueError(f"truncated block at {offset:#x}")
        header = raw[offset:offset + 32]
        if header[:2] != b"OE":
            raise ValueError(f"unsupported signature at {offset:#x}")
        if model is None:
            model = header[2:4]
        elif model != header[2:4]:
            raise ValueError(f"mixed model identifiers at {offset:#x}")
        
        address = struct.unpack_from("<I", header, 8)[0]
        size = struct.unpack_from("<I", header, 12)[0]
        version = struct.unpack_from("<H", header, 16)[0]
        kind = struct.unpack_from("<H", header, 20)[0]
        
        if not size or size % 16:
            raise ValueError(f"invalid payload size at {offset:#x}")
        end = offset + size + 64
        if end > len(raw):
            raise ValueError(f"payload exceeds image at {offset:#x}")
            
        trailer = raw[end - 32:end]
        if header[:28] != trailer[:28]:
            raise ValueError(f"header/trailer mismatch at {offset:#x}")
        if header[28:32] != b"\0" * 4:
            raise ValueError(f"unexpected header checksum field at {offset:#x}")
            
        payload = decode(raw[offset + 32:end - 32])
        if (sum32(header) + sum32(payload) + sum32(trailer)) & 0xFFFFFFFF != 0:
            raise ValueError(f"checksum mismatch at {offset:#x}")
            
        blocks.append(ContainerBlock(
            offset=offset,
            header=header,
            payload=payload,
            trailer=trailer,
            kind=kind,
            address=address,
            version=version
        ))
        offset = end
    return blocks


def assemble_container(blocks: List[ContainerBlock]) -> bytes:
    buf = bytearray()
    for b in blocks:
        trailer = bytearray(b.trailer)
        trailer[28:32] = b"\0" * 4
        checksum = -(sum32(b.header) + sum32(b.payload) + sum32(trailer)) & 0xFFFFFFFF
        struct.pack_into("<I", trailer, 28, checksum)

        enc_payload = encode(b.payload)

        buf.extend(b.header)
        buf.extend(enc_payload)
        buf.extend(trailer)
    return bytes(buf)


def patch_firmware(input_path: Path, output_path: Path, dry_run: bool = False):
    print(f"[*] Reading source firmware from {input_path}...")
    raw = input_path.read_bytes()
    blocks = parse_container(raw)
    print(f"[+] Loaded container with {len(blocks)} partitions.")

    # Partition 0 is kind 0x100
    p0 = blocks[0]
    if p0.kind != 0x100:
        raise ValueError(f"Expected block 0 kind 0x100, got {p0.kind:#x}")

    print(f"[*] Checking Partition 0 (Length: {len(p0.payload):,} bytes)...")
    curr_bytes = p0.payload[STACKING_PATCH_OFFSET:STACKING_PATCH_OFFSET+2]
    vma = BASE_VMA + STACKING_PATCH_OFFSET

    if curr_bytes == PATCH_BYTES:
        print(f"[!] Firmware is ALREADY PATCHED at {vma:#x} (offset {STACKING_PATCH_OFFSET:#x}).")
        return
    elif curr_bytes != STOCK_BYTES:
        raise ValueError(
            f"Unexpected bytes at offset {STACKING_PATCH_OFFSET:#x} ({vma:#x}): "
            f"expected {STOCK_BYTES.hex()}, found {curr_bytes.hex()}."
        )

    print(f"[+] Target found: offset {STACKING_PATCH_OFFSET:#x} ({vma:#x}): {curr_bytes.hex()} -> {PATCH_BYTES.hex()}")
    if dry_run:
        print("[*] Dry run requested. Exiting without writing changes.")
        return

    # Apply patch to payload
    payload_mod = bytearray(p0.payload)
    payload_mod[STACKING_PATCH_OFFSET:STACKING_PATCH_OFFSET+2] = PATCH_BYTES
    p0.payload = bytes(payload_mod)

    print("[*] Rebuilding container and recalculating additive checksums...")
    repacked = assemble_container(blocks)

    # Verification
    print("[*] Verifying roundtrip integrity of repacked binary...")
    vblocks = parse_container(repacked)
    assert len(vblocks) == len(blocks), "Partition count mismatch after repacking"
    assert vblocks[0].payload[STACKING_PATCH_OFFSET:STACKING_PATCH_OFFSET+2] == PATCH_BYTES, "Patch verification failed"
    assert len(repacked) == len(raw), "Repacked binary length mismatch"
    print("[+] Repacked container verified successfully!")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(repacked)
    print(f"[+] Successfully wrote patched firmware to: {output_path}")
    print(f"    Size: {len(repacked):,} bytes")


def main():
    parser = argparse.ArgumentParser(
        description="Olympus OM-D E-M1 Mark II v3.70 Focus Stacking Limit Removal Tool"
    )
    parser.add_argument("input", nargs="?", default="E1259999.BIN", help="Path to input E1259999.BIN")
    parser.add_argument("-o", "--output", default="output/E1259999_STACKING_PATCHED.BIN", help="Path to output BIN")
    parser.add_argument("--dry-run", action="store_true", help="Inspect without modifying")
    args = parser.parse_args()

    input_file = Path(args.input)
    output_file = Path(args.output)

    if not input_file.is_file():
        sys.exit(f"Error: input file {input_file} does not exist.")

    patch_firmware(input_file, output_file, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
