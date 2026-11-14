#!/usr/bin/env python3
"""Halation h6: the h2 passes of patches/halation with the same photo, fewer instructions, fewer locks and flushes, and no
pool block when LOOKS.BIN is loaded. Layer on the v0.32 chain (plugins=False), after extras_pages (its sdk cut frees the
claim). Offline. h6.s.in has the contract, docs/HALATION_RED.md "h6" the numbers.

  .venv/bin/python -I patches/v032/build.py releases/v0.31d/edits.json --out generated/halation_h6/edits.json --version 0.33 \\
      --extra halation_h6=patches/halation_h6/build.py

apply(spec, version) -> spec. Edits:
  - hl_run's first three instructions (5 B, inside halation's `.hlb`) -> `jmp h6_run`. hl_lvl, hl_grain, the flag hook, the
    Extras sector and the call into gc_grain stay as they are; the rest of hl_run and hl_pa / hl_pb / hl_box / hl_li /
    hl_gpb / hl_row / hl_seg / hl_pc / hl_x98 and the old tables stay in place, unused (RECLAIM below);
  - code and tables at CLAIM + 16, in the sec-5 claim of the dead `sdk api` shell handlers (CODE_SPACE_SURVEY section 2;
    the tail of the shelved overlay claim, unused with plugins=False).
HL_CAP is the most of our own work one lock may mask, in instructions (flushes and the stock lock code not counted).
"""
import argparse, copy, importlib.util, json, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SRC = 'patches/halation_h6'


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


XP = _load('ep7_xp_build_h6', ROOT / 'patches/extras_pages/build.py')
HB = _load('hl_build_h6', ROOT / 'patches/halation/build.py')
ST, KH, B3 = XP.ST, XP.KH, XP.B3
T1 = HB.T1
BASE, STOCK = XP.BASE, XP.STOCK

CLAIM = (0x607c6420, 0x607c8420)          # sec 5, 8 KB of the dead sdk-api handlers (the shelved overlay claim's tail)
GUARD = 16
AT = CLAIM[0] + GUARD
# Naive reference-scan hits into the claim that are not address uses, each checked by disassembly (pin_reasons() re-derives
# them from the image; verify.py runs it). address, its four bytes, what they are:
#   i  inside the one instruction named, as opcode / register-list / frame / displacement bytes or half of another operand
#   x  they start inside the instruction named and run over its end into the next one
#   d  data: the table named
PINS_TXT = '''
0x6010b0ad fc817ca0 i mov d0,(0x621da07c)
0x6010b74a fc817ca0 i mov d0,(0x621da07c)
0x6010b840 fc817ca0 i mov d0,(0x621da07c)
0x6010bd29 fc817ca0 i mov d0,(0x621da07c)
0x6010be30 fc817ca0 i mov d0,(0x621da07c)
0x60209f80 cd82e480 i call 0x60208402,[d2],8
0x60333a58 fc837c60 i movhu d0,(0xa273607c)
0x603ca46d fc827c60 i movbu d0,(0x6226607c)
0x603d6a2b cd7ce480 i call 0x603d4ea7,[d2],28
0x6063e9d7 cd74e480 i call 0x6063ce4b,[d2],28
0x60bc3a0e fc81e440 i mov d0,(0xa26a40e4)
0x60c4a434 fc83e480 i movhu d0,(0x623380e4)
0x609e0467 7272e440 x add a0,a2
0x60c9982e f1787c60 x add a2,a0
0x60d05893 10707ca0 x mov a0,(16,sp)
0x613193ff 0184e440 x sub d0,d1
0x605aaf18 e1737ca0 d entropy: the 160 KB of high-entropy data that end section 3 (0x6058f000..0x605b7000), its neighbours are no addresses
0x60a6363e 597c7ca0 d pairs: a sec-5 u8 curve with every value twice (.. 38 38 59 59 7c 7c a0 a0 c1 c1 ..)
0x60b81427 607e7ca0 d ptrs: byte 3 of the aligned sec-5 pointer table 0x60b81400.. (words 0x60a07d13 / 0x60a07c7e ..), as extras_pages pins 0x60b814f3
0x60b81443 60767ca0 d ptrs
0x60b8146b 606e7ca0 d ptrs
0x60b81473 60667ca0 d ptrs
0x60b814db 607e7ca0 d ptrs
0x60f0ae67 8282e480 d double: bytes 3..6 of the double 540.56 in the sec-6 table of {double, double, double, id} records (as split_tone pins 0x60f09dd0)
'''
PINS = {int(f[0], 16): (f[1], f[2], ' '.join(f[3:])) for f in (l.split() for l in PINS_TXT.strip().splitlines())}
HL_RUN, ENTRY_OLD = 0x601de917, bytes.fromhex('4304420800')   # hl_run: mov a0,(4,sp); mov d0,(8,sp); clr d0
HL_CALL = (0x601de902, bytes.fromhex('cd1500f060'))            # hl_grain: call hl_run,[d2,d3,a2,a3],96, its only caller
BAD = T1.BAD                              # mul is used (every return is `ret`)

# ---- the lock budget
HL_CAP = 120000                           # instructions of our own work under one lock, at most (a row over it alone goes alone)
E_LOCK = 300                              # the lock's own share: gc_open after the lock is taken, the close before the unlock
EA_SAMPLE, EA_ROW = 10, 120               # pass A: a sample at its worst (every one adds), a row's fixed part
EC_PAIR, EC_SEG, EC_ROW = 41, 30, 130     # pass C: a pair at its worst (both chroma bytes clamp; + 3 pairs per strip run for its set-up),
                                          # a strip of the band walked, a row's fixed part
# ---- LOOKS.BIN block L (class 2, 16448 B): fm_load asks 0..2640, split_tone's S is 2688..5808
L_LO, L_HI = 5824, 16384                  # ours: the grid, only while the passes run
RECLAIM = (('.hlb', 0x601de91c, 0x601dea3a, 'hl_run after its first 5 B'), ('.text', 0x601e0850, 0x601e0b34, 'hl_pb .. hl_seg, hl_tint, hl_gm'),
           ('.hlc', 0x601e3ae4, 0x601e3b33, 'hl_pa, hl_x98'), ('.hlp', 0x605b7780, 0x605b77fb, 'hl_pc'))


def u32(im, a):
    return struct.unpack_from('<I', im, a - BASE)[0]


def ztab():
    return [0] + [-(-32 // x) for x in range(1, 33)]


def check_strips():
    """The pairs with g >= 1 of a strip, as h6_nz takes them from h6_z, against v = 64 a + 2 (b - a) j, g = v >> 6, for every a, b."""
    z = ztab()
    for a in range(256):
        for b in range(256):
            g = [(64 * a + 2 * (b - a) * j) >> 6 for j in range(32)]
            if min(64 * a + 2 * (b - a) * j for j in range(32)) < 0 or max(g) > 255:
                raise SystemExit(f'strip {a}, {b}: v out of range')
            if a == 0:
                lo, hi = (32, 32) if b <= 1 else (z[min(b, 32)], 32)
            elif b == 0:
                lo, hi = 0, 33 - z[min(a, 32)]
            else:
                lo, hi = 0, 32
            if [j for j in range(32) if g[j]] != list(range(lo, hi)):
                raise SystemExit(f'strip {a}, {b}: pairs with glow are not {lo}..{hi}')


def check_claim(spec, stock, im):
    """As patches/looks_split and patches/i18n_zh: inside the dead handlers, stock, clear of edits and of the double
    constant's alias, the shell cut, and no reference from outside the dead code (abs32 on four aliases, rel calls and jumps)."""
    lo5, hi5, off5 = KH.sec(stock, 5)
    if not (lo5 <= CLAIM[0] and CLAIM[1] <= hi5 and KH.DEAD[1][0] <= CLAIM[0] and CLAIM[1] <= KH.DEAD[1][1]):
        raise SystemExit('claim not inside the dead handler range of section 5')
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a, n = int(e['addr'], 16), len(e['new']) // 2
            if a < CLAIM[1] and CLAIM[0] < a + n:
                raise SystemExit(f'claim overlaps edit {e["addr"]}')
    if im[CLAIM[0] - BASE:CLAIM[1] - BASE] != stock[CLAIM[0] - BASE:CLAIM[1] - BASE]:
        raise SystemExit('claim not stock')
    if CLAIM[0] <= (KH.DOUBLE_K - off5) & 0xffffffff < CLAIM[1]:
        raise SystemExit('the 0x40e4ab40 double constant aliases into the claim')
    for w, v in KH.SUBCMD.items():
        if u32(im, w) == v:
            raise SystemExit(f'sdk sub-command word {w:#x} still stock: apply extras_pages first')
    KH.pin_fp(stock)
    KH.FALSE_POS.update(XP.PINS)
    KH.FALSE_POS.update({a: b for a, (b, _, _) in PINS.items()})
    bad = KH.scan(im, CLAIM[0], CLAIM[1], off5, KH.DEAD)
    if bad:
        raise SystemExit(f'reference into the claim: {[(k, hex(a)) for k, a in bad[:6]]} ({len(bad)})')


def pin_reasons(im):
    """Each pin against the image: the instruction a consensus of linear sweeps puts over it, or the data it sits in. -> bad pins."""
    import math, re, subprocess, tempfile
    bad = []
    with tempfile.NamedTemporaryFile(suffix='.bin') as tf:
        tf.write(im); tf.flush()

        def over(x):
            got = set()
            for i in range(8):
                out = subprocess.run([B3.TC / 'mn10300-elf-objdump', '-b', 'binary', '-m', 'am33-2', '-D', f'--adjust-vma={BASE:#x}',
                                      f'--start-address={x - 64 - i:#x}', f'--stop-address={x + 16:#x}', tf.name], capture_output=True, text=True, check=True).stdout
                d = [(int(m.group(1), 16), m.group(2), m.group(3).strip()) for m in re.finditer(r'^\s*([0-9a-f]+):\t[0-9a-f ]+?\s*\t(\S+)[ \t]*(.*)$', out, re.M)]
                b = max(a for a, _, _ in d if a <= x)
                got.add((b, min((a for a, _, _ in d if a > b), default=b + 8), ' '.join(next(t for t in d if t[0] == b)[1:]).strip()))
            return got.pop() if len(got) == 1 else (0, 0, '')
        for x, (b4, kind, why) in PINS.items():
            o = x - BASE
            ok = im[o:o + 4].hex() == b4
            if kind in 'ix':
                b, nxt, txt = over(x)
                ok &= txt == why and b <= x and ((kind == 'i' and x + 4 <= nxt and not (nxt - b == 6 and x == nxt - 4)) or (kind == 'x' and x < nxt < x + 4))
            elif why.startswith('entropy'):
                w = im[o - 512:o + 512]
                ok &= -sum(w.count(v) / 1024 * math.log2(w.count(v) / 1024) for v in set(w)) > 7.5 and \
                    not any(0x60020020 <= (v & 0xbfffffff) < 0x62800000 for v in struct.unpack_from('<8I', im, o - 16) if v != u32(im, x))
            elif why.startswith('pairs'):
                ok &= all(im[o - 15 + 2 * k] == im[o - 14 + 2 * k] for k in range(16)) and len(set(im[o - 15:o + 17])) > 8
            elif why.startswith('ptrs'):
                ok &= x % 4 == 3 and all(0x60a07000 <= u32(im, a) < 0x60a08000 for a in (x - 7, x - 3, x + 1, x + 5))
            elif why.startswith('double'):
                ok &= all(1.0 < struct.unpack_from('<d', im, o - 3 + 8 * k)[0] < 2000.0 for k in (-1, 0, 1))
            else:
                ok = False
            if not ok:
                bad.append(hex(x))
    return bad


def check_sites(spec, im):
    hl = spec.get('halation', {})
    if hl.get('test') != 'h7' or hl.get('symbols', {}).get('hl_run') != hex(HL_RUN):
        raise SystemExit('needs halation h7 (v0.31b .. v0.32a) with hl_run where it was')
    if im[HL_RUN - BASE:HL_RUN - BASE + 5] != ENTRY_OLD:
        raise SystemExit(f'hl_run entry {im[HL_RUN - BASE:HL_RUN - BASE + 5].hex()}')
    at, call = HL_CALL
    if im[at - BASE:at - BASE + 5] != call or at + struct.unpack('<h', call[1:3])[0] != HL_RUN:
        raise SystemExit('hl_grain: call hl_run,[d2,d3,a2,a3],96 not found')
    # nothing else enters there: no address of, call or jump to the five bytes from outside halation's own blocks
    own = tuple((int(lo, 16), int(lo, 16) + n) for lo, hi, n in hl['regions'].values())
    other = KH.scan(im, HL_RUN, HL_RUN + 5, KH.sec(STOCK.read_bytes(), 5)[2], own)
    if other:
        raise SystemExit(f'another reference to hl_run: {[(k, hex(a)) for k, a in other[:4]]}')
    if spec['ap_custom']['symbols'].get('ap_P') != hex(ST.AP_P) or im[ST.AP_P - BASE:ST.AP_P + 3 - BASE] != bytes.fromhex('fcaec2'):
        raise SystemExit('ap_P moved')
    if spec.get('grain_cpu', {}).get('test') != 'r2':
        raise SystemExit('needs grain_cpu r2 (gc_open)')
    if (hl['thr'], list(hl['gmax'])) != (HB.THR, list(HB.GMAX)) or [list(r) for r in hl['tints'].values()] != [list(r) for r in HB.tint_rows(hl['swap'])]:
        raise SystemExit('halation constants differ from patches/halation')


def check_l(spec):
    """L's tail: nobody else may hold what the grid takes (patches/v032 guards the L request against split_tone's S the same way)."""
    if ST.LOFF + ST.SBYTES > L_LO or L_HI > 16384 or L_LO % 4 or (ST.LTAG, ST.LBACK) != (2112, 2116) or ST.BLOCK2 != 0x4040:
        raise SystemExit(f'L tail {L_LO}..{L_HI} collides with split_tone S {ST.LOFF}..{ST.LOFF + ST.SBYTES}, or the block layout changed')
    req = spec.get('looks_split', {}).get('L', {}).get('size', ST.LREQ)
    if req > ST.LOFF or req > L_LO:
        raise SystemExit(f'L request {req} reaches the tail')
    for name, v in spec.items():
        t = v.get('L_tail') if isinstance(v, dict) else None
        if name != 'halation_h6' and t and int(t['lo']) < L_HI and L_LO < int(t['hi']):
            raise SystemExit(f'{name} holds L+{t["lo"]}..{t["hi"]}: collides with the halation grid at L+{L_LO}..{L_HI}')


def source(hl):
    tl = '\n'.join(' .long ' + ','.join(str(v) for v in r) for r in HB.tint_rows(hl['swap']))
    s = (HERE / 'h6.s.in').read_text()
    sub = dict(thr=hl['thr'], cap=HL_CAP, e_lock=E_LOCK, ea_sample=EA_SAMPLE, ea_row=EA_ROW, ec_pair=EC_PAIR, ec_seg=EC_SEG, ec_row=EC_ROW,
               fmagic=hex(ST.FMAGIC), lmagic=hex(ST.LMAGIC), ltag=ST.LTAG, lback=ST.LBACK, loff=L_LO, tailw=(L_HI - L_LO) // 4,
               npool2=hex(-ST.POOL2 & 0xffffffff), liml=hex(ST.POOL2_END - ST.POOL2 - L_HI + 1),
               tint=tl, gmax=','.join(map(str, hl['gmax'])), ztab=','.join(map(str, ztab())))
    for k, v in sub.items():
        s = s.replace('{' + k + '}', str(v))
    if '{' in s or '}' in s:
        raise SystemExit('unfilled placeholder')
    return s


def stores():
    """Every register-indirect store the code may make: photo bytes through a0, the grid through a0 / a1 / a2."""
    ok = {'mov d0,(a1)', 'movbu d0,(a0)', 'movbu d0,(a2)', 'movbu d2,(a2)'}
    ok |= {f'movbu d0,({o},a0)' for o in range(0, 32, 2)} | {f'movbu d1,({o},a0)' for o in range(1, 32, 2)}
    return ok


def build_code(spec):
    g = {k: int(v, 16) for k, v in spec['grain_cpu']['symbols'].items()}
    syms = dict(gc_open=g['gc_open'], ep7_ap_p=ST.AP_P, **{k: T1.SYMS[k] for k in ('ep7_flush', 'ep7_modeset', 'ep7_unlock', 'ep7_malloc', 'ep7_free')})
    code, lst, sy, _ = B3.assemble(source(spec['halation']), AT, syms)
    if sy['h6_run'] != AT or AT + len(code) > CLAIM[1] - GUARD:
        raise SystemExit(f'{len(code)} B does not fit')
    if sy['h6_tint'] % 4:
        raise SystemExit('h6_tint misaligned')
    tb = b''.join(struct.pack('<3i', *r) for r in HB.tint_rows(spec['halation']['swap'])) + bytes(spec['halation']['gmax']) + bytes(ztab())
    if code[sy['h6_tint'] - AT:] != tb or sy['h6_end'] != AT + len(code):
        raise SystemExit('tables')
    ins = B3.disasm(code, AT, sy['h6_tint'])
    if any(op in BAD for _, op, _ in ins) or any(op.startswith('.') or op == '(bad)' for _, op, _ in ins):
        raise SystemExit('forbidden or undecodable instruction')
    if any(code[a - AT] == 0xfb for a, _, _ in ins):
        raise SystemExit('fb-prefixed form')
    ok = stores()
    for a, txt, kd, _ in B3.store_audit(ins):
        if kd == 'abs' or (kd == 'ind' and txt not in ok):
            raise SystemExit(f'store at {a:#x}: {txt} ({kd})')
    tg = {(op, int(args.split(',')[0], 16)) for _, op, args in ins if op in ('call', 'calls', 'jmp') and args.startswith('0x')}
    out = {(o, t) for o, t in tg if not AT <= t < sy['h6_tint']}
    want = {('call', syms[k]) for k in syms}
    if out != want or any(op == 'calls' or (op == 'jmp' and not args.startswith('0x')) for _, op, args in ins):
        raise SystemExit(f'call targets {sorted((o, hex(t)) for o, t in out)}')
    return code, sy, lst


def apply(spec, version='0.33'):
    stock = STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    if 'halation_h6' in spec:
        raise SystemExit('halation_h6 already applied')
    if 'extras_pages' not in spec or 'split_tone' not in spec:
        raise SystemExit('needs the v0.32 chain with extras_pages (plugins=False)')
    im = ST.img_of(spec, stock)
    check_claim(spec, stock, im)
    check_sites(spec, im)
    check_l(spec)
    check_strips()
    code, sy, lst = build_code(spec)
    spec['edits'].append(dict(kind='0x100', addr=hex(AT), expect=stock[AT - BASE:AT - BASE + len(code)].hex(), new=code.hex(), source=SRC,
                              why=f'halation h6 {version}: h6_run .. h6_crow + tables ({len(code)} B, sec-5 dead sdk-api handlers, '
                                  f'claim {CLAIM[0]:#x}..{CLAIM[1]:#x})'))
    ST.put(spec, stock, HL_RUN, ENTRY_OLD, b'\xdc' + struct.pack('<i', sy['h6_run'] - HL_RUN), 'halation h6: hl_run -> jmp h6_run (same frame)')
    spec['halation_h6'] = dict(built_by=SRC, test='h6', version=version, claim=[hex(CLAIM[0]), hex(CLAIM[1])], code=[hex(AT), len(code)],
                               site=dict(hl_run=hex(HL_RUN)), cap=HL_CAP,
                               bounds=dict(e_lock=E_LOCK, ea_sample=EA_SAMPLE, ea_row=EA_ROW, ec_pair=EC_PAIR, ec_seg=EC_SEG, ec_row=EC_ROW),
                               L_tail=dict(lo=L_LO, hi=L_HI, use='the cell grid, while the passes run (nothing is kept)'),
                               reclaim=[[n, hex(lo), hex(hi), why] for n, lo, hi, why in RECLAIM],
                               symbols={k: hex(v) for k, v in sy.items() if k.startswith('h6_')})
    return spec


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--version', default='0.33')
    ap.add_argument('--listing', type=Path)
    a = ap.parse_args()
    spec = apply(json.loads(a.spec.read_text()), a.version)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(spec, indent=1))
    if a.listing:
        a.listing.write_text(build_code(spec)[2])
    print(json.dumps({k: v for k, v in spec['halation_h6'].items() if k != 'symbols'}))
