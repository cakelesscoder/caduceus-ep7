#!/usr/bin/env python3
"""Emulator checks for the clean restart (patches/clean_boot). Offline. docs/GRAIN_HANG.md "Clean restart".

  .venv/bin/python -I patches/clean_boot/verify.py BASE.json NEW.json [PKGDIR]
  BASE = the same chain without the layer, NEW = with `--extra clean_boot=patches/clean_boot/build.py`.

The run is one shutter half-press, from the card loader's hook (sd_hook) to the stock code after it (0x602c8064), on the real
code of every layer on the way: the gate, sd_go, cl_first, sd_load (+ cb_zero), ap_pre / ap_boot, mv_trig, fm_load (+ ls_chk),
mv_load, ap_post, ap_load, ed_trig. Stubs: the stock trigger call, the task id, malloc / free (a bump allocator over the three
real pools, which is how the stock one hands blocks out until every block has been used once), the file calls (the release
card's four files), the two settings getters. Every stub call is logged. Only the regions a case names exist, so an access
anywhere else is a fault.

  T  cb_zero by itself, from sd_load's entry to its `call ep7_fopen`: every register, the flags, MDR and the stack are BASE's;
     the block is zero and the bytes around it are untouched; an unaligned block is cleared the same way; without a block
     nothing is stored and the loader leaves through its own `jmp sd_out`
  C  clean power-on (DRAM zero): the calls, their order and arguments, every heap block, the state word, the boot byte, the
     registers and the whole stack == BASE. DRAM full of 0xee: the same calls, and P / P2 / P3 == the clean power-on's
  R  restart with stale DRAM: the heap of a finished session (every mark and pointer set, the editors used and unsaved, a
     split-tone block S, a grain record) is still there. NEW: the calls and the tables are the clean power-on's, fm_load
     allocates a new L, and with the old session's other blocks unmapped nothing faults. Then, on that state, the real split
     tone pass (st), halation's grid choice (h6_run) and the grain record (gc_mark): S and the grid in the new L, a new record,
     nothing stored in an old block, the Film page valid. The BUNDLES retry (P lands on the old P2's block) and the half-press
     after a fault (a crash record in RAM, its file written first): as the same presses on zero DRAM.
     BASE on the same DRAM does take the stale blocks each time (a fixture BASE passed would show nothing)
  N  no card: no call at all. No BUNDLES.BIN: malloc, fopen, free, the retry armed. The retry on the next press: the full
     load. No memory: nothing. All == BASE
  A  every memory access of cb_zero in the traced run is a byte store into the block, each byte once
  P  anti-brick: package reparses, decoded == stock + edits (the image emulated above), restore == stock, only our bytes
     differ from BASE
"""
import importlib.util, json, re, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tools')); sys.path.insert(0, str(ROOT / 'external/oly_fw_analysis/tools'))
from penf_emulator import Region, execute  # noqa: E402
import build_package as BP, oly_container as oc  # noqa: E402


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


CB = _load('clean_boot_build_v', HERE / 'build.py')
STV = _load('split_tone_verify_cb', ROOT / 'patches/split_tone/verify.py')     # the tone-hook fixture and the bend model
AP = _load('ap_custom_build_cb', ROOT / 'patches/ap_custom/build.py')
FC = _load('ep7_crash_fmt_cb', ROOT / 'tools/ep7_crash.py')                     # the crash record's format
B3, ST, LE = CB.B3, CB.ST, CB.XP.LE
MV = AP.MV
BASE = CB.BASE
CARD = ROOT / 'releases/v0.32b/card/EP7MOD'
NAMES = ('BUNDLES.BIN', 'LOOKS.BIN', 'MOVIE.BIN', 'AP.BIN')
CRASH = 'CRASH.BIN'                       # patches/crash_log writes it on the half-press after a fault
POOLS = ((0xa1bce7c0, 0xc0, 0xb2), (B3.POOL, 0x840, 0x15), (ST.POOL2, ST.BLOCK2, 0x2b))   # heap class 0..2: pool base, block stride, blocks
MAPPED = {0: (40, 41, 42), 1: (6, 7, 8, 9, 10), 2: (5, 6, 7, 8, 9, 10, 11)}    # the blocks that exist in a run
SPARE = {0: 42, 1: 10, 2: 11}                                                 # where a malloc of the passes below would land
K0 = {0: 40, 1: 6, 2: 5}                                                       # the allocator's next block per class at the half-press
P_AT, P2_AT, P3_AT = (POOLS[1][0] + i * POOLS[1][1] for i in (6, 7, 8))
STK, SP0 = 0x18010000, 0x18011000
FAR, LOGB, ALLOCB, PTAB, FILES, CALLER, RECB = 0x18100000, 0x18200000, 0x18210000, 0x18220000, 0x18300000, 0x18400000, 0x18410000
TRIG_RET = 0x602c8064
KEEP = ('d0', 'd1', 'd2', 'd3', 'a0', 'a1', 'a2', 'a3', 'sp', 'pc', 'mdr', 'psw', 'lir', 'lar')
REGS = dict(d0=0, d1=0, a0=SP0 + 16, a1=0, d2=0x1111, d3=0x2222, a2=0x3333, a3=0x4444, mdr=0x5555)
TRACE = []                                # (instruction map, rows) of the traced run, for A
W62, W63 = 0x58, 0x51                     # a split for the tone pass: Shadows Cyan +5, Highlights Orange +5
LOFF, GOFF = ST.LOFF, 5824                # S and the halation grid inside L


def blk(c, i):
    return POOLS[c][0] + i * POOLS[c][1]


def image(spec):
    pkg, rst, info = BP.build(spec, BP.STOCK.read_bytes())
    return [b for b in oc.parse(pkg) if b.kind == 0x100][0].payload, pkg, rst, info


def u32(b, o):
    return struct.unpack_from('<I', b, o)[0]


def where(a):
    """A heap address as block + offset."""
    for c, (base, stride, count) in enumerate(POOLS):
        if base <= a < base + count * stride:
            i, o = divmod(a - base, stride)
            return f'c{c}b{i}' + (f'+{o}' if o else '')
    return hex(a)


# ------------------------------------------------------------------ the stubs
LOG = ''' mov ({logp:#x}),a3
 mov {id},d2
 mov d2,(a3)
 mov {x},(4,a3)
 mov {y},(8,a3)
 add 12,a3
 mov a3,({logp:#x})
'''


def stub_unit():
    """One unit at FAR: each service's body, entered by a jmp from the service's address with the caller's frame."""
    lg = lambda i, x, y: LOG.format(logp=LOGB, id=i, x=x, y=y)
    body = dict(
        malloc=f''' mov d0,d3
 mov ({ALLOCB + 12:#x}),d2        /* the n-th call from now fails */
 cmp 0,d2
 beq 1f
 add -1,d2
 mov d2,({ALLOCB + 12:#x})
 cmp 0,d2
 bne 1f
 mov 0,a0
 bra 3f
1:
 mov {ALLOCB:#x},a2
 mov {POOLS[0][1]},d2
 cmp 128,d3
 bls 2f
 add 4,a2
 mov {POOLS[1][1]},d2
 cmp 2048,d3
 bls 2f
 add 4,a2
 mov {POOLS[2][1]},d2
2:
 mov (a2),a0
 mov a0,d1
 add d2,d1
 mov d1,(a2)
3:
''' + lg(1, 'd3', 'a0') + ' mov 0x5a5a0001,d0\n mov 0x5a5a0002,d1\n mov 0x5a5a0003,a1\n',
        free=lg(7, 'a0', 'a0') + ' mov 0x5a5a0071,d0\n',
        fopen=f''' mov a0,d3
 mov {PTAB:#x},a2
1:
 mov (a2),d2
 cmp 0,d2
 beq 2f
 cmp d2,d3
 beq 3f
 add 8,a2
 bra 1b
2:
 mov 0,a0
 bra 4f
3:
 mov (4,a2),a0
4:
''' + lg(2, 'd3', 'a0') + ' mov 0x5a5a0021,d0\n mov 0x5a5a0022,d1\n mov 0x5a5a0023,a1\n',
        fseek=lg(3, 'a0', 'd1') + ' clr d0\n',
        ftell=' mov (4,a0),d0\n' + lg(4, 'a0', 'd0'),
        fread=''' mov (4,a1),d2
 cmp d1,d2
 bls 1f
 mov d1,d2
1:
 mov d2,d3
 mov (a1),a2
 mov a0,a3
 cmp 0,d2
 beq 3f
2:
 movbu (a2),d0
 movbu d0,(a3)
 inc a2
 inc a3
 add -1,d2
 bne 2b
3:
''' + lg(5, 'a0', 'd3') + ' mov d3,d0\n',
        fwrite=lg(10, 'a0', 'd1') + ' mov d1,d0\n',
        fclose=lg(6, 'a0', 'a0') + ' clr d0\n',
        sget=lg(8, 'd0', 'd0') + ' mov 3,d0\n',
        getter=lg(9, 'd0', 'd1') + ' clr d0\n')
    ret = dict(malloc='[],4', free='[],4', fopen='[],4', fseek='[d2,d3,a2,a3],20', ftell='[d2,a2,a3],16', fread='[d2,d3,a2,a3],24', fwrite='[d2,d3,a2,a3],24',
               fclose='[d2,a2,a3],16', sget='[],4', getter='[d2,d3],12')
    text = ' .am33_2\n .text\n .global _start\n_start:\n'
    for k, b in body.items():
        text += f's_{k}:\n movm [d2,d3,a2,a3],(sp)\n{b} movm (sp),[d2,d3,a2,a3]\n ret {ret[k]}\n'
    code, _, sy, _ = B3.assemble(text, FAR, {})
    return code, {k: sy['s_' + k] for k in body}


def small(addr, text, name):
    c, _, _, _ = B3.assemble(' .am33_2\n .text\n .global _start\n_start:\n' + text + '\n', addr, {})
    return Region(name, addr, c, 'rx')


class World:
    """The image's code, the stubs and the card files for one spec."""

    def __init__(self, m, spec, unit):
        self.m, self.spec = m, spec
        sv = {k: int(v, 16) for k, v in spec['sd_bundles_v3']['services'].items()}
        self.sd = {k: int(v, 16) for k, v in spec['sd_bundles_v3']['symbols'].items()}
        self.at = dict(malloc=sv['ep7_malloc'], free=sv['ep7_free'], fopen=sv['ep7_fopen'], fclose=sv['ep7_fclose'], fseek=sv['ep7_fseek'], ftell=sv['ep7_ftell'],
                       fread=sv['ep7_fread'], fwrite=int(spec['look_editor']['stock']['ep7_fwrite'], 16), sget=AP.SGET, getter=AP.GETTER)
        self.sv = sv
        code, sy = unit
        self.stubs = [Region('far', FAR, code, 'rx')] + [Region('j_' + k, a, b'\xdc' + struct.pack('<i', sy[k] - a), 'rx') for k, a in self.at.items()]
        self.io = [small(sv['ep7_trig'], ' ret [d2,d3,a2,a3],36', 'trig'), small(sv['ep7_get_tid'], ' mov 5,d0\n movhu d0,(a0)\n clr d0\n ret [a2],4', 'tid')]
        fm = BASE + m.index(b'C:\\EP7MOD\\LOOKS.BIN\0', 0x6143a400 - BASE)
        self.path = {'BUNDLES.BIN': self.sd['sd_path'], 'LOOKS.BIN': fm, 'MOVIE.BIN': int(spec['v026_movie']['wheel_symbols']['mv_pbin'], 16),
                     'AP.BIN': int(spec['ap_custom']['symbols']['ap_pbin'], 16)}
        if not 0x6143a400 <= fm < 0x6143a800 or any(self.cstr(a) != ('C:\\EP7MOD\\' + n).encode() for n, a in self.path.items()):
            raise SystemExit('card file paths')
        self.files = {n: (CARD / n).read_bytes() for n in NAMES}
        self.rec = int(spec['crash_log']['record'][0], 16) if 'crash_log' in spec else None
        if self.rec:
            self.path[CRASH] = int(spec['crash_log']['symbols']['cl_path'], 16)
        self.sym = {k: int(v, 16) for layer in ('ap_custom', 'grain_cpu', 'halation_h6', 'crash_log') for k, v in spec.get(layer, {}).get('symbols', {}).items()}

    def cstr(self, a):
        return bytes(self.m[a - BASE:self.m.index(b'\0', a - BASE)])

    def code(self, *names):
        rg = dict(sec1=(0x601de000, 0x601e4000), sec3=(0x605b7180, 0x605b7800), ls=(0x607d5500, 0x607d5900), sec6=(0x612429c0, 0x61242d00), sec9=(0x6143a300, 0x6143a800),
                  h6=tuple(int(x, 16) for x in self.spec['halation_h6']['claim']))
        return [Region(n, lo, self.m[lo - BASE:hi - BASE], 'rx') for n, (lo, hi) in rg.items() if n in names]

    def heap(self, dram, absent=(), only=None):
        return [Region(f'c{c}b{i}', blk(c, i), bytes(dram.get((c, i), bytes(POOLS[c][1]))), 'rw', True)
                for c, idx in MAPPED.items() for i in idx if (c, i) not in absent and (only is None or c in only)]

    def data(self, k, present=NAMES, fail=0):
        pt = bytearray(0x200)
        fl = bytearray(0x1000 * len(NAMES))
        for n, name in enumerate(NAMES):
            f = self.files[name]
            fl[0x1000 * n:0x1000 * n + len(f)] = f
            struct.pack_into('<II', pt, 0x100 + 16 * n, FILES + 0x1000 * n, len(f))
        for j, name in enumerate(x for x in NAMES + (CRASH,) if x in present and x in self.path):     # the crash file: a handle to write to
            struct.pack_into('<II', pt, 8 * j, self.path[name], PTAB + 0x100 + 16 * (NAMES + (CRASH,)).index(name))
        return [Region('log', LOGB, struct.pack('<I', LOGB + 16) + bytes(0x7fc), 'rw', True), Region('ptab', PTAB, bytes(pt), 'r'), Region('files', FILES, bytes(fl), 'r'),
                Region('alloc', ALLOCB, struct.pack('<4I', blk(0, k[0]), blk(1, k[1]), blk(2, k[2]), fail), 'rw', True)]

    def log(self, mem):
        """-> [(call, ...)] with heap addresses as block names and file handles as file names."""
        lg, out = mem['log'], []
        hname = {PTAB + 0x100 + 16 * n: name for n, name in enumerate(NAMES + (CRASH,))}
        pname = {a: n for n, a in self.path.items()}
        for o in range(16, u32(lg, 0) - LOGB, 12):
            i, x, y = struct.unpack_from('<3I', lg, o)
            out.append({1: lambda: ('malloc', x, where(y) if y else None), 2: lambda: ('fopen', pname.get(x) or self.cstr(x).decode(), bool(y)), 3: lambda: ('fseek', hname[x], y),
                        4: lambda: ('ftell', hname[x], y), 5: lambda: ('fread', where(x), y), 6: lambda: ('fclose', hname[x]), 7: lambda: ('free', where(x)),
                        8: lambda: ('sget', x), 9: lambda: ('getter', hex(x), y), 10: lambda: ('fwrite', where(x), y)}[i]())
        return out


class Run:
    def __init__(self, w, r):
        self.r, self.fault, self.status, self.reg = r, r['fault'], r['status'], r['registers']
        self.mem = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}
        self.blocks = {(int(n[1]), int(n[3:])): v for n, v in self.mem.items() if re.fullmatch(r'c\db\d+', n)}
        self.log = w.log(self.mem) if 'log' in self.mem else []
        self.state = struct.unpack_from('<H', self.mem['state'], 2)[0] if 'state' in self.mem else None
        self.boot = self.mem['boot'][AP.BOOT & 0xf] if 'boot' in self.mem else None
        self.ok = not self.fault and self.status == 'returned'

    def why(self):
        f = self.fault
        return f"{self.status} pc {self.reg['pc']:#x}" + (f" fault {['read', 'write', 'exec'][f['map']] if f['kind'] == 1 else 'instruction'} at {where(f['address'])} from {f['pc']:#x}" if f else '')


def press(w, dram, k=K0, *, present=NAMES + (CRASH,), state=0, boot=0, mounted=True, fail=0, absent=(), rec=None):
    """One half-press event through the whole hook chain. dram: {(class, block): bytes} as the RAM is before it; k: the
    allocator's next block per class; absent: blocks that do not exist in this run; rec: the crash record's RAM."""
    stk = bytearray(0x2000); struct.pack_into('<I', stk, SP0 - STK + 16, B3.EV_PRESS)
    sv = w.sv
    rg = w.code('sec1', 'sec3', 'ls', 'sec6', 'sec9') + w.stubs + w.io + w.data(k, present, fail) + w.heap(dram, absent) + [
        Region('secbits', sv['ep7_secbits'], struct.pack('<I', 0x1ff), 'r'), Region('ms', sv['ep7_ms_a'], struct.pack('<I', 0xf000 if mounted else 0) + bytes(28), 'r'),
        Region('state', 0x622cbcc0, struct.pack('<HHI', 5, state, 0), 'rw', True), Region('boot', AP.BOOT & ~0xf, bytes([boot if i == (AP.BOOT & 0xf) else 0 for i in range(16)]), 'rw', True),
        Region('stack', STK, bytes(stk), 'rw', True), Region('t', TRIG_RET, b'\xcb', 'rx')]
    if w.rec:
        rg.append(Region('rec', w.rec, rec or bytes(FC.FILE_LEN), 'rw', True))   # the crash record's RAM: no record unless a case brings one
    return Run(w, execute(rg, dict(REGS, pc=w.sd['sd_hook'], sp=SP0), TRIG_RET, limit=6_000_000, timeout=600))


def same(a, b, skip=()):
    """Two runs: registers, calls and every captured byte."""
    if not (a.ok and b.ok):
        return f'{a.why()} / {b.why()}'
    if any(a.reg[k] != b.reg[k] for k in KEEP):
        return 'registers ' + str({k: (hex(a.reg[k]), hex(b.reg[k])) for k in KEEP if a.reg[k] != b.reg[k]})
    if a.log != b.log:
        return f'calls {[x for x in zip(a.log, b.log) if x[0] != x[1]][:2]} ({len(a.log)}, {len(b.log)})'
    d = [n for n in a.mem if n not in skip and a.mem[n] != b.mem.get(n)]
    return f'memory {d}' if d or set(a.mem) != set(b.mem) else ''


def shape(log):
    """The calls without block identities: what was asked for, in order."""
    return [x[:2] if x[0] in ('malloc', 'fopen', 'ftell', 'fseek', 'fclose', 'sget') else (x[0], x[2]) if x[0] in ('fread', 'fwrite') else (x[0],) for x in log]


def lw(b):
    """What fm_load and ls_chk write of the LOOKS.BIN block L: the file, the tags, n, pos, snap; the split stash."""
    return b[:2129] + b[2560:2632]


def lc(b):
    """The same of the Movie / AP copies L2 / L3 (the stash is not copied)."""
    return b[:2129]


def tables(run, l=(2, 5), l2=(2, 6), l3=(2, 7)):
    """Everything a first half-press loads: P, P2, P3 (the 1024 B that were asked for) and the three LOOKS.BIN blocks."""
    b = run.blocks
    return [b[(1, i)][:1024] for i in (6, 7, 8)] + [lw(b[l]), lc(b[l2]), lc(b[l3])]


# ------------------------------------------------------------------ T
def t_stub(wo, wn):
    bad, n = [], 0
    ld, out = wn.sd['sd_load'], wn.sd['sd_out']
    call_fopen = int(wn.spec['clean_boot']['back']['block'], 16) + 12
    lo, hi = int(wn.spec['clean_boot']['code'][0], 16), int(wn.spec['clean_boot']['code'][0], 16) + wn.spec['clean_boot']['code'][1]
    ins = {x: (op, args) for x, op, args in B3.disasm(wn.m[lo - BASE:hi - BASE], lo)}
    regs = dict(d0=0xd0d0d0d0, d1=0xd1d1d1d1, d2=0x2222, d3=0x3333, a0=0xa0a0a0a0, a1=0xa1a1a1a1, a2=0xa2a2, a3=0xa3a3, mdr=0x6d6d, psw=0x000f, lir=0x1111, lar=0x2222, sp=SP0)
    pool0 = b'\x99' * 0x1000
    for name, a0 in (('a block', P_AT), ('a block at an odd address', P_AT + 1), ('a block 2 past a word', P_AT + 2), ('no block', 0)):
        res = []
        for w in (wo, wn):
            rg = w.code('sec3') + [small(w.at['malloc'], f' mov {a0:#x},a0\n mov 0x5a5a0001,d0\n mov 0x5a5a0002,d1\n mov 0x5a5a0003,a1\n ret [],4', 'ma'),
                                   Region('pool', P_AT - 0x400, pool0, 'rw', True), Region('stack', STK, b'\x77' * 0x2000, 'rw', True)]
            stop = call_fopen if a0 else out
            tr = w is wn and a0 == P_AT
            r = execute(rg, dict(regs, pc=ld), stop, limit=20000, trace_limit=100000 if tr else 0)
            if tr:
                TRACE.append((ins, r['trace'], a0))
            res.append(Run(w, r))
        a, b = res
        n += 1
        exp = bytearray(pool0)
        if a0:
            exp[a0 - P_AT + 0x400:a0 - P_AT + 0x400 + 1024] = bytes(1024)
        msg = same(a, b, skip=('pool',))                       # every register (flags, MDR, LIR, LAR too) and the whole stack
        if msg or a.mem['pool'] != pool0 or b.mem['pool'] != bytes(exp):
            bad.append((name, msg, a.mem['pool'] == pool0, b.mem['pool'] == bytes(exp)))
    return bad, n


# ------------------------------------------------------------------ C
CLEAN = [('malloc', 1024, 'c1b6'), ('fopen', 'BUNDLES.BIN', True), ('fseek', 'BUNDLES.BIN', 1), ('ftell', 'BUNDLES.BIN', 680), ('fseek', 'BUNDLES.BIN', 2), ('fread', 'c1b6', 680), ('fclose', 'BUNDLES.BIN'),
         ('malloc', 2640, 'c2b5'), ('fopen', 'LOOKS.BIN', True), ('fseek', 'LOOKS.BIN', 1), ('ftell', 'LOOKS.BIN', 2112), ('fseek', 'LOOKS.BIN', 2), ('fread', 'c2b5', 2112), ('fclose', 'LOOKS.BIN'),
         ('malloc', 1024, 'c1b7'), ('fopen', 'MOVIE.BIN', True), ('fread', 'c1b7+800', 96), ('fclose', 'MOVIE.BIN'), ('malloc', 2560, 'c2b6'), ('sget', MV.ALL0), ('sget', MV.ALL1),
         ('malloc', 1024, 'c1b8'), ('fopen', 'AP.BIN', True), ('fread', 'c1b8+800', 96), ('fclose', 'AP.BIN'), ('malloc', 2560, 'c2b7'), ('sget', MV.ALL0), ('sget', MV.ALL1)]


def marks(p):
    """The marks and pointers of a block P, by name."""
    w = lambda o: u32(p, o)
    return dict(EP7E=p[LE.EMARK:LE.EMARK + 4] == b'EP7E', dirty=p[LE.DIRTY], S=where(w(ST.SPTR)) if w(ST.SPTR) else 0, EP7V=p[MV.VM:MV.VM + 4] == b'EP7V', P2=where(w(MV.VP)) if w(MV.VP) else 0,
                EP7T=p[MV.VT:MV.VT + 4] == b'EP7T', EP7A=p[AP.AM:AP.AM + 4] == b'EP7A', P3=where(w(AP.AP3)) if w(AP.AP3) else 0, EP7U=p[AP.ATR:AP.ATR + 4] == b'EP7U',
                grain=where(w(1000)) if w(1000) else 0, EP7M=p[1008:1012] == b'EP7M', L=where(w(1016)) if w(1016) else 0, looks=bytes(p[1020:1024]))


def loaded(run, l='c2b5', l2='c2b6', l3='c2b7'):
    """The end state of a first half-press with the four card files: tables loaded, every block where the calls put it."""
    b, bad = run.blocks, []
    p, p2, p3 = b[(1, 6)], b[(1, 7)], b[(1, 8)]
    f = lambda n: (CARD / n).read_bytes()
    L, L2, L3 = (b[(2, int(x[3:]))] for x in (l, l2, l3))
    mk = marks(p)
    want = dict(EP7E=False, dirty=0, S=0, EP7V=True, P2='c1b7', EP7T=True, EP7A=True, P3='c1b8', EP7U=True, grain=0, EP7M=False, L=l, looks=b'EP7F')
    if mk != want:
        bad.append(('P marks', {k: v for k, v in mk.items() if v != want[k]}))
    if run.state != P_AT - B3.POOL + 1 or run.boot != 1:
        bad.append(('state / boot byte', hex(run.state), run.boot))
    if p[:544] != f('BUNDLES.BIN')[:544] or p[672:676] != b'EP7N' or p[544:672] != f('BUNDLES.BIN')[544:672]:
        bad.append('P table / names')
    if L[:12] != f('LOOKS.BIN')[:12] or L[2112:2116] != b'EP7L' or u32(L, 2116) != P_AT or L[2120] != (len(f('LOOKS.BIN')) - 64) // 64:
        bad.append('L file / tags')
    if p2[224:288] != f('MOVIE.BIN')[16:80] or p2[592:608] != f('MOVIE.BIN')[80:96] or p2[MV.VM:MV.VM + 4] != b'EP7V' or u32(p2, MV.VP) != P2_AT or where(u32(p2, 1016)) != l2 or u32(L2, 2116) != P2_AT:
        bad.append('P2 (Movie slot)')
    if p3[224:288] != f('AP.BIN')[16:80] or p3[592:608] != f('AP.BIN')[80:96] or u32(p3, MV.VP) != P3_AT or where(u32(p3, 1016)) != l3 or u32(L3, 2116) != P3_AT:
        bad.append('P3 (AP slot)')
    if any(x[:2112] != L[:2112] for x in (L2, L3)):
        bad.append('L2 / L3 are not copies of L')
    return bad


def t_clean(wo, wn):
    bad, n = [], 0
    a, b = press(wo, {}), press(wn, {})
    n += 1
    msg = same(a, b)
    if msg or b.log != CLEAN or loaded(b):
        bad.append(('zero DRAM', msg, [x for x in zip(b.log, CLEAN) if x[0] != x[1]][:3], loaded(b) if b.ok else ''))
    # DRAM that holds something, but no mark. NEW: registers, flags, calls, tables and the stack are those of the zero-DRAM run,
    # whatever the RAM held. BASE: the same calls, with the RAM's bytes left in P (its last compare reads one: the flags differ)
    ee = {(c, i): b'\xee' * POOLS[c][1] for c, idx in MAPPED.items() for i in idx}
    a2, b2 = press(wo, ee), press(wn, ee)
    n += 1
    left = sum(x == 0xee for x in a2.blocks.get((1, 6), b'')[:1024])
    g = a2.ok and b2.ok and a2.log == CLEAN and b2.log == CLEAN and tables(b2) == tables(b) and all(b2.reg[k] == b.reg[k] for k in KEEP) and b2.mem['stack'] == b.mem['stack']
    g = g and (b2.state, b2.boot) == (b.state, b.boot) and all(a2.reg[k] == b2.reg[k] for k in KEEP if k != 'psw') and left >= 150 and not any(x == 0xee for x in b2.blocks[(1, 6)][:1024])
    if not g:
        bad.append(('DRAM 0xee', a2.why(), b2.why(), left, [i for i, (x, y) in enumerate(zip(tables(b2), tables(b))) if x != y] if b2.ok else ''))
    return bad, n, b, left


# ------------------------------------------------------------------ the passes that use P after the half-press
def tone(w, blocks, l_at, m_at, *, marker=True):
    """The real tone hook (st) on a capture (or live view) job of COLOR1, with the split W62 / W63 in its slot. l_at, m_at: the two
    class-2 blocks that exist (the block P+1016 should name, and another). -> (P after, the two blocks after, the gamma slots, result)."""
    p = bytearray(blocks[(1, 6)]); p[32 + 62], p[32 + 63] = W62, W63
    fx = STV.fixture(slots={0: (W62, W63)}, marker=marker)
    fx.update(p=bytes(p), s=blocks[l_at], mb=blocks[m_at], state=struct.pack('<HHI', 0, P_AT - B3.POOL + 1, 0))
    keep = STV.P, STV.LBLK, STV.MBLK
    STV.P, STV.LBLK, STV.MBLK = P_AT, blk(*l_at), blk(*m_at)
    try:
        r, m = STV.run(w.m, fx, prof=1)
    finally:
        STV.P, STV.LBLK, STV.MBLK = keep
    return m.get('pool'), m.get('S'), m.get('M'), struct.unpack_from('<III', m['O'], 2596) if 'O' in m else None, r


def curve(buf, at, a):
    return [list(struct.unpack_from('<256H', buf, a - at + 512 * c)) for c in range(3)]


def grid(w, blocks, absent=()):
    """halation h6 from its entry to pass A, for a full-size photo: where it puts the cell grid. -> (grid address, block to free, mallocs, run)."""
    rec = bytearray(88)
    struct.pack_into('<I', rec, 0, 0xa4000000); struct.pack_into('<HHHH', rec, 8, 0x0302, 5184, 5184, 3888); struct.pack_into('<I', rec, 72, 2 * 5184 * 3888)
    rg = w.code('sec1', 'h6') + w.stubs + w.data(SPARE) + w.heap(blocks, absent) + [
        Region('state', 0x622cbcc0, struct.pack('<HHI', 5, P_AT - B3.POOL + 1, 0), 'r'), Region('recd', RECB, bytes(rec), 'r'), Region('stack', STK, bytes(0x2000), 'rw', True)]
    r = Run(w, execute(rg, dict(pc=w.sym['h6_run'], sp=SP0, a0=RECB, d0=0x13, d2=1, d3=2, a2=3, a3=4), w.sym['h6_pa'], limit=200000, breakpoints=[w.sym['h6_ret']]))
    st = r.mem['stack']
    return u32(st, SP0 - STK + 36), u32(st, SP0 - STK + 40), [x for x in r.log if x[0] == 'malloc'], r


def film(w, blocks, absent=()):
    """fm_valid, the Film page's own test of P+1016 / P+1020 and L's tags -> 1 when COLOR1-4 have a LOOKS.BIN table."""
    fv = u32(w.m, int(w.spec['look_editor']['symbols']['ed_cfg_fv'], 16) - BASE)
    c, _, _, _ = B3.assemble(f' .am33_2\n .text\n .global _start\n_start:\n mov {fv:#x},a0\n calls (a0)\n nop\n', CALLER, {})
    rg = w.code('sec1') + w.heap(blocks, absent, only=(1, 2)) + [Region('caller', CALLER, c, 'rx'), Region('stack', STK, bytes(0x2000), 'rw')]
    r = execute(rg, dict(pc=CALLER, sp=SP0, a2=P_AT), CALLER + len(c) - 1, limit=2000)
    return None if r['fault'] or r['status'] != 'returned' else r['registers']['d0']


def record(w, blocks, k0, absent=(), stage=1):
    """The grain record as the capture hooks ask for it: gc_mark(stage, guard 2). -> (P+1000 after, mallocs, run)."""
    at = w.sym['gc_mark']
    rg = w.code('sec1') + w.stubs + w.data({0: k0, 1: 9, 2: 10}) + w.heap(blocks, absent, only=(0, 1)) + [
        Region('state', 0x622cbcc0, struct.pack('<HHI', 5, P_AT - B3.POOL + 1, 0), 'r'), Region('stack', STK, bytes(0x2000), 'rw', True),
        Region('caller', CALLER, b'\xdd' + struct.pack('<i', at - CALLER) + b'\xf0\x20', 'rx')]
    r = Run(w, execute(rg, dict(pc=CALLER, sp=SP0, d0=stage, d1=2, d2=1, d3=2, a2=3, a3=4), CALLER + 7, limit=20000))
    return (u32(r.blocks[(1, 6)], 1000) if (1, 6) in r.blocks else None), [x for x in r.log if x[0] == 'malloc'], r


# ------------------------------------------------------------------ R
def old_session(wn, clean):
    """The heap a finished session leaves in DRAM: the clean half-press, then the editors used (an unsaved edit), a split-tone pass
    (S in L's tail, published), a grain shot (the record), the mono page opened. S's curve bytes then changed, as by a later owner
    of that RAM: a pass that still trusts S would send them to the gamma stage."""
    d = dict(clean.blocks)
    p, s, _, slots, r = tone(wn, d, (2, 5), (2, 9))
    if r['fault'] or u32(p, ST.SPTR) != blk(2, 5) + LOFF or slots[0] != blk(2, 5) + LOFF + 32:
        raise SystemExit(f'old session: the tone pass did not build S ({r["fault"]})')
    p = bytearray(p); p[32 + 62] = p[32 + 63] = 0
    d[(1, 6)], d[(2, 5)] = bytes(p), s
    ptr, mal, r = record(wn, d, 40)
    if not r.ok or ptr != blk(0, 40) or r.blocks[(0, 40)][:4] != b'GDIA':
        raise SystemExit(f'old session: no grain record ({r.why()})')
    g = bytearray(r.blocks[(0, 40)]); g[5], g[4], g[38] = 6, 3, 2
    p = bytearray(r.blocks[(1, 6)])
    p[LE.EMARK:LE.EMARK + 4] = b'EP7E'; p[LE.AXIS], p[LE.DIRTY], p[LE.STATUS] = 2, 1, 1
    p[1004:1008] = bytes((3, 1, 4, 1)); p[1008:1012] = b'EP7M'
    L = bytearray(d[(2, 5)])
    L[LOFF + 32:LOFF + 32 + 1536] = struct.pack('<H', 0x0bad) * 768                # set 0's three curves
    L[GOFF:GOFF + 6000] = b'\x77' * 6000                                           # what a halation shot left of its grid
    d[(1, 6)], d[(0, 40)], d[(2, 5)] = bytes(p), bytes(g), bytes(L)
    return d


def t_restart(wo, wn, clean):
    bad, n, info = [], 0, []
    src = list(struct.unpack_from('<256H', wn.m, STV.ROW0 - BASE))
    want = STV.bend(src, W62, W63)
    old = old_session(wn, clean)
    om = marks(old[(1, 6)])
    info.append('old session P: ' + ', '.join(f'{k} {v}' for k, v in om.items() if v not in (False, 0)))
    olds = [(2, 5), (2, 6), (2, 7), (0, 40)]                    # the old session's L, L2, L3 and grain record
    for name, k, l, l2, l3, gnew, other in (('the pools give the same blocks', K0, (2, 5), (2, 6), (2, 7), (0, 40), (2, 9)),
                                            ('the pools give other class-0 / class-2 blocks', {0: 41, 1: 6, 2: 8}, (2, 8), (2, 9), (2, 10), (0, 41), (2, 5))):
        moved = k != K0
        # ---- NEW: the half-press
        b = press(wn, old, k)
        n += 1
        g = b.ok and shape(b.log) == shape(CLEAN) and not loaded(b, *(f'c{c}b{i}' for c, i in (l, l2, l3)))
        if g and not moved:                                     # same blocks: the clean power-on's calls and tables, byte for byte
            g = b.log == CLEAN and tables(b) == tables(clean) and all(b.reg[k] == clean.reg[k] for k in KEEP) and b.mem['stack'] == clean.mem['stack']
        if g and moved:                                         # other blocks: the same tables at the new places, the old blocks as they were
            rel = lambda blkb, o, v: bytes(blkb[:o]) + struct.pack('<I', v) + bytes(blkb[o + 4:])
            exp = tables(clean)
            exp[:3] = [rel(t, 1016, blk(*x)) for t, x in zip(exp[:3], (l, l2, l3))]
            g = all(b.blocks[x] == old[x] for x in olds) and tables(b, l, l2, l3) == exp and all(b.reg[k] == clean.reg[k] for k in KEEP)
            b2 = press(wn, old, k, absent=olds)                 # and with the old blocks gone, nothing misses them
            g = g and b2.ok and b2.log == b.log and all(b2.blocks[x] == b.blocks[x] for x in b2.blocks)
        if not g:
            bad.append((name, 'NEW half-press', b.why(), shape(b.log) == shape(CLEAN), loaded(b, *(f'c{c}b{i}' for c, i in (l, l2, l3))) if b.ok else ''))
            continue
        # ---- NEW: split tone, capture and live view, from that state. S goes into the new L and is built again
        for marker in (True, False):
            p, s, mb, slots, r = tone(wn, b.blocks, l, other, marker=marker)
            n += 1
            s_at = blk(*l) + LOFF
            set_at = s_at + 32 + (0 if marker else ST.SETSZ)
            if r['fault'] or u32(p, ST.SPTR) != s_at or slots != (set_at, set_at + 512, set_at + 1024) or curve(s, blk(*l), set_at) != want or s[:LOFF] != b.blocks[l][:LOFF] or mb != b.blocks[other]:
                bad.append((name, 'NEW tone pass', 'capture' if marker else 'live view', r['fault'], hex(u32(p, ST.SPTR)) if p else None))
        # ---- NEW: the Film page has its table; halation's grid in the new L, nothing asked from malloc; the grain record made again
        ga, fr, mal, r = grid(wn, b.blocks, absent=olds if moved else ())
        n += 1
        gb = r.blocks.get(l, b'')
        if not r.ok or ga != blk(*l) + GOFF or fr or mal or gb[:GOFF] != b.blocks[l][:GOFF] or any(r.blocks[x] != b.blocks[x] for x in r.blocks if x != l) or any(gb[GOFF:GOFF + 4944]) \
                or film(wn, b.blocks, absent=olds if moved else ()) != 1:
            bad.append((name, 'NEW halation grid / Film page', r.why(), where(ga), mal))
        ptr, mal, r = record(wn, b.blocks, k[0], absent=[x for x in olds if x[0] == 0] if moved else ())
        n += 1
        rec = r.blocks.get(gnew, b'')
        if not r.ok or ptr != blk(*gnew) or mal != [('malloc', 128, where(blk(*gnew)))] or rec[:4] != b'GDIA' or rec[4:6] != bytes((2, 1)) or any(rec[6:128]):
            bad.append((name, 'NEW grain record', r.why(), where(ptr or 0), mal))
        # ---- BASE on the same DRAM: it keeps the old session's marks (what the layer is for; a fixture BASE passed would show nothing)
        a = press(wo, old, k)
        n += 1
        am = marks(a.blocks[(1, 6)]) if a.ok else {}
        fo = [x[1] for x in a.log if x[0] == 'fopen']
        stale = a.ok and 'LOOKS.BIN' not in fo and am['L'] == 'c2b5' and am['S'] == f'c2b5+{LOFF}' and am['grain'] == 'c0b40' and am['EP7M'] and 'C:\\EP7MOD\\BUNDLES.NEW' in fo
        if not stale:
            bad.append((name, 'BASE is expected to keep the stale marks', a.why(), am, fo))
            continue
        ptr, mal, r = record(wo, a.blocks, k[0], stage=7)        # a later stage than the old record's: gc_mark stores it
        p, s, mb, slots, r2 = tone(wo, a.blocks, l, other)
        sold = (s if not moved else mb)
        n += 2
        if not (r.ok and ptr == blk(0, 40) and not mal and r.blocks[(0, 40)][4:6] == bytes((2, 7)) != old[(0, 40)][4:6]):
            bad.append((name, 'BASE is expected to write the old grain record', r.why(), where(ptr or 0), mal))
        if r2['fault'] or slots[0] != blk(2, 5) + LOFF + 32 or curve(sold, blk(2, 5), slots[0])[0] != [0x0bad] * 256:
            bad.append((name, 'BASE is expected to use the old S', r2['fault'], slots))
        fv = film(wo, a.blocks)                                 # same blocks: the Movie slot's L2 lands on the old L and takes its back pointer
        if fv != (1 if moved else 0):
            bad.append((name, 'BASE Film page', fv))
        if moved:
            ga, fr, mal, r = grid(wo, a.blocks)
            a2 = press(wo, old, k, absent=olds)
            n += 2
            if not (r.ok and ga == blk(2, 5) + GOFF and not mal):
                bad.append((name, 'BASE is expected to put the grid in the old L', r.why(), where(ga)))
            if a2.ok or not a2.fault or where(a2.fault['address'])[:4] != 'c2b5':
                bad.append((name, 'BASE is expected to read the old L', a2.why()))
            info.append(f'BASE, other blocks: LOOKS.BIN not read, L = {am["L"]} (not allocated), S = {am["S"]}, grid at {where(ga)}, grain record {am["grain"]}; '
                        f'with the old blocks unmapped: {a2.why()}')
        else:
            info.append(f'BASE, same blocks: LOOKS.BIN not read; calls {len(a.log)} (clean: {len(CLEAN)}), extra fopen {[x for x in fo if x not in NAMES]}; '
                        f'L2 = {where(u32(a.blocks[(1, 7)], 1016))} = the old L, back pointer now P2: no Film page on COLOR1-4 (fm_valid {fv}); the tone pass takes the old S')
    # ---- the BUNDLES retry after a restart (no file on the first press: the card was still mounting). The allocator is one class-1
    # block on, so P lands on the old session's P2, which says 'EP7V' and points at itself, with the old P's handle beside it
    kr = dict(K0); kr[1] = 7
    tb = lambda run: [run.blocks[(1, i)][:1024] for i in (7, 8, 9)] + [lw(run.blocks[(2, 5)]), lc(run.blocks[(2, 6)]), lc(run.blocks[(2, 7)])]
    ref = press(wn, press(wn, {}, present=()).blocks, kr, state=0, boot=0x10)        # the same two presses on zero DRAM
    b1 = press(wn, old, present=())
    b, b_ = (press(wn, b1.blocks, kr, state=b1.state, boot=b1.boot, absent=x) for x in ((), [(1, 6)]))
    n += 1
    if not (ref.ok and b1.ok and b.ok and b_.ok and shape(ref.log) == shape(CLEAN) and (b1.state, b1.boot) == (0, 0x10) and b.log == ref.log == b_.log and tb(b) == tb(ref) == tb(b_)
            and all(b.reg[k] == ref.reg[k] for k in KEEP) and (b.state, b.boot) == (ref.state, ref.boot) == (blk(1, 7) - B3.POOL + 1, 0x11)):
        bad.append(('the retry, P on the old P2 block', 'NEW', b1.why(), b.why(), b_.why()))
    a1 = press(wo, old, present=())
    a, a_ = (press(wo, a1.blocks, kr, state=a1.state, boot=a1.boot, absent=x) for x in ((), [(1, 6)]))
    n += 1
    am = marks(a.blocks[(1, 7)]) if a.ok else {}
    fo = [x[1] for x in a.log if x[0] == 'fopen']
    if not (a1.ok and a.ok and fo == ['BUNDLES.BIN'] and am['EP7V'] and am['P2'] == 'c1b7' and a_.fault and where(a_.fault['address'])[:4] == 'c1b6'):
        bad.append(('the retry, P on the old P2 block', 'BASE is expected to take P for a swapped-in slot', a.why(), am, fo, a_.why()))
    else:
        info.append(f'BASE, the retry puts P on the old P2 (c1b7): EP7V and a pointer to itself, so it reads as a swapped-in slot of the old P (c1b6); loaded: {fo} only; '
                    f'with the old P unmapped: {a_.why()}')
    # ---- the half-press after a fault: the crash record is in RAM too, and its card copy takes the class-2 block L had
    rec = FC.MAGIC_OK + b'\x5c' * (FC.SLOT - 4) + bytes(2 * FC.SLOT)
    wrote = [('malloc', FC.FILE_LEN, 'c2b5'), ('fopen', CRASH, True), ('fwrite', 'c2b5', FC.FILE_LEN), ('fclose', CRASH), ('free', 'c2b5')]
    ls = ((2, 6), (2, 7), (2, 8))
    ref, a0 = press(wn, {}, rec=rec), press(wo, {}, rec=rec)
    b = press(wn, old, rec=rec)
    n += 1
    msg = same(a0, ref)                                           # zero DRAM: as BASE, the record written
    if msg or shape(ref.log) != shape(CLEAN[:7]) + shape(wrote) + shape(CLEAN[7:]) or ref.log[7:12] != wrote or loaded(ref, *(f'c{c}b{i}' for c, i in ls)) or any(ref.mem['rec'][:4]) \
            or not b.ok or b.log != ref.log or tables(b, *ls) != tables(ref, *ls) or any(b.reg[k] != ref.reg[k] for k in KEEP) or b.mem['rec'] != ref.mem['rec'] or film(wn, b.blocks) != 1:
        bad.append(('after a fault (crash record in RAM)', 'NEW', msg, ref.why(), b.why(), ref.log[7:12]))
    a = press(wo, old, rec=rec)
    n += 1
    am = marks(a.blocks[(1, 6)]) if a.ok else {}
    fo = [x[1] for x in a.log if x[0] == 'fopen']
    slots = tone(wo, a.blocks, (2, 5), (2, 9))[3] if a.ok else None
    if not (a.ok and 'LOOKS.BIN' not in fo and CRASH in fo and am['L'] == 'c2b5' and a.blocks[(2, 5)][2112:2116] != b'EP7L' and film(wo, a.blocks) == 0 and slots == (STV.ROW0,) * 3):
        bad.append(('after a fault (crash record in RAM)', 'BASE is expected to keep the old L pointer', a.why(), am, fo, slots))
    else:
        info.append(f'BASE, after a fault: the crash copy takes c2b5, LOOKS.BIN is not read and P+1016 still says {am["L"]} (the freed copy, tags gone): no Film page (fm_valid 0), '
                    f'no split tone (the pass leaves the stock curve)')
    return bad, n, info


# ------------------------------------------------------------------ N
def t_nocard(wo, wn):
    bad, n = [], 0

    def both(name, want_log, want_state, want_boot, skip=(), **kw):
        nonlocal n
        a, b = press(wo, {}, **kw), press(wn, {}, **kw)
        n += 1
        msg = same(a, b, skip)
        if msg or b.log != want_log or (b.state, b.boot) != (want_state, want_boot):
            bad.append((name, msg, b.log[:4], hex(b.state or 0), b.boot))
        return a, b

    both('no card (no medium mounted)', [], 0, 0, mounted=False)
    # no file: the block is taken, cleared (NEW) and given back; ap_boot arms the retry (state 0, count 1)
    a, b = both('card without BUNDLES.BIN', [('malloc', 1024, 'c1b6'), ('fopen', 'BUNDLES.BIN', False), ('free', 'c1b6')], 0, 0x10, skip=('c1b6',), present=())
    if a.ok and b.ok and (a.blocks[(1, 6)] != bytes(0x840) or b.blocks[(1, 6)] != bytes(0x840)):
        bad.append('no file: the freed block')
    # the retry on the next half-press finds the files: the bump allocator is one class-1 block on, everything else as a first press
    k = dict(K0); k[1] = 7
    a, b = press(wo, a.blocks, k, state=a.state, boot=a.boot), press(wn, b.blocks, k, state=b.state, boot=b.boot)
    n += 1
    msg = same(a, b)
    mk = marks(b.blocks[(1, 7)]) if b.ok else {}
    if msg or shape(b.log) != shape(CLEAN) or b.boot != 0x11 or b.state != blk(1, 7) - B3.POOL + 1 or (mk.get('L'), mk.get('looks'), mk.get('EP7A'), mk.get('EP7V')) != ('c2b5', b'EP7F', True, True):
        bad.append(('the retry loads', msg, hex(b.state or 0), b.boot, mk))
    both('no memory for P', [('malloc', 1024, None)], 0, 0x10, fail=1)
    return bad, n


# ------------------------------------------------------------------ A
def t_align():
    bad, hit = [], []
    for ins, rows, a0 in TRACE:
        for row in rows:
            if row['pc'] not in ins:
                continue
            op, args = ins[row['pc']]
            m = re.search(r'\(([^)]*)\)', args)
            if not m:
                continue
            addr = sum(row[p] if p in row else int(p, 0) for p in (p.strip() for p in m.group(1).split(','))) & 0xffffffff
            if op != 'movbu' or not args.endswith(')') or row['d0'] != 0:
                bad.append((hex(row['pc']), op, args))
            hit.append(addr)
        if sorted(hit) != list(range(a0, a0 + 1024)):
            bad.append(('stores', len(hit), len(set(hit))))
    return bad, len(hit)


# ------------------------------------------------------------------ P
def t_pkg(new_s, new, pkg, rst, info, disk, old):
    sb = {b.kind: b for b in oc.parse(BP.STOCK.read_bytes())}
    good = True
    for b in oc.parse(pkg):
        exp = bytearray(sb[b.kind].payload)
        for e in new_s['edits']:
            if int(e['kind'], 16) == b.kind:
                o = BP.resolve(b.kind, e['addr']); nb = bytes.fromhex(e['new']); exp[o:o + len(nb)] = nb
        good &= bytes(exp) == b.payload and (b.kind != 0x100 or b.payload == new)
    for b in oc.parse(rst):
        good &= b.payload == sb[b.kind].payload
    s = new_s['clean_boot']
    site, at, ln = int(s['site'], 16), int(s['code'][0], 16), s['code'][1]
    ours = [(site, 5), (CB.HLP[1], CB.HLP[2] - CB.HLP[1])]
    import numpy as np
    diff = [BASE + int(i) for i in np.nonzero(np.frombuffer(old, np.uint8) != np.frombuffer(new, np.uint8))[0]] if len(old) == len(new) else []
    stray = [hex(a) for a in diff if not any(a0 <= a < a0 + k for a0, k in ours)]
    good = bool(good) and not stray and len(old) == len(new) and bool(diff)
    good &= new[site - BASE:site - BASE + 5] == b'\xdc' + struct.pack('<i', int(s['symbols']['cb_zero'], 16) - site)
    good &= set(new[at + ln - BASE:CB.CLAIM[1] - BASE]) == {0xff} and new[at - BASE:at - BASE + ln] != old[at - BASE:at - BASE + ln]
    if disk:
        good &= (disk / 'patched.pkg.bin').read_bytes() == pkg and (disk / 'restore-stock.pkg.bin').read_bytes() == rst
    return good, f'{info["edits"]} edits, {info["changed_payload_bytes"]} B; {len(diff)} B differ from BASE; stray {stray[:6]}' + ('; package files on disk match' if disk else '')


def main():
    base_s, new_s = (json.loads(Path(p).read_text()) for p in sys.argv[1:3])
    disk = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    if 'clean_boot' in base_s or 'clean_boot' not in new_s:
        raise SystemExit('BASE must lack the layer, NEW must have it')
    stock = CB.STOCK.read_bytes()
    if [tuple(u32(stock, t + 4 * c - BASE) for t in (0x60026df4, 0x60026e34, 0x60026e04)) for c in range(3)] != list(POOLS):
        raise SystemExit('heap pool tables')                     # base, stride, block count of the three classes, as the stubs model them
    old, *_ = image(base_s)
    new, pkg, rst, info = image(new_s)
    unit = stub_unit()
    wo, wn = World(old, base_s, unit), World(new, new_s, unit)
    ok = True
    bad, n = t_stub(wo, wn); ok &= not bad
    print(f"{'PASS' if not bad else 'FAIL'} T cb_zero against the loader without it: {n - len(bad)}/{n}", bad[:4] if bad else '', flush=True)
    bad, n, clean, left = t_clean(wo, wn); ok &= not bad
    print(f"{'PASS' if not bad else 'FAIL'} C clean power-on == BASE: {n - len(bad)}/{n}; {len(clean.log)} calls; with DRAM 0xee BASE keeps {left} such bytes in P, NEW none", bad[:4] if bad else '', flush=True)
    if not bad:
        bad, n, text = t_restart(wo, wn, clean); ok &= not bad
        print(f"{'PASS' if not bad else 'FAIL'} R restart with stale DRAM: {n - len(bad)}/{n}", bad[:4] if bad else '', flush=True)
        for t in text:
            print('    ' + t)
        bad, n = t_nocard(wo, wn); ok &= not bad
        print(f"{'PASS' if not bad else 'FAIL'} N no card / no file / retry / no memory == BASE: {n - len(bad)}/{n}", bad[:4] if bad else '', flush=True)
    bad, n = t_align(); ok &= not bad and n > 0
    print(f"{'PASS' if not bad and n else 'FAIL'} A alignment: {n} accesses of cb_zero, all byte stores into the block", bad[:4] if bad else '', flush=True)
    good, txt = t_pkg(new_s, new, pkg, rst, info, disk, old); ok &= good
    print(f"{'PASS' if good else 'FAIL'} P anti-brick: {txt}")
    print('ALL PASS' if ok else 'FAILURES')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
