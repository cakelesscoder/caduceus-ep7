#!/usr/bin/env python3
"""Emulator checks for the crash record (patches/crash_log). Offline. docs/CRASH_LOG.md.

  .venv/bin/python -I patches/crash_log/verify.py BASE.json NEW.json [PKGDIR] [--out DIR]
  BASE = the same chain without the layer, NEW = with `--extra crash_log=patches/crash_log/build.py`.
  --out DIR: the CRASH.BIN of the D run and the decoder's text are left there.

  C1  the patched NMI handler entered at its site with a synthetic frame, rings, heap and stack, on CPU0 and CPU2: the slot
      holds every field and copy, the sum is right, the first record store is the busy mark and the last the complete mark;
      the other slots, the frames and everything else are untouched; at 0x60059ab1 every register, MDR, LIR, LAR and the PSW
      are those of the stock handler, and the stack differs only in the 28 B below sp.
      No card table, a handle out of range or unaligned, a wrong P magic, a null / out-of-pool / unaligned / overrunning
      record pointer, a wrong record magic, a bad TCB pointer, a bad SP: nothing outside the mapped regions is touched (the
      emulator faults on any such access) and the rest of the record is complete.
      A slot that holds a record keeps it (count, cause, PC of the later entry); a busy slot and an unknown CPU write nothing.
  C2  the real card loader from sd_hook on a half-press, file calls logged: with a record, one fopen("C:\\EP7MOD\\CRASH.BIN",
      "w") + one fwrite(copy, 1, 9396, handle) + fclose + free, the marks already 0 at the fopen, the file = the slots with a
      record and zeros elsewhere, RAM changed in the marks only; a damaged or a busy record is written too; no mark, no card
      table (BUNDLES.BIN missing), no memory: no file call and RAM untouched; fopen fails: no fwrite. In every case the
      registers handed to the next hook (ap_pre) and the loaded table are those of BASE.
  D   the decoder on the file of C1 + C2: cause, CPU, task, PC symbol and owner, ring, grain fields; its task names == the
      three name tables of the image
  X   every word / halfword access our code makes in the traced runs is aligned
  P   anti-brick: package reparses, decoded == stock + edits (the image emulated above), restore == stock, only our sites
      differ from BASE
"""
import argparse, importlib.util, json, re, struct, sys
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


CB = _load('crash_log_build_v', HERE / 'build.py')
F, B3 = CB.F, CB.B3
BASE, R, SLOT = CB.BASE, CB.R, F.SLOT
OK, BUSY = F.MAGIC_OK, F.MAGIC_BUSY
STK, STK_LEN, TCB_AT, FAR = 0x62500000, 0x3000, 0x62200040, 0x18100000    # the interrupted stacks: RAM addresses, as the stub checks
SPS = [STK + 0x400 + 0x1000 * c for c in range(3)]    # each CPU's frame SP; the handler's sp at the site is 16 B below
SP0 = SPS[0]
REGS = dict(d0=0, d1=0x12345641, d2=0x22220002, d3=0x33330003, a0=0x98e000a4, a1=0x98e0008c, a2=0xa2a20002, a3=0xa3a30003,
            mdr=0x60059aab, psw=0x0001, lir=0x11112222, lar=0x33334444)        # as wdt_hw_set returns: d0 = 0, Z set
KEEP = ('d0', 'd1', 'd2', 'd3', 'a0', 'a1', 'a2', 'a3', 'sp', 'mdr', 'psw', 'lir', 'lar')
H_OK = 0x2401                             # a card-table handle: P = pool + 0x2400
P_AT = CB.B3.POOL + H_OK - 1
G_AT = CB.G_POOL[0] + 0x1200              # a grain record in the class-0 pool
TRACES = []                               # (instruction map, trace rows) of the traced runs, for X
BUILD = ['']                              # the NEW spec's version: its tag is in every record


def image(spec):
    pkg, rst, info = BP.build(spec, BP.STOCK.read_bytes())
    return [b for b in oc.parse(pkg) if b.kind == 0x100][0].payload, pkg, rst, info


def img(m, lo, hi, name, perm='rx'):
    return Region(name, lo, m[lo - BASE:hi - BASE], perm)


def stub(addr, text, name, syms=None):
    c, _, _, _ = B3.assemble(' .am33_2\n .text\n .global _start\n_start:\n' + text + '\n', addr, syms or {})
    return Region(name, addr, c, 'rx')


def mem(r):
    return {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}


def accesses(rows, ins):
    """Every memory operand of our traced instructions -> (pc, 'r' / 'w', size, address, value stored)."""
    out = []
    for row in rows:
        if row['pc'] not in ins:
            continue
        op, args = ins[row['pc']]
        if op == 'movm':
            out.append((row['pc'], 'w' if args.endswith('(sp)') else 'r', 4, row['sp'], None))
            continue
        size = {'mov': 4, 'movhu': 2, 'movbu': 1}.get(op)
        m = re.search(r'\(([^)]*)\)', args)
        if not size or not m:
            continue
        addr = sum(row[p] if p in row else int(p, 0) for p in (p.strip() for p in m.group(1).split(','))) & 0xffffffff
        store = args.rstrip().endswith(')')
        out.append((row['pc'], 'w' if store else 'r', size, addr, row[args.split(',')[0]] if store else None))
    return out


# ------------------------------------------------------------------ fixtures
def frames():
    f = bytearray(0xc0)
    for c in range(3):
        struct.pack_into('<5I', f, 0x40 * c, 0x7700 + c, SPS[c], 0x0f01 + c, 0x60350000 + 0x111 * c, 0xb0b0 + c)
        struct.pack_into('<8I', f, 0x40 * c + 0x20, *(0xd0000000 + 0x01010101 * (8 * c + k) for k in range(8)))
    return f


def rings():
    """0xa26a0a90..0xa26a1cb0: the abort word, three rings (each: tail, head, 256 entries, overflow ring), the working-block pointer."""
    b = bytearray(0x1220)
    struct.pack_into('<I', b, 4, 0xab07ab07)
    for c in range(3):
        o = 0x10 + 0x448 * c
        struct.pack_into('<HHHH', b, o, 250, 37, 3 + c, 3 + c)
        for i in range(256):
            struct.pack_into('<BBH', b, o + 8 + 4 * i, b'IiFMPvV?'[(i + c) % 8], (60, 62, 91, 93, 101)[i % 5], 0x1001 + (i % 19))
        for i in range(16):
            struct.pack_into('<I', b, o + 0x408 + 4 * i, 0x0f0f0000 + 16 * c + i)
    struct.pack_into('<I', b, CB.RECBLK - 0xa26a0a90, 0xa6543210)
    return b


def grec(stage=6, rows=1024):
    g = bytearray(128)
    g[:4] = b'GDIA'; g[4] = 0; g[5] = stage; g[7] = 3
    struct.pack_into('<HHHHHHHHHH', g, 8, 0x0111, 5184, 0, rows, 0x0302, 5184, 5184, 3888, 0, 0)
    struct.pack_into('<II', g, 28, 0xc8123400, 40310784)
    g[36], g[37], g[38], g[39] = 0x23, 0x02, 2, 3
    struct.pack_into('<II', g, 40, 0x70123400, 0x9e3779b9)
    struct.pack_into('<IHBBHH', g, 48, 0x00080080, 0x1000, 1, 7, 3888, 0x1001)
    g[60], g[61], g[95] = 11, 1, 0
    struct.pack_into('<H', g, 96, 0x12)
    return g


def stack_bytes():
    s = bytearray(STK_LEN)
    for i in range(0, STK_LEN, 4):
        struct.pack_into('<I', s, i, 0x5a000000 + i)
    struct.pack_into('<I', s, SP0 - STK + 0x18, 0x603e5e00)      # two words that read as return addresses, for the decoder
    struct.pack_into('<I', s, SP0 - STK + 0x30, 0x60354300)
    return s


def c1_regions(m, s, cpu=0, rec=None, fr=None, handle=H_OK, pmagic=b'EP7B', gptr=G_AT, gmagic=b'GDIA', tcbp=TCB_AT, tid=31, nmi=4, syserr=0x20,
               pool=True, grecmap=True, tcbmap=True, cpuw=None):
    """The handler, our code and the RAM / registers the stub may read. Only what a case says exists is mapped."""
    lo, hi = (int(x, 16) for x in s['claim'])
    io = bytearray(0x100); struct.pack_into('<I', io, 0x50, (0xbeef0000 | cpu) if cpuw is None else cpuw); struct.pack_into('<I', io, 0x44, syserr)
    p = bytearray(1024); p[:4] = pmagic; struct.pack_into('<I', p, CB.GPTR, gptr & 0xffffffff)
    g = grec(); g[:4] = gmagic
    tw = {a: Region(f'tcbw{i}', a & ~0xf, bytes(a & 0xf) + struct.pack('<I', tcbp if i == cpu else 0x0bad0bad) + bytes(12 - (a & 0xf)), 'r') for i, a in enumerate(CB.TCB)}
    ad = bytearray(0x20); struct.pack_into('<4I', ad, 8, 0xc0de0000 + cpu, 0x0da7a000, 0x0da7a111, 0x5a5a0000 + cpu)
    rg = [img(m, 0x60059a00, 0x60059d00, 'handler'), img(m, lo, hi, 'cl'),
          Region('stk', STK, bytes(stack_bytes()), 'rw', True), Region('frames', CB.FRAMES, bytes(fr or frames()), 'r'),
          Region('rec', R, bytes(rec) if rec is not None else b'\x99' * F.FILE_LEN, 'rw', True),
          Region('io', 0x8000, bytes(io), 'r'), Region('io89', 0x8900, struct.pack('<I', nmi), 'r'), *tw.values(),
          Region('st', CB.STATE_LO, struct.pack('<HHI', 144, handle, 0), 'r'), Region('ring', 0xa26a0a90, bytes(rings()), 'r'),
          Region('xc', CB.XCODE & ~0xf, struct.pack('<4I', 0x33, 0, 0, 0), 'r'), Region('sect', CB.SECT, struct.pack('<I', 0x1ff), 'r'),
          Region('wm', CB.WMODE & ~0xf, bytes(4) + struct.pack('<3I', 3, 0, 4), 'r'), Region('ad', CB.ADDEC + 0x100 * (cpu if cpu < 3 else 0), bytes(ad), 'r')]
    if pool:
        rg.append(Region('pool', P_AT, bytes(p), 'r'))
    if grecmap:
        rg.append(Region('grec', G_AT, bytes(g), 'r'))
    if tcbmap:
        rg.append(Region('tcb', TCB_AT - 0x40, bytes(0x40 + 16) + struct.pack('<h', tid) + bytes(14), 'r'))
    return rg


def c1_run(m, s, ins=None, extra=(), **kw):
    rg = c1_regions(m, s, **kw) + list(extra)
    r = execute(rg, dict(REGS, pc=CB.SITE, sp=SPS[kw.get('cpu', 0)] - 16), CB.BACK, limit=200000, timeout=120, trace_limit=100000 if ins else 0)
    if ins:
        TRACES.append((ins, r['trace']))
    return r, mem(r)


def expect_slot(cpu, flags, fr, *, tid=31, tcbp=TCB_AT, handle=H_OK, p=P_AT, gptr=G_AT, grain=None, stack=None, nmi=4, syserr=0x20):
    """The record the stub must leave for these inputs."""
    s = bytearray(SLOT)
    rb = rings()
    struct.pack_into('<4I', s, F.O_INFO, F.VERSION | cpu << 8 | flags << 16, nmi, syserr, tid & 0xffffffff)
    struct.pack_into('<4I', s, F.O_TCB, tcbp, 0x33, 0x1ff, 144 | handle << 16)
    struct.pack_into('<4I', s, F.O_P, p, gptr & 0xffffffff, 0xab07ab07, 0xa6543210)
    struct.pack_into('<3I', s, F.O_WMODE, 3, 0, 4)
    struct.pack_into('<4I', s, F.O_ADDEC, 0xc0de0000 + cpu, 0x0da7a000, 0x0da7a111, 0x5a5a0000 + cpu)
    struct.pack_into('<2I', s, F.O_SIZE, SLOT, F.build_tag(BUILD[0]))
    s[F.O_FRAMES:F.O_FRAMES + 0xc0] = fr
    s[F.O_RING0:F.O_RING0 + 0x448] = rb[0x10:0x10 + 0x448]
    if cpu:
        s[F.O_RINGN:F.O_RINGN + 0x448] = rb[0x10 + 0x448 * cpu:0x10 + 0x448 * (cpu + 1)]
    if grain is not None:
        s[F.O_GRAIN:F.O_GRAIN + 128] = grain
    if stack is not None:
        s[F.O_STACK:F.O_STACK + F.STACK_LEN] = stack
    s[:4] = OK
    struct.pack_into('<I', s, F.O_SUM, F.checksum(s))
    return bytes(s)


# ------------------------------------------------------------------ C1
def t_c1(old, new, s, ins):
    bad, n = [], 0
    fr = frames()
    stk = stack_bytes()
    snap = lambda sp: bytes(stk[sp - STK:sp - STK + F.STACK_LEN])
    ALL = F.F_TID | F.F_PH | F.F_PM | F.F_GP | F.F_GM | F.F_STK
    # stock at the site: the registers the handler goes on with
    want_regs = {}
    for cpu in range(3):
        r0 = execute(c1_regions(old, s, cpu=cpu), dict(REGS, pc=CB.SITE, sp=SPS[cpu] - 16), CB.BACK, limit=10)
        want_regs[cpu] = {k: r0['registers'][k] for k in KEEP}
        if r0['fault'] or r0['completed'] != 1 or want_regs[cpu]['a0'] != CB.HOOK_IMM or mem(r0)['stk'] != bytes(stk):
            return [('stock site', r0['fault'], r0['completed'])], 1

    def check(name, r, m, cpu, want, rec0=None, wrote=True):
        nonlocal n
        n += 1
        rr = r['registers']
        got = m['rec']
        base = bytes(rec0) if rec0 is not None else b'\x99' * F.FILE_LEN
        exp = bytearray(base)
        if want is not None:
            exp[cpu * SLOT:(cpu + 1) * SLOT] = want
        sp = SPS[cpu] - 16                                   # the stub's scratch is the 28 B below the handler's sp, nothing else
        stk_ok = m['stk'][sp - STK:] == bytes(stk)[sp - STK:] and m['stk'][:sp - 28 - STK] == bytes(stk)[:sp - 28 - STK]
        ok = not r['fault'] and rr['pc'] == CB.BACK and all(rr[k] == want_regs[cpu][k] for k in KEEP) and got == bytes(exp) and stk_ok
        if not ok:
            d = [hex(i) for i in range(0, F.FILE_LEN, 4) if got[i:i + 4] != exp[i:i + 4]][:6]
            bad.append((name, r['fault'], hex(rr['pc']), {k: hex(rr[k]) for k in KEEP if rr[k] != want_regs[cpu][k]}, d, stk_ok))
        return ok

    # the full record, CPU0 and CPU2, traced: order of the record stores
    for cpu in (0, 2):
        r, m = c1_run(new, s, ins, cpu=cpu)
        check(f'CPU{cpu} full', r, m, cpu, expect_slot(cpu, ALL | (F.F_RN if cpu else 0), fr, grain=grec(), stack=snap(SPS[cpu])))
        n += 1
        w = [(a, v) for pc, k, sz, a, v in accesses(r['trace'], ins) if k == 'w' and R <= a < R + F.FILE_LEN]
        slot = R + cpu * SLOT
        if not (w and w[0] == (slot, struct.unpack('<I', BUSY)[0]) and w[-1] == (slot, struct.unpack('<I', OK)[0]) and w[-2][0] == slot + F.O_SUM
                and [a for a, _ in w].count(slot) == 2 and all(slot <= a < slot + SLOT for a, _ in w) and len(r['trace']) == r['completed']):
            bad.append((f'CPU{cpu} store order', [(hex(a), hex(v)) for a, v in w[:2] + w[-2:]], len(r['trace']), r['completed']))
    r, m = c1_run(new, s, cpu=1)                             # CPU1: the middle frame / ring / TCB word / ADDEC block
    check('CPU1 full', r, m, 1, expect_slot(1, ALL | F.F_RN, fr, grain=grec(), stack=snap(SPS[1])))
    # pointers that must not be followed: the target is not mapped, so a read there would fault
    NOG = ALL & ~(F.F_GP | F.F_GM)
    NOP = NOG & ~(F.F_PH | F.F_PM)
    cases = [('no card table (handle 0)', dict(handle=0, pool=False, grecmap=False), dict(flags=NOP, handle=0, p=0, gptr=0)),
             ('handle 0xffff (load failed)', dict(handle=0xffff, pool=False, grecmap=False), dict(flags=NOP, handle=0xffff, p=0, gptr=0)),
             ('handle past the pool', dict(handle=CB.B3.LIM + 1, pool=False, grecmap=False), dict(flags=NOP, handle=CB.B3.LIM + 1, p=0, gptr=0)),
             ('handle unaligned', dict(handle=H_OK + 2, pool=False, grecmap=False), dict(flags=NOP, handle=H_OK + 2, p=0, gptr=0)),
             ('P magic wrong', dict(pmagic=b'XXXX'), dict(flags=ALL & ~F.F_PM, grain=grec())),
             ('record pointer null', dict(gptr=0, grecmap=False), dict(flags=NOG, gptr=0)),
             ('record pointer below the pool', dict(gptr=CB.G_POOL[0] - 4, grecmap=False), dict(flags=NOG, gptr=CB.G_POOL[0] - 4)),
             ('record pointer overruns the pool', dict(gptr=CB.G_POOL[1] - 124, grecmap=False), dict(flags=NOG, gptr=CB.G_POOL[1] - 124)),
             ('record pointer past the pool', dict(gptr=CB.G_POOL[1], grecmap=False), dict(flags=NOG, gptr=CB.G_POOL[1])),
             ('record pointer in another pool', dict(gptr=P_AT + 0x400, grecmap=False), dict(flags=NOG, gptr=P_AT + 0x400)),
             ('record pointer unaligned', dict(gptr=G_AT + 2, grecmap=False), dict(flags=NOG, gptr=G_AT + 2)),
             ('record pointer odd', dict(gptr=G_AT + 1, grecmap=False), dict(flags=NOG, gptr=G_AT + 1)),
             ('record magic wrong', dict(gmagic=b'XDIA'), dict(flags=ALL & ~F.F_GM, grain=bytes(b'XDIA') + bytes(grec()[4:]))),
             ('TCB pointer odd', dict(tcbp=TCB_AT + 1, tcbmap=False), dict(flags=ALL & ~F.F_TID, tid=-1, tcbp=TCB_AT + 1, grain=grec())),
             ('TCB pointer null', dict(tcbp=0, tcbmap=False), dict(flags=ALL & ~F.F_TID, tid=-1, tcbp=0, grain=grec())),
             ('TCB pointer outside RAM', dict(tcbp=0x98e00000, tcbmap=False), dict(flags=ALL & ~F.F_TID, tid=-1, tcbp=0x98e00000, grain=grec())),
             ('TCB pointer at the end of RAM', dict(tcbp=0x68000000 - 0x100, tcbmap=False), dict(flags=ALL & ~F.F_TID, tid=-1, tcbp=0x68000000 - 0x100, grain=grec())),
             ('tid negative (no task)', dict(tid=-3), dict(flags=ALL, tid=-3, grain=grec()))]
    for name, kw, ex in cases:
        r, m = c1_run(new, s, **kw)
        flags = ex.pop('flags')
        check(name, r, m, 0, expect_slot(0, flags, fr, stack=snap(SP0), **ex))
    # the two record-pool limits that must pass: the first and the last 128-B place
    for name, g_at in (('record at the pool start', CB.G_POOL[0]), ('record at the pool end', CB.G_POOL[1] - 128)):
        r, m = c1_run(new, s, extra=[Region('grec', g_at, bytes(grec()), 'r')], gptr=g_at, grecmap=False)
        check(name, r, m, 0, expect_slot(0, ALL, fr, gptr=g_at, grain=grec(), stack=snap(SP0)))
    # a bad SP in the frame: no stack copy (the handler's own sp, a register, stays good)
    for name, spv in (('SP unaligned', SP0 + 2), ('SP outside RAM', 0x40001000), ('SP at the end of RAM', 0x68000000 - F.STACK_LEN + 4), ('SP null', 0)):
        f2 = bytearray(fr); struct.pack_into('<I', f2, 4, spv)
        r, m = c1_run(new, s, fr=f2)
        check(name, r, m, 0, expect_slot(0, ALL & ~F.F_STK, f2, grain=grec()))
    # the uncached alias of the stack is RAM too
    f2 = bytearray(fr); struct.pack_into('<I', f2, 4, 0xa2300000)
    r, m = c1_run(new, s, extra=[Region('ustk', 0xa2300000, bytes(range(256)) * 2, 'r')], fr=f2)
    check('SP on the uncached alias', r, m, 0, expect_slot(0, ALL, f2, grain=grec(), stack=bytes(range(256)) * 2))
    # a slot that holds a record keeps it: only the later-entry words change, the sum still holds
    rec0 = bytearray(b'\x99' * F.FILE_LEN)
    first = expect_slot(0, ALL, fr, grain=grec(), stack=snap(SP0))
    rec0[:SLOT] = first
    f2 = bytearray(fr); struct.pack_into('<I', f2, 12, 0x60059cec)
    w1 = bytearray(first); struct.pack_into('<4I', w1, F.O_LATER, 1, 2, 0x20, 0x60059cec)
    r, m = c1_run(new, s, rec=rec0, fr=f2, nmi=2)
    check('second NMI: record kept, counted', r, m, 0, bytes(w1), rec0=rec0)
    rec1 = bytearray(rec0); rec1[:SLOT] = w1
    w2 = bytearray(w1); struct.pack_into('<4I', w2, F.O_LATER, 2, 6, 0x208, 0x60059cec)
    r, m = c1_run(new, s, rec=rec1, fr=f2, nmi=6, syserr=0x208)
    if check('third NMI', r, m, 0, bytes(w2), rec0=rec1) and F.state(m['rec'][:SLOT]) != 'ok':
        bad.append(('later entries break the sum',))
    # a busy slot (the stub was entered and did not finish) and an unknown CPU: nothing is written, nothing is read
    rec0 = bytearray(b'\x99' * F.FILE_LEN); rec0[:4] = BUSY
    r, m = c1_run(new, s, rec=rec0, pool=False, grecmap=False, tcbmap=False)
    check('busy slot: skipped', r, m, 0, None, rec0=rec0)
    for cpuw in (3, 0x00010007):
        r, m = c1_run(new, s, cpuw=cpuw, pool=False, grecmap=False, tcbmap=False)
        check(f'CPU word {cpuw:#x}: skipped', r, m, 0, None)
    # the high half of the CPU word is ignored, as in the handler (exthu)
    r, m = c1_run(new, s, cpuw=0x00050000)
    check('CPU word 0x50000 = CPU0', r, m, 0, first)
    return bad, n


# ------------------------------------------------------------------ C2
LOG, PX, BX, FILE_AT, FS2 = 0x18200000, P_AT, 0xa1de0000, 0x18300000, 0x18070000
H_BUN, H_CR = 0x41, 0x42


def c2_regions(m, spec, s, rec, *, bundles=True, heap_ok=True, crash_open=True):
    """The loader (sec 3), our code, the services as logging stubs. LOG: +0 malloc n, +4 free n, +8 fopen n, +12 fwrite n, +16 fclose n,
    +0x20 malloc sizes, +0x40 free pointers, +0x60 fopen {path, mode, mark0, mark1, mark2} x 3, +0xc0 fwrite {buf, size, count, handle,
    mark0..2}, +0xe0 fclose handles."""
    sv = {k: int(v, 16) for k, v in spec['sd_bundles_v3']['services'].items()}
    sy = {k: int(v, 16) for k, v in spec['sd_bundles_v3']['symbols'].items()}
    lo, hi = (int(x, 16) for x in s['claim'])
    f = (ROOT / 'releases/v0.32b/card/EP7MOD/BUNDLES.BIN').read_bytes()
    marks = lambda base: ''.join(f' mov ({R + i * SLOT:#x}),d2\n mov d2,({base + 4 * i},a2)\n' for i in range(3))
    idx = lambda off, shift: f' mov ({LOG + off:#x}),d2\n mov d2,d3\n inc d3\n mov d3,({LOG + off:#x})\n' + ' asl2 d2\n' * shift
    far = {
        'malloc': idx(0, 1) + f''' mov {LOG + 0x20:#x},a2
 add d2,a2
 mov d0,(a2)
 mov {PX:#x},a0
 cmp 0,d2
 beq 1f
 mov {BX if heap_ok else 0:#x},a0
1:
 jmp back
''',
        'free': idx(4, 1) + f' mov {LOG + 0x40:#x},a2\n add d2,a2\n mov a0,(a2)\n jmp back\n',
        'fopen': idx(8, 0) + f''' mov d2,d3
 asl2 d2
 asl2 d3
 asl2 d3
 add d3,d2
 mov {LOG + 0x60:#x},a2
 add d2,a2
 mov a0,(a2)
 mov a1,(4,a2)
''' + marks(8) + f''' cmp {sy['sd_path']:#x},a0
 bne 1f
 mov {H_BUN if bundles else 0},a0
 jmp back
1:
 mov {H_CR if crash_open else 0},a0
 jmp back
''',
        'fwrite': idx(12, 0) + f''' mov {LOG + 0xc0:#x},a2
 mov a0,(a2)
 mov d0,(4,a2)
 mov d1,(8,a2)
 mov a1,(12,a2)
''' + marks(16) + f''' mov {FILE_AT:#x},a2
 mov d1,d2
 lsr 2,d2
 cmp 0,d2
 beq 2f
1:
 mov (a0),d3
 mov d3,(a2)
 inc4 a0
 inc4 a2
 add -1,d2
 bne 1b
2:
 mov d1,d0
 jmp back
''',
        'fclose': idx(16, 1) + f' mov {LOG + 0xe0:#x},a2\n add d2,a2\n mov a0,(a2)\n clr d0\n jmp back\n',
        'fread': f''' mov {FS2:#x},a2
 mov d1,d2
 mov d1,d3
 cmp 0,d2
 beq 2f
1:
 movbu (a2),d0
 movbu d0,(a0)
 inc a0
 inc a2
 add -1,d2
 bne 1b
2:
 mov d3,d0
 jmp back
'''}
    # each service: its entry jumps to a far stub with [d2,d3,a2,a3] saved; the stub ends in the service's own ret
    rets = {'malloc': 'ret [],4', 'free': 'ret [],4', 'fopen': 'ret [],4', 'fwrite': 'ret [d2,d3,a2,a3],24', 'fclose': 'ret [d2,a2,a3],16', 'fread': 'ret [d2,d3,a2,a3],24'}
    at = {'malloc': sv['ep7_malloc'], 'free': sv['ep7_free'], 'fopen': sv['ep7_fopen'], 'fwrite': CB.FWRITE, 'fclose': sv['ep7_fclose'], 'fread': sv['ep7_fread']}
    rg = []
    for i, (k, body) in enumerate(far.items()):
        fa = FAR + 0x400 * i
        text = ' movm [d2,d3,a2,a3],(sp)\n' + body.replace(' jmp back\n', f' movm (sp),[d2,d3,a2,a3]\n {rets[k]}\n')
        rg += [stub(at[k], ' jmp tgt', 'j_' + k, dict(tgt=fa)), stub(fa, text, 's_' + k)]
    stk = bytearray(0x1000); struct.pack_into('<I', stk, 0x800 + 16, CB.B3.EV_PRESS)
    ap_pre = int(spec['ap_custom']['symbols']['ap_pre'], 16)
    rg += [img(m, 0x605b7400, 0x605b7800, 'sec3'), img(m, lo, hi, 'cl'), stub(sv['ep7_trig'], ' ret [d2,d3,a2,a3],36', 'trig'),
           stub(sv['ep7_get_tid'], ' mov 5,d0\n movhu d0,(a0)\n clr d0\n ret [a2],4', 'tid'),
           stub(sv['ep7_fseek'], ' clr d0\n ret [d2,d3,a2,a3],20', 'fs'), stub(sv['ep7_ftell'], f' mov {len(f)},d0\n ret [d2,a2,a3],16', 'ft'),
           Region('secbits', sv['ep7_secbits'], struct.pack('<I', 0x1ff), 'r'), Region('ms', sv['ep7_ms_a'], struct.pack('<I', 0xf000) + bytes(28), 'r'),
           Region('state', 0x622cbcc0, struct.pack('<HHI', 5, 0, 0), 'rw', True), Region('pool', PX, bytes(1024), 'rw', True),
           Region('rec', R, bytes(rec), 'rw', True), Region('heap', BX, b'\xee' * 0x4040, 'rw', True), Region('file', FILE_AT, b'\xdd' * 0x2800, 'rw', True),
           Region('log', LOG, bytes(0x100), 'rw', True), Region('bun', FS2, f.ljust(0x400, b'\0'), 'r'),
           Region('stack', 0x18010000, bytes(stk), 'rw'), Region('t', ap_pre, b'\xcb', 'rx')]
    return rg, sy, ap_pre


def c2_run(m, spec, s, rec, ins=None, **kw):
    rg, sy, stop = c2_regions(m, spec, s, rec, **kw)
    r = execute(rg, dict(pc=sy['sd_hook'], sp=0x18010800, d0=0, d1=0, a0=0x18010810, a1=0, d2=0x1111, d3=0x2222, a2=0x3333, a3=0x4444, mdr=0x5555),
                stop, limit=3000000, timeout=300, trace_limit=100000 if ins else 0, trace_tail=bool(ins))
    if ins:
        TRACES.append((ins, r['trace']))
    mm = mem(r)
    lg = mm['log']
    u = lambda o, k=1: list(struct.unpack_from(f'<{k}I', lg, o))
    cnt = dict(zip(('malloc', 'free', 'fopen', 'fwrite', 'fclose'), u(0, 5)))
    return dict(r=r, m=mm, cnt=cnt, sizes=u(0x20, cnt['malloc']), freed=u(0x40, cnt['free']), opens=[u(0x60 + 20 * i, 5) for i in range(cnt['fopen'])],
                write=u(0xc0, 7), closed=u(0xe0, cnt['fclose']), reg=r['registers'], sy=sy, stop=stop)


def cstr(m, a):
    return bytes(m[a - BASE:m.index(b'\0', a - BASE)])


def t_c2(old, new, base_s, new_s, s, ins, first):
    bad, n = [], 0
    sym = {k: int(v, 16) for k, v in s['symbols'].items()}
    garbage = b'\x99' * F.FILE_LEN
    one = bytearray(garbage); one[:SLOT] = first
    two = bytearray(one); two[2 * SLOT:2 * SLOT + 4] = BUSY
    dmg = bytearray(one); dmg[F.O_RING0 + 40] ^= 0x04
    near = bytearray(garbage); near[:4] = struct.pack('<I', struct.unpack('<I', OK)[0] + 1); near[SLOT:SLOT + 4] = struct.pack('<I', struct.unpack('<I', BUSY)[0] - 1)
    h = PX - CB.B3.POOL + 1
    out = {}

    def run(name, rec, present, **kw):
        """present: the slots that hold a record. -> the NEW run."""
        nonlocal n
        n += 1
        a = c2_run(new, new_s, s, rec, ins if name == 'one record' else None, **kw)
        b = c2_run(old, base_s, s, rec, **kw)
        wrote = bool(present) and kw.get('bundles', True) and kw.get('heap_ok', True)
        exp_rec = bytearray(rec)
        exp_file = bytearray()
        for i in range(3):
            if i in present:
                exp_file += rec[i * SLOT:(i + 1) * SLOT]
                if wrote:
                    exp_rec[i * SLOT:i * SLOT + 4] = bytes(4)
            else:
                exp_file += bytes(SLOT)
        opened = wrote and kw.get('crash_open', True)
        loaded = kw.get('bundles', True)
        ok = not a['r']['fault'] and not b['r']['fault'] and a['reg']['pc'] == b['reg']['pc'] == a['stop']       # both reach the next hook, ap_pre
        ok &= all(a['reg'][k] == b['reg'][k] for k in ('d0', 'd1', 'd2', 'd3', 'a0', 'a1', 'a2', 'a3', 'sp'))
        ok &= (bool(present) and kw.get('bundles', True)) or a['reg']['mdr'] == b['reg']['mdr']        # MDR too, unless our code made a call
        ok &= a['m']['pool'] == b['m']['pool'] and a['m']['state'] == b['m']['state'] and (struct.unpack_from('<H', a['m']['state'], 2)[0] == (h if loaded else 0xffff))
        ok &= a['m']['rec'] == bytes(exp_rec) and b['m']['rec'] == bytes(rec)
        ok &= b['cnt'] == dict(malloc=1, free=0 if loaded else 1, fopen=1, fwrite=0, fclose=1 if loaded else 0)
        ok &= a['sizes'] == [1024] + ([F.FILE_LEN] if bool(present) and loaded else []) and a['freed'] == ([] if loaded else [PX]) + ([BX] if wrote else [])
        ok &= a['cnt']['fopen'] == 1 + wrote and a['cnt']['fwrite'] == int(opened) and a['closed'] == ([H_BUN] if loaded else []) + ([H_CR] if opened else [])
        if wrote:
            p_, mo, m0, m1, m2 = a['opens'][1]
            ok &= cstr(new, p_) == b'C:\\EP7MOD\\CRASH.BIN' and cstr(new, mo) == b'w' and (p_, mo) == (sym['cl_path'], sym['cl_mode'])
            ok &= all(mk == 0 or i not in present for i, mk in enumerate((m0, m1, m2)))            # every mark of a record is 0 before the file call
            ok &= a['m']['heap'][:F.FILE_LEN] == bytes(exp_file) and a['m']['heap'][F.FILE_LEN:] == b'\xee' * (0x4040 - F.FILE_LEN)
        else:
            ok &= a['m']['heap'] == b'\xee' * 0x4040
        if opened:
            ok &= a['write'][:4] == [BX, 1, F.FILE_LEN, H_CR] and a['m']['file'][:F.FILE_LEN] == bytes(exp_file) and a['m']['file'][F.FILE_LEN:] == b'\xdd' * (0x2800 - F.FILE_LEN)
            ok &= all(mk == 0 or i not in present for i, mk in enumerate(a['write'][4:7]))
        else:
            ok &= a['m']['file'] == b'\xdd' * 0x2800
        if not ok:
            bad.append((name, a['r']['fault'], b['r']['fault'], hex(a['reg']['pc']), a['cnt'], b['cnt'], a['sizes'], [hex(x) for x in a['freed']], [hex(x) for x in a['write'][:4]],
                        {k: (hex(a['reg'][k]), hex(b['reg'][k])) for k in ('d0', 'd1', 'd2', 'd3', 'a0', 'a1', 'a2', 'a3', 'sp', 'mdr') if a['reg'][k] != b['reg'][k]}))
        out[name] = a
        return a

    run('one record', one, {0})
    run('a record and a busy slot', two, {0, 2})
    run('damaged record (sum differs)', dmg, {0})
    run('no mark (0x99 fill)', garbage, set())
    run('no mark (zeros)', bytes(F.FILE_LEN), set())
    run('marks off by one', near, set())
    run('record, but no card table (BUNDLES.BIN missing)', one, {0}, bundles=False)
    run('no record, no card table', garbage, set(), bundles=False)
    run('record, no memory for the copy', one, {0}, heap_ok=False)
    run('record, fopen fails', one, {0}, crash_open=False)
    return bad, n, out


# ------------------------------------------------------------------ D
def t_dec(new, new_s, s, out, outdir):
    bad, n = [], 0
    # the decoder's task names are the image's three tables
    for cpu, a in enumerate((0x613ff240, 0x6140033a, 0x61400b18)):
        t, p = {}, a - BASE
        while re.fullmatch(rb'[A-Za-z0-9_]{2,23}', new[p:p + 24].split(b'\0')[0]):
            t[struct.unpack_from('<H', new, p + 24)[0]] = new[p:p + 24].split(b'\0')[0].decode(); p += 26
        n += 1
        if t != F.TASKS[cpu]:
            bad.append(('task table', cpu, len(t), len(F.TASKS[cpu])))
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        sp = Path(td) / 'spec.json'; sp.write_text(json.dumps(new_s))
        ws = F.Where(ROOT / 'docs/atlas.json', ROOT / 'docs/CODE_SPACE_MAP.md', sp)
    w = F.Where(ROOT / 'docs/atlas.json', ROOT / 'docs/CODE_SPACE_MAP.md', None)
    files = {}
    for name, key in (('CRASH.BIN', 'one record'), ('CRASH_2.BIN', 'a record and a busy slot'), ('CRASH_damaged.BIN', 'damaged record (sum differs)')):
        files[name] = out[key]['m']['file'][:F.FILE_LEN]
    text = '\n'.join(F.decode(files['CRASH.BIN'], ws))
    need = [f'{F.FILE_LEN} B, 1 record', f"= the spec's build ({BUILD[0]})", '== slot 0: complete, checksum ok', 'FATAL_SYSTEM_ERROR: MEM', 'CPU       0', 'task      31 REC_IMAGE', 'PC        0x60350000',
            'stage 6 (pass: writing rows)', 'rows done 1024 of 3888', 'level 2', "magic b'GDIA'", 'capture ring: 43 entries (tail 250, head 37)', 'HLS_EVENT task id 144',
            'CPU2 frame as CPU0 read it', 'system-down code 0x33', '+0x018  0x603e5e00  REC_IMAGE+0xa9', '+0x030  0x60354300']
    n += 1
    if any(x not in text for x in need):
        bad.append(('decode', [x for x in need if x not in text]))
    t2 = '\n'.join(F.decode(files['CRASH_2.BIN'], w))
    t3 = '\n'.join(F.decode(files['CRASH_damaged.BIN'], w))
    n += 2
    if '2 records' not in t2 or '== slot 2: INCOMPLETE' not in t2:
        bad.append(('decode busy', t2[:200]))
    if 'CHECKSUM MISMATCH' not in t3 or 'task      31 REC_IMAGE' not in t3:
        bad.append(('decode damaged', t3[:200]))
    # where a PC lies: our code by the spec and by the claim map, stock code by the atlas
    g2 = int(new_s['grain_g2']['symbols']['g2_blk'], 16)
    for a, want, wh in ((g2 + 0x5c, ('g2_blk+0x5c', 'OURS', 'patches/grain_g2'), ws), (g2 + 0x5c, ('in our claim', 'grain_g2'), w), (0x60635050, ('fwrite+0xf', 'stock code'), ws),
                        (0x60059cec, ('nmi_wdt_branch+0x89', 'stock code'), ws), (int(s['symbols']['cl_nmi'], 16) + 4, ('cl_nmi+0x4', 'OURS', 'patches/grain_cpu'), ws),
                        (0xa1f8d800, ('RAM',), ws)):
        n += 1
        d = wh.describe(a)
        if any(x not in d for x in want):
            bad.append(('where', hex(a), d))
    if outdir:
        outdir.mkdir(parents=True, exist_ok=True)
        for name, b in files.items():
            (outdir / name).write_bytes(b)
        (outdir / 'CRASH.txt').write_text(text + '\n')
    return bad, n, text


# ------------------------------------------------------------------ X
def t_align():
    bad, n = [], 0
    for ins, rows in TRACES:
        for pc, k, size, addr, _ in accesses(rows, ins):
            n += 1
            if addr % size:
                bad.append((hex(pc), ins[pc], hex(addr)))
    return bad, n


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
    s = new_s['crash_log']
    ours = [(int(s['site'], 16), 6), (int(s['code'][0], 16), s['code'][1]), (int(s['c2_site'], 16), 5)]
    import numpy as np
    diff = [BASE + int(i) for i in np.nonzero(np.frombuffer(old, np.uint8) != np.frombuffer(new, np.uint8))[0]] if len(old) == len(new) else []
    stray = [hex(a) for a in diff if not any(a0 <= a < a0 + k for a0, k in ours)]
    good = bool(good) and not stray and len(old) == len(new) and bool(diff)
    site = int(s['site'], 16)
    good &= new[site - BASE:site - BASE + 6] == b'\xdc' + struct.pack('<i', int(s['symbols']['cl_nmi'], 16) - site) + b'\xcb'
    c2 = int(s['c2_site'], 16)
    good &= new[c2 - BASE:c2 - BASE + 5] == b'\xdc' + struct.pack('<i', int(s['symbols']['cl_first'], 16) - c2)
    if disk:
        good &= (disk / 'patched.pkg.bin').read_bytes() == pkg and (disk / 'restore-stock.pkg.bin').read_bytes() == rst
    return good, f'{info["edits"]} edits, {info["changed_payload_bytes"]} B; {len(diff)} B differ from BASE; stray {stray[:6]}' + ('; package files on disk match' if disk else '')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('base', type=Path)
    ap.add_argument('new', type=Path)
    ap.add_argument('pkg', type=Path, nargs='?')
    ap.add_argument('--out', type=Path)
    a = ap.parse_args()
    base_s, new_s = json.loads(a.base.read_text()), json.loads(a.new.read_text())
    if 'crash_log' in base_s or 'crash_log' not in new_s:
        raise SystemExit('BASE must lack the layer, NEW must have it')
    old, *_ = image(base_s)
    new, pkg, rst, info = image(new_s)
    s = new_s['crash_log']
    BUILD[0] = s['version']
    at, ln = int(s['code'][0], 16), s['code'][1]
    sym = {k: int(v, 16) for k, v in s['symbols'].items()}
    ins = {x: (op, args) for x, op, args in B3.disasm(new[at - BASE:at - BASE + ln], at, sym['cl_path'])}
    ok = True
    bad, n = t_c1(old, new, s, ins); ok &= not bad
    print(f"{'PASS' if not bad else 'FAIL'} C1 fault-time stub: {n - len(bad)}/{n}", bad[:5] if bad else '', flush=True)
    first = expect_slot(0, F.F_TID | F.F_PH | F.F_PM | F.F_GP | F.F_GM | F.F_STK, frames(), grain=grec(), stack=bytes(stack_bytes()[SP0 - STK:SP0 - STK + F.STACK_LEN]))
    bad, n, out = t_c2(old, new, base_s, new_s, s, ins, first); ok &= not bad
    print(f"{'PASS' if not bad else 'FAIL'} C2 next-boot writer: {n - len(bad)}/{n}", bad[:5] if bad else '', flush=True)
    bad, n, text = t_dec(new, new_s, s, out, a.out); ok &= not bad
    print(f"{'PASS' if not bad else 'FAIL'} D decoder: {n - len(bad)}/{n}", bad[:5] if bad else '', flush=True)
    bad, n = t_align(); ok &= not bad and n > 0
    print(f"{'PASS' if not bad and n else 'FAIL'} X alignment: {n - len(bad)}/{n} accesses in {len(TRACES)} traced runs", bad[:5] if bad else '', flush=True)
    good, txt = t_pkg(new_s, new, pkg, rst, info, a.pkg, old); ok &= good
    print(f"{'PASS' if good else 'FAIL'} P anti-brick: {txt}")
    print('ALL PASS' if ok else 'FAILURES')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
