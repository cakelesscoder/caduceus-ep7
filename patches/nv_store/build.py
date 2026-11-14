#!/usr/bin/env python3
"""Settings-memory probe and marker: steps S0 + S1 of docs/INTERNAL_STORAGE.md (looks in the camera's own memory). nv.s.in has
the contract; the file and the marker are tools/ep7_nvprobe.py. Development layer on the v0.33 chain, after clean_boot. Offline.

  .venv/bin/python -I patches/v032/build.py releases/v0.31d/edits.json --out generated/nv_store/edits.json --version 0.34 \\
      --extra grain_g2=patches/grain_g2/build.py --extra halation_h6=patches/halation_h6/build.py \\
      --extra crash_log=patches/crash_log/build.py --extra clean_boot=patches/clean_boot/build.py \\
      --extra nv_store=patches/nv_store/build.py

apply(spec, version) -> spec. Edits:
  - the displacement of `call sd_load,[d2,d3,a2,a3],36` at the head of crash_log's cl_first (4 B, inside the grain_cpu edit)
    -> nv_load, which calls sd_load itself on the same contract;
  - nv_load + the two file paths at CLAIM + 16, in the sec-5 dead `sdk api` handlers (CODE_SPACE_SURVEY section 2).
What the layer may store into the camera's settings image is fixed here and checked on the assembled code: eight `mov d0,(abs)`
to the 16 bytes at MODE image offset 0x3A000, cached and uncached, between its cpu_lock and its cpu_unlock, and nothing else
outside its heap block and its stack frame.
"""
import argparse, copy, importlib.util, json, re, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SRC = 'patches/nv_store'


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


XP = _load('ep7_xp_build_nv', ROOT / 'patches/extras_pages/build.py')
F = _load('ep7_nvprobe_fmt', ROOT / 'tools/ep7_nvprobe.py')
ST, KH, B3 = XP.ST, XP.KH, XP.B3
BASE, STOCK = XP.BASE, XP.STOCK

CLAIM = (0x607d7900, 0x607d8000)          # sec 5, 1792 B of the dead sdk-api handlers; inside a run no outside reference points into
GUARD = 16
AT = CLAIM[0] + GUARD
# ---- the settings store (docs/INTERNAL_STORAGE.md section 2; ATLAS section 3)
BANKP = 0xa2711a9c                        # MODE bank object pointer
ROM_LIST = 0x60096f90                     # MODE records: {u16 id, u16 cksum, u32 gen}, then {u16 key, u16 count, defaults}
SLOT_M, SLOT_E, LFAIL = 0x61b213a1, 0x61b213a0, 0xa2715cb8
C = F.MODE_RAM + F.RESERVE                # the reserve: cached, uncached, and the same bytes of the shadow
U = C + 0x40000000
S = F.MODE_SHADOW + F.RESERVE
STORES = tuple(x + k for x in (C, U) for k in (0, 4, 8, 12))    # every store the layer may make outside its block and its frame
CPU_LOCK, CPU_UNLOCK, FWRITE = 0x6006a922, 0x6006a96b, 0x60635041
CL_OLD = bytes.fromhex('f024')            # cl_first's call: [d2,d3,a2,a3],36 after the d32 displacement
BAD = {'mul', 'mulu', 'div', 'divu', 'ext', 'setlb', 'llt', 'lne', 'leq', 'lra', 'lcc', 'lcs', 'trap', 'rti', 'rets', 'retf', 'calls', 'movm'}

# Stock bytes this layer relies on: (address, bytes, what)
NEED = (
    (0x6005c2f1, '04fcde40f96fa2', 'prm_bank_new: the bank objects start at 0xa26ff940'),
    (0x6005c30e, '44221ca507', 'prm_bank_new: 28 B each, 7 of them'),
    (0x6005db03, 'cdeee72008fc80901a71a2', 'prm_banks_init: 1st bank object (FLASH)'),
    (0x6005db62, 'cd8fe72008fc80941a71a2', 'prm_banks_init: 2nd (BKRAM)'),
    (0x6005dbab, 'cd46e72008fc80981a71a2', 'prm_banks_init: 3rd (EEROM)'),
    (0x6005dc19, 'cdd8e62008fc809c1a71a2', 'prm_banks_init: 4th = MODE, pointer at 0xa2711a9c'),
    (0x6005dc28, 'fcac906f0960', 'MODE: id from the ROM list 0x60096f90'),
    (0x6005dc39, '00fcdd0080a7a2', 'MODE: shadow copy 0 = 0xa2a78000'),
    (0x6005dc6b, 'fcdd00a44e62', 'MODE: RAM image 0x624ea400'),
    (0x6005dc7c, 'fccc00000400', 'MODE: size 0x40000'),
    (0x6005c32b, 'f8340cde0000f83410de0000f81014de0000', 'bank object: ROM +12, RAM +16, size +20'),
    (0x6005c33d, '145450f3d0de0000', 'bank object: shadow copies from +4'),
    (0x6005c326, 'f070de0000', 'bank object: id (u16) at +0'),
    (0x6005c5e6, '9008f16c2208850cf10499', 'prm_bank_save: compare from +8 over size - 12'),
    (0x6005c60d, 'f1eccd02020000f1ec5804cdcf012008', 'prm_bank_save: generation + 1 (RAM +4) before the checksum'),
    (0x6005c811, '50704060de0000', 'generation: the word at image +4'),
    (0x6005c635, '8cddccaa00008004f1e058040499cd36f6f014', 'prm_bank_save: flash source = the uncached RAM image, destination = the shadow'),
    (0x6005eadf, '9687821f93f1dcdd1c8600008004f1e0f8e207aa04c808aa02c80bca1257f3eff3ecca11f1d8eff4cff4ccca08f1d8f44ff44cdff014',
     'the stock property store: each value to the cached address (a3), then to its uncached alias (a0 = to_uncached)'),
    (0x600216fd, 'fca9a113b261', 'flash layer: the MODE slot byte 0x61b213a1'),
    (0x6002167b, 'fc86a013b261', 'flash layer: the EEROM slot byte 0x61b213a0'),
    (0x6005f089, 'fcacb85c71a204fc87b85c71a2de0000', 'MODE load-failed flag 0xa2715cb8'),
    (0x60020117, 'fcdce8e80260fcdd20e00260fcdee00fb261', 'boot data copy 0x6002e020..0x6002e8e8 -> 0x61b20fe0 (the slot tables)'),
    (0x6002e3a8, '000004000080a7a200002440', 'MODE slot 0: size, shadow, flash 0x40240000'),
    (0x6002e3c4, '000004000080a7a200002840', 'MODE slot 1: flash 0x40280000'),
    (0x6006a922, 'fca5fc06f08f82', 'cpu_lock: d0 in, token out'),
    (0x6006a968, 'df8008', 'cpu_lock: ret [d2],8'),
    (0x6006a96b, '82fca44000f08f', 'cpu_unlock: token in d0'),
    (0x6006a9a7, 'df8008', 'cpu_unlock: ret [d2],8'),
    (0x60022782, 'fac88000c505', 'malloc: <= 128 B is class 0'),
    (0x600227b1, 'df0004', 'malloc: ret [],4'),
    (0x60022801, 'df0004', 'free: ret [],4'),
    (0x60634fbc, '00cd9b13f02cdf0004', 'fopen: ret [],4'),
    (0x6063503e, 'dfb010', 'fclose: ret [d2,a2,a3],16'),
    (0x60635041, '4704878293', 'fwrite: a1 handle, d1 count, d0 size, a0 buffer'),
    (0x606350cc, 'dff018', 'fwrite: ret [d2,d3,a2,a3],24'),
)


def u32(im, a):
    return struct.unpack_from('<I', im, a - BASE)[0]


def walk_tail(stock):
    """The MODE ROM list, packed as prm_bank_fill_defaults 0x6005e309 packs it -> image offset of the first unused byte."""
    p, cur = ROM_LIST + 8, 8
    if struct.unpack_from('<H', stock, ROM_LIST - BASE)[0] != F.MODE_ID:
        raise SystemExit('MODE ROM list: id')
    while True:
        key, cnt = struct.unpack_from('<HH', stock, p - BASE)
        if key == 0:
            return cur
        w = key & 3 or 4
        cur = ((cur + w - 1) & -w) + w * cnt                     # each record aligned to its width (the image itself is 4-aligned)
        if cur > F.MODE_SIZE - 4:
            raise SystemExit('MODE ROM list does not fit')
        p = (p + 4 + w * cnt + 3) & ~3


def check_stock(stock):
    for a, h, what in NEED:
        if stock[a - BASE:a - BASE + len(h) // 2].hex() != h:
            raise SystemExit(f'{a:#x}: stock bytes differ ({what})')
    B3.pool_check(stock)
    if walk_tail(stock) != F.TAIL:
        raise SystemExit(f'the MODE records end at {walk_tail(stock):#x}, not {F.TAIL:#x}')
    if not (F.TAIL < F.RESERVE and F.RESERVE + F.RESERVE_LEN < F.TAIL_END == F.MODE_SIZE - 4 and F.TAIL % 4 == 0 and F.RESERVE % 4 == 0 and F.RESERVE_LEN % 4 == 0):
        raise SystemExit('reserve / tail constants')
    if F.MODE_OBJ != 0xa26ff940 + 3 * 28 or F.FILE_LEN > 128 or F.FILE_LEN % 4 or F.O_STAGE + F.M_LEN > F.O_NEW or F.M_LEN != 16:
        raise SystemExit('format constants')


def check_claim(spec, stock, im):
    """As patches/halation_h6: inside the dead handlers, stock, clear of edits and of the double constant's alias, the shell
    cut, and no reference from outside the dead code (abs32 on four aliases, rel calls and jumps)."""
    lo5, hi5, off5 = KH.sec(stock, 5)
    if not (lo5 <= CLAIM[0] and CLAIM[1] <= hi5 and KH.DEAD[1][0] <= CLAIM[0] and CLAIM[1] <= KH.DEAD[1][1]):
        raise SystemExit('claim not inside the dead handler range of section 5')
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a, n = int(e['addr'], 16), len(e['new']) // 2
            if a < CLAIM[1] and CLAIM[0] < a + n:
                raise SystemExit(f'claim overlaps edit {e["addr"]}')
    for k, v in spec.items():
        if isinstance(v, dict) and k != 'nv_store' and isinstance(v.get('claim'), list) and len(v['claim']) == 2:
            try:
                a, b = (int(x, 16) for x in v['claim'])
            except (TypeError, ValueError):
                continue
            if a < CLAIM[1] and CLAIM[0] < b:
                raise SystemExit(f'claim overlaps {k}\'s {v["claim"]}')
    if im[CLAIM[0] - BASE:CLAIM[1] - BASE] != stock[CLAIM[0] - BASE:CLAIM[1] - BASE]:
        raise SystemExit('claim not stock')
    if CLAIM[0] <= (KH.DOUBLE_K - off5) & 0xffffffff < CLAIM[1]:
        raise SystemExit('the 0x40e4ab40 double constant aliases into the claim')
    for w, v in KH.SUBCMD.items():
        if u32(im, w) == v:
            raise SystemExit(f'sdk sub-command word {w:#x} still stock: apply extras_pages first')
    KH.pin_fp(stock)
    KH.FALSE_POS.update(XP.PINS)
    bad = KH.scan(im, CLAIM[0], CLAIM[1], off5, KH.DEAD)
    if bad:
        raise SystemExit(f'reference into the claim: {[(k, hex(a)) for k, a in bad[:6]]} ({len(bad)})')


def check_site(spec, im):
    """cl_first starts `call sd_load,[d2,d3,a2,a3],36` (d32) and nothing else of it reaches sd_load. -> (site, sd, sv)."""
    for k in ('crash_log', 'clean_boot', 'sd_bundles_v3', 'look_editor'):
        if k not in spec:
            raise SystemExit(f'needs {k} (the v0.33 chain with crash_log and clean_boot)')
    sd = {k: int(v, 16) for k, v in spec['sd_bundles_v3']['symbols'].items()}
    sv = {k: int(v, 16) for k, v in spec['sd_bundles_v3']['services'].items()}
    cl = {k: int(v, 16) for k, v in spec['crash_log']['symbols'].items()}
    site = cl['cl_first']
    if im[site - BASE] != 0xdd or site + struct.unpack_from('<i', im, site + 1 - BASE)[0] != sd['sd_load'] or im[site + 5 - BASE:site + 7 - BASE] != CL_OLD:
        raise SystemExit('cl_first does not start with call sd_load,[d2,d3,a2,a3],36')
    c2 = int(spec['crash_log']['c2_site'], 16)
    if im[c2 - BASE] != 0xdc or c2 + struct.unpack_from('<i', im, c2 + 1 - BASE)[0] != site or c2 != sd['sd_gout'] - 5:
        raise SystemExit('sd_go does not end in jmp cl_first')
    if im[sd['sd_out'] - BASE:sd['sd_out'] - BASE + 3] != bytes.fromhex('dff024'):
        raise SystemExit('sd_load does not end in ret [d2,d3,a2,a3],36')
    if B3.STATE != int(spec['sd_bundles_v3']['state'], 16) or B3.LIM != int(spec['sd_bundles_v3']['lim'], 16) or int(spec['look_editor']['stock']['ep7_fwrite'], 16) != FWRITE:
        raise SystemExit('loader constants')
    return site, sd, sv


def sub(version):
    """nv.s.in's fields, from the format in tools/ep7_nvprobe.py."""
    off = {k.lower(): v for k, v in vars(F).items() if k.startswith('O_') and isinstance(v, int)}
    bits = {k.lower(): hex(v) for k, v in vars(F).items() if k.startswith('F_') and isinstance(v, int)}
    act = {k.lower(): v for k, v in vars(F).items() if k.startswith('A_') and isinstance(v, int)}
    if max(off.values()) + 16 > 127 + 16 or max(act.values()) > 255:
        raise SystemExit('displacements')
    return dict(off, **bits, **act, ram=hex(F.MODE_RAM), shadow=hex(F.MODE_SHADOW), size=hex(F.MODE_SIZE), mode_id=F.MODE_ID, mode_obj=hex(F.MODE_OBJ), bankp=hex(BANKP),
                c=hex(C), c_end=hex(C + F.RESERVE_LEN), u=hex(U), s=hex(S), tail_lo=hex(F.MODE_RAM + F.TAIL), tail_hi=hex(F.MODE_RAM + F.TAIL_END),
                slot_m=hex(SLOT_M), slot_e=hex(SLOT_E), lfail=hex(LFAIL), state=hex(B3.STATE), lim=hex(B3.LIM), pool=hex(B3.POOL), bmagic=hex(B3.MAGIC),
                file_len=F.FILE_LEN, file_words=F.FILE_LEN // 4, file_magic=hex(struct.unpack('<I', F.FILE_MAGIC)[0]), verlen=hex(F.FILE_VERSION | F.FILE_LEN << 16),
                m_magic=hex(struct.unpack('<I', F.M_MAGIC)[0]), m_version=F.M_VERSION, m_len=F.M_LEN, build=hex(F.build_tag(version)))


def build_code(syms, version):
    code, lst, sy, _ = B3.assemble(B3.subst((HERE / 'nv.s.in').read_text(), sub(version)), AT, syms)
    if sy['nv_load'] != AT or sy['nv_end'] != AT + len(code) or AT + len(code) > CLAIM[1] - GUARD:
        raise SystemExit(f'layout: {len(code)} B')
    ins = B3.disasm(code, AT, sy['nv_path'])
    if any(op.startswith('.') or op == '(bad)' or op in BAD for _, op, _ in ins) or any(code[a - AT] == 0xfb for a, _, _ in ins):
        raise SystemExit('undecodable or forbidden instruction, or an fb-prefixed form')
    if code[sy['nv_path'] - AT:] != b'C:\\EP7MOD\\NVPROBE.BIN\0C:\\EP7MOD\\FORGET.BIN\0w\0r\0':
        raise SystemExit('strings')
    # one way out, sd_load's own return; every branch stays inside the code
    if [(op, args) for _, op, args in ins if op == 'ret'] != [('ret', '[d2,d3,a2,a3],36')] or ins[-1][1] != 'ret':
        raise SystemExit('not ending on its one ret [d2,d3,a2,a3],36')
    for a, op, args in ins:
        for t in re.findall(r'0x([0-9a-f]{8})', args):
            if (op[0] == 'b' or op == 'jmp') and not AT <= int(t, 16) < sy['nv_path']:
                raise SystemExit(f'branch out at {a:#x}')
        if op == 'jmp' and not args.startswith('0x'):
            raise SystemExit(f'indirect jump at {a:#x}')
    # the calls, in address order
    calls = [(args.split(',')[0], args.split(',', 1)[1]) for _, op, args in ins if op == 'call']
    want = [(hex(syms[k]), fr) for k, fr in (('ep7_sd_load', '[d2,d3,a2,a3],36'), ('ep7_malloc', '[],4'), ('ep7_sd_crc', '[d2,d3],12'), ('ep7_fopen', '[],4'), ('ep7_fclose', '[d2,a2,a3],16'),
                                              ('ep7_sd_crc', '[d2,d3],12'), ('ep7_cpu_lock', '[d2],8'), ('ep7_cpu_unlock', '[d2],8'), ('ep7_sd_crc', '[d2,d3],12'), ('ep7_fopen', '[],4'),
                                              ('ep7_fwrite', '[d2,d3,a2,a3],24'), ('ep7_fclose', '[d2,a2,a3],16'), ('ep7_free', '[],4'))]
    if calls != want:
        raise SystemExit(f'calls {calls}')
    # ---- the stores. Absolute: exactly the eight, in order, one straight run `mov (k,a2),d0; mov d0,(abs)` between the lock and
    # the unlock, entered only from above (no label inside but nv_put itself)
    st = B3.store_audit(ins)
    ab = [(a, txt, t) for a, txt, kd, t in st if kd == 'abs']
    if [(txt, t) for _, txt, t in ab] != [(f'mov d0,({t:#x})', t) for t in STORES]:
        raise SystemExit(f'absolute stores: {[(txt, hex(t)) for _, txt, t in ab]}')
    run = [x for x in ins if sy['nv_put'] <= x[0] < sy['nv_put_end']]
    exp = [x for k in range(8) for x in (('mov', f'({F.O_STAGE + 4 * (k % 4)},a2),d0'), ('mov', f'd0,({STORES[k]:#x})'))]
    if [(op, args) for _, op, args in run] != exp:
        raise SystemExit(f'the store run is not the reviewed sequence: {run}')
    lock = next(a for a, op, args in ins if op == 'call' and args.startswith(hex(syms['ep7_cpu_lock'])))
    unlock = next(a for a, op, args in ins if op == 'call' and args.startswith(hex(syms['ep7_cpu_unlock'])))
    if not lock < sy['nv_put'] < sy['nv_put_end'] <= sy['nv_unlock'] < unlock:
        raise SystemExit('the stores are not between cpu_lock and cpu_unlock')
    locked = [x for x in ins if lock < x[0] < unlock]
    if any(op == 'call' for _, op, _ in locked):
        raise SystemExit('a call inside the locked part')
    for a, op, args in ins:                                       # into the locked part only through the lock call; into the run only from its top
        for t in re.findall(r'0x([0-9a-f]{8})', args):
            if (op[0] == 'b' or op == 'jmp') and lock < int(t, 16) <= unlock and not lock < a < unlock:
                raise SystemExit(f'branch into the locked part from {a:#x}')
            if (op[0] == 'b' or op == 'jmp') and sy['nv_put'] < int(t, 16) < sy['nv_put_end']:
                raise SystemExit(f'branch into the store run from {a:#x}')
    # the two tests that guard the run sit in the locked part before it: the generations, then the 16 bytes at both addresses
    head = [(op, args) for a, op, args in ins if lock < a < sy['nv_put']]
    gen = [('mov', f'({F.MODE_RAM + 4:#x}),d0'), ('mov', f'({F.MODE_SHADOW + 4:#x}),d1'), ('cmp', 'd1,d0')]
    if not any(head[i:i + 3] == gen for i in range(len(head))) or [args for op, args in head if op == 'mov' and args.startswith('(0x')][2:] != [f'({x + k:#x}),d0' for k in (0, 4, 8, 12) for x in (C, U)]:
        raise SystemExit('the locked tests are not the reviewed ones')
    # everything else: the heap block (through a2 with a displacement inside it, a0 in the clear loop, a1 in COPY4) and the frame
    for a, txt, kd, _ in st:
        if kd == 'abs':
            continue
        m = re.fullmatch(r'mov (d[0-3]|a0),\((\d+),a2\)', txt)
        if not (kd == 'sp' and re.fullmatch(r'mov (d[01]|a[01]),\((4|8|12|16),sp\)', txt)
                or kd == 'ind' and (txt in ('mov d0,(a0)', 'mov d0,(a1)', 'mov d0,(a2)') or m and int(m.group(2)) + 4 <= F.FILE_LEN)):
            raise SystemExit(f'store at {a:#x}: {txt} ({kd})')
    if sum(txt == 'mov d0,(a0)' for _, txt, _, _ in st) != 1 or sum(txt == 'mov d0,(a1)' for _, txt, _, _ in st) != 2:
        raise SystemExit('the clear loop and the two COPY4 are not the only indirect stores through a0 / a1')
    if any('sp' in args and not re.fullmatch(r'((d[01]|a[01]),\((4|8|12|16),sp\)|\((4|8|12|16),sp\),(d[01]|a[01]))', args) for _, op, args in ins if op != 'ret'):
        raise SystemExit('stack use beyond the four saved results')
    return code, sy, lst


def put(spec, stock, addr, old, new, why):
    """Into the edit that covers addr, as patches/crash_log put()."""
    im = ST.img_of(spec, stock)
    if im[addr - BASE:addr - BASE + len(old)] != old:
        raise SystemExit(f'{addr:#x}: {im[addr - BASE:addr - BASE + len(old)].hex()} != {old.hex()} ({why})')
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a, n = int(e['addr'], 16), len(e['new']) // 2
            if a <= addr and addr + len(new) <= a + n:
                b = bytearray.fromhex(e['new']); b[addr - a:addr - a + len(new)] = new; e['new'] = b.hex()
                e['why'] += f' [nv_store: {why}]'
                return
            if a < addr + len(new) and addr < a + n:
                raise SystemExit(f'{addr:#x}: straddles edit {e["addr"]}')
    raise SystemExit(f'{addr:#x}: no edit holds it')


def symbols(spec, sd, sv):
    return dict(ep7_sd_load=sd['sd_load'], ep7_sd_crc=sd['sd_crc'], ep7_malloc=sv['ep7_malloc'], ep7_free=sv['ep7_free'], ep7_fopen=sv['ep7_fopen'],
                ep7_fclose=sv['ep7_fclose'], ep7_fwrite=FWRITE, ep7_cpu_lock=CPU_LOCK, ep7_cpu_unlock=CPU_UNLOCK)


def apply(spec, version='0.34'):
    stock = STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    if 'nv_store' in spec:
        raise SystemExit('nv_store already applied')
    check_stock(stock)
    im = ST.img_of(spec, stock)
    site, sd, sv = check_site(spec, im)
    check_claim(spec, stock, im)
    crc = B3.disasm(im[sd['sd_crc'] - BASE:sd['sd_path'] - BASE], sd['sd_crc'])[:12]
    if [(op, args) for _, op, args in crc][:5] != [('movbu', '(a0),d2'), ('xor', 'd2,d0'), ('mov', '8,d3'), ('btst', '1,d0'), ('beq', hex(sd['sd_b0']))] \
            or ('xor', '-306674912,d0') not in [(op, args) for _, op, args in crc] or not KH.sec(stock, 3)[0] <= sd['sd_crc'] < KH.sec(stock, 3)[1]:
        raise SystemExit('sd_crc is not the loader\'s CRC routine (a0 data, d0 running CRC, d1 length; ret [d2,d3],12)')
    code, sy, lst = build_code(symbols(spec, sd, sv), version)
    spec['edits'].append(dict(kind='0x100', addr=hex(AT), expect=stock[AT - BASE:AT - BASE + len(code)].hex(), new=code.hex(), source=SRC,
                              why=f'nv_store {version}: nv_load ({len(code)} B, sec-5 dead sdk-api handlers, claim {CLAIM[0]:#x}..{CLAIM[1]:#x}): '
                                  f'settings-memory probe (EP7MOD/NVPROBE.BIN) and the 16-byte marker at MODE image offset {F.RESERVE:#x}'))
    put(spec, stock, site + 1, struct.pack('<i', sd['sd_load'] - site), struct.pack('<i', sy['nv_load'] - site),
        'cl_first: call sd_load -> call nv_load (calls sd_load, then the probe and the marker)')
    spec['nv_store'] = dict(built_by=SRC, version=version, stage='S0 + S1 (docs/INTERNAL_STORAGE.md section 4)', build_tag=hex(F.build_tag(version)),
                            claim=[hex(CLAIM[0]), hex(CLAIM[1])], code=[hex(AT), len(code)], site=hex(site), file='EP7MOD/NVPROBE.BIN', file_len=F.FILE_LEN,
                            forget='EP7MOD/FORGET.BIN', marker=dict(image_offset=hex(F.RESERVE), cached=hex(C), uncached=hex(U), len=F.M_LEN, magic=F.M_MAGIC.decode()),
                            reserve=[hex(F.RESERVE), hex(F.RESERVE + F.RESERVE_LEN)], stores=[hex(x) for x in STORES],
                            reads=dict(bank_pointer=hex(BANKP), bank_object=hex(F.MODE_OBJ), ram=hex(F.MODE_RAM), shadow=hex(F.MODE_SHADOW), slots=[hex(SLOT_M), hex(SLOT_E)], load_failed=hex(LFAIL)),
                            symbols={k: hex(v) for k, v in sy.items() if k.startswith('nv_')})
    return spec


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--version', default='0.34')
    ap.add_argument('--listing', type=Path)
    a = ap.parse_args()
    spec = apply(json.loads(a.spec.read_text()), a.version)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(spec, indent=1))
    if a.listing:
        sd = {k: int(v, 16) for k, v in spec['sd_bundles_v3']['symbols'].items()}
        sv = {k: int(v, 16) for k, v in spec['sd_bundles_v3']['services'].items()}
        a.listing.write_text(build_code(symbols(spec, sd, sv), a.version)[2])
    print(json.dumps({k: v for k, v in spec['nv_store'].items() if k != 'symbols'}))
