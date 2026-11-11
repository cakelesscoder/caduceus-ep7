#!/usr/bin/env python3
"""Generate EM1MOD/LOOKS.BIN and the firmware's built-in looks for the E-M1 Mark II.

Since v0.3 the card file IS the E-P7 LOOKS.BIN v3 (tools/ep7_looks_bin.py, webapp/src/format.ts
encodeLooksBin): one file for both cameras.
  header 64 B: 'EP7B', u16 3, u16 64, u32 1100, u32 64 n, u32 CRC-32 (bytes 0..15 + 20..end),
               E-P7 main SHA prefix 5dd9af16, u16 n, u16 64, u32 layout CRC 0x68068776, 32 zero bytes
  record 64 B: the canonical Caduceus look record (lookRecord):
    +0..11 hue[12], +12..23 light[12] (UI order), +24 grain, +25..27 WB, +28..29 effect, +30 vignette,
    +31 flags (2 = H/L on, colour), +32 tone flag (1: +33 blacks, +34 whites, +35 HL, +36 MID, +37 SH,
    S nibbles +38..43, +44 = 1; 0: raw S[12] at +33..44), +45 class, +46 mask, +47 tint, +48 name[16]
The E-M1 II loader checks magic, version, lengths and CRC, and ignores the E-P7-only fields (+8 build,
+20 SHA prefix, +28 layout CRC). v0.1-v0.2 used an 'EM1B' file with 128-byte slots and Color Creator
vivid/hue at +64/+65; that format is retired.
"""
import json
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

GRAIN_BYTE = {
    "off": 0,
    "global": 0,
    "standard": 6,
    "fine": 1,
    "low": 1,
    "film": 2,
    "medium": 2,
    "med": 2,
    "high": 2,
}

EFFECT_BYTE = {
    "none": 0,
    "bloom": 1,
    "halation": 2,
    "clarity": 3,
}

# Canonical 16 Caduceus recipes (from sim/recipes/library_v2.json & library_v1.json)
CANONICAL_16_IDS = [
    ("lib2_provia",    "Provia"),
    ("lib2_velvia",    "Velvia"),
    ("lib2_astia",     "Astia"),
    ("lib2_cl_chrome", "Cl. Chrome"),
    ("lib2_cl_neg",    "Classic Neg"),
    ("lib_nostalgic",  "Nostalgic"),
    ("lib2_reala",     "Reala Ace"),
    ("lib2_eterna",    "Eterna"),
    ("lib2_bleach",    "Bleach Byp."),
    ("lib2_kchrome",   "Kodachrome64"),
    ("lib2_portra",    "Portra 400"),
    ("lib2_ektar",     "Ektar 100"),
    ("lib2_gold",      "Gold 200"),
    ("lib2_trix",      "Tri-X 400"),
    ("lib2_cinestill", "CineStill800"),
    ("lib2_acros",     "Acros"),
]



def load_canonical_looks() -> list[dict]:
    v1 = json.loads((ROOT / "sim" / "recipes" / "library_v1.json").read_bytes())["recipes"]
    v2 = json.loads((ROOT / "sim" / "recipes" / "library_v2.json").read_bytes())["recipes"]
    all_recipes = {**v1, **v2}
    looks = []
    for rid, display_name in CANONICAL_16_IDS:
        rec = dict(all_recipes[rid])
        rec["display_name"] = display_name
        looks.append(rec)
    return looks


def make_look_record(rec: dict) -> bytes:
    """Build 64-byte canonical Caduceus lookRecord matching webapp/src/format.ts."""
    r = bytearray(64)
    is_mono = rec.get("base", "").startswith("Monochrome")

    hue = rec.get("hue", [0] * 12)
    light = rec.get("light", [0] * 12)
    sat = rec.get("sat", [0] * 12)

    for k in range(12):
        r[k] = int(hue[k]) & 0xFF
        r[12 + k] = int(light[k]) & 0xFF

    r[24] = GRAIN_BYTE.get(rec.get("grain", "off"), 0)

    wb = rec.get("wb_shift")
    if wb:
        r[25] = 1
        r[26] = int(wb.get("a_b", 0)) & 0xFF
        r[27] = int(wb.get("g_m", 0)) & 0xFF

    eff = rec.get("effect")
    if eff and eff.get("type") in EFFECT_BYTE:
        r[28] = EFFECT_BYTE[eff["type"]]
        r[29] = int(eff.get("strength", 1)) & 0xFF

    r[30] = int(rec.get("vignette", 0)) & 0xFF
    r[31] = 0 if is_mono else 2  # FLAG_HL = 2
    r[45] = 1 if is_mono else 0  # CLASS_OFF

    tone = rec.get("tone") or {}
    hl = int(tone.get("highlights", 0))
    mid = int(tone.get("midtones", 0))
    sh = int(tone.get("shadows", 0))
    blk = int(tone.get("blacks", 0))
    wht = int(tone.get("whites", 0))
    # webapp format.ts hasTone: only colour looks carry a tone block (mono: mask 2, no tone)
    has_tone = (not is_mono) and any(v != 0 for v in (hl, mid, sh, blk, wht))

    r[32] = 1 if has_tone else 0
    r[33] = blk & 0xFF
    r[34] = wht & 0xFF
    r[35] = hl & 0xFF
    r[36] = mid & 0xFF
    r[37] = sh & 0xFF
    # Same layout as webapp/src/format.ts lookRecord(). Until 2026-11-10 this wrote the packed
    # nibbles AND raw sat[k] over +33..+44, so colour looks carried saturation in the tone bytes.
    if has_tone:
        r[46] = 1
        for k in range(12):
            r[38 + (k >> 1)] |= (int(sat[k]) & 15) << (4 * (k & 1))
        r[44] = 1
    else:
        r[32] = 0
        r[33:38] = bytes(5)
        if not is_mono:
            for k in range(12):
                r[33 + k] = int(sat[k]) & 0xFF
        r[46] = 2 if is_mono else 3

    name_str = rec.get("display_name") or rec["name"]
    name_bytes = name_str[:15].encode("ascii")
    r[48:48 + len(name_bytes)] = name_bytes
    return bytes(r)


def build_builtin_looks() -> bytes:
    """Return the 1,024-byte (16 x 64B) canonical lookRecord table for firmware inclusion."""
    looks = load_canonical_looks()
    out = bytearray(16 * 64)
    for i, look in enumerate(looks):
        out[i * 64:(i + 1) * 64] = make_look_record(look)
    return bytes(out)


EP7_HDR_LEN = 64
EP7_REC_LEN = 64
EP7_FW_BUILD = 1100
EP7_SHA_PREFIX = bytes.fromhex("5dd9af16")
EP7_LAYOUT_CRC = 0x68068776   # webapp/src/format.ts LAYOUT_CRC


def build_looks_bin() -> bytes:
    """Return EM1MOD/LOOKS.BIN in the E-P7 v3 format (64 + 64 n bytes)."""
    recs = [make_look_record(look) for look in load_canonical_looks()]
    n = len(recs)
    assert 1 <= n <= 32
    buf = bytearray(EP7_HDR_LEN + EP7_REC_LEN * n)
    buf[0:4] = b"EP7B"
    struct.pack_into("<HHII", buf, 4, 3, EP7_HDR_LEN, EP7_FW_BUILD, EP7_REC_LEN * n)
    buf[20:24] = EP7_SHA_PREFIX
    struct.pack_into("<HHI", buf, 24, n, EP7_REC_LEN, EP7_LAYOUT_CRC)
    for j, r in enumerate(recs):
        buf[EP7_HDR_LEN + EP7_REC_LEN * j:EP7_HDR_LEN + EP7_REC_LEN * (j + 1)] = r
    crc = zlib.crc32(bytes(buf[0:16]) + bytes(buf[20:])) & 0xFFFFFFFF
    struct.pack_into("<I", buf, 16, crc)
    return bytes(buf)


def write_builtin_inc(path) -> None:
    """builtin_looks.inc for color_creator_wheel: the same 16 records, used without a card."""
    data = build_builtin_looks()
    assert len(data) == 16 * 64
    lines = ["/* generated by em1mk2/patches/sd_loader/make_looks_bin.py: 16 x 64-byte look records */",
             ".balign 4", "builtin_looks:"]
    for i in range(0, len(data), 16):
        lines.append("    .byte " + ",".join(str(b) for b in data[i:i + 16]))
    Path(path).write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    import sys
    version = sys.argv[1] if len(sys.argv) > 1 else "v0.1"
    data = build_looks_bin()
    for d in [
        ROOT / "releases" / "em1mk2" / version / "card" / "EM1MOD",
        ROOT / "card" / "EM1MOD",
    ]:
        d.mkdir(parents=True, exist_ok=True)
        out_path = d / "LOOKS.BIN"
        out_path.write_bytes(data)
        print(f"Wrote {len(data)} bytes to {out_path} (E-P7 v3, {(len(data) - 64) // 64} looks)")
