#!/usr/bin/env python3
"""M-mode dial, ported from phocean/omsystem-ep7 (Apache-2.0): patches/dial_iso + patches/dial_expcomp, docs/DIAL_ISO.md,
docs/DIAL_EXPCOMP.md there. Camera-tested on their builds. Offline layer:

  .venv/bin/python -I patches/mdial/build.py <spec> --out <edits.json>
  (release chain: patches/v032/build.py ... --extra mdial=patches/mdial/build.py)

What it does: Custom Menu B > Dial function M/B offers {Shutter, Exp comp} (first choice, was {FNo., Shutter}) and the stock
{Shutter, FNo.}. In mode M with a lens without contacts, the free dial sets ISO (FNo. choice) or exposure comp (Exp comp
choice); with a contact lens it keeps / gets aperture. The rule-engine byte that refuses exposure comp in M is unlocked.

Edits (their bytes; only the stub moves):
  - stub dl_fn (mdial.s.in = their dial_iso.s.in) in a sec-5 claim of the dead `sdk api` handlers, not at 0x60210900
    (Caduceus's bundle table): the assembler re-makes its call / jmp displacements for the new address;
  - hook 0x60cdc837 (9 B, dial routine 0x60cdc82c) `mov d0,a3; call 0x60cc8be9,[d2,d3],8` -> `jmp dl_fn` + 4 nop,
    resume 0x60cdc840;
  - dial_expcomp's 4 data edits: M/B list 0x604bb43c, the two label lists 0x611d6d32 / 0x611d6d4a, rule byte 0x6044afda.
Refuses when any of these bytes (or the hook interior, or the M/B validator record's list pointer) has been changed by an
earlier layer, when a callee's prologue / return frame is not as their study assumed, or on the usual code audits.
"""
import argparse, copy, importlib.util, json, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SRC = 'patches/mdial'


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


JA = _load('ep7_ja_build_md', ROOT / 'patches/i18n_ja/build.py')
ST, KH, B3, BASE, STOCK, BAD = JA.ST, JA.KH, JA.B3, JA.BASE, JA.STOCK, JA.BAD

CLAIM = (0x607e3a00, 0x607e3c00)          # 512 B; scan of 0x607c9c20..0x607e87c5 on the v0.34a image: no reference into it
GUARD = 16
AT = CLAIM[0] + GUARD
HOOK, RESUME = 0x60cdc837, 0x60cdc840
HOOK_STOCK = bytes.fromhex('f1e3ddb0c3feffc008')     # mov d0,a3 ; call 0x60cc8be9,[d2,d3],8
WATCH = (0x60cdc82c, 0x60cdc848)                     # no other layer may touch the routine head around the hook
GETSID, LENS, RULE = 0x60ccf9f3, 0x602ea74c, 0x60cc8be9
CALLEE = {GETSID: ('822c800c4204', 0x60ccfa43, 'dfa018'), LENS: ('80048501', 0x602ea78e, 'df80'),
          RULE: ('0cfac8800c', 0x60cc8c08, 'dec008')}   # their study: prologue, return frame
FRAMES = {GETSID: '[d2,a2],24', LENS: '[d2],28', RULE: '[d2,d3],8'}
MB_RECORD, MB_LIST = 0x604ccd74, 0x604bb43c          # validator record of sid 76 (Dial function M/B) and its list
DATA = [(0x604bb43c, '0300000004000000', '0400000002000000', 'M/B list first entry {FNo., Shutter} -> {Shutter, Exp comp}'),
        (0x611d6d32, '9302', '9402', 'M/B page, first dial label list, first choice: FNo. (659) -> Shutter (660)'),
        (0x611d6d4a, '9402', '9202', 'M/B page, second dial label list, first choice: Shutter (660) -> Exp comp icon (658)'),
        (0x6044afda, '00', '02', 'rule engine, sid 2 (exp comp) group 0 in M: compare sid 15210 with 2 (never) -> exp comp allowed in M')]


def u32(im, a):
    return struct.unpack_from('<I', im, a - BASE)[0]


def build_code():
    syms = dict(ep7_getsid=GETSID, ep7_lens=LENS, ep7_rule=RULE, ep7_resume=RESUME)
    code, lst, sy, _ = B3.assemble((HERE / 'mdial.s.in').read_text(), AT, syms)
    if sy['dl_fn'] != AT or AT + len(code) > CLAIM[1] - GUARD:
        raise SystemExit(f'{len(code)} B does not fit / dl_fn not at the claim start')
    ins = B3.disasm(code, AT)
    if any(op in BAD for _, op, _ in ins) or any(op.startswith('.') or op == '(bad)' for _, op, _ in ins):
        raise SystemExit('forbidden or undecodable instruction')
    if any(code[a - AT] == 0xfb for a, _, _ in ins):
        raise SystemExit('fb-prefixed form')
    if B3.store_audit(ins) or any('(' in args for _, op, args in ins if op not in ('call', 'jmp')):
        raise SystemExit('the stub must not touch memory')
    calls = {(op, args) for _, op, args in ins if op in ('call', 'jmp', 'calls')}
    want = {('call', f'{t:#x},{f}') for t, f in FRAMES.items()} | {('jmp', f'{RESUME:#x}')}
    if calls != want:
        raise SystemExit(f'call / jmp set {sorted(calls)}')
    if ins[-1][1:] != ('jmp', f'{RESUME:#x}') or ins[-1][0] + 5 != AT + len(code):
        raise SystemExit('stub must end with jmp 0x60cdc840')
    return code, sy


def apply(spec, version='0.34a'):
    stock = STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    if 'mdial' in spec:
        raise SystemExit('mdial already applied')
    if 'extras_pages' not in spec:
        raise SystemExit('needs extras_pages (the sdk sub-command cut that makes the claim dead)')
    im = ST.img_of(spec, stock)
    spans = [(int(e['addr'], 16), int(e['addr'], 16) + len(e['new']) // 2) for e in spec['edits']
             if e['kind'] == '0x100' and not e['addr'].startswith('off:')]
    for lo, hi, what in [(WATCH[0], WATCH[1], 'dial routine head')] + [(a, a + len(o) // 2, w) for a, o, _, w in DATA] \
            + [(MB_RECORD, MB_RECORD + 20, 'M/B validator record')]:
        if any(a < hi and lo < b for a, b in spans):
            raise SystemExit(f'{what} {lo:#x}: already edited by another layer')
    if stock[HOOK - BASE:RESUME - BASE] != HOOK_STOCK or stock[RESUME - BASE:RESUME - BASE + 2] != bytes.fromhex('4220'):
        raise SystemExit('hook / resume bytes differ from the study')
    if HOOK + 2 + struct.unpack_from('<i', stock, HOOK + 3 - BASE)[0] != RULE:
        raise SystemExit('hook call target is not the rule lookup')
    for a, old, _, w in DATA:
        if stock[a - BASE:a - BASE + len(old) // 2].hex() != old:
            raise SystemExit(f'{w}: stock bytes differ')
    if u32(im, MB_RECORD + 4) != MB_LIST or struct.unpack_from('<H', im, MB_RECORD - BASE)[0] != 76:
        raise SystemExit('M/B validator record is not sid 76 -> 0x604bb43c (moved by a layer?)')
    for t, (pro, ret_at, ret_b) in CALLEE.items():
        if stock[t - BASE:t - BASE + len(pro) // 2].hex() != pro or stock[ret_at - BASE:ret_at - BASE + len(ret_b) // 2].hex() != ret_b:
            raise SystemExit(f'callee {t:#x}: prologue / return frame differ from the study')
        if im[t - BASE:t - BASE + 16] != stock[t - BASE:t - BASE + 16]:
            raise SystemExit(f'callee {t:#x} head edited by a layer')
    if JA._refs(im, HOOK + 1, RESUME, KH.sec(stock, 5)[2]):
        raise SystemExit('reference into the hook interior')
    JA.check_claim(spec, stock, im, CLAIM)
    code, sy = build_code()
    spec['edits'].append(dict(kind='0x100', addr=hex(AT), expect=stock[AT - BASE:AT - BASE + len(code)].hex(), new=code.hex(),
                              source=SRC, why=f'mdial {version}: dl_fn ({len(code)} B, from phocean/omsystem-ep7 dial_iso; '
                                              f'sec-5 dead sdk-api handlers, claim {CLAIM[0]:#x}..{CLAIM[1]:#x})'))
    new = b'\xdc' + struct.pack('<i', AT - HOOK) + b'\xcb' * 4
    spec['edits'].append(dict(kind='0x100', addr=hex(HOOK), expect=HOOK_STOCK.hex(), new=new.hex(), source=SRC,
                              why=f'mdial {version}: dial routine `mov d0,a3; call 0x60cc8be9,[d2,d3],8` -> jmp dl_fn + 4 nop '
                                  f'(resume {RESUME:#x})'))
    for a, old, nw, w in DATA:
        spec['edits'].append(dict(kind='0x100', addr=hex(a), expect=old, new=nw, source=SRC, why=f'mdial {version} (dial_expcomp): {w}'))
    spec['mdial'] = dict(built_by=SRC, version=version, origin='phocean/omsystem-ep7 patches/dial_iso + dial_expcomp (Apache-2.0)',
                         claim=[hex(CLAIM[0]), hex(CLAIM[1])], code=[hex(AT), len(code)], hook=hex(HOOK), resume=hex(RESUME),
                         data=[hex(a) for a, *_ in DATA], symbols={k: hex(v) for k, v in sy.items() if k.startswith('dl_')})
    return spec


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--version', default='0.34a')
    a = ap.parse_args()
    spec = apply(json.loads(a.spec.read_text()), a.version)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(spec, indent=1))
    print(json.dumps({k: v for k, v in spec['mdial'].items() if k != 'symbols'}))
