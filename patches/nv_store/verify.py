#!/usr/bin/env python3
"""Emulator checks for the settings-memory probe and marker (patches/nv_store). Offline. docs/INTERNAL_STORAGE.md S0 + S1.

  .venv/bin/python -I patches/nv_store/verify.py BASE.json NEW.json [PKGDIR]
  BASE = the same chain without the layer, NEW = with `--extra nv_store=patches/nv_store/build.py`.

The run is the harness of patches/clean_boot/verify.py: one shutter half-press from the card loader's hook to the stock code
after it, on the real code of every layer on the way, with the services as logged stubs. Added here: the camera's settings
image (cached and uncached as two separate memories, so a store to only one of them shows), its shadow, the bank object, the
CPU word, and cpu_lock / cpu_unlock as logged stubs. **Memory protection is the store check:** of the settings image only the
16 marker bytes (cached and uncached) are writable, and only in the cases that expect a store; the shadow, the bank object
and everything else of the image are read-only, so one stray store anywhere is a fault and fails the case.

  M  the round trip with the stock routines: a valid image with a zero tail -> half-press: marker 1 at both addresses, file as
     the model says -> stock prm_bank_save up to its flash call (the tail-only change is seen, generation + 1, sum 0, source =
     the uncached image) -> stock prm_bank_load from that image -> half-press: marker 1 found, the same in the shadow,
     marker 2 written -> save, load -> FORGET.BIN: cleared at both addresses -> save, load -> FORGET.BIN again: nothing to clear
  S  every case below runs with the protection above; the cases that must not store run with the 16 bytes read-only too.
     Control: the first power-on with the 16 bytes read-only faults at the first store (cached); with only the cached ones
     writable, at the fifth (uncached). So the protection does see each of the two stores' homes
  G  a save in flight: generations differ before the lock (nothing done, no lock taken); a save that starts between the check
     and the lock (the lock stub raises the RAM generation): lock, no store, unlock, "put off"; the 16 bytes changed in
     that window: no store either
  Z  non-zero bytes: in the tail outside the reserve, in the reserve after the marker, foreign bytes in the 16, a damaged
     marker (left alone; cleared with FORGET.BIN), cached != uncached, RAM != shadow
  B  the wrong bank object: another pointer (never followed: its target is not mapped), RAM, size, shadow or id wrong, the
     image's id wrong, another CPU
  N  no card, no BUNDLES.BIN, a BUNDLES.BIN that fails its check, no memory for P: == BASE, with no settings memory mapped at
     all (one read would fault). No memory for our 128 B: the same, plus one refused malloc
  C  clean power-on: BASE's calls with ours in one place, the same tables, registers, state, live stack; the half-press
     after a fault (a crash record in RAM): our file, then crash_log's, both as BASE's / the model's
  X  traced: every word and halfword access of the layer is aligned and every store is in the block, the frame or the 16
     bytes (the first and the last 100,000 instructions of the layer by itself; the rest is the tail-scan loop)
  D  the decoder (tools/ep7_nvprobe.py) on the files of the cases above: go / STOP as expected
  P  anti-brick: package reparses, decoded == stock + edits (the image emulated above), restore == stock, only our bytes
     differ from BASE
"""
import importlib.util, json, re, struct, sys, zlib
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


NB = _load('nv_store_build_v', HERE / 'build.py')
CBV = _load('clean_boot_verify_nv', ROOT / 'patches/clean_boot/verify.py')     # the half-press harness
CLV = _load('crash_log_verify_nv', ROOT / 'patches/crash_log/verify.py')       # accesses(): the memory operands of a trace
F, B3, BASE = NB.F, NB.B3, NB.BASE
FC, AP = CBV.FC, CBV.AP
NAMES, CRASH, NVP, FORGET = CBV.NAMES, CBV.CRASH, 'NVPROBE.BIN', 'FORGET.BIN'
ALLN = NAMES + (CRASH, NVP, FORGET)
POOLS, K0, blk, where, u32 = CBV.POOLS, CBV.K0, CBV.blk, CBV.where, CBV.u32
STK, SP0, LOGB, PTAB, FILES, ALLOCB, CALLER, TRIG_RET = CBV.STK, CBV.SP0, CBV.LOGB, CBV.PTAB, CBV.FILES, CBV.ALLOCB, CBV.CALLER, CBV.TRIG_RET
KEEP, REGS, CLEAN = CBV.KEEP, CBV.REGS, CBV.CLEAN
FAR2, POKEB = 0x18500000, 0x18510000
RAM, SIZE, SHD, C, U = F.MODE_RAM, F.MODE_SIZE, F.MODE_SHADOW, NB.C, NB.U
RAM_U = RAM + 0x40000000
OFF, MLEN = F.RESERVE, F.M_LEN
BANKS = 0xa26ff940
TOKEN = 0x80000abc
VERSION = ['']
FILES_SEEN = []                           # (case, file bytes, expected verdict) for D
TRACES = []


# ------------------------------------------------------------------ the stubs added to the harness
def lock_unit():
    lg = lambda i, x, y: CBV.LOG.format(logp=LOGB, id=i, x=x, y=y)
    text = f''' .am33_2
 .text
 .global _start
_start:
s_lock:
 movm [d2,d3,a2,a3],(sp)
{lg(11, 'd0', 'd0')} mov ({POKEB:#x}),a2             /* what another task does between our check and the lock: one word, if a case asks */
 cmp 0,a2
 beq 1f
 mov ({POKEB + 4:#x}),d2
 mov d2,(a2)
1:
 mov {TOKEN:#x},d0
 movm (sp),[d2,d3,a2,a3]
 ret [d2],8
s_unlock:
 movm [d2,d3,a2,a3],(sp)
{lg(12, 'd0', 'd0')} clr d0
 movm (sp),[d2,d3,a2,a3]
 ret [d2],8
'''
    code, _, sy, _ = B3.assemble(text, FAR2, {})
    return code, sy


class World(CBV.World):
    def __init__(self, m, spec, unit, lk):
        super().__init__(m, spec, unit)
        self.nv = spec.get('nv_store')
        code, sy = lk
        self.lk = [Region('far2', FAR2, code, 'rx')] + [Region('j_' + k, a, b'\xdc' + struct.pack('<i', sy['s_' + k] - a), 'rx')
                                                        for k, a in (('lock', NB.CPU_LOCK), ('unlock', NB.CPU_UNLOCK))]
        if self.nv:
            sy = {k: int(v, 16) for k, v in self.nv['symbols'].items()}
            self.path[NVP], self.path[FORGET] = sy['nv_path'], sy['nv_fpath']
            lo, hi = (int(x, 16) for x in self.nv['claim'])
            self.nvcode = [Region('nv', lo, m[lo - BASE:hi - BASE], 'rx')]
            self.nvsym = sy
            if any(self.cstr(a) != ('C:\\EP7MOD\\' + n).encode() for n, a in ((NVP, sy['nv_path']), (FORGET, sy['nv_fpath']))):
                raise SystemExit('our file paths')
        else:
            self.nvcode = []

    def data(self, k, present=NAMES, fail=0):
        pt = bytearray(0x200)
        fl = bytearray(0x1000 * len(NAMES))
        for n, name in enumerate(NAMES):
            f = self.files[name]
            fl[0x1000 * n:0x1000 * n + len(f)] = f
            struct.pack_into('<II', pt, 0x100 + 16 * n, FILES + 0x1000 * n, len(f))
        for j, name in enumerate(x for x in ALLN if x in present and x in self.path):     # CRASH / NVPROBE: a handle to write to; FORGET: an empty file
            struct.pack_into('<II', pt, 8 * j, self.path[name], PTAB + 0x100 + 16 * ALLN.index(name))
        return [Region('log', LOGB, struct.pack('<I', LOGB + 16) + bytes(0x7fc), 'rw', True), Region('ptab', PTAB, bytes(pt), 'r'), Region('files', FILES, bytes(fl), 'r'),
                Region('alloc', ALLOCB, struct.pack('<4I', blk(0, k[0]), blk(1, k[1]), blk(2, k[2]), fail), 'rw', True)]

    def log(self, mem):
        lg, out = mem['log'], []
        hname = {PTAB + 0x100 + 16 * n: name for n, name in enumerate(ALLN)}
        pname = {a: n for n, a in self.path.items()}
        for o in range(16, u32(lg, 0) - LOGB, 12):
            i, x, y = struct.unpack_from('<3I', lg, o)
            out.append({1: lambda: ('malloc', x, where(y) if y else None), 2: lambda: ('fopen', pname.get(x) or self.cstr(x).decode(), bool(y)), 3: lambda: ('fseek', hname[x], y),
                        4: lambda: ('ftell', hname[x], y), 5: lambda: ('fread', where(x), y), 6: lambda: ('fclose', hname[x]), 7: lambda: ('free', where(x)),
                        8: lambda: ('sget', x), 9: lambda: ('getter', hex(x), y), 10: lambda: ('fwrite', where(x), y), 11: lambda: ('lock', x), 12: lambda: ('unlock', x)}[i]())
        return out


def bank_obj(ram=RAM, size=SIZE, shadow=SHD, ident=F.MODE_ID, copy=0):
    return struct.pack('<HBBIIIIII', ident, copy, 0, shadow, 0, NB.ROM_LIST, ram, size, 1)


class Mem:
    """The settings memory of one half-press. cached / uncached: the image as each address range reads it; shadow: the copy the
    boot read from flash. writable: which of the 16 marker bytes' two homes may be stored to ('cu', 'c', '' ...); hdr: the
    image's first 16 bytes writable too (for the lock stub's poke)."""

    def __init__(self, cached, uncached=None, shadow=None, *, writable='cu', hdr=False, bankp=F.MODE_OBJ, obj=None, cpu=0, slots=(1, 0, 0), poke=None, obj_at=F.MODE_OBJ):
        self.c, self.u, self.s = bytes(cached), bytes(uncached if uncached is not None else cached), bytes(shadow if shadow is not None else cached)
        self.writable, self.hdr, self.bankp, self.obj, self.cpu, self.slots, self.poke, self.obj_at = writable, hdr, bankp, obj or bank_obj(), cpu, slots, poke, obj_at

    def regions(self):
        def img(tag, base, b, w):
            out, cuts = [], [0, 16, OFF, OFF + MLEN, SIZE]
            for lo, hi in zip(cuts, cuts[1:]):
                rw = (lo == OFF and w) or (lo == 0 and self.hdr and tag == 'bk')
                out.append(Region(f'{tag}_{lo:x}', base + lo, b[lo:hi], 'rw' if rw else 'r', True))
            return out
        tab = bytearray(7 * 28)
        k = (self.obj_at - BANKS) // 28
        tab[28 * k:28 * k + 28] = self.obj
        m, e, lf = self.slots
        pk = self.poke or (0, 0)
        return img('bk', RAM, self.c, 'c' in self.writable) + img('bu', RAM_U, self.u, 'u' in self.writable) + [
            Region('shd', SHD, self.s, 'r'), Region('banks', BANKS, bytes(tab), 'r'),
            Region('bankp', NB.BANKP & ~0x3f, bytes(NB.BANKP & 0x3f) + struct.pack('<I', self.bankp) + bytes(0x3c - (NB.BANKP & 0x3f)), 'r'),
            Region('cpuid', 0x8040, bytes(0x10) + struct.pack('<I', self.cpu) + bytes(12), 'r'),
            Region('slots', NB.SLOT_E & ~0xf, bytes([e, m]) + bytes(14), 'r'), Region('lfail', NB.LFAIL & ~0xf, bytes(8) + struct.pack('<H', lf) + bytes(6), 'r'),
            Region('poke', POKEB, struct.pack('<II', *pk), 'r')]


def image_of(run, tag):
    """The cached ('bk') or uncached ('bu') image after a run."""
    return b''.join(run.mem[f'{tag}_{lo:x}'] for lo in (0, 16, OFF, OFF + MLEN))


def press(w, dram=None, k=K0, *, present=NAMES + (CRASH, NVP), state=0, boot=0, mounted=True, fail=0, rec=None, mem=None, files=None):
    """One half-press through the whole hook chain, as patches/clean_boot/verify.py press(), with the settings memory `mem`
    (None: not mapped at all) and the lock stubs."""
    stk = bytearray(0x2000); struct.pack_into('<I', stk, SP0 - STK + 16, B3.EV_PRESS)
    sv = w.sv
    keep = w.files
    if files:
        w.files = dict(keep, **files)
    try:
        rg = w.code('sec1', 'sec3', 'ls', 'sec6', 'sec9') + w.nvcode + w.stubs + w.lk + w.io + w.data(k, present, fail) + w.heap(dram or {}) + [
            Region('secbits', sv['ep7_secbits'], struct.pack('<I', 0x1ff), 'r'), Region('ms', sv['ep7_ms_a'], struct.pack('<I', 0xf000 if mounted else 0) + bytes(28), 'r'),
            Region('state', 0x622cbcc0, struct.pack('<HHI', 5, state, 0), 'rw', True), Region('boot', AP.BOOT & ~0xf, bytes([boot if i == (AP.BOOT & 0xf) else 0 for i in range(16)]), 'rw', True),
            Region('stack', STK, bytes(stk), 'rw', True), Region('t', TRIG_RET, b'\xcb', 'rx')]
    finally:
        w.files = keep
    if w.rec:
        rg.append(Region('rec', w.rec, rec or bytes(FC.FILE_LEN), 'rw', True))
    if mem:
        rg += mem.regions()
    return CBV.Run(w, execute(rg, dict(REGS, pc=w.sd['sd_hook'], sp=SP0), TRIG_RET, limit=12_000_000, timeout=900))


# ------------------------------------------------------------------ the model: what the layer must find, do and report
def words(b, o, n):
    return struct.unpack_from(f'<{n}I', b, o)


def model(mem, *, forget=False, under_lock=None):
    """-> (file, the 16 bytes cached after, uncached after, action). under_lock: None, 'save' or 'changed' (the lock stub's poke)."""
    c, u, s = mem.c, mem.u, mem.s
    d = bytearray(F.FILE_LEN)
    d[:4] = F.FILE_MAGIC
    struct.pack_into('<I', d, F.O_VERLEN, F.FILE_VERSION | F.FILE_LEN << 16)
    struct.pack_into('<I', d, F.O_CPU, mem.cpu)
    fl = F.F_CPU0 if mem.cpu & 0xffff == 0 else 0
    struct.pack_into('<I', d, F.O_BANK, mem.bankp)
    if mem.bankp == F.MODE_OBJ:
        ident, copy, _, shd0, _, _, ram, size, _ = struct.unpack('<HBBIIIIII', mem.obj)
        struct.pack_into('<3I', d, F.O_BRAM, ram, size, ident | copy << 16)
        if (ram, size, shd0, ident) == (RAM, SIZE, SHD, F.MODE_ID):
            fl |= F.F_BANK
    d[F.O_RHDR:F.O_RHDR + 8] = c[:8]
    d[F.O_SHDR:F.O_SHDR + 8] = s[:8]
    if u32(c, 0) & 0xffff == F.MODE_ID:
        fl |= F.F_ID
    if c[4:8] == s[4:8]:
        fl |= F.F_GEN
    m, e, lf = mem.slots
    struct.pack_into('<I', d, F.O_SLOT, m | e << 8 | lf << 16)
    nz = [o for lo, hi in ((F.TAIL, OFF), (OFF + F.RESERVE_LEN, F.TAIL_END)) for o in range(lo, hi, 4) if c[o:o + 4] != bytes(4)]
    struct.pack_into('<II', d, F.O_TNZ, len(nz), nz[0] if nz else 0)
    fl |= 0 if nz else F.F_TAIL
    res = range(OFF, OFF + F.RESERVE_LEN, 4)
    rnz = sum(c[o:o + 4] != bytes(4) for o in res if o >= OFF + MLEN)
    cu = sum(c[o:o + 4] != u[o:o + 4] for o in res)
    cs = sum(c[o:o + 4] != s[o:o + 4] for o in res)
    struct.pack_into('<3I', d, F.O_RNZ, rnz, cu, cs)
    fl |= (0 if rnz else F.F_REST) | (0 if cu else F.F_CU) | (0 if cs else F.F_CS)
    pre = c[OFF:OFF + MLEN]
    d[F.O_PRE:F.O_PRE + MLEN] = pre
    d[F.O_SHD:F.O_SHD + MLEN] = s[OFF:OFF + MLEN]
    st, cnt = F.marker_state(pre)
    fl |= {'absent': F.F_ABSENT, 'valid': F.F_VALID | F.F_OURS, 'damaged': F.F_OURS, 'foreign': 0}[st]
    fl |= F.F_FORGET if forget else 0
    act, new, c16, u16 = F.A_NONE, None, pre, u[OFF:OFF + MLEN]
    if fl & F.F_ALL == F.F_ALL:
        if forget:
            act, new = (F.A_FORGET_EMPTY, None) if st == 'absent' else (F.A_CLEARED, bytes(MLEN)) if st in ('valid', 'damaged') else (F.A_FOREIGN, None)
        elif st == 'absent' or st == 'valid':
            n = 1 if st == 'absent' else (cnt + 1) & 0xffffffff
            act, new = F.A_WRITTEN, F.marker(n)
            struct.pack_into('<I', d, F.O_NEW, n)
        else:
            act = F.A_FOREIGN if st == 'foreign' else F.A_DAMAGED
    if new is not None:
        fl |= F.F_LOCK
        if under_lock == 'save':
            act = F.A_SAVE
        elif under_lock == 'changed':
            act = F.A_CHANGED
            c16 = pre[:4] + struct.pack('<I', mem.poke[1]) + pre[8:]
        else:
            c16 = u16 = new
            fl |= F.F_READBACK
    struct.pack_into('<3I', d, F.O_POST0, u32(c16, 0), u32(c16, 4), u32(u16, 4))
    struct.pack_into('<I', d, F.O_BUILD, F.build_tag(VERSION[0]))
    struct.pack_into('<I', d, F.O_FLAGS, fl | act << 24)
    struct.pack_into('<I', d, F.O_CRC, zlib.crc32(bytes(d[:F.O_CRC])))
    return bytes(d), c16, u16, act


OURS = lambda forget, locked: ([('malloc', F.FILE_LEN, 'c0b40'), ('fopen', FORGET, forget)] + ([('fclose', FORGET)] if forget else []) + ([('lock', 0), ('unlock', TOKEN)] if locked else [])
                               + [('fopen', NVP, True), ('fwrite', 'c0b40', F.FILE_LEN), ('fclose', NVP), ('free', 'c0b40')])


def check(name, w, mem, *, forget=False, under_lock=None, verdict=None, want_act=None, **kw):
    """A half-press with `mem`: the calls, the file and the 16 bytes at both addresses are the model's; nothing else of the
    settings memory changed (it could not: read-only). -> (problems, run)."""
    present = NAMES + (CRASH, NVP) + ((FORGET,) if forget else ())
    r = press(w, mem=mem, present=present, **kw)
    exp, c16, u16, act = model(mem, forget=forget, under_lock=under_lock)
    bad = []
    if not r.ok:
        return [(name, r.why())], r
    got = r.blocks[(0, 40)][:F.FILE_LEN]
    locked = bool(u32(exp, F.O_FLAGS) & F.F_LOCK)
    if got != exp:
        bad.append((name, 'file', [(o, got[o:o + 4].hex(), exp[o:o + 4].hex()) for o in range(0, F.FILE_LEN, 4) if got[o:o + 4] != exp[o:o + 4]][:4]))
    if r.log[7:7 + len(OURS(forget, locked))] != OURS(forget, locked) or CBV.shape(r.log[:7] + r.log[7 + len(OURS(forget, locked)):]) != CBV.shape(CLEAN):
        bad.append((name, 'calls', r.log[7:17]))
    ci, ui = image_of(r, 'bk'), image_of(r, 'bu')
    wc = mem.c[:OFF] + c16 + mem.c[OFF + MLEN:]
    if mem.poke and mem.poke[0] == RAM + 4:
        wc = wc[:4] + struct.pack('<I', mem.poke[1]) + wc[8:]
    if ci != wc or ui != mem.u[:OFF] + u16 + mem.u[OFF + MLEN:]:
        bad.append((name, 'settings memory', ci[OFF:OFF + MLEN].hex(), ui[OFF:OFF + MLEN].hex()))
    if want_act is not None and act != want_act:
        bad.append((name, 'model action', act, want_act))
    if CBV.loaded(r):
        bad.append((name, 'tables', CBV.loaded(r)))
    FILES_SEEN.append((name, got, verdict or ('go' if u32(exp, F.O_FLAGS) & F.F_ALL == F.F_ALL and act in (F.A_WRITTEN, F.A_CLEARED, F.A_FORGET_EMPTY, F.A_SAVE) else 'stop')))
    return bad, r


# ------------------------------------------------------------------ the stock routines (as the scratch study emu_mode_tail.py)
PRM = (0x6005c2d0, 0x6005f460)
FLASH_OP, WR = 0x6005bc79, 0x18600000


def stock_regions(m, ram, shadow):
    sl = lambda lo, hi, n: Region(n, lo, m[lo - BASE:hi - BASE], 'rx')
    b = bytearray(0x600)
    b[84:112] = bank_obj()
    return [sl(*PRM, 'prm'), sl(0x60022f89, 0x60022fab, 'memcmp'), sl(0x600670bc, 0x60067146, 'alias'), sl(NB.ROM_LIST, 0x600be010, 'moderom'),
            Region('trace', 0x60023079, bytes.fromhex('df0004'), 'rx'), Region('lock', NB.CPU_LOCK, bytes.fromhex('00df8008'), 'rx'),
            Region('flush', 0x60066fc0, bytes.fromhex('dfc010'), 'rx'), Region('unlock', NB.CPU_UNLOCK, bytes.fromhex('df8008'), 'rx'),
            Region('ram', RAM, bytes(ram), 'rw', True), Region('ram_u', RAM_U, bytes(ram), 'rw', False, 'ram'),
            Region('shd', SHD, bytes(shadow), 'rw', True), Region('shd_c', SHD - 0x40000000, bytes(shadow), 'rw', False, 'shd'),
            Region('vars', 0xa2715a80, bytes(0x100), 'rw', True), Region('flags', 0xa2715cb0, bytes(16), 'rw', True), Region('banks', BANKS, bytes(b), 'rw'),
            Region('stack', STK, bytes(0x2000), 'rw')]


def stock_call(m, target, mask, frame, regs, ram, shadow, bp=()):
    code = b'\xdd' + struct.pack('<i', target - WR) + bytes([mask, frame])
    r = dict(d2=0x22334455, d3=0x66778899, a2=0xaabbccdd, a3=0x11223344, sp=SP0, pc=WR)
    r.update(regs)
    res = execute([Region('caller', WR, code, 'rx')] + stock_regions(m, ram, shadow), r, WR + len(code), limit=60_000_000, timeout=600, breakpoints=bp)
    res['mem'] = {x['name']: bytes.fromhex(x['hex']) for x in res['memory']}
    return res


def hsum(b):
    return sum(struct.unpack(f'<{len(b) // 2}H', b)) & 0xffff


def fresh_image(m, gen=41):
    """A valid MODE image as the camera builds one: the ROM defaults (stock builder), id, generation, the stock checksum."""
    r = stock_call(m, 0x6005e309, 0xf0, 0x34, dict(d0=SIZE, a0=RAM, a1=NB.ROM_LIST + 8), bytes(SIZE), bytes(SIZE))
    img = bytearray(r['mem']['ram'])
    cur = u32(r['mem']['vars'], 0xa2715ab8 - 0xa2715a80)
    if r['fault'] or cur != RAM + F.TAIL or any(img[F.TAIL:]):
        raise SystemExit('stock default image')
    struct.pack_into('<HHI', img, 0, F.MODE_ID, 0, gen)
    r = stock_call(m, 0x6005c7e7, 0x20, 0x08, dict(d0=SIZE, a0=RAM), img, bytes(SIZE))
    img = r['mem']['ram']
    if r['fault'] or hsum(img):
        raise SystemExit('stock checksum')
    return img


def save_load(m, ram, shadow):
    """The camera switched off and on: stock prm_bank_save (to its flash call), then stock prm_bank_load of what it would program.
    -> (the image the next power-on has in RAM and in its shadow, problems)."""
    bad = []
    r = stock_call(m, 0x6005c5be, 0xf0, 0x18, dict(a0=BANKS + 84), ram, shadow, bp=(FLASH_OP,))
    g, out = r['registers'], r['mem']['ram']
    if g['pc'] != FLASH_OP or (g['d0'], g['d1'], g['a0'], g['a1']) != (SIZE, 0, RAM_U, SHD):
        bad.append(('save: the flash call', hex(g['pc']), r['fault']))
    if u32(out, 4) != (u32(ram, 4) + 1) & 0xffffffff or hsum(out) or out[8:] != ram[8:]:
        bad.append('save: generation + 1, sum 0, nothing else changed')
    r = stock_call(m, 0x6005c524, 0xb0, 0x14, dict(a0=BANKS + 84), bytes(SIZE), out)
    if r['fault'] or r['registers']['d0'] & 0xffff or r['mem']['ram'] != out:
        bad.append('load: the saved image is not taken whole')
    return out, bad


# ------------------------------------------------------------------ M
def t_round(w):
    bad, n, m = [], 0, w.m
    img0 = fresh_image(m)
    # no save when nothing changed (the compare is the camera's only trigger)
    r = stock_call(m, 0x6005c5be, 0xf0, 0x18, dict(a0=BANKS + 84), img0, img0, bp=(FLASH_OP,))
    n += 1
    if r['registers']['pc'] == FLASH_OP or r['registers']['d0'] & 0xffff:
        bad.append('stock save with nothing changed: it writes')
    cur, steps = img0, []
    for name, forget, act, state in (('first power-on: no marker', False, F.A_WRITTEN, ('valid', 1)), ('second power-on: marker 1 from flash', False, F.A_WRITTEN, ('valid', 2)),
                                     ('FORGET.BIN: marker 2 from flash', True, F.A_CLEARED, ('absent', None)), ('FORGET.BIN again: nothing there', True, F.A_FORGET_EMPTY, ('absent', None))):
        mem = Mem(cur, writable='cu' if act in (F.A_WRITTEN, F.A_CLEARED) else '')
        b, r = check(name, w, mem, forget=forget, want_act=act)
        n += 1
        bad += b
        if b:
            break
        ci, ui = image_of(r, 'bk'), image_of(r, 'bu')
        if ci != ui or F.marker_state(ci[OFF:OFF + MLEN]) != state:
            bad.append((name, 'the two addresses differ after the half-press, or the marker is not', state))
            break
        steps.append((name, F.marker_state(ci[OFF:OFF + MLEN])))
        if ci == cur:                                              # nothing changed: the camera would not save
            continue
        cur, b = save_load(m, ci, cur)
        n += 1
        bad += [(name, x) for x in b]
    return bad, n, steps


# ------------------------------------------------------------------ S (control)
def t_control(w, img0):
    bad = []
    put = w.nvsym['nv_put']
    for name, writable, at, k in (('all read-only', '', C, 0), ('uncached read-only', 'c', U, 4)):
        r = press(w, mem=Mem(img0, writable=writable))
        f = r.fault
        pc = put + 3 + 9 * k                                      # the k-th `mov d0,(abs)` of the run (3 B load + 6 B store each)
        if not f or f['kind'] != 1 or f['map'] != 1 or f['address'] != at or f['pc'] != pc:
            bad.append((name, r.why(), hex(pc)))
    return bad, 2


# ------------------------------------------------------------------ G, Z, B
def live(r):
    """The stack from the final sp up."""
    return r.mem['stack'][r.reg['sp'] - STK:]


def with_bytes(img, at, b):
    return img[:at] + b + img[at + len(b):]


def t_guards(w, img0, img1):
    """img0: a valid image without a marker; img1: one with marker 1 (saved and loaded)."""
    bad, n = [], 0

    def case(name, mem, **kw):
        nonlocal n, bad
        b, r = check(name, w, mem, **kw)
        n += 1
        bad += b
        return r

    g1 = with_bytes(img0, 4, struct.pack('<I', u32(img0, 4) + 1))
    # G
    r = case('G generations differ (a save is running)', Mem(g1, shadow=img0, writable=''), want_act=F.A_NONE)
    if r.ok and any(x[0] in ('lock', 'unlock') for x in r.log):
        bad.append('G: the lock was taken')
    case('G a save starts between the check and the lock', Mem(img0, writable='', hdr=True, poke=(RAM + 4, u32(img0, 4) + 1)), under_lock='save', want_act=F.A_SAVE)
    case('G the same with a marker to raise', Mem(img1, writable='', hdr=True, poke=(RAM + 4, u32(img1, 4) + 1)), under_lock='save', want_act=F.A_SAVE)
    case('G the 16 bytes change between the check and the lock', Mem(img0, writable='c', poke=(C + 4, 0x1234)), under_lock='changed', want_act=F.A_CHANGED)
    case('G FORGET.BIN, a save starts before the lock', Mem(img1, writable='', hdr=True, poke=(RAM + 4, u32(img1, 4) + 1)), forget=True, under_lock='save', want_act=F.A_SAVE)
    # Z
    for name, at in (('just after the records', F.TAIL), ('the word before the reserve', OFF - 4), ('the word after the reserve', OFF + F.RESERVE_LEN), ('the last compared word', F.TAIL_END - 4)):
        x = with_bytes(img0, at, b'\x01\0\0\0')
        case(f'Z a non-zero word in the tail: {name}', Mem(x, writable=''), want_act=F.A_NONE)
        case(f'Z the same, FORGET.BIN: {name}', Mem(with_bytes(img1, at, b'\0\0\x80\0'), writable=''), forget=True, want_act=F.A_NONE)
    case('Z a non-zero word in the reserve after the marker', Mem(with_bytes(img1, OFF + MLEN, b'\0\0\0\x01'), writable=''), want_act=F.A_NONE)
    case('Z the reserve\'s last word non-zero', Mem(with_bytes(img0, OFF + F.RESERVE_LEN - 4, b'\x01\0\0\0'), writable=''), want_act=F.A_NONE)
    foreign = with_bytes(img0, OFF, b'OM3U' + bytes(12))
    case('Z foreign bytes in the 16', Mem(foreign, writable=''), want_act=F.A_FOREIGN)
    case('Z foreign bytes, FORGET.BIN', Mem(foreign, writable=''), forget=True, want_act=F.A_FOREIGN)
    dmg = with_bytes(img1, OFF + 12, b'\xff\xff\xff\xff')
    case('Z a damaged marker is left alone', Mem(dmg, writable=''), want_act=F.A_DAMAGED)
    case('Z a marker of another version is left alone', Mem(with_bytes(img1, OFF + 8, b'\x02\0\0\0'), writable=''), want_act=F.A_DAMAGED)
    case('Z a damaged marker, FORGET.BIN: cleared', Mem(dmg), forget=True, want_act=F.A_CLEARED, verdict='go')
    case('Z counter 0xffffffff wraps', Mem(with_bytes(img0, OFF, F.marker(0xffffffff))), want_act=F.A_WRITTEN)
    case('Z cached != uncached in the 16', Mem(img1, uncached=img0, shadow=img1, writable=''), want_act=F.A_NONE)
    case('Z cached != uncached later in the reserve', Mem(img0, uncached=with_bytes(img0, OFF + 0x800, b'\x01\0\0\0'), writable=''), want_act=F.A_NONE)
    case('Z RAM != shadow in the 16 (a marker not from flash)', Mem(img1, shadow=img0 if u32(img0, 4) == u32(img1, 4) else with_bytes(img0, 4, img1[4:8]), writable=''), want_act=F.A_NONE)
    # B
    case('B the bank pointer is another object: not followed', Mem(img0, writable='', bankp=F.MODE_OBJ + 28, obj_at=F.MODE_OBJ), want_act=F.A_NONE)
    case('B the bank pointer is 0', Mem(img0, writable='', bankp=0), want_act=F.A_NONE)
    case('B the bank object names another RAM', Mem(img0, writable='', obj=bank_obj(ram=RAM + 0x1000)), want_act=F.A_NONE)
    case('B another size', Mem(img0, writable='', obj=bank_obj(size=0x20000)), want_act=F.A_NONE)
    case('B another shadow', Mem(img0, writable='', obj=bank_obj(shadow=SHD + 0x40000)), want_act=F.A_NONE)
    case('B another id', Mem(img0, writable='', obj=bank_obj(ident=67)), want_act=F.A_NONE)
    case('B the image carries another id', Mem(with_bytes(img0, 0, b'\x43\0'), writable=''), want_act=F.A_NONE)
    case('B the half-press runs on CPU 1', Mem(img0, writable='', cpu=1), want_act=F.A_NONE)
    case('B CPU word with a high half only', Mem(img0, cpu=0x10000), want_act=F.A_WRITTEN)
    case('B the camera refused its image at this start (flag only)', Mem(img0, slots=(0, 1, 1)), want_act=F.A_WRITTEN)
    return bad, n


# ------------------------------------------------------------------ N
def t_none(wo, wn):
    """Nothing of ours runs unless BUNDLES.BIN loaded: the settings memory is not mapped at all in these runs."""
    bad, n = [], 0

    def both(name, want_log=None, **kw):
        nonlocal n
        a, b = press(wo, **kw), press(wn, **kw)
        n += 1
        msg = CBV.same(a, b, skip=('stack',))                     # the dead stack below sp differs: NEW's load goes through one more call
        if msg or (want_log is not None and b.log != want_log) or live(a) != live(b):
            bad.append((name, msg, b.log[:5]))
        return a, b

    both('no card (no medium mounted)', [], mounted=False)
    a, b = both('card without BUNDLES.BIN (no EP7MOD folder)', [('malloc', 1024, 'c1b6'), ('fopen', 'BUNDLES.BIN', False), ('free', 'c1b6')], present=())
    f = (CBV.CARD / 'BUNDLES.BIN').read_bytes()
    both('BUNDLES.BIN that fails its check', files={'BUNDLES.BIN': f[:40] + bytes([f[40] ^ 1]) + f[41:]})
    both('no memory for P', [('malloc', 1024, None)], fail=1)
    # no memory for our 128 B: P loads, our malloc is refused, nothing else of ours; the rest of the half-press as BASE
    a, b = press(wo), press(wn, fail=2)
    n += 1
    if not (a.ok and b.ok) or b.log != CLEAN[:7] + [('malloc', F.FILE_LEN, None)] + CLEAN[7:] or CBV.tables(a) != CBV.tables(b) or any(a.reg[k] != b.reg[k] for k in KEEP) \
            or (a.state, a.boot) != (b.state, b.boot) or any(b.blocks[(0, 40)]):
        bad.append(('no memory for our block', a.why(), b.why(), b.log[7:9]))
    return bad, n


# ------------------------------------------------------------------ C
def t_clean(wo, wn, img0):
    bad, n = [], 0
    a = press(wo)
    b_, b = check('C clean power-on', wn, Mem(img0), want_act=F.A_WRITTEN)
    n += 1
    bad += b_
    if not (a.ok and b.ok) or a.log != CLEAN or b.log != CLEAN[:7] + OURS(False, True) + CLEAN[7:] or CBV.tables(a) != CBV.tables(b) or any(a.reg[k] != b.reg[k] for k in KEEP) \
            or (a.state, a.boot) != (b.state, b.boot) or live(a) != live(b) or any(a.mem[x] != b.mem[x] for x in a.mem if re.fullmatch(r'c[12]b\d+', x)):
        bad.append(('clean power-on against BASE', a.why(), b.why(), [k for k in KEEP if a.reg[k] != b.reg[k]]))
    # the half-press after a fault: crash_log writes its file on the same half-press, after ours
    rec = FC.MAGIC_OK + b'\x5c' * (FC.SLOT - 4) + bytes(2 * FC.SLOT)
    wrote = [('malloc', FC.FILE_LEN, 'c2b5'), ('fopen', CRASH, True), ('fwrite', 'c2b5', FC.FILE_LEN), ('fclose', CRASH), ('free', 'c2b5')]
    a = press(wo, rec=rec)
    mem = Mem(img0)
    b = press(wn, rec=rec, mem=mem)
    n += 1
    exp, c16, u16, _ = model(mem)
    ls = ((2, 6), (2, 7), (2, 8))
    if not (a.ok and b.ok) or a.log[:12] != CLEAN[:7] + wrote or b.log != a.log[:7] + OURS(False, True) + a.log[7:] or b.blocks[(0, 40)][:F.FILE_LEN] != exp \
            or CBV.tables(a, *ls) != CBV.tables(b, *ls) or a.mem['rec'] != b.mem['rec'] or a.blocks[(2, 5)] != b.blocks[(2, 5)] or any(a.reg[k] != b.reg[k] for k in KEEP) \
            or image_of(b, 'bk')[OFF:OFF + MLEN] != c16 or image_of(b, 'bu')[OFF:OFF + MLEN] != u16:
        bad.append(('after a fault (crash record in RAM)', a.why(), b.why(), b.log[7:20]))
    return bad, n


# ------------------------------------------------------------------ X
def t_trace(w, img0, img1):
    """The layer by itself (sd_load returns at once, a table is loaded): the first and the last 100,000 instructions traced."""
    bad, acc, cover, total, stores = [], 0, set(), [], set()
    sy = w.nvsym
    lo, hi = sy['nv_load'], sy['nv_path']
    ins = {x: (op, args) for x, op, args in B3.disasm(w.m[lo - BASE:hi - BASE], lo)}
    sec3 = bytearray(w.m[0x605b7180 - BASE:0x605b7800 - BASE])
    o = w.sd['sd_load'] - 0x605b7180
    sec3[o:o + 3] = bytes.fromhex('dff024')                       # fixture: sd_load = ret [d2,d3,a2,a3],36
    p = bytearray(0x840); p[:4] = b'EP7B'
    call = b'\xdd' + struct.pack('<i', lo - CALLER) + bytes([0xf0, 36])
    b_at, f0 = blk(0, 40), SP0 - 36                               # our block; the layer's frame (its sp while it runs)
    for name, img, forget in (('marker written', img0, False), ('marker raised', img1, False), ('marker cleared', img1, True)):
        mem = Mem(img)
        present = (NVP,) + ((FORGET,) if forget else ())
        for tail in (False, True):
            rg = [Region('sec3', 0x605b7180, bytes(sec3), 'rx'), Region('caller', CALLER, call, 'rx')] + w.nvcode + w.stubs + w.lk + w.data(K0, present) + [
                Region('c1b6', blk(1, 6), bytes(p), 'r'), Region('c0b40', b_at, bytes(0xc0), 'rw', True), Region('state', 0x622cbcc0, struct.pack('<HHI', 5, blk(1, 6) - B3.POOL + 1, 0), 'r'),
                Region('stack', STK, bytes(0x2000), 'rw', True)] + mem.regions()
            r = execute(rg, dict(REGS, pc=CALLER, sp=SP0), CALLER + len(call), limit=6_000_000, trace_limit=100000, trace_tail=tail, timeout=600)
            if r['fault'] or r['status'] != 'returned':
                bad.append((name, r['status'], r['fault']))
                continue
            total.append(r['completed'])
            exp = model(mem, forget=forget)[0]
            got = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}['c0b40'][:F.FILE_LEN]
            if got != exp:
                bad.append((name, 'file'))
            for pc, kind, size, addr, _ in CLV.accesses(r['trace'], ins):
                acc += 1
                cover.add(pc)
                if addr % size:
                    bad.append((name, 'unaligned', hex(pc), hex(addr)))
                if kind == 'w':
                    stores.add(addr)
                if kind == 'w' and not (b_at <= addr < b_at + F.FILE_LEN or f0 + 4 <= addr <= f0 + 16 or C <= addr < C + MLEN or U <= addr < U + MLEN):
                    bad.append((name, 'store outside the allowed set', hex(pc), hex(addr)))
            cover |= {row['pc'] for row in r['trace'] if row['pc'] in ins}
    never = sorted(set(ins) - cover)
    if not set(NB.STORES) <= stores:
        bad.append(('the eight stores were not all traced', sorted(hex(x) for x in set(NB.STORES) - stores)))
    return bad, acc, len(cover), len(ins), never, total, len(stores)


# ------------------------------------------------------------------ D
def t_decode():
    bad = []
    for name, f, verdict in FILES_SEEN:
        lines, v = F.decode(f, VERSION[0])
        if v != verdict:
            bad.append((name, v, verdict, lines[-1][:80]))
    cut = FILES_SEEN[0][1]
    if F.decode(cut[:-1])[1] != 'bad file' or F.decode(cut[:60] + bytes([cut[60] ^ 1]) + cut[61:])[1] != 'bad file':
        bad.append('a cut or changed file is not refused')
    return bad, len(FILES_SEEN) + 2


# ------------------------------------------------------------------ P
def t_pkg(new_s, new, pkg, rst, info, disk, old):
    import numpy as np
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
    s = new_s['nv_store']
    site, at, ln = int(s['site'], 16), int(s['code'][0], 16), s['code'][1]
    ours = [(site + 1, 4), (at, ln)]
    diff = [BASE + int(i) for i in np.nonzero(np.frombuffer(old, np.uint8) != np.frombuffer(new, np.uint8))[0]] if len(old) == len(new) else []
    ver = [a for a in diff if not any(a0 <= a < a0 + k for a0, k in ours)]            # the version string differs when BASE is another version
    fv = int(new_s['fw_version']['str_at'], 16)
    stray = [hex(a) for a in ver if not fv <= a < fv + 16]
    stock = BP.STOCK.read_bytes()
    main = [b for b in oc.parse(stock) if b.kind == 0x100][0].payload
    good = bool(good) and not stray and len(old) == len(new) and bool(diff)
    good &= new[site - BASE:site - BASE + 7] == b'\xdd' + struct.pack('<i', int(s['symbols']['nv_load'], 16) - site) + b'\xf0\x24'
    lo, hi = (int(x, 16) for x in s['claim'])
    good &= new[lo - BASE:at - BASE] == main[lo - BASE:at - BASE] and new[at + ln - BASE:hi - BASE] == main[at + ln - BASE:hi - BASE]     # the guards and the rest of the claim are stock
    if disk:
        good &= (disk / 'patched.pkg.bin').read_bytes() == pkg and (disk / 'restore-stock.pkg.bin').read_bytes() == rst
    return good, f'{info["edits"]} edits, {info["changed_payload_bytes"]} B; {len(diff)} B differ from BASE ({len(ver)} of them the version text); stray {stray[:6]}' + ('; package files on disk match' if disk else '')


def main():
    base_s, new_s = (json.loads(Path(p).read_text()) for p in sys.argv[1:3])
    disk = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    if 'nv_store' in base_s or 'nv_store' not in new_s or base_s['fw_version']['value'] != new_s['fw_version']['value']:
        raise SystemExit('BASE must lack the layer, NEW must have it, both built as the same version')
    VERSION[0] = new_s['nv_store']['version']
    stock = NB.STOCK.read_bytes()
    if [tuple(u32(stock, t + 4 * c - BASE) for t in (0x60026df4, 0x60026e34, 0x60026e04)) for c in range(3)] != list(POOLS):
        raise SystemExit('heap pool tables')
    old, *_ = CBV.image(base_s)
    new, pkg, rst, info = CBV.image(new_s)
    if new[PRM[0] - BASE:PRM[1] - BASE] != stock[PRM[0] - BASE:PRM[1] - BASE]:
        raise SystemExit('the settings store\'s code is not stock in this image')
    unit, lk = CBV.stub_unit(), lock_unit()
    wo, wn = World(old, base_s, unit, lk), World(new, new_s, unit, lk)
    ok = True
    bad, n, steps = t_round(wn); ok &= not bad
    print(f"{'PASS' if not bad else 'FAIL'} M round trip with the stock save and load: {n} steps; " + '; '.join(f'{a}: {b[0]}' + (f' {b[1]}' if b[1] else '') for a, b in steps), bad[:4] if bad else '', flush=True)
    img0 = fresh_image(new)
    img1, b = save_load(new, with_bytes(img0, OFF, F.marker(1)), img0)
    bad, n = t_guards(wn, img0, img1); bad += b; ok &= not bad
    print(f"{'PASS' if not bad else 'FAIL'} G Z B guards (save in flight, non-zero bytes, wrong bank object; no store, by read-only memory): {n - len(bad)}/{n}", bad[:4] if bad else '', flush=True)
    bad, n = t_control(wn, img0); ok &= not bad
    print(f"{'PASS' if not bad else 'FAIL'} S control: read-only marker bytes fault at the layer's own store, cached then uncached: {n - len(bad)}/{n}", bad[:4] if bad else '', flush=True)
    bad, n = t_none(wo, wn); ok &= not bad
    print(f"{'PASS' if not bad else 'FAIL'} N no card / no BUNDLES.BIN / bad file / no memory == BASE, settings memory not mapped: {n - len(bad)}/{n}", bad[:4] if bad else '', flush=True)
    bad, n = t_clean(wo, wn, img0); ok &= not bad
    print(f"{'PASS' if not bad else 'FAIL'} C clean power-on and the half-press after a fault against BASE: {n - len(bad)}/{n}", bad[:4] if bad else '', flush=True)
    bad, acc, cov, nins, never, total, nst = t_trace(wn, img0, img1); ok &= not bad and acc > 0
    print(f"{'PASS' if not bad and acc else 'FAIL'} X traced accesses: {acc}, all aligned; stores to {nst} addresses, every one in the block, the frame or the 16 bytes (all eight of those seen); "
          f"{cov}/{nins} instructions of the layer seen ({max(total) if total else 0} run per half-press at most, every one traced)" if total and max(total) <= 200000 else 'X: a run longer than the two traces cover', bad[:4] if bad else '', flush=True)
    if never:
        print('    not reached in the traced runs: ' + ' '.join(hex(a) for a in never[:40]) + (' ...' if len(never) > 40 else ''))
    bad, n = t_decode(); ok &= not bad
    print(f"{'PASS' if not bad else 'FAIL'} D decoder verdicts: {n - len(bad)}/{n}", bad[:4] if bad else '', flush=True)
    good, txt = t_pkg(new_s, new, pkg, rst, info, disk, old); ok &= good
    print(f"{'PASS' if good else 'FAIL'} P anti-brick: {txt}")
    print('ALL PASS' if ok else 'FAILURES')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
