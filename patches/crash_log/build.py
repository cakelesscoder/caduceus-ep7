#!/usr/bin/env python3
"""Crash record: the fault CPU, task, PC, cause, the stock capture history and our grain record, on the card after the next
power-on. docs/CRASH_LOG.md, docs/RE_CAPTURE.md section 4.1 (the design); cl.s.in has the contract. Layer on the v0.32 chain
after grain_g2 (it lives in r2 bytes that g2 left unused). Offline.

  .venv/bin/python -I patches/v032/build.py releases/v0.31d/edits.json --out generated/crash_log/edits.json --version 0.33 \\
      --extra grain_g2=patches/grain_g2/build.py --extra crash_log=patches/crash_log/build.py

apply(spec, version) -> spec. Edits:
  - 0x60059aab in the NMI handler, `mov 0x600774ec,a0` (6 B) -> `jmp cl_nmi; nop` (C1);
  - sd_go's `call sd_load,[d2,d3,a2,a3],36` in the card loader (5 B) -> `jmp cl_first` (C2);
  - cl_nmi / cl_first + the file path, in section 1: the body of r2's gc_grain after grain_g2's jmp (inside the grain_cpu edit).
The record format is tools/ep7_crash.py (the decoder); this file only fills cl.s.in from it.
"""
import argparse, copy, hashlib, importlib.util, json, re, struct
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SRC = 'patches/crash_log'


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


XP = _load('ep7_xp_build_cl', ROOT / 'patches/extras_pages/build.py')
GB = _load('grain_g2_build_cl', ROOT / 'patches/grain_g2/build.py')       # read only: its checks of the r2 routines we mirror
F = _load('ep7_crash_fmt', ROOT / 'tools/ep7_crash.py')
ST, KH, B3 = XP.ST, XP.KH, XP.B3
BASE, STOCK = XP.BASE, XP.STOCK

# ---- the record: RAM that boot does not clear and no stock code addresses (RE_CAPTURE 4.1), uncached alias
R = 0xa2ae8100
R_FREE = (0x62ae80c0, 0x62de0000)         # after the three NMI frames, before the ICTLOG mirror
FRAMES = 0x62ae8000                       # 3 x 0x40 B, cached (each CPU's NMI entry writes its own)
RING = 0xa26a0aa0                         # capture-history ring, 0x448 B per CPU
TCB = (0x621a630c, 0x626616c4, 0x6267c09c)    # current-TCB pointer per CPU; tid = s16 at +16
STATE_LO = 0x622cbcc0                     # u16 HLS_EVENT tid, u16 card-table handle (B3.STATE)
G_POOL = (0xa1bce7c0, 0xa1bd6d40)         # class-0 heap pool (malloc <= 128 B): where r2's 128-B grain record lives
GPTR, GDIA, G_BLK = 1000, struct.unpack('<I', b'GDIA')[0], 128
XCODE, SECT, ABORT, RECBLK, WMODE, ADDEC = 0x8ff000b0, 0xa272e420, 0xa26a0a94, 0xa26a1ca8, 0xa2716034, 0x9a000000
RAM = 0x08000000                          # RAM on both aliases reaches at least this far: the OSD string tables load at 0xa407f540
# ---- C1
SITE, SITE_OLD, BACK, HOOK_IMM = 0x60059aab, bytes.fromhex('fcdcec740760'), 0x60059ab1, 0x600774ec
HANDLER = (0x60059a9d, 0x60059cee)        # the NMI handler, one entry (the three vector stubs' `calls`)
# ---- C2
C2_OLD, C2_RET = bytes.fromhex('cd0800f024'), bytes.fromhex('dff024')    # call sd_load,[d2,d3,a2,a3],36 (d16); ret [d2,d3,a2,a3],36
FWRITE = 0x60635041
# ---- code: r2's gc_grain after its first 6 B, unused since grain_g2 (its entry is `jmp g2_grain; nop`)
HOLE_SHA = '8e8cf503726bf907'             # the r2 bytes of gc_grain's body (903 B): what this layer may overwrite
AT_PAD = 1                                # the code starts 4-aligned
STEP_WORDS = ST.STEP_WORDS                # dead EVF step-table words: the only stock references into these tables
BAD = {'mul', 'mulu', 'div', 'divu', 'ext', 'setlb', 'llt', 'lne', 'leq', 'lra', 'lcc', 'lcs', 'trap', 'rti', 'rets', 'retf', 'calls'}
# naive scan hits into the claim that are no address uses, each checked by disassembly / by the words around it: {address: (4 bytes, what)}
PINS = {0x6014f1b2: ('f0031e60', 'stock code `mov (a3),a0; exthu d2; mov d0,(a0)` (as grain_cpu r2 pins it)'),
        0x6107a5d6: ('f4011ea0', 'sec-6 record: u16 500, then the low half of the pointer 0x6107a01e (as grain_cpu r2 pins it)'),
        0x601e543e: ('cc60af52', 'byte 2 of the handler pointer 0x60cc0f89 in the debug-shell command table 0x601e5410.. ("mddyna")'),
        0x601e08c2: ('42048680', 'halation hl_box `mov d0,(4,sp); mov d1,d2; mov 2,d0`, read on the flash alias')}

# Stock bytes this layer relies on: (address, bytes, what)
NEED = (
    (0x60059aa2, '8001dd077ffcff0000', 'handler: mov 1,d0; call wdt_hw_set,[],0 right before the site'),
    (0x60059aab, 'fcdcec740760dd4e8afcfff01c', 'site: mov 0x600774ec,a0; call dbg_printf,[d2,d3,a2,a3],28'),
    (0x600219d5, '6070a000c807db70a000d9de0000', 'wdt_hw_set returns d0 = 0 from `cmp 0,d0`'),
    (0x60059ab8, '3250801e', 'handler: cpu = (0x8050), exthu'),
    (0x60059acd, 'fca00c631a62fccf0080ae62f8601018', 'handler CPU0: TCB word, frame, tid = exth (16,TCB)'),
    (0x60059af6, 'fca0c4166662fccf4080ae62f8601018', 'handler CPU1: TCB word, frame, tid'),
    (0x60059b1f, 'fca09cc06762fccf8080ae62f8601018', 'handler CPU2: TCB word, frame, tid'),
    (0x60059c18, '300089', 'handler: NMIINTREG (0x8900)'),
    (0x60059c28, '304480', 'handler: SYSERRREG (0x8044)'),
    (0x60055250, 'fc812080ae62fc803080ae62', 'NMI stub CPU0: d0 -> frame +0x20, a0 -> +0x30'),
    (0x60055293, '5800fc810880ae625804fc810c80ae623cfc800480ae62', 'NMI stub CPU0: (sp) -> +8, (4,sp) -> +0xc, sp -> +4'),
    (0x603e4e90, 'fb154804fcc1a00a6aa2', 'history ring: 0x448 B per CPU at 0xa26a0aa0'),
    (0x60022782, 'fac88000c505', 'malloc: <= 128 B is class 0'),
    (0x600227b6, 'fcc8c0e7bca1c40dfcc8406dbda1c605', 'free: class-0 pool bounds'),
    (0x600227b1, 'df0004', 'malloc: ret [],4'),
    (0x60022801, 'df0004', 'free: ret [],4'),
    (0x600589d9, 'fc81b000f08f', 'system-down code word 0x8ff000b0'),
    (0x600672ee, '305080fcdc346071a21c54f300', 'window mode array 0xa2716034, one word per CPU'),
    (0x6005616f, 'fca40800009a', 'ADDEC handler CPU0: ADDR (0x9a000008)'),
    (0x60056182, 'fca40c00009a', 'ADDEC handler CPU0: R DATA'),
    (0x60056195, 'fca41000009a', 'ADDEC handler CPU0: W DATA'),
    (0x600561a8, 'fca41400009a', 'ADDEC handler CPU0: STATUS'),
    (0x600561f8, 'fca40801009a', 'ADDEC handler CPU1: + 0x100'),
    (0x603dfa1a, 'fca4940a6aa2', 'REC abort word 0xa26a0a94'),
    (0x603ecaab, 'fca5a81c6aa2', 'REC working block pointer 0xa26a1ca8'),
    (0x60634fbc, '00cd9b13f02cdf0004', 'fopen: ret [],4'),
    (0x6063503e, 'dfb010', 'fclose: ret [d2,a2,a3],16'),
    (0x60635041, '4704878293', 'fwrite: a1 handle, d1 count, d0 size, a0 buffer'),
    (0x606350cc, 'dff018', 'fwrite: ret [d2,d3,a2,a3],24'),
)


def u32(im, a):
    return struct.unpack_from('<I', im, a - BASE)[0]


def sub(version):
    """cl.s.in's fields, from the format in tools/ep7_crash.py."""
    g_span = G_POOL[1] - G_POOL[0] - G_BLK + 1
    if F.GRAIN_LEN != G_BLK or F.RING_LEN != 0x448 or F.FRAMES_LEN != 0xc0 or F.NCPU != 3:
        raise SystemExit('format / firmware sizes differ')
    if not (R_FREE[0] <= R - 0x40000000 and R - 0x40000000 + F.FILE_LEN <= R_FREE[1] and R % 4 == 0 and F.SLOT % 4 == 0 and F.BODY % 4 == 0):
        raise SystemExit('record area')
    if F.FILE_LEN > 16384 or F.FILE_LEN <= 2048:
        raise SystemExit('the file copy must be a class-2 malloc')
    off = {k.lower(): hex(v) for k, v in vars(F).items() if k.startswith('O_') and isinstance(v, int)}
    off.update({f'o_wmode{4 * i}': hex(F.O_WMODE + 4 * i) for i in (1, 2)}, **{f'o_addec{4 * i}': hex(F.O_ADDEC + 4 * i) for i in (1, 2, 3)})
    flags = {k.lower(): v for k, v in vars(F).items() if k.startswith('F_') and isinstance(v, int)}
    if not (-128 <= ABORT - RING < 128 and 0 <= RECBLK - RING < 0x8000 and max(v for k, v in vars(F).items() if k.startswith('O_') and isinstance(v, int) and v < F.O_FRAMES) < 128):
        raise SystemExit('displacements')
    return dict(off, **flags, r=hex(R), slot=hex(F.SLOT), frames=hex(FRAMES), ring=hex(RING), ring_len=hex(F.RING_LEN),
                magic_ok=hex(struct.unpack('<I', F.MAGIC_OK)[0]), magic_busy=hex(struct.unpack('<I', F.MAGIC_BUSY)[0]), version=F.VERSION,
                tcb0=hex(TCB[0]), tcb1=hex(TCB[1]), tcb2=hex(TCB[2]), tcb_lim=hex(RAM - 0x100), sp_lim=hex(RAM - F.STACK_LEN),
                state_lo=hex(STATE_LO), state=hex(B3.STATE), lim=hex(B3.LIM), pool=hex(B3.POOL), bmagic=hex(B3.MAGIC),
                gptr=GPTR, g_lo=hex(G_POOL[0]), g_span=hex(g_span), gdia=hex(GDIA),
                xcode=hex(XCODE), sect=hex(SECT), abort_d=ABORT - RING, recblk_d=RECBLK - RING, wmode=hex(WMODE), addec=hex(ADDEC),
                body=hex(F.BODY), body_words=(F.SLOT - F.BODY) // 4, frames_words=F.FRAMES_LEN // 4, ring_words=F.RING_LEN // 4,
                grain_words=F.GRAIN_LEN // 4, stack_words=F.STACK_LEN // 4, hook_imm=hex(HOOK_IMM), build_tag=hex(F.build_tag(version)),
                ncpu=F.NCPU, file_len=F.FILE_LEN, file_words=F.FILE_LEN // 4, slot_words=F.SLOT // 4)


def check_stock(stock):
    for a, h, what in NEED:
        if stock[a - BASE:a - BASE + len(h) // 2].hex() != h:
            raise SystemExit(f'{a:#x}: stock bytes differ ({what})')
    B3.pool_check(stock)                                         # class-1 pool bounds: P and its 1024 B
    if STATE_LO + 2 != B3.STATE or B3.BUF_SIZE != 1024 or GPTR + 4 > B3.BUF_SIZE:
        raise SystemExit('card-table constants differ')
    # the handler: one linear pass from its entry; the site is two whole instructions, and no branch of it lands inside
    ins = B3.disasm(stock[HANDLER[0] - BASE:HANDLER[1] - BASE], HANDLER[0])
    at = {a for a, _, _ in ins}
    if not {SITE, BACK} <= at or any(SITE < a < BACK for a in at) or any(op.startswith('.') or op == '(bad)' for _, op, _ in ins):
        raise SystemExit('the NMI handler does not decode as mapped')
    for a, op, args in ins:
        for t in re.findall(r'0x([0-9a-f]{8})', args):
            if SITE < int(t, 16) < BACK and op[0] in 'bjl':
                raise SystemExit(f'handler branch into the site from {a:#x}')
    if u32(stock, SITE + 2) != HOOK_IMM:
        raise SystemExit('displaced immediate')


def refs(im, lo, hi, off, allow=()):
    """abs32 at every byte on the four aliases + d16 / d32 call, calls and jmp encodings into [lo, hi), as patches/keyhook scan()
    and tools/ep7_xref.py. -> [(kind, address)] minus the pinned sites and the allowed source ranges."""
    d = np.frombuffer(im, np.uint8).astype(np.int64)
    w = d[:-3] | (d[1:-2] << 8) | (d[2:-1] << 16) | (d[3:] << 24)
    pc = np.arange(len(d) - 8, dtype=np.int64) + BASE
    ok = lambda at: any(x <= at < y for x, y in allow) or (at in PINS and PINS[at][0] == im[at - BASE:at - BASE + 4].hex())
    bad = []
    for o in (0, 0x40000000, off, (off + 0x40000000) & 0xffffffff):
        a, b = (lo + o) & 0xffffffff, (hi + o) & 0xffffffff
        bad += [('abs32', int(i) + BASE) for i in np.nonzero((w >= a) & (w < b))[0] if not ok(int(i) + BASE)]
    for op, at_, n in (((0xdd,), 1, 4), ((0xdc,), 1, 4), ((0xcd,), 1, 2), ((0xcc,), 1, 2), ((0xfa, 0xff), 2, 2), ((0xfc, 0xff), 2, 4)):
        m = d[:-8] == op[0]
        if len(op) == 2:
            m &= d[1:-7] == op[1]
        b = [d[at_ + k:len(d) - 8 + at_ + k] for k in range(n)]
        disp = b[0] | (b[1] << 8) if n == 2 else b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24)
        disp = np.where(disp >= (1 << (8 * n - 1)), disp - (1 << (8 * n)), disp)
        bad += [('rel', int(x) + BASE) for x in np.nonzero(m & (pc + disp >= lo) & (pc + disp < hi))[0] if not ok(int(x) + BASE)]
    return sorted(set(bad))


def hole(spec):
    """-> (lo, hi, g): r2's gc_grain body, declared unused by grain_g2, and the grain symbols."""
    if 'grain_g2' not in spec or spec['grain_cpu'].get('test') != 'r2':
        raise SystemExit('needs grain_cpu r2 + grain_g2 (the code lives in the r2 bytes g2 left unused)')
    g = {k: int(v, 16) for k, v in spec['grain_cpu']['symbols'].items()}
    lo, hi = g['gc_grain'] + 6, g['gc_cls']
    if [hex(lo), hex(hi)] not in spec['grain_g2']['unused_r2']:
        raise SystemExit('grain_g2 does not list gc_grain\'s body as unused')
    return lo, hi, g


def check_sites(spec, stock, im, lo, hi, g, at, end):
    for a, n, what in ((SITE, 6, 'NMI handler site'),):
        if im[a - BASE:a - BASE + n] != stock[a - BASE:a - BASE + n]:
            raise SystemExit(f'{what}: already edited')
    if im[SITE - BASE:SITE - BASE + 6] != SITE_OLD:
        raise SystemExit('site bytes')
    if refs(im, SITE + 1, BACK, 0):                              # the base image has one alias pair; nothing lands inside the site
        raise SystemExit(f'reference into the NMI site: {refs(im, SITE + 1, BACK, 0)[:4]}')
    # the card loader: sd_go ends `call sd_load; sd_gout: ret`
    sd = {k: int(v, 16) for k, v in spec['sd_bundles_v3']['symbols'].items()}
    c2 = sd['sd_gout'] - 5
    if im[c2 - BASE:c2 - BASE + 5] != C2_OLD or c2 + struct.unpack_from('<h', im, c2 + 1 - BASE)[0] != sd['sd_load'] or im[sd['sd_gout'] - BASE:sd['sd_gout'] - BASE + 3] != C2_RET:
        raise SystemExit('sd_go: call sd_load,[d2,d3,a2,a3],36; ret [d2,d3,a2,a3],36 not found')
    if sd['sd_go'] + 12 != c2 or im[sd['sd_out'] - BASE:sd['sd_out'] - BASE + 3] != C2_RET:
        raise SystemExit('sd_go / sd_out layout')
    if B3.STATE != int(spec['sd_bundles_v3']['state'], 16) or B3.LIM != int(spec['sd_bundles_v3']['lim'], 16):
        raise SystemExit('loader state constants')
    # the hole: g2's jmp before it, the r2 bytes in it, live code around it that never branches in
    if im[g['gc_grain'] - BASE] != 0xdc or im[g['gc_grain'] + 5 - BASE] != 0xcb or g['gc_grain'] + struct.unpack_from('<i', im, g['gc_grain'] + 1 - BASE)[0] != int(spec['grain_g2']['symbols']['g2_grain'], 16):
        raise SystemExit('gc_grain is not `jmp g2_grain; nop`')
    if hashlib.sha256(im[lo - BASE:hi - BASE]).hexdigest()[:16] != HOLE_SHA:
        raise SystemExit('gc_grain\'s body differs from r2: another layer uses these bytes')
    if GB.sha(im, g, GB.USED) != GB.USED_SHA:
        raise SystemExit('gc_pp / gc_blk / gc_mark differ from r2 (the record chain this layer mirrors)')
    if not (lo <= at and end <= hi and at % 4 == 0):
        raise SystemExit(f'{end - at} B do not fit the hole {lo:#x}..{hi:#x}')
    for a, b in ((g['gc_open'], g['gc_grain'] + 6), (g['gc_cls'], g['gc_fill'])):
        for x, op, args in B3.disasm(im[a - BASE:b - BASE], a):
            if any(lo <= int(t, 16) < hi for t in re.findall(r'0x([0-9a-f]{8})', args)):
                raise SystemExit(f'live grain code at {x:#x} refers into the hole: {op} {args}')
    return c2, sd


def build_code(at, syms, version):
    code, lst, sy, _ = B3.assemble(B3.subst((HERE / 'cl.s.in').read_text(), sub(version)), at, syms)
    if sy['cl_nmi'] != at or sy['cl_end'] != at + len(code):
        raise SystemExit('layout')
    ins = B3.disasm(code, at, sy['cl_path'])
    if any(op.startswith('.') or op == '(bad)' for _, op, _ in ins) or any(code[a - at] == 0xfb for a, _, _ in ins):
        raise SystemExit('undecodable instruction or fb-prefixed form')
    c1 = [x for x in ins if x[0] < sy['cl_first']]
    c2 = [x for x in ins if x[0] >= sy['cl_first']]
    # C1: no call, no return, nothing that touches MDR / LIR / LAR; it leaves by one jmp, to the handler
    if any(op in BAD | {'call', 'ret'} for _, op, _ in c1):
        raise SystemExit('C1: forbidden instruction')
    out = [(a, int(args, 16)) for a, op, args in c1 if op == 'jmp' and not at <= int(args, 16) < sy['cl_first']]
    if out != [(c1[-1][0], BACK)]:
        raise SystemExit(f'C1 exits: {out}')
    for a, op, args in c1:
        for t in re.findall(r'0x([0-9a-f]{8})', args):
            if op[0] == 'b' and not at <= int(t, 16) < sy['cl_first']:
                raise SystemExit(f'C1 branch out at {a:#x}')
    for a, txt, kd, _ in B3.store_audit(c1):                     # record stores through a2 (the slot) and a1 (the copies), and the stack
        if not (kd == 'sp' or (kd == 'ind' and re.fullmatch(r'mov d[0-3],\((\d+,)?a2\)|mov d0,\(a1\)', txt))):
            raise SystemExit(f'C1 store at {a:#x}: {txt} ({kd})')
    stack = [(op, args) for _, op, args in c1 if 'sp' in args]
    if stack[:2] != [('movm', '[d2,d3,a2,a3],(sp)'), ('add', '-12,sp')] or stack[-2:] != [('add', '12,sp'), ('movm', '(sp),[d2,d3,a2,a3]')] \
            or any(op == 'add' or op == 'movm' for op, _ in stack[2:-2]) or any(not re.fullmatch(r'(d[01]|a1),\(([48],)?sp\)|\(([48],)?sp\),(d[01]|a1)', a_) for _, a_ in stack[2:-2]):
        raise SystemExit(f'C1 stack use: {stack}')
    if [(op, args) for _, op, args in c1[-3:]] != [('cmp', '0,d0'), ('mov', f'{HOOK_IMM},a0'), ('jmp', hex(BACK))]:
        raise SystemExit(f'C1 tail: {c1[-3:]}')
    # C2: the calls it makes and nothing else; one ret, sd_gate's own, at the end; branches stay inside
    if any(op in BAD for _, op, _ in c2) or [(op, args) for _, op, args in c2 if op == 'ret'] != [('ret', '[d2,d3,a2,a3],36')] or c2[-1][1] != 'ret':
        raise SystemExit('C2: forbidden instruction, or not ending on its one ret [d2,d3,a2,a3],36')
    calls = [(args.split(',')[0], args.split(',', 1)[1]) for _, op, args in c2 if op == 'call']
    want = [(hex(syms[k]), fr) for k, fr in (('ep7_sd_load', '[d2,d3,a2,a3],36'), ('ep7_malloc', '[],4'), ('ep7_fopen', '[],4'), ('ep7_fwrite', '[d2,d3,a2,a3],24'),
                                              ('ep7_fclose', '[d2,a2,a3],16'), ('ep7_free', '[],4'))]
    if calls != want:
        raise SystemExit(f'C2 calls {calls}')
    for a, op, args in c2:
        for t in re.findall(r'0x([0-9a-f]{8})', args):
            if (op[0] == 'b' or op == 'jmp') and not sy['cl_first'] <= int(t, 16) < sy['cl_path']:
                raise SystemExit(f'C2 branch out at {a:#x}')
    for a, txt, kd, _ in B3.store_audit(c2):                     # the heap copy (a1, a0), the record's marks (a2), sd_gate's frame
        if not (kd == 'sp' or (kd == 'ind' and txt in ('mov d0,(a1)', 'mov d0,(a0)', 'mov d0,(a2)'))):
            raise SystemExit(f'C2 store at {a:#x}: {txt} ({kd})')
    if code[sy['cl_path'] - at:] != b'C:\\EP7MOD\\CRASH.BIN\0w\0':
        raise SystemExit('strings')
    return code, sy, lst


def put(spec, stock, addr, old, new, why):
    """Into the edit that covers addr (the grain_cpu block, the card loader), as patches/grain_g2 put()."""
    im = ST.img_of(spec, stock)
    if im[addr - BASE:addr - BASE + len(old)] != old:
        raise SystemExit(f'{addr:#x}: {im[addr - BASE:addr - BASE + len(old)].hex()[:32]} != {old.hex()[:32]} ({why})')
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a, n = int(e['addr'], 16), len(e['new']) // 2
            if a <= addr and addr + len(new) <= a + n:
                b = bytearray.fromhex(e['new']); b[addr - a:addr - a + len(new)] = new; e['new'] = b.hex()
                e['why'] += f' [crash_log: {why}]'
                return
            if a < addr + len(new) and addr < a + n:
                raise SystemExit(f'{addr:#x}: straddles edit {e["addr"]}')
    raise SystemExit(f'{addr:#x}: no edit holds it')


def apply(spec, version='0.33'):
    stock = STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    if 'crash_log' in spec:
        raise SystemExit('crash_log already applied')
    check_stock(stock)
    im = ST.img_of(spec, stock)
    lo, hi, g = hole(spec)
    at = lo + AT_PAD
    sd = {k: int(v, 16) for k, v in spec['sd_bundles_v3']['symbols'].items()}
    sv = {k: int(v, 16) for k, v in spec['sd_bundles_v3']['services'].items()}
    syms = dict(ep7_nmi_back=BACK, ep7_sd_load=sd['sd_load'], ep7_malloc=sv['ep7_malloc'], ep7_free=sv['ep7_free'], ep7_fopen=sv['ep7_fopen'],
                ep7_fclose=sv['ep7_fclose'], ep7_fwrite=FWRITE)
    if sv['ep7_secbits'] != SECT:
        raise SystemExit('sections-loaded word')
    code, sy, lst = build_code(at, syms, version)
    end = at + len(code)
    claim = (lo, (end + 15) & ~15)
    c2, sd = check_sites(spec, stock, im, lo, hi, g, at, end)
    # no reference into the claim but the dead tables' step-table words, and the unused r2 code around it
    dead = [(int(a, 16), int(b, 16)) for a, b in spec['grain_g2']['unused_r2']]
    bad = refs(im, claim[0], claim[1], KH.sec(stock, 1)[2], allow=[STEP_WORDS] + dead)
    if bad:
        raise SystemExit(f'reference into the claim: {[(k, hex(a)) for k, a in bad[:8]]} ({len(bad)})')
    if not (KH.sec(stock, 1)[0] <= claim[0] and claim[1] <= KH.sec(stock, 1)[1]):
        raise SystemExit('the claim is not in section 1')
    put(spec, stock, at, im[at - BASE:end - BASE], code, f'cl_nmi / cl_first ({len(code)} B) over r2\'s unused gc_grain body')
    put(spec, stock, c2, C2_OLD, b'\xdc' + struct.pack('<i', sy['cl_first'] - c2), 'sd_go: call sd_load -> jmp cl_first (calls it, then the crash record)')
    spec['edits'].append(dict(kind='0x100', addr=hex(SITE), expect=SITE_OLD.hex(), new=(b'\xdc' + struct.pack('<i', sy['cl_nmi'] - SITE) + b'\xcb').hex(), source=SRC,
                              why=f'crash_log {version}: NMI handler `mov 0x600774ec,a0` (after wdt_hw_set(1)) -> jmp cl_nmi; nop'))
    spec['grain_g2']['unused_r2'] = [[hex(claim[1]), hex(hi)] if r == [hex(lo), hex(hi)] else r for r in spec['grain_g2']['unused_r2']]
    spec['crash_log'] = dict(built_by=SRC, version=version, build_tag=hex(F.build_tag(version)), format=F.VERSION, file='EP7MOD/CRASH.BIN', file_len=F.FILE_LEN, slot=F.SLOT, record=[hex(R), hex(R + F.FILE_LEN)],
                             code=[hex(at), len(code)], claim=[hex(claim[0]), hex(claim[1])], site=hex(SITE), back=hex(BACK), c2_site=hex(c2),
                             stack_bytes=28, c1_len=sy['cl_first'] - at, c2_len=sy['cl_path'] - sy['cl_first'],
                             symbols={k: hex(v) for k, v in sy.items() if k.startswith('cl_')})
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
        s = spec['crash_log']
        sd = {k: int(v, 16) for k, v in spec['sd_bundles_v3']['symbols'].items()}
        sv = {k: int(v, 16) for k, v in spec['sd_bundles_v3']['services'].items()}
        a.listing.write_text(build_code(int(s['code'][0], 16), dict(ep7_nmi_back=BACK, ep7_sd_load=sd['sd_load'], ep7_malloc=sv['ep7_malloc'], ep7_free=sv['ep7_free'],
                                                                     ep7_fopen=sv['ep7_fopen'], ep7_fclose=sv['ep7_fclose'], ep7_fwrite=FWRITE), a.version)[2])
    print(json.dumps({k: v for k, v in spec['crash_log'].items() if k != 'symbols'}))
