#!/usr/bin/env python3
"""grain g3: r2's film grain from a ring in ROM, tables in ROM, no heap. Layer on the v0.32 chain (plugins=False), after
extras_pages (its sdk cut frees the claims). Offline. g3.s.in has the contract, model.py the integers, docs/GRAIN_PORT.md
"g3" the reasons (g2, released in v0.32b, looked tiled at High; its files are build_g2.py, g2.s.in, model_g2.py,
verify_g2.py, and REV = 'g2' below still builds it).

  .venv/bin/python -I patches/v032/build.py releases/v0.31d/edits.json --out OUT.json --version 0.33 \\
      --extra grain_g2=patches/grain_g2/build.py [--extra halation_h6=... --extra crash_log=...]
  .venv/bin/python -I patches/grain_g2/build.py --pins SPEC      # re-derive every pinned scan hit by disassembly

apply(spec, version) -> spec. The layer keeps its name and spec key (`grain_g2`: other layers read `unused_r2` and the
symbols g2_grain / g2_blk). Edits:
  - gc_grain's first three instructions (6 B, inside the grain_cpu r2 block) -> `jmp g2_grain; nop`. Both callers (gc_ob's
    call, and halation's grain hand-off, which jumps there from gc_gs) arrive with the frame g2_grain expects. The rest of
    gc_grain, gc_fill, gc_next, gc_p2, gc_tbl, gc_cach, gc_stab and gc_G are no longer used (`unused_r2`);
  - the ring and the three T2 tables: the whole 64 KB claim CLAIM of the dead `sdk api` shell handlers (CODE_SPACE_SURVEY
    section 2), which g2 held too;
  - the code: a second claim CODE in the same dead handlers, between halation_h6's claim and extras_pages'.
K below is the number of rows per lock.
"""
import argparse, copy, hashlib, importlib.util, json, re, struct, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SRC = 'patches/grain_g2'


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


XP = _load('ep7_xp_build_g2', ROOT / 'patches/extras_pages/build.py')
T1 = _load('grain_cpu_t1_g2', ROOT / 'patches/grain_cpu/build.py')
M = _load('grain_g2_model', HERE / 'model.py')
ST, KH, B3 = XP.ST, XP.KH, XP.B3
BASE, STOCK = XP.BASE, XP.STOCK

REV = 'g3'                                # 'g2': the v0.32b revision (build_g2.py), kept as the record
K = 3                                     # rows per lock (interrupts masked for K rows): 3 masks about what g2's 4 did. Any K >= 1
CLAIM = (0x607b6420, 0x607c6420)          # sec 5, 64 KB of the dead sdk-api handlers: the ring and the tables, all of it
CODE = (0x607c8420, 0x607c9420)           # sec 5, 4 KB of the same handlers: the code, 16 B stock guards at both ends
GUARD = 16
AT = CODE[0] + GUARD
RING_AT = CLAIM[0]                        # g3_ring, 16384 B
T_AT = CLAIM[0] + 0x4000                  # g3_T: Low, Med, High, 16384 B each, to CLAIM's end
HW_MAX = 5461                             # as r2: the offsets' span 16383 - Hw stays wide
ENTRY_OLD = bytes.fromhex('4304423c8504')  # gc_grain: mov a0,(4,sp); mov d0,(60,sp); mov 4,d1
FRAME = bytes.fromhex('f090')             # [d2,d3,a2,a3],144
# r2 routines the pass calls, and the pass it replaces, as the v0.27..v0.32 chain has them: any other bytes mean a layer changed them
USED = (('gc_pp', 'gc_clr'), ('gc_mark', 'gc_flag'), ('gc_open', 'gc_grain'), ('gc_cls', 'gc_fill'), ('gc_btab', 'gc_stab'))
OLD = (('gc_grain', 'gc_cls'), ('gc_fill', 'gc_btab'))
USED_SHA = '1f3836d0ef91092b'
OLD_SHA = '15c1a8bae6654d57'
BAD = T1.BAD
STORES = {'movbu d0,(38,a1)', 'movhu d0,(16,a1)', 'movhu d0,(18,a1)', 'movhu d0,(20,a1)', 'movhu d0,(22,a1)', 'movhu d0,(10,a1)',
          'movhu d0,(56,a1)', 'movhu d0,(24,a1)', 'movhu d0,(26,a1)', 'mov d0,(28,a1)', 'mov d0,(32,a1)', 'movbu d1,(61,a1)',
          'movhu d0,(14,a1)', 'mov d0,(44,a1)',                                   # the grain record, as r2
          'movbu d0,(a0)'} | {f'movbu d0,({2 * i},a0)' for i in range(1, 64)}     # Y bytes of the image: even offsets from a pixel
PIN_FILES = ((CLAIM, 'pins.txt'), (CODE, 'pins_g3.txt'))


def u32(im, a):
    return struct.unpack_from('<I', im, a - BASE)[0]


def pins():
    """pins.txt + pins_g3.txt -> {address: bytes}: the naive scan hits into the two claims that are not address uses, each with its reason."""
    out = {}
    for _, name in PIN_FILES:
        for line in (HERE / name).read_text().splitlines():
            f = line.split('#')[0].split()
            if f:
                out[int(f[0], 16)] = f[1]
    return out


def check_claims(spec, stock, im):
    """As patches/looks_split and patches/i18n_zh, for both claims: inside the dead handlers, stock, clear of edits and of the double
    constant's alias, the shell cut, and no reference from outside the dead code (abs32 on four aliases, rel calls and jumps)."""
    lo5, hi5, off5 = KH.sec(stock, 5)
    for claim in (CLAIM, CODE):
        if not (lo5 <= claim[0] and claim[1] <= hi5 and KH.DEAD[1][0] <= claim[0] and claim[1] <= KH.DEAD[1][1]):
            raise SystemExit('claim not inside the dead handler range of section 5')
        for e in spec['edits']:
            if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
                a, n = int(e['addr'], 16), len(e['new']) // 2
                if a < claim[1] and claim[0] < a + n:
                    raise SystemExit(f'claim {claim[0]:#x} overlaps edit {e["addr"]}')
        if im[claim[0] - BASE:claim[1] - BASE] != stock[claim[0] - BASE:claim[1] - BASE]:
            raise SystemExit(f'claim {claim[0]:#x} not stock')
        if claim[0] <= (KH.DOUBLE_K - off5) & 0xffffffff < claim[1]:
            raise SystemExit('the 0x40e4ab40 double constant aliases into the claim')
    for w, v in KH.SUBCMD.items():
        if u32(im, w) == v:
            raise SystemExit(f'sdk sub-command word {w:#x} still stock: apply extras_pages first')
    KH.FALSE_POS.clear()
    KH.FALSE_POS.update(pins())
    for claim in (CLAIM, CODE):
        bad = KH.scan(im, claim[0], claim[1], off5, KH.DEAD)
        if bad:
            raise SystemExit(f'reference into the claim {claim[0]:#x}: {[(k, hex(a)) for k, a in bad[:6]]} ({len(bad)})')


def sha(im, g, ranges):
    return hashlib.sha256(b''.join(im[g[a] - BASE:g[b] - BASE] for a, b in ranges)).hexdigest()[:16]


def check_sites(spec, im, g):
    if spec['grain_cpu'].get('test') != 'r2' or spec['grain_cpu'].get('k') != 4:
        raise SystemExit('needs grain_cpu r2')
    at = g['gc_grain']
    if im[at - BASE:at - BASE + 6] != ENTRY_OLD:
        raise SystemExit(f'gc_grain entry {im[at - BASE:at - BASE + 6].hex()}')
    if sha(im, g, OLD) != OLD_SHA:
        raise SystemExit('the r2 pass differs from the v0.27..v0.32 chain: a layer hooked inside it')
    if sha(im, g, USED) != USED_SHA:
        raise SystemExit('gc_pp / gc_blk / gc_mark / gc_cnt / gc_open / gc_cls differ from the v0.27..v0.32 chain')
    # gc_ob's call: the frame g2_grain returns through
    body = im[g['gc_ob'] - BASE:g['gc_g1'] - BASE]
    calls = [i for i in range(len(body) - 5) if body[i] == 0xcd and g['gc_ob'] + i + struct.unpack_from('<h', body, i + 1)[0] == at]
    if len(calls) != 1 or body[calls[0] + 3:calls[0] + 5] != FRAME:
        raise SystemExit('gc_ob: call gc_grain,[d2,d3,a2,a3],144 not found')
    if im[g['gc_G'] - BASE:g['gc_G'] - BASE + 256] != bytes(M.weights()):
        raise SystemExit('gc_G differs from the model weights')
    if list(struct.unpack_from('<3H', im, g['gc_stab'] - BASE)) != [M.S[1], M.S[2], M.S[3]]:
        raise SystemExit('gc_stab differs from the model strengths')


def source(k=None):
    k = K if k is None else k
    if not 1 <= k <= 127:
        raise SystemExit(f'K = {k}')
    at = lambda d, r: f'({d},{r})' if d else f'({r})'
    px = ''.join(f' movbu {at(i, "a1")},d0\n movbu {at(i, "a2")},d1\n add d1,d0\n movbu {at(2 * i, "a0")},d1\n asl 6,d1\n add d1,d0\n'
                 f' movbu (d0,a3),d0\n movbu d0,{at(2 * i, "a0")}\n' for i in range(64))
    src = (HERE / 'g3.s.in').read_text()
    if re.search(r'^\s*\.(long|hword|short|word|byte)\b', src, re.M):
        raise SystemExit('g3.s.in: no data tables in the code block')
    return B3.subst(src, dict(k=k, hw_max=HW_MAX, px64=px.rstrip('\n')))


def build_code(g, k=None):
    syms = dict(gc_cnt=g['gc_cnt'], gc_blk=g['gc_blk'], gc_mark=g['gc_mark'], gc_open=g['gc_open'], gc_cls=g['gc_cls'],
                ep7_flush=T1.SYMS['ep7_flush'], ep7_modeset=T1.SYMS['ep7_modeset'], ep7_unlock=T1.SYMS['ep7_unlock'],
                g3_ring=RING_AT, g3_T=T_AT)
    code, lst, sy, _ = B3.assemble(source(k), AT, syms)
    if sy['g2_grain'] != AT or sy['g2_end'] != AT + len(code) or AT + len(code) > CODE[1] - GUARD:
        raise SystemExit(f'{len(code)} B does not fit')
    ins = B3.disasm(code, AT)
    if ins[-1][1] != 'rets' or ins[-1][0] + 2 != AT + len(code):
        raise SystemExit('disassembly does not end on the last rets')
    if any(op in BAD for _, op, _ in ins) or any(op.startswith('.') or op == '(bad)' for _, op, _ in ins):
        raise SystemExit('forbidden or undecodable instruction')
    if any(code[a - AT] == 0xfb for a, _, _ in ins):
        raise SystemExit('fb-prefixed form')
    for a, txt, kd, _ in B3.store_audit(ins):
        if kd == 'abs' or (kd == 'ind' and txt not in STORES):
            raise SystemExit(f'store at {a:#x}: {txt} ({kd})')
    if any(op == 'add' and re.fullmatch(r'-?\d+,sp', args) for _, op, args in ins):
        raise SystemExit('the stack pointer moves: g3 lives in r2\'s frame')
    tg = {(op, int(args.split(',')[0], 16)) for _, op, args in ins if op in ('call', 'calls', 'jmp') and args.startswith('0x')}
    tg = {(o, t) for o, t in tg if not (o == 'jmp' and AT <= t < AT + len(code))}
    want = {('call', syms[n]) for n in ('gc_cnt', 'gc_blk', 'gc_mark', 'gc_open', 'gc_cls', 'ep7_flush', 'ep7_modeset', 'ep7_unlock')}
    want |= {('calls', sy['g3_next']), ('calls', sy['g3_row'])}
    if tg != want:                                                    # in particular: no malloc, no free
        raise SystemExit(f'call targets {sorted((o, hex(t)) for o, t in tg)}')
    if any(op in ('call', 'calls') for a, op, _ in ins if sy['g3_next'] <= a < sy['g2_end']):   # they share the frame: a call would take their return slot
        raise SystemExit('g3_next / g3_row make a call')
    back = [a for a, op, args in ins if op == 'jmp' and args.startswith(hex(sy['g2_blk']))]
    if len(back) != 1:
        raise SystemExit('g2_blk: one back jump expected')
    blk = [(op, args) for a, op, args in ins if sy['g2_blk'] <= a <= back[0]]
    if len(blk) != 8 * 64 + 6 or sum(x == ('asl', '6,d1') for x in blk) != 64 or sum(op == 'movbu' for op, _ in blk) != 5 * 64:
        raise SystemExit(f'g2_blk: {len(blk)} instructions')
    return code, sy, lst, dict(pixel=8, block=len(blk), per_pixel=round(len(blk) / 64, 3))


def data():
    rg = M.ring()
    if rg.shape != (M.RING,) or int(rg.max()) > 30 or int(rg.min()) < 0:
        raise SystemExit('ring range')
    tabs = [M.table2(lv) for lv in (1, 2, 3)]
    if any(x.shape != (256, 64) or x.dtype.itemsize != 1 for x in tabs):
        raise SystemExit('table shape')
    d = bytes(rg.astype('uint8')) + b''.join(x.tobytes() for x in tabs)
    if len(d) != CLAIM[1] - CLAIM[0] or T_AT - RING_AT != M.RING:
        raise SystemExit('data size')
    return d


def put(spec, stock, addr, old, new, why):
    """Into the edit that covers addr (the grain_cpu block), as patches/split_tone put()."""
    im = ST.img_of(spec, stock)
    if im[addr - BASE:addr - BASE + len(old)] != old:
        raise SystemExit(f'{addr:#x}: {im[addr - BASE:addr - BASE + len(old)].hex()} != {old.hex()} ({why})')
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a, n = int(e['addr'], 16), len(e['new']) // 2
            if a <= addr and addr + len(new) <= a + n:
                b = bytearray.fromhex(e['new']); b[addr - a:addr - a + len(new)] = new; e['new'] = b.hex()
                e['why'] += f' [grain_g2: {why}]'
                return
            if a < addr + len(new) and addr < a + n:
                raise SystemExit(f'{addr:#x}: straddles edit {e["addr"]}')
    raise SystemExit(f'{addr:#x}: no edit holds it')


def apply(spec, version='0.33'):
    if REV == 'g2':
        return _load('grain_g2_build_g2', HERE / 'build_g2.py').apply(spec, version)
    if REV != 'g3':
        raise SystemExit(f'REV = {REV}')
    stock = STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    if 'grain_g2' in spec:
        raise SystemExit('grain_g2 already applied')
    for k in ('grain_cpu', 'extras_pages'):
        if k not in spec:
            raise SystemExit(f'needs {k}')
    for k in ('keyhook', 'overlay_probe', 'diag', 'plugin_loader'):
        if k in spec:
            raise SystemExit(f'{k} is in the spec: its claim is this one (plugins are shelved; build without them)')
    im = ST.img_of(spec, stock)
    g = {k: int(v, 16) for k, v in spec['grain_cpu']['symbols'].items()}
    check_sites(spec, im, g)
    check_claims(spec, stock, im)
    code, sy, lst, cost = build_code(g)
    d = data()
    for at, new, why in ((AT, code, f'grain_g2 {version} (g3): g2_grain / g3_next / g3_row ({len(code)} B, K = {K}), claim {CODE[0]:#x}..{CODE[1]:#x}'),
                         (RING_AT, d, f'grain_g2 {version} (g3): g3_ring (r2 fill, seed {M.RING_SEED}) + g3_T Low / Med / High ({len(d)} B), claim {CLAIM[0]:#x}..{CLAIM[1]:#x}')):
        spec['edits'].append(dict(kind='0x100', addr=hex(at), expect=stock[at - BASE:at - BASE + len(new)].hex(), new=new.hex(), source=SRC,
                                  why=why + ', sec-5 dead sdk-api handlers'))
    at = g['gc_grain']
    put(spec, stock, at, ENTRY_OLD, b'\xdc' + struct.pack('<i', sy['g2_grain'] - at) + b'\xcb', 'gc_grain -> jmp g2_grain; nop')
    spec['grain_g2'] = dict(built_by=SRC, rev='g3', version=version, claim=[hex(CLAIM[0]), hex(CLAIM[1])], claim_code=[hex(CODE[0]), hex(CODE[1])],
                            code=[hex(AT), len(code)], ring=[hex(RING_AT), M.RING], tables=[hex(T_AT), 3 * 16384],
                            free=[hex(AT + len(code)), hex(CODE[1] - GUARD)], k=K, hw_max=HW_MAX, frame_growth=0, ring_seed=M.RING_SEED,
                            fill_end=hex(M.fill_end()), strengths=[M.S[1], M.S[2], M.S[3]], centre=M.C, site=hex(at), instructions=cost, pins=len(pins()),
                            unused_r2=[[hex(g[a] + (6 if a == 'gc_grain' else 0)), hex(g[b])] for a, b in
                                       (('gc_grain', 'gc_cls'), ('gc_fill', 'gc_btab'), ('gc_stab', 'gc_t9'), ('gc_G', 'gc_end'))],
                            symbols={k: hex(v) for k, v in dict(sy, g3_ring=RING_AT, g3_T=T_AT).items() if k.startswith(('g2_', 'g3_'))})
    return spec


# ---------------------------------------------------------------- pins: the reason for each one, re-derived by disassembly
PINS_HEAD = '''# Naive reference-scan hits into the grain_g2 claim {lo}..{hi} that are not address uses (build.py check_claims).
# Written and re-checked by `build.py --pins SPEC [--write-pins]`; docs/GRAIN_PORT.md "g2" has the method and the counts.
# address, its four bytes, scan kind (abs32: the bytes read as an address in the claim on one of the four aliases; rel: a
# cc / cd / dc / dd byte whose displacement lands in the claim), then what the bytes are:
#   i ADDR  inside the one instruction at ADDR, as opcode, register-list, frame or displacement bytes, not as its address operand
#   x ADDR  they run over the end of the instruction at ADDR into the next one
'''


def sweep(img, lo, hi):
    out = subprocess.run([B3.TC / 'mn10300-elf-objdump', '-b', 'binary', '-m', 'am33-2', '-D', f'--adjust-vma={BASE:#x}',
                          f'--start-address={lo:#x}', f'--stop-address={hi:#x}', img], capture_output=True, text=True, check=True).stdout
    return [(int(m.group(1), 16), m.group(2), m.group(3).strip()) for m in re.finditer(r'^\s*([0-9a-f]+):\t[0-9a-f ]+?\s*\t(\S+)[ \t]*(.*)$', out, re.M)]


def reason(img, im, x, kind, back=64, n=16):
    """The instruction over byte x on which n sweeps agree (they start one byte apart, 64 bytes or more before x): the
    code is self-synchronising, and this matched every hit that lies in a function with a known entry.
    -> ('i' inside that instruction, not as its address operand | 'x' running over its end | None, its address)."""
    cover = set()
    for i in range(n):
        d = sweep(img, x - back - i, x + 16)
        addrs = [a for a, _, _ in d]
        b = max(a for a in addrs if a <= x)
        cover.add((b, min((a for a in addrs if a > b), default=b + 8), next(t for t in d if t[0] == b)[1:]))
    if len(cover) != 1:
        return None, 0
    (b, nxt, (op, args)), = cover
    if kind == 'rel':                              # the cc / cd / dc / dd byte must not start an instruction
        return ('i' if b != x else None), b
    if x + 4 > nxt:
        return 'x', b
    val = u32(im, x)
    toks = re.split(r'[,() ]+', args)
    if {hex(val), str(val), str(val - (1 << 32))} & set(toks):
        return None, b
    return 'i', b


def pins_table(spec_path, write=False):
    """Scan both claims in the image without this layer's edits; classify every hit; compare with (or write) the two pin files."""
    import tempfile
    stock = STOCK.read_bytes()
    spec = json.loads(Path(spec_path).read_text())
    spec['edits'] = [e for e in spec['edits'] if e.get('source') != SRC]
    im = bytearray(ST.img_of(spec, stock))
    if 'grain_g2' in spec:                         # the redirect sits inside the grain_cpu edit: undo it
        at = int(spec['grain_g2']['site'], 16); im[at - BASE:at - BASE + 6] = ENTRY_OLD
    im = bytes(im)
    off5 = KH.sec(stock, 5)[2]
    total = 0
    with tempfile.NamedTemporaryFile(suffix='.bin') as tf:
        tf.write(im); tf.flush()
        for claim, name in PIN_FILES:
            KH.FALSE_POS.clear()
            rows, bad = [], []
            for kind, x in sorted(KH.scan(im, claim[0], claim[1], off5, KH.DEAD), key=lambda h: h[1]):
                c, b = reason(tf.name, im, x, kind)
                rows.append((x, im[x - BASE:x - BASE + 4].hex(), kind, c, b))
                if c is None:
                    bad.append((kind, hex(x)))
            if bad:
                raise SystemExit(f'not a false positive by disassembly: {bad}')
            text = ''.join(f'{x:#x} {b4} {kind} {c} {b:#x}\n' for x, b4, kind, c, b in rows)
            if write and name != 'pins.txt':       # pins.txt is g2's file, unchanged: the same claim, the same hits
                (HERE / name).write_text(PINS_HEAD.replace('{lo}', hex(claim[0])).replace('{hi}', hex(claim[1])) + text)
            have = '\n'.join(l for l in (HERE / name).read_text().splitlines() if l.startswith('0x')) + '\n'
            if have != text:
                raise SystemExit(f'{name} differs from the scan')
            total += len(rows)
    return total


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path, nargs='?')
    ap.add_argument('--out', type=Path)
    ap.add_argument('--version', default='0.33')
    ap.add_argument('--listing', type=Path)
    ap.add_argument('--pins', type=Path, metavar='SPEC', help='re-derive every pin by disassembly and compare with the pin files')
    ap.add_argument('--write-pins', action='store_true')
    a = ap.parse_args()
    if a.pins:
        print(pins_table(a.pins, a.write_pins), 'pins, each re-derived')
        sys.exit(0)
    spec = apply(json.loads(a.spec.read_text()), a.version)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(spec, indent=1))
    if a.listing:
        a.listing.write_text(build_code({k: int(v, 16) for k, v in spec['grain_cpu']['symbols'].items()})[2])
    print(json.dumps({k: v for k, v in spec['grain_g2'].items() if k != 'symbols'}))
