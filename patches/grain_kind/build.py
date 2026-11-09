#!/usr/bin/env python3
"""grain_cpu kind guard fix, gk1: gc_flag's guards 05..08 read the source request's Mode, not capture+194. Offline.
docs/GRAIN_PORT.md "Kind guard fix (gk1)". Layer: apply(spec) on v0.30 (grain_cpu r2). Stacked by patches/recview (0.31r2).

  .venv/bin/python -I patches/grain_kind/build.py releases/v0.30/edits.json --out generated/grain_kind/edits.json
"""
import argparse, copy, importlib.util, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


RV = _load('recview_build', ROOT / 'patches/recview/build.py')
SB3, BASE, rel = RV.SB3, RV.BASE, RV.rel
SRC = 'patches/grain_kind'
AT, END = 0x601de800, 0x601de880                       # dead EVF gamma table space, after recview's claim
GC_FLAG = 0x601dfd15                                   # grain_cpu r2 gc_flag (v0.27 .. v0.30)
SITE_REC, OLD_REC, BACK_REC = 0x601dfd30, bytes.fromhex('fa63c200f8713a'), 0x601dfd37   # movhu (194,a3),d0; movhu d0,(58,a1)
SITE_KIND, OLD_KIND, BACK_KIND = 0x601dfd87, bytes.fromhex('fa63c2008505'), 0x601dfdab  # movhu (194,a3),d0; mov 5,d1
SKIP = 0x601dfdc6                                      # gc_flag label 9 (guard exit, d1 = id)
GUARDS = bytes.fromhex('fac80120c83585' '06fac80620c82d85' '07fac80810c82585' '08fac80610c81d')   # the four kind tests after SITE_KIND
TAIL_KIND = bytes.fromhex('f8402e28ffa002c40df84032cd7e01c00c04ca0904')                       # 0x601dfdab..: Art test, gc_pend, clr d1


def apply(spec):
    stock = RV.STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    if 'grain_kind' in spec:
        raise SystemExit('grain_kind already applied')
    g = spec.get('grain_cpu', {})
    if g.get('test') != 'r2' or int(g['symbols']['gc_flag'], 16) != GC_FLAG:
        raise SystemExit('base grain_cpu is not r2 at 0x601dfd15')
    im = RV.img_of(spec, stock)
    o = lambda a, n: im[a - BASE:a - BASE + n]
    if o(SITE_REC, 7) != OLD_REC or o(SITE_KIND, 6) != OLD_KIND or o(SITE_KIND + 6, len(GUARDS)) != GUARDS or o(BACK_KIND, len(TAIL_KIND)) != TAIL_KIND:
        raise SystemExit('gc_flag bytes differ from r2')
    if o(SKIP, 3) != bytes.fromhex('8001cd'):           # mov 1,d0; call gc_mark
        raise SystemExit('gc_flag label 9 differs')
    RV.AT, RV.END = AT, END                            # reuse recview's free-space check on this block
    RV.check_free(spec, stock)
    syms = dict(ep7_rec_back=BACK_REC, ep7_kind_back=BACK_KIND, ep7_skip=SKIP, ep7_type=RV.TYPE_FN)
    code, lst, s, _ = SB3.assemble((HERE / 'gk.s.in').read_text(), AT, syms)
    if AT + len(code) > END:
        raise SystemExit(f'{len(code)} B does not fit {END - AT}')
    ins = SB3.disasm(code, AT, s['gk_end'])
    if (any(op in RV.BAD for _, op, _ in ins) or any(k == 'abs' for _, _, k, _ in SB3.store_audit(ins))
            or any(code[a - AT] == 0xfb for a, _, _ in ins) or AT % 4):
        raise SystemExit('forbidden instruction, fb-prefixed form, absolute store or misaligned block')
    if [t for _, t, k, _ in SB3.store_audit(ins) if k == 'ind'] != ['movhu d0,(58,a1)']:
        raise SystemExit(f'unexpected stores: {SB3.store_audit(ins)}')
    spec['edits'].append(dict(kind='0x100', addr=hex(AT), expect=stock[AT - BASE:AT - BASE + len(code)].hex(), new=code.hex(), source=SRC,
                              why=f'grain_kind gk1 gk_rec / gk_kind ({len(code)} B, dead EVF gamma table)'))
    RV.put(spec, stock, SITE_REC, OLD_REC, b'\xdc' + rel(SITE_REC, s['gk_rec']) + b'\xcb\xcb', 'gc_flag record kind -> gk_rec (source Mode)')
    RV.put(spec, stock, SITE_KIND, OLD_KIND, b'\xdc' + rel(SITE_KIND, s['gk_kind']) + b'\xcb', 'gc_flag kind guards -> gk_kind (source Mode, forced branch, type != 0x1000)')
    for e in spec['edits']:
        e['why'] = e['why'].replace('[recview: gc_flag', '[grain_kind: gc_flag')
    spec['grain_kind'] = dict(built_by=SRC, test='gk1', code_at=hex(AT), code_len=len(code), claim=[hex(AT), hex(END)],
                              sites=[hex(SITE_REC), hex(SITE_KIND)], symbols={k: hex(v) for k, v in s.items() if k.startswith('gk_')})
    return spec


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    spec = apply(json.loads(a.spec.read_text()))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(spec, indent=1))
    print(json.dumps({k: v for k, v in spec['grain_kind'].items() if k != 'symbols'}), spec['grain_kind']['symbols'])
