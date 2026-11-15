#!/usr/bin/env python3
"""Movie quality: 4K gets its own bit-rate choice in the camera's movie slot editor (docs/RE_MOVIE.md "Movie quality layer").
4K F stays 100 Mbit/s (stock), 4K SF is 150 Mbit/s, 4K N is 60 Mbit/s, chosen per slot in the same Bit Rate column that FHD
and HD use. An alternative to patches/movie_bitrate (4K always 150 M): the build refuses if both are in the chain. Layer it
with --extra after v033b; look_hw and shortcut_cycle_v2 may be present (no shared bytes):

  .venv/bin/python -I patches/v032/build.py releases/v0.31d/edits.json --out generated/v034_quality/edits.json --version 0.34a \\
      --extra grain_g2=patches/grain_g2/build.py --extra halation_h6=patches/halation_h6/build.py \\
      --extra crash_log=patches/crash_log/build.py --extra clean_boot=patches/clean_boot/build.py \\
      --extra v033b=patches/v033b/build.py --extra look_hw=patches/look_hw/build.py \\
      --extra shortcut_cycle=patches/shortcut_cycle_v2/build.py --extra movie_quality=patches/movie_quality/build.py

How stock handles 4K quality (all [V] code / bytes): the slot arrays already hold a quality per slot for every size (keys
0xf031 size, 0xf041 quality; the validators let slots 0-4 and 7 store 6/1/2, slots 1-4 and 7 also 5), but 4K never uses it:
  - the slot editor (actuator kind 13, params 31-36 = slots 0-4, 7; columns size / bit rate / fps) skips the bit-rate column
    when the size column is 8 or 9: cursor predicates 0x60e1e8fd (Right from column 0) and 0x60e1e92d (Left from column 2);
  - its viewer draws "--" (kind-5 text 0x611ddc78) in place of the bit-rate value when the size is 8 (slot-0 drawer 0x60e973bf,
    slots 1-4 drawer 0x60e9757e) or 8 / 9 (slot-7 drawer 0x60e97758);
  - the recorder's quality getter 0x6031bf37 returns 1 (F) for size 8 or 9. It is the only reader of key 0xf041 in the image;
    every recording, split and remaining-time path takes the quality from it (callers 0x6030bbb3 settings record,
    0x603183a9 estimate, 0x603269ba HS estimate) and turns it into the table column (6 -> SF col 1, 1 -> F col 2, 2 -> N
    col 3, 5 -> ALL-I col 0 + picture type 1) in 0x6031f0a3 / 0x6031f33f / 0x6031f454;
  - the bitrate table 0x60539b84 has only the F column for 4K (SF / N / ALL-I cells are 0: a 0 cell is an error in the
    size calculator, 0xa003, and in the encoder setter).

Edits:
  U1 0x60e1e917, 0x60e1e947 (imm8 of `cmp 8,d0` in the two cursor predicates) 8 -> 9: the column is skipped for C4K only.
  U2 0x60e974a2, 0x60e97670, 0x60e9784e (imm8 of `cmp 8,d1` in the three drawers) 8 -> 9: "--" for C4K only, else the value.
  R  0x6031bf37 (8 B: mov d0,d2; exthu d2; mov 0xf031,d0) -> jmp mq_get + 3 nop. mq_get (mq.s.in, section 1, in grain_g2's
     unused r2 piece 0x601e074d-0x601e084d): C4K -> 1; 4K -> the slot's quality, 5 (ALL-I) -> 6 (SF: no 4K intra mode);
     other sizes -> the slot's quality (stock).
  B  bitrate table mode 1 (4K): SF column 30p 0x60539bf8, 25p 0x60539c08, 24p 0x60539c18: 0 -> 150 000 000; N column 30p
     0x60539c00, 25p 0x60539c10, 24p 0x60539c20: 0 -> 60 000 000. F (0x60539bfc / c0c / c1c) stays 100 000 000.
  C  0x603d19db (6 B: mov 105000000,d0, ulMaxBitrate for every mode but C4K and FHD ALL-I) -> jmp mq_ceil + nop: 157 500 000
     when ulBitRate > 100 M (only the new 4K SF), else 105 000 000 as stock. So every stock level stays byte-identical in
     its encoder block too; only SF / N are new.

User note (draft): In the movie quality editor (select a movie slot, then edit it), 4K now has a Bit Rate setting like Full
HD: SF about 150 Mbit/s, F about 100 Mbit/s (stock 4K), N about 60 Mbit/s. Each slot keeps its own choice. A slot that was 4K
before keeps whatever bit rate it last had for Full HD (often F, the stock 4K rate), so check it once. 4K SF files split
about every 3 min 20 s (F: 5 min 20 s, N: 8 min 40 s) because each file stays under 4 GB, and the remaining time shows about
two thirds of F's. Use a V30 card for 4K SF. Slots 1-4 also offer ALL-I in that column: for 4K it records as SF.

apply(spec, version) -> spec (adds 13 edits + the mq_get / mq_ceil code inside the grain_cpu edit, and spec['movie_quality']).
"""
import argparse, copy, hashlib, importlib.util, json, re, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SRC = 'patches/movie_quality'


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


MB = _load('movie_bitrate_build_mq', ROOT / 'patches/movie_bitrate/build.py')
CL, ST, KH, B3 = MB.CL, MB.ST, MB.KH, MB.B3
BASE, STOCK = MB.BASE, MB.STOCK
GETTER = 0x6005e971
CEIL_BACK = 0x603d19e1                                                  # `mov d0,(4,a2)` after the ceiling mov

TABLE, ROW = MB.TABLE, MB.ROW
FPS_ROW = {30: 2, 25: 3, 24: 4}
SF = {f: TABLE + ROW + r * 0x10 + 1 * 4 for f, r in FPS_ROW.items()}     # 0x60539bf8 / c08 / c18
NN = {f: TABLE + ROW + r * 0x10 + 3 * 4 for f, r in FPS_ROW.items()}     # 0x60539c00 / c10 / c20
FF = MB.CELLS                                                           # F cells, stay 100 M
NEW_SF, NEW_N = 150_000_000, 60_000_000

# U1 cursor predicates: (function, imm address); each is `cmp 8,d0 (a0 08); beq; cmp 9,d0 (a0 09); bne` on the size column
PRED = {0x60e1e8fd: 0x60e1e917, 0x60e1e92d: 0x60e1e947}
PRED_CTX = bytes.fromhex('a008c806a009c90d')
# U2 drawers: (function start, end, imm address, stock bytes from the movhu before the compare)
DRAW = [(0x60e973bf, 0x60e9757e, 0x60e974a2, 'f8bd4482a508c92c'), (0x60e9757e, 0x60e97758, 0x60e97670, 'f8bd4882a508c92c'),
        (0x60e97758, 0x60e97960, 0x60e9784e, 'f8bd4882a508c806a509c92c')]
DASH = 0x611ddc78                                                       # the "--" text the drawers use
# R the quality getter
QG, QG_END = 0x6031bf37, 0x6031bf6a
QG_STOCK = bytes.fromhex('821efccc31f000009000') + b'\x89'
HOLE = ('0x601e074d', '0x601e084d')                                     # grain_g2 unused r2 piece (not look_hw's, not v033b's)
# a coincidence into the claim: unaligned bytes of a data table (aligned words there: 0x07648003, 0x6100a01e)
CODE_PINS = {0x6100a55a: ('64071ea0', 'data bytes straddling two words of a section-6 table, read as 0xa01e0764'),
             0x601e10f5: ('ccb1f600', 'inside tone_ends\' `mov 63153,d0` (fc cc b1 f6 00 00) at 0x601e10f4, read as jmp d16')}
BAD = {'mul', 'mulu', 'div', 'divu', 'ext', 'setlb', 'llt', 'lne', 'leq', 'lra', 'lcc', 'lcs', 'trap', 'rti', 'rets', 'retf', 'calls', 'movm', 'jmp'}


def u32(m, a):
    return struct.unpack_from('<I', m, a - BASE)[0]


def check_stock(stock):
    MB.check_stock(stock)
    for f in FPS_ROW:
        if u32(stock, SF[f]) or u32(stock, NN[f]) or u32(stock, TABLE + ROW + FPS_ROW[f] * 0x10) or u32(stock, FF[f]) != 100_000_000:
            raise SystemExit(f'4K {f}p row is not [0, 0, 100 M, 0] in stock')
    for fn, imm in PRED.items():
        if stock[imm - 1 - BASE:imm + 7 - BASE] != PRED_CTX:
            raise SystemExit(f'cursor predicate {fn:#x} differs from stock')
    for lo, hi, imm, ctx in DRAW:
        c = bytes.fromhex(ctx)
        if stock[imm - 5 - BASE:imm - 5 + len(c) - BASE] != c:
            raise SystemExit(f'drawer {lo:#x} compare differs from stock')
    if struct.unpack_from('<H', stock, DASH - BASE)[0] != 0x2d2d:
        raise SystemExit('"--" text differs')
    if stock[QG - BASE:QG + len(QG_STOCK) - BASE] != QG_STOCK:
        raise SystemExit('quality getter differs from stock')


def whole_insn(im, lo, hi, site, n, what):
    ins = B3.disasm(im[lo - BASE:hi - BASE], lo, hi)
    at = {a for a, _, _ in ins}
    if site not in at or site + n not in at:
        raise SystemExit(f'{what}: {site:#x} is not whole instructions in the linear decode of {lo:#x}')
    inside = [(a, op, t) for a, op, args in ins for t in re.findall(r'0x([0-9a-f]{8})', args)
              if (op[0] in 'bjl' or op.startswith('call')) and site < int(t, 16) < site + n]
    return ins, inside


def check_sites(spec, stock, im):
    off2, off6 = KH.sec(stock, 2)[2], KH.sec(stock, 6)[2]
    scans = []
    for fn, imm in PRED.items():                      # the compare is one instruction; nothing lands on its immediate
        ins, inside = whole_insn(im, fn, fn + 48, imm - 1, 2, f'predicate {fn:#x}')
        if inside or CL.refs(im, imm, imm + 1, off6):
            raise SystemExit(f'reference into {imm:#x}')
        scans.append(hex(imm))
    for lo, hi, imm, _ in DRAW:
        ins, inside = whole_insn(im, lo, hi, imm - 1, 2, f'drawer {lo:#x}')
        if inside or CL.refs(im, imm, imm + 1, off6):
            raise SystemExit(f'reference into {imm:#x}')
        scans.append(hex(imm))
    ins, inside = whole_insn(im, QG, QG_END, QG, 8, 'quality getter')
    far = CL.refs(im, QG + 1, QG + 8, off2)
    if inside or far:
        raise SystemExit(f'references into the getter head: {inside[:3]} {far[:3]}')
    into_rest = [(a, op) for a, op, args in ins for t in re.findall(r'0x([0-9a-f]{8})', args)
                 if (op[0] in 'bj') and QG + 8 <= int(t, 16) < QG_END]
    far_rest = CL.refs(im, QG + 8, QG_END, off2, allow=[(QG, QG_END)])
    if far_rest:
        raise SystemExit(f'references from outside into the getter body: {far_rest[:3]}')
    for a in list(SF.values()) + list(NN.values()):
        if [r for r in CL.refs(im, a, a + 4, off2, allow=[(TABLE, MB.BUF_TABLE + MB.BUF_LEN)]) if r[1] not in MB.PINS]:
            raise SystemExit(f'reference to the table word {a:#x}')
    MB.table_refs(im, stock)
    n, into = MB.ceiling_scan(im, stock)
    return scans, len(ins), into_rest, into


def check_slots(stock):
    """Every slot that can hold 4K must let its quality hold 6 and 1 (the column writes through the validator)."""
    out = {}
    tab = 0x604cc98c
    rec = {}
    for i in range(1333):
        s, attr, lst, alt, nb, el, sub, ty, z = struct.unpack_from('<HHIIHHBBH', stock, tab + 20 * i - BASE)
        rec[s] = [stock[lst - BASE + j] for j in range(nb)] if el == 1 else None
    for k in range(8):
        sizes, quals = rec.get(700 + k), rec.get(708 + k)
        if sizes and 8 in sizes and not (quals and 6 in quals and 1 in quals):
            raise SystemExit(f'slot {k}: 4K allowed but quality {quals} lacks 6 / 1')
        out[k] = dict(sizes=sizes, qualities=quals)
    return out


def build_code(spec, stock, im):
    if list(HOLE) not in spec['grain_g2']['unused_r2']:
        raise SystemExit('grain_g2 no longer lists the r2 piece as unused')
    lo, hi = (int(v, 16) for v in HOLE)
    at = (lo + 3) & ~3                                                   # 0x601e0750
    code, _, sy, _ = B3.assemble((HERE / 'mq.s.in').read_text(), at, dict(ep7_getter=GETTER, ep7_ceil_back=CEIL_BACK))
    end = at + len(code)
    claim = (lo, (end + 15) & ~15)
    if sy['mq_get'] != at or claim[1] + 16 > hi:
        raise SystemExit('mq_get layout')
    ins = B3.disasm(code, at, end)
    ce = sy['mq_ceil']
    g, c = [x for x in ins if x[0] < ce], [x for x in ins if x[0] >= ce]
    calls = [(a, args) for a, op, args in g if op == 'call']
    rets = [(a, args) for a, op, args in g if op == 'ret']
    if any(op in BAD for _, op, _ in g) or any(code[a - at] == 0xfb for a, _, _ in ins) or B3.store_audit(ins) \
            or len(calls) != 3 or any(not args.startswith(f'{GETTER:#x},[d2,d3],12') for _, args in calls) \
            or rets != [(g[-1][0], '[d2],8')]:
        raise SystemExit(f'mq_get audit: {[(hex(a), op, args) for a, op, args in g]}')
    if [op for _, op, _ in c] != ['mov', 'cmp', 'bhi', 'mov', 'jmp', 'mov', 'jmp'] \
            or [args for _, op, args in c if op == 'jmp'] != [hex(CEIL_BACK)] * 2 \
            or [args for _, op, args in c if op == 'mov'] != ['(a2),d0', '105000000,d0', '157500000,d0'] or c[1][2] != '100000000,d0':
        raise SystemExit(f'mq_ceil audit: {[(hex(a), op, args) for a, op, args in c]}')
    dead = [(int(a, 16), int(b, 16)) for a, b in spec['grain_g2']['unused_r2']]
    bad = [r for r in CL.refs(im, claim[0], claim[1], KH.sec(stock, 1)[2], allow=[CL.STEP_WORDS] + dead)
           if not (r[1] in CODE_PINS and im[r[1] - BASE:r[1] + 4 - BASE].hex() == CODE_PINS[r[1]][0])]
    if bad:
        raise SystemExit(f'reference into the mq_get claim: {[(k, hex(a)) for k, a in bad[:6]]}')
    return at, code, claim, ins, sy


def apply(spec, version='0.34a'):
    stock = STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    if 'movie_quality' in spec:
        raise SystemExit('movie_quality already applied')
    if 'movie_bitrate' in spec:
        raise SystemExit('movie_bitrate is in the chain: movie_quality is its alternative (4K F stays 100 M here)')
    check_stock(stock)
    im = ST.img_of(spec, stock)
    sites = [(a, a + 4) for a in list(SF.values()) + list(NN.values())] + [(MB.CEIL_AT, MB.CEIL_AT + 6), (QG, QG_END)] \
        + [(a, a + 1) for a in PRED.values()] + [(d[2], d[2] + 1) for d in DRAW]
    for lo, hi in sites:
        if MB.overlaps(spec, lo, hi):
            raise SystemExit(f'{lo:#x}: overlaps edit {MB.overlaps(spec, lo, hi)}')
    if im[TABLE - BASE:MB.BUF_TABLE + MB.BUF_LEN - BASE] != stock[TABLE - BASE:MB.BUF_TABLE + MB.BUF_LEN - BASE]:
        raise SystemExit('another layer changed the bitrate / buffer tables')
    scans, n_qg, into_rest, ceil_into = check_sites(spec, stock, im)
    slots = check_slots(stock)
    at, code, claim, ins, sy = build_code(spec, stock, im)
    why = f'movie_quality mq_get ({len(code)} B) over r2\'s unused bytes'
    CL.put(spec, stock, at, im[at - BASE:at + len(code) - BASE], code, why)
    g = next(e for e in spec['edits'] if e['why'].endswith(f' [crash_log: {why}]'))
    g['why'] = g['why'][:-len(f' [crash_log: {why}]')] + f' [movie_quality: {why}]'
    spec['grain_g2']['unused_r2'] = [[hex(claim[1]), HOLE[1]] if r == list(HOLE) else r for r in spec['grain_g2']['unused_r2']]
    jmp = b'\xdc' + struct.pack('<i', at - QG) + b'\xcb' * 3
    E = lambda a, old, new, w: spec['edits'].append(dict(kind='0x100', addr=hex(a), expect=old.hex(), new=new.hex(), source=SRC, why=w))
    E(QG, QG_STOCK[:8], jmp, 'movie_quality R: quality getter 0x6031bf37 head -> jmp mq_get (4K keeps the slot\'s bit rate)')
    for fn, imm in PRED.items():
        E(imm, b'\x08', b'\x09', f'movie_quality U1: slot editor cursor predicate {fn:#x} cmp 8 -> 9 (skip the bit-rate column for C4K only)')
    for lo, _, imm, _ in DRAW:
        E(imm, b'\x08', b'\x09', f'movie_quality U2: slot editor drawer {lo:#x} cmp 8 -> 9 ("--" for C4K only)')
    for f in sorted(FPS_ROW, reverse=True):
        E(SF[f], bytes(4), struct.pack('<I', NEW_SF), f'movie_quality B: 4K {f}p SF (table mode 1, column 1) 0 -> 150 M bit/s')
        E(NN[f], bytes(4), struct.pack('<I', NEW_N), f'movie_quality B: 4K {f}p N (table mode 1, column 3) 0 -> 60 M bit/s')
    cj = b'\xdc' + struct.pack('<i', sy['mq_ceil'] - MB.CEIL_AT) + b'\xcb'
    E(MB.CEIL_AT, im[MB.CEIL_AT - BASE:MB.CEIL_AT + 6 - BASE], cj,
      'movie_quality C: encoder setter 0x603d19db mov 105000000,d0 -> jmp mq_ceil (157.5 M only for ulBitRate > 100 M, else 105 M)')
    spec['movie_quality'] = dict(built_by=SRC, version=version, code=[hex(at), len(code)], claim=[hex(claim[0]), hex(claim[1])],
                                 symbols=dict(mq_get=hex(at), mq_ceil=hex(sy['mq_ceil'])), getter=hex(QG), getter_scan=f'{n_qg} instructions; body branches {into_rest}',
                                 ui_imms=scans, sf={f'{k}p': hex(v) for k, v in SF.items()}, n={f'{k}p': hex(v) for k, v in NN.items()},
                                 rates=dict(sf=NEW_SF, f=100_000_000, n=NEW_N), ceiling=dict(site=hex(MB.CEIL_AT), stub=hex(sy['mq_ceil']), rule='ulBitRate > 100 M -> 157.5 M else 105 M', branched_from=ceil_into),
                                 slots={k: v for k, v in slots.items()})
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
    print(json.dumps({k: v for k, v in spec['movie_quality'].items() if k != 'slots'}))
