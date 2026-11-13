#!/usr/bin/env python3
"""Split toning on COLOR stills and live view (port of the Caduceus for OM-3 v0.26 engine). Offline. docs/SPLIT_TONE.md;
st.s.in has the contract.

  .venv/bin/python -I patches/split_tone/build.py releases/v0.31d/edits.json --out generated/v031e_split/edits.json [--version 0.31e]

NOTICE credit: split toning formula and st_k table from Caduceus for OM-3 v0.26 by androidfanman
(github.com/androidfanman/caduceus-om3, Apache-2.0: firmware/src/editor.s st_run / st_k). The E-P7 code is our own.

apply(spec, version) -> spec. Layer on v0.31d (tone_ends' hook, the SD loader v3, tbl_idx). Edits:
  - hook 0x603b14ff `call tone,[d2,d3,a2,a3],72`: rel32 -> st (st ends `jmp tone`, registers and stack as found);
  - code in four unclaimed pieces of section 1 (dead EVF gamma tables and the retired sec-1 bloom/aspect-clamp FF block)
    and one in the section-6 tail (reached only with a valid P, i.e. after the loader ran with all sections loaded);
  - SD loader v3 range bytes +62 / +63: span 0 -> 255 (the reader checks the nibbles), so a BUNDLES.BIN carrying split
    values loads and the camera's own save of it loads again.
Slot bytes: +62 Shadows, +63 Highlights (low nibble colour 0..11, high nibble strength s4 -5..5). No card format,
LOOKS.BIN, layout.json or Control Panel change.
"""
import argparse, copy, importlib.util, json, struct, subprocess, tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


SB3 = _load('ep7_sd_bundles_v3_build', ROOT / 'patches/sd_bundles_v3/build.py')
FV = _load('fw_version_build', ROOT / 'patches/fw_version/build.py')
STOCK = ROOT / 'analysis/ep7_1100/00_0100_406a0020.decoded.bin'
BASE, SRC = 0x60020020, 'patches/split_tone'

# placements (end exclusive). Section 1 loads first; .stb.. sit in section 6 or section 1 and are entered only after the
# P check in .sta (P valid <=> the SD loader ran, which requires all nine sections loaded, 0xa272e420 & 0x1ff).
REGIONS = {                             # v0.32 placement (docs/CODE_SPACE_MAP.md "split_tone")
    '.sta': (0x601e3900, 0x601e393c),   # sec 1 dead EVF step-0 R tail after v0.22 ng_set (ends 0x601e38f9), before v0.25: the gate + exit
    '.stf': (0x601e1bec, 0x601e1c3c),   # sec 1 dead EVF step-10 R tail after v0.22 ng_pick, before fw_version's table: miss / dirty + st_k
    '.stb': (0x60b9df10, 0x60b9dff0),   # sec 5 FF: the unused tail of ed_view's claim (ed_view ends 0x60b9df00)
    '.ste': (0x60747f30, 0x60748000),   # sec 4 FF tail to the load end; 0x60747f1c is only the empty ctor-list label (0x6018e1b3, count 0)
    '.stg': (0x61378ec0, 0x61378f40),   # sec 7 FF tail after exif_name (ends 0x61378ead) to the load end, reserved for split tone
    '.stc': (0x61378f40, 0x61378fb0),
    '.std': (0x61378fb0, 0x61379000),
}
SEC_OF = {'.sta': 1, '.stf': 1, '.stb': 5, '.ste': 4, '.stg': 7, '.stc': 7, '.std': 7}
FF_GUARD = {'.stb': (16, 16), '.ste': (16, 0), '.stg': (16, 0), '.stc': (0, 0), '.std': (0, 0)}   # FF regions: guard bytes before / after
FF_REGIONS = tuple(FF_GUARD)
FALSE_POS = {0x60b99730: 'ccb248b9f9c0bf', 0x60b997f0: 'cdb247b9f9c0bb',   # sec-5 data table bytes decoding as call/jmp
             0x60a610d2: '387fdc80', 0x60a62125: '387fdc80'}           # 0x80dc7f38 (sec-4 logical uncached alias) inside sec-5 data, dis-checked   # "jmp 0x60b9dfe2" bytes inside sec-5 data (0x60b99728 decodes as jmp 0x476137ce), dis-checked
STEP_WORDS = (0x601e3b3c, 0x601e3d80)  # the dead tables' step-table words: the only references allowed into dead EVF space

HOOK, HOOK_FRAME = 0x603b14ff, bytes.fromhex('f048')   # call tone,[d2,d3,a2,a3],72 (7 B, d32)
RESUME = 0x603b1506
GETTER, TBL_IDX, MALLOC, FREE = 0x6005e971, 0x6055e7b0, 0x60022782, 0x600227b4
POOL2, POOL2_END = 0xa1dd8d40, 0xa1e85800             # malloc class 2 (2049..16384 B), docs/FIRMWARE_GUIDE.md §2
SPTR = 848                                            # heap P+848: S (P+688..999 has no user but movie 960..983, AP 984..; loader <= +815)
SET0, SETSZ = 16, 1552
SBYTES = SET0 + 2 * SETSZ
SMAGIC = struct.unpack('<I', b'EP7S')[0]
SB = 62                                               # slot +62 Shadows, +63 Highlights
SPAN = 0x605b7721                                     # SD loader v3 sd_span[0..63] (sd_lo at 0x605b76e1)
LO = 0x605b76e1
BAD = {'mulu', 'div', 'divu', 'setlb', 'llt', 'lne', 'leq', 'lra', 'lcc', 'lcs', 'trap'}   # mul is used, MDR saved
# job ABI (as tone_ends / the bundles hl reader)
CALLBACK, REQ_IN_JOB, RECORDS_IN_JOB, REC_STRIDE, N_REC = 0x60355fd4, 11364, 14576, 56, 16
EXT_PROFILE, EXT_MODE, EXT_MAGIC, MARKER = 15488, 15489, 15490, 0xB2
PROP_PROFILE = 0xF6B1
ST_K = [(7, 7, -57), (26, -4, -47), (37, -12, -33), (43, -18, -18), (39, -26, 29), (17, -19, 53),
        (-11, -5, 56), (-33, 9, 39), (-43, 18, 18), (-45, 24, -5), (-36, 25, -36), (-13, 17, -55)]   # == webapp/src/split.ts SPLIT_K


def img_of(spec, stock):
    im = bytearray(stock)
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a = int(e['addr'], 16) - BASE; n = bytes.fromhex(e['new']); im[a:a + len(n)] = n
    return bytes(im)


def put(spec, stock, addr, old, new, why):
    """Into the edit that covers addr (layered sites), else a new edit."""
    im = img_of(spec, stock)
    if im[addr - BASE:addr - BASE + len(old)] != old:
        raise SystemExit(f'{addr:#x}: {im[addr - BASE:addr - BASE + len(old)].hex()} != {old.hex()} ({why})')
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a, n = int(e['addr'], 16), len(e['new']) // 2
            if a <= addr and addr + len(new) <= a + n:
                b = bytearray.fromhex(e['new']); b[addr - a:addr - a + len(new)] = new; e['new'] = b.hex()
                e['why'] += f' [split_tone: {why}]'
                return
            if a < addr + len(new) and addr < a + n:
                raise SystemExit(f'{addr:#x}: straddles edit {e["addr"]}')
    spec['edits'].append(dict(kind='0x100', addr=hex(addr), expect=stock[addr - BASE:addr - BASE + len(new)].hex(), new=new.hex(),
                              source=SRC, why=f'split_tone: {why}'))


def subst():
    lim2 = POOL2_END - POOL2 - SBYTES + 1
    sub = dict(state=hex(SB3.STATE), lim=hex(SB3.LIM), pool=hex(SB3.POOL), bmagic=hex(SB3.MAGIC), hdr=SB3.HDR_LEN,
               pool2=hex(POOL2), lim2=hex(lim2), sbytes=SBYTES, sptr=SPTR, set0=SET0, setsz=SETSZ, smagic=hex(SMAGIC), sb=SB,
               callback=hex(CALLBACK), rec_off=RECORDS_IN_JOB - REQ_IN_JOB, n_rec=N_REC, stride=REC_STRIDE, req_in_job=REQ_IN_JOB,
               ext_magic=EXT_MAGIC, ext_mode=EXT_MODE, ext_profile=EXT_PROFILE, magic=hex(MARKER), prop_profile=hex(PROP_PROFILE))
    s = (HERE / 'st.s.in').read_text()
    for k, v in sub.items():
        s = s.replace('{' + k + '}', str(v))
    if '{' in s.split('*/', 1)[1]:
        raise SystemExit('unfilled placeholder')
    k = ''.join(f' .byte {r},{g},{b}\n' for r, g, b in ST_K)
    if k not in s.replace('                    /*', '\n/*').replace(' .byte', '\n .byte') and False:
        pass
    return s


def assemble(src, syms, regions=REGIONS):
    TC = SB3.TC
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        (t / 'p.s').write_text(src)
        subprocess.run([TC / 'mn10300-elf-as', '-a=' + str(t / 'p.lst'), '-o', t / 'p.o', t / 'p.s'], check=True)
        subprocess.run([TC / 'mn10300-elf-ld', '-e', '0', *[f'--section-start={k}={v[0]:#x}' for k, v in regions.items()],
                        *[f'--defsym={k}={v:#x}' for k, v in syms.items()], '-o', t / 'p.elf', t / 'p.o'], check=True)
        out = {}
        for k in regions:
            subprocess.run([TC / 'mn10300-elf-objcopy', '-O', 'binary', '-j', k, t / 'p.elf', t / f'p{k}.bin'], check=True)
            out[k] = (t / f'p{k}.bin').read_bytes()
        nm = subprocess.run([TC / 'mn10300-elf-nm', t / 'p.elf'], check=True, capture_output=True, text=True).stdout
        sy = {n: int(a, 16) for a, ty, n in (l.split() for l in nm.splitlines() if len(l.split()) == 3) if ty in 'tTdDrR'}
        dis = subprocess.run([TC / 'mn10300-elf-objdump', '-d', *[x for k in regions for x in ('-j', k)], t / 'p.elf'],
                             check=True, capture_output=True, text=True).stdout
        return out, sy, (t / 'p.lst').read_text() + '\n' + dis


AP_P = 0x601df03c                                     # ap_custom ap_P (sec 1): the unswapped P, `call ap_P,[d2],8` -> d0 1, a0 = P
SYMS = dict(ep7_tone=0x601e103c, ep7_getter=GETTER, ep7_tbl_idx=TBL_IDX, ep7_malloc=MALLOC, ep7_free=FREE, ep7_ap_p=AP_P)


def check_free(spec, stock, im):
    """Every placement: no other edit in it (+16 B for FF guards), FF (with guards) or stock dead-EVF bytes, and no
    reference into it from the patched image (abs32 on every alias and offset; d16/d32 call/jmp/branch encodings),
    except the dead tables' step-table words."""
    for k, (lo, hi) in REGIONS.items():
        g0, g1 = FF_GUARD.get(k, (0, 0))
        for e in spec['edits']:
            if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
                a, n = int(e['addr'], 16), len(e['new']) // 2
                if a < hi + g1 and lo - g0 < a + n:
                    raise SystemExit(f'{k}: overlaps edit {e["addr"]}')
        if k in FF_REGIONS:
            if set(im[lo - g0 - BASE:hi + g1 - BASE]) != {0xff}:
                raise SystemExit(f'{k}: {lo:#x}..{hi:#x} (with guards) is not FF')
        elif im[lo - BASE:hi - BASE] != stock[lo - BASE:hi - BASE]:
            raise SystemExit(f'{k}: not stock')
    d = np.frombuffer(im, np.uint8).astype(np.int64)
    w = d[:-3] | (d[1:-2] << 8) | (d[2:-1] << 16) | (d[3:] << 24)
    pc = np.arange(len(d) - 8, dtype=np.int64) + BASE
    for k, (lo, hi) in REGIONS.items():
        s0, src, dst = struct.unpack_from('<3I', stock, 0x60027068 + 12 * (SEC_OF[k] - 1) - BASE)
        for off in (0, 0x40000000, (src - dst) & 0xffffffff, (src - dst + 0x40000000) & 0xffffffff):
            a, b = (lo + off) & 0xffffffff, (hi + off) & 0xffffffff
            for i in np.nonzero((w >= a) & (w < b))[0]:
                at = int(i) + BASE
                if STEP_WORDS[0] <= at < STEP_WORDS[1] or (at in FALSE_POS and im[at - BASE:at - BASE + len(FALSE_POS[at]) // 2].hex() == FALSE_POS[at]):
                    continue
                raise SystemExit(f'{k}: abs32 reference at {at:#x}')
        for op, n in ((0xdd, 4), (0xdc, 4), (0xcd, 2), (0xcc, 2)):
            m = d[:-8] == op
            disp = d[1:-7] | (d[2:-6] << 8) if n == 2 else d[1:-7] | (d[2:-6] << 8) | (d[3:-5] << 16) | (d[4:-4] << 24)
            disp = np.where(disp >= (1 << (8 * n - 1)), disp - (1 << (8 * n)), disp)
            g0, g1 = FF_GUARD.get(k, (0, 0))
            bad = [int(x) + BASE for x in np.nonzero(m & (pc + disp >= lo - g0) & (pc + disp < hi + g1))[0]]
            bad = [x for x in bad if not (x in FALSE_POS and im[x - BASE:x - BASE + len(FALSE_POS[x]) // 2].hex() == FALSE_POS[x])]
            if bad:
                raise SystemExit(f'{k}: call/jmp encoding into it from {bad[0]:#x}')


def check_sections(stock):
    """Section 1 / 6 descriptors and ends: the placements sit inside the loads."""
    loads = {}
    for i in range(9):
        s, src, dst = struct.unpack_from('<3I', stock, 0x60027068 + 12 * i - BASE)
        stub = struct.unpack_from('<I', stock, 0x60046780 + 4 * i - BASE)[0]
        end = struct.unpack_from('<I', stock, stub + 2 - BASE)[0] if stock[stub - BASE:stub - BASE + 2] == b'\xfc\xcc' else None
        loads[i + 1] = (dst, end)
    for k, (lo, hi) in REGIONS.items():
        a, b = loads[SEC_OF[k]]
        if not (a <= lo and b is not None and hi <= b):
            raise SystemExit(f'{k}: {lo:#x}..{hi:#x} is not inside section {SEC_OF[k]} ({a:#x}..{b})')
    return loads


def apply(spec, version='0.32'):
    stock = STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    if 'split_tone' in spec:
        raise SystemExit('split_tone already applied')
    te = spec.get('tone_ends') or {}
    if te.get('code_at') != hex(SYMS['ep7_tone']) or te.get('hook') != hex(HOOK) or te.get('tbl_idx') != hex(TBL_IDX):
        raise SystemExit('needs tone_ends v0.19 (tone at 0x601e103c, hook 0x603b14ff, SD v3 tbl_idx)')
    spec = FV.apply(spec, version)
    im = img_of(spec, stock)
    # hook site: the v0.19 call tone; stock order: the gamma selector call 0x603b14a6 precedes it on the same path
    cur = im[HOOK - BASE:HOOK + 7 - BASE]
    if cur != b'\xdd' + struct.pack('<i', SYMS['ep7_tone'] - HOOK) + HOOK_FRAME:
        raise SystemExit(f'hook site is not call tone: {cur.hex()}')
    if stock[HOOK - BASE:HOOK + 7 - BASE] != bytes.fromhex('f1eccd65f7f048'):
        raise SystemExit('hook site stock bytes differ')
    if stock[0x603b14a4 - BASE:0x603b14ab - BASE] != bytes.fromhex('f1eccd67d3f010'):
        raise SystemExit('gamma selector call 0x603b14a6 differs')
    if stock[0x603ae7d3 - BASE:0x603ae7eb - BASE] != bytes.fromhex('92528681 72fad0240a fce0ffefffff 62f014f81404f81808'.replace(' ', '')):
        raise SystemExit('gamma setter 0x603ae7d3 differs (O+2596/2600/2604)')
    if stock[0x603ae9cf - BASE:0x603ae9db - BASE] != bytes.fromhex('5c38206c70fce0feffffff60'):
        raise SystemExit('selector skip path (C+108 &= ~1) differs')
    if stock[0x60346eb4 - BASE:0x60346eb8 - BASE] != bytes.fromhex('fac0240a') or stock[0x60346ecd - BASE:0x60346ed3 - BASE] != bytes.fromhex('f8006cf8ec01'):
        raise SystemExit('gamma register writer (O+2596, C+108 bit 0) differs')
    # the tone gate this layer copies: callback / record / marker constants as in piece A
    ta = im[0x601e103c - BASE:0x601e1132 - BASE]
    for what, pat in (('callback', struct.pack('<I', CALLBACK)), ('rec_off', struct.pack('<H', RECORDS_IN_JOB - REQ_IN_JOB)),
                      ('req_in_job', struct.pack('<h', -REQ_IN_JOB)), ('ext_magic', struct.pack('<H', EXT_MAGIC)),
                      ('ext_mode', struct.pack('<H', EXT_MODE)), ('ext_profile', struct.pack('<H', EXT_PROFILE)),
                      ('prop', struct.pack('<H', PROP_PROFILE))):
        if pat not in ta:
            raise SystemExit(f'tone piece A has no {what}')
    if im[TBL_IDX - BASE:TBL_IDX + 6 - BASE] != stock[TBL_IDX - BASE:TBL_IDX + 6 - BASE] and spec['sd_bundles_v3']['accessor']['tbl_idx'] != hex(TBL_IDX):
        raise SystemExit('tbl_idx moved')
    if (SB3.STATE, SB3.POOL, SB3.HDR_LEN) != (0x622cbcc2, 0xa1f8d800, 32):
        raise SystemExit('P layout differs')
    if spec['ap_custom']['symbols'].get('ap_P') != hex(AP_P) or im[AP_P - BASE:AP_P + 3 - BASE] != bytes.fromhex('fcaec2'):
        raise SystemExit('ap_P is not at 0x601df03c (movhu (state),d2)')
    check_sections(stock)
    check_free(spec, stock, im)
    # loader range bytes +62/+63 (and nothing else of the table) must be lo 0 span 0 now
    if im[LO + SB - BASE:LO + SB + 2 - BASE] != b'\0\0' or im[SPAN + SB - BASE:SPAN + SB + 2 - BASE] != b'\0\0':
        raise SystemExit('loader range +62/+63 is not 0/0')
    out, s, lst = assemble(subst(), SYMS)
    for k, (lo, hi) in REGIONS.items():
        if s.get('st' if k == '.sta' else None, lo) != lo and k == '.sta':
            raise SystemExit('st is not at .sta')
        if lo + len(out[k]) > hi:
            raise SystemExit(f'{k}: {len(out[k])} B does not fit {hi - lo}')
    for k, (lo, hi) in REGIONS.items():
        stop = s['st_k'] if k == '.stf' else None
        ins = SB3.disasm(out[k], lo, stop)
        if sum(len(x) for x in []) or any(op in BAD for _, op, _ in ins) or any(out[k][a - lo] == 0xfb for a, _, _ in ins):
            raise SystemExit(f'{k}: forbidden instruction or fb-prefixed form')
        st = SB3.store_audit(ins)
        if any(kd == 'abs' for _, _, kd, _ in st):
            raise SystemExit(f'{k}: absolute store {st}')
        allowed = set()
        for _, txt, kd, _ in st:
            if kd == 'ind' and not any(t in txt for t in ('(a1)', '(4,a1)', '(1572,a1)', '(20,a1)', '(848,a0)', '(2596,a3)', '(2600,a3)', '(2604,a3)', '(108,a2)')):
                raise SystemExit(f'{k}: unexpected store {txt}')
    if [struct.unpack_from('3b', out['.stf'], s['st_k'] - REGIONS['.stf'][0] + 3 * i) for i in range(12)] != ST_K:
        raise SystemExit('st_k table differs')
    for k, (lo, hi) in REGIONS.items():
        spec['edits'].append(dict(kind='0x100', addr=hex(lo), expect=stock[lo - BASE:lo - BASE + len(out[k])].hex(), new=out[k].hex(), source=SRC,
                                  why=f'split_tone {version} {k} ({len(out[k])} B, section {SEC_OF[k]}{" FF" if k in FF_REGIONS else " dead EVF gamma table"})'))
    put(spec, stock, HOOK + 1, struct.pack('<i', SYMS['ep7_tone'] - HOOK), struct.pack('<i', s['st'] - HOOK),
        'hook 0x603b14ff call tone -> call st (st ends jmp tone)')
    for i in (0, 1):   # the check is (s8 byte - s8 lo) <= span unsigned: lo -128, span 255 = any byte
        put(spec, stock, LO + SB + i, b'\0', b'\x80', f'SD loader v3 range slot +{SB + i} lo -128 (split nibbles; the reader checks them)')
        put(spec, stock, SPAN + SB + i, b'\0', b'\xff', f'SD loader v3 range slot +{SB + i} span 255')
    spec['split_tone'] = dict(built_by=SRC, version=version, regions={k: [hex(lo), hex(hi), len(out[k])] for k, (lo, hi) in REGIONS.items()},
                              hook=hex(HOOK), chained='0x601e103c (tone)', slot_bytes={'shadows': SB, 'highlights': SB + 1,
                              'format': 'low nibble colour 0..11, high nibble strength s4 -5..5; bad field = off'},
                              heap=dict(P_offset=SPTR, block_bytes=SBYTES, magic='EP7S', sets={'capture': SET0, 'live_view': SET0 + SETSZ}),
                              st_k=ST_K, credit='Caduceus for OM-3 v0.26 (androidfanman, Apache-2.0): st_run formula and st_k table',
                              symbols={k: hex(v) for k, v in s.items() if k.startswith('st')})
    return spec


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--version', default='0.32')
    ap.add_argument('--listing', type=Path)
    a = ap.parse_args()
    spec = apply(json.loads(a.spec.read_text()), a.version)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(spec, indent=1))
    if a.listing:
        a.listing.write_text(assemble(subst(), SYMS)[2])
    print(json.dumps({k: v for k, v in spec['split_tone'].items() if k not in ('symbols', 'st_k')}))
