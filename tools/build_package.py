#!/usr/bin/env python3
"""Build a component-selective update package + matching stock restore.

Supports multiple camera models (E-P7, OM-D E-M1 Mark II, etc.) via camera profiles.
OFFLINE. Never contacts a camera. Output names are deliberately NOT SD-loadable
(`*.pkg.bin`); copying to DCOLYMP/E1xx9999.BIN is a separate, manual,
human-approved step.

Edits file (JSON):
  {"camera": "em1mk2",                  # optional, defaults to 'ep7'
   "components": ["0x100"],            # kinds to include (main always first)
   "edits": [{"kind": "0x100", "addr": "0x603549d7", "expect": "aabb", "new": "ccdd",
              "why": "..."}]}
  addr is a CPU address for main (camera's main_base) or "off:0x..." decoded offset.

Checks (all must pass, else nothing is written):
  - stock input SHA-256 exact; container parse + exact round trip
  - every edit's stock bytes match `expect`; no overlapping edits
  - same payload length; metadata (header, trailer[:28]) unchanged
  - output re-parses; every component checksum valid; untouched components
    byte-identical to stock; changed-byte count == sum of edit lengths
  - restore package == exact byte slices of the stock file
"""
import argparse, hashlib, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'external/oly_fw_analysis/tools'))

import cameras

try:
    import oly_container as oc
except ImportError:
    # Fallback to local container helpers from caduceus
    sys.path.insert(0, str(ROOT))
    import caduceus as oc


def sha(b):
    return hashlib.sha256(b).hexdigest()


def resolve(kind, addr, main_base: int):
    if addr.startswith('off:'):
        return int(addr[4:], 16)
    a = int(addr, 16)
    if kind != 0x100:
        raise ValueError('CPU addresses only valid for main (0x100); use off:')
    return a - main_base


def build(spec, stock_bytes, camera=None):
    cam = camera or cameras.get_camera(spec.get('camera'))
    if sha(stock_bytes) != cam.stock_sha:
        raise ValueError(f'stock firmware hash mismatch: got {sha(stock_bytes)}, expected {cam.stock_sha}')
    blocks = oc.parse(stock_bytes)
    # Reconstruct check
    if hasattr(oc, 'reconstruct'):
        if oc.reconstruct(blocks) != stock_bytes:
            raise ValueError('stock round trip failed')
    by_kind = {b.kind if hasattr(b, 'kind') else oc.kind(b[1]): b for b in blocks}
    kinds = [int(k, 16) for k in spec['components']]
    if (0x100 in kinds and kinds[0] != 0x100) or len(set(kinds)) != len(kinds) or any(k not in by_kind for k in kinds):
        raise ValueError('components must be unique and exist (0x100 first if present)')

    def get_payload(b):
        return b.payload if hasattr(b, 'payload') else b[2]

    def get_header(b):
        return b.header if hasattr(b, 'header') else b[1]

    def get_trailer(b):
        return b.trailer if hasattr(b, 'trailer') else b[3]

    def get_offset(b):
        return b.offset if hasattr(b, 'offset') else b[0]

    payloads = {k: bytearray(get_payload(by_kind[k])) for k in kinds}
    spans, total = {}, 0
    for e in spec['edits']:
        k = int(e['kind'], 16)
        if k not in payloads:
            raise ValueError(f'edit for component {e["kind"]} not included')
        off = resolve(k, e['addr'], cam.main_base)
        exp, new = bytes.fromhex(e['expect']), bytes.fromhex(e['new'])
        if len(exp) != len(new) or not new:
            raise ValueError(f'edit {e["addr"]}: expect/new length mismatch')
        if not 0 <= off <= len(payloads[k]) - len(new):
            raise ValueError(f'edit {e["addr"]}: out of range')
        for (a, b) in spans.get(k, []):
            if off < b and a < off + len(new):
                raise ValueError(f'edit {e["addr"]}: overlaps another edit')
        if bytes(get_payload(by_kind[k])[off:off + len(exp)]) != exp:
            raise ValueError(f'edit {e["addr"]}: stock bytes differ from expect')
        spans.setdefault(k, []).append((off, off + len(new)))
        payloads[k][off:off + len(new)] = new
        total += sum(x != y for x, y in zip(exp, new))

    out_blocks = []
    for k in kinds:
        b = by_kind[k]
        orig_p = get_payload(b)
        h = get_header(b)
        t = get_trailer(b)
        new_p = bytes(payloads[k])
        if new_p != orig_p:
            if hasattr(oc, 'replace_payload'):
                nb = oc.replace_payload(b, new_p)
                out_h = nb.header
                out_p = oc.encode(nb.payload)
                out_t = nb.trailer
            else:
                out_h = h
                out_p = oc.encode(new_p)
                out_t = oc.reseal(h, new_p, t)
        else:
            out_h = h
            out_p = oc.encode(orig_p)
            out_t = t
        if out_h != h or out_t[:28] != t[:28]:
            raise ValueError('metadata changed')
        out_blocks.append((out_h, out_p, out_t))

    pkg = b''.join(h + p + t for h, p, t in out_blocks)
    restore = b''.join(stock_bytes[get_offset(by_kind[k]):get_offset(by_kind[k]) + 64 + len(get_payload(by_kind[k]))] for k in kinds)

    # ---- verification of outputs
    re_pkg, re_rst = oc.parse(pkg), oc.parse(restore)
    re_pkg_kinds = [b.kind if hasattr(b, 'kind') else oc.kind(b[1]) for b in re_pkg]
    re_rst_kinds = [b.kind if hasattr(b, 'kind') else oc.kind(b[1]) for b in re_rst]
    if re_pkg_kinds != kinds or re_rst_kinds != kinds:
        raise ValueError('output component list wrong')
    changed = 0
    for nb, sb in zip(re_pkg, (by_kind[k] for k in kinds)):
        nb_h, sb_h = get_header(nb), get_header(sb)
        nb_t, sb_t = get_trailer(nb), get_trailer(sb)
        nb_p, sb_p = get_payload(nb), get_payload(sb)
        if nb_h != sb_h or nb_t[:28] != sb_t[:28]:
            raise ValueError('output metadata differs from stock')
        changed += sum(x != y for x, y in zip(nb_p, sb_p))
    if changed != total:
        raise ValueError(f'changed bytes {changed} != edited bytes {total}')
    for rb, sb in zip(re_rst, (by_kind[k] for k in kinds)):
        if get_payload(rb) != get_payload(sb):
            raise ValueError('restore payload differs from stock')
    return pkg, restore, dict(camera=cam.id, components=[hex(k) for k in kinds], edits=len(spec['edits']),
                              changed_payload_bytes=changed)


def find_stock_file(cam: cameras.Camera) -> Path:
    candidates = [
        ROOT / 'stock_firmware' / cam.stock_name,
        ROOT / 'stock_firmware' / cam.id / cam.stock_name,
        ROOT / 'stock_firmware' / f"omd{cam.id}" / cam.stock_name,
        ROOT / cam.id / 'firmware' / cam.stock_name,
        ROOT / 'cache' / cam.stock_name,
    ]
    for alt in cam.alt_stock_names:
        candidates.extend([
            ROOT / 'stock_firmware' / alt,
            ROOT / 'stock_firmware' / cam.id / alt,
            ROOT / 'stock_firmware' / f"omd{cam.id}" / alt,
            ROOT / cam.id / 'firmware' / alt,
            ROOT / alt,
        ])
    for p in candidates:
        if p.is_file() and p.stat().st_size == cam.stock_size:
            return p
    raise ValueError(f"Stock firmware file for {cam.name} not found. Place {cam.stock_name} in stock_firmware/ or pass --stock.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True, help='new directory')
    ap.add_argument('--camera', type=str, default=None, help='Target camera ID (ep7, em1mk2, etc.)')
    ap.add_argument('--stock', type=Path, default=None, help='Path to stock firmware binary')
    a = ap.parse_args()
    if a.out.exists():
        sys.exit('output directory must not exist')
    spec = json.loads(a.spec.read_text())
    cam = cameras.get_camera(a.camera or spec.get('camera'))
    stock_path = a.stock if a.stock else find_stock_file(cam)
    stock_bytes = stock_path.read_bytes()
    pkg, restore, info = build(spec, stock_bytes, camera=cam)
    a.out.mkdir(parents=True)
    (a.out / 'patched.pkg.bin').write_bytes(pkg)
    (a.out / 'restore-stock.pkg.bin').write_bytes(restore)
    info.update(spec=str(a.spec), spec_sha256=sha(a.spec.read_bytes()), stock_sha256=cam.stock_sha,
                patched_sha256=sha(pkg), restore_sha256=sha(restore), bytes=len(pkg),
                camera=cam.id, camera_name=cam.name,
                camera_contacted=False,
                note=f'Not SD-loadable by name. Card update name is {cam.card_name}. Container validity != bootability.')
    (a.out / 'build.json').write_text(json.dumps(info, indent=2) + '\n')
    print(json.dumps(info, indent=2))


if __name__ == '__main__':
    try:
        main()
    except ValueError as e:
        sys.exit(f'error: {e}')
