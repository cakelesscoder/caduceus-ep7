#!/usr/bin/env python3
"""Resident plugin key hook + plugin API v1.1 (E-P7 1.1). Offline. docs/PLUGINS.md §7-§9; kh.s.in has the contract.

  .venv/bin/python -I patches/keyhook/build.py generated/v032/edits.json --out OUT.json

apply(spec, version) -> spec. Layer after plugin_loader (needs its pl_api / pl_chk). Edits:
  - code `.kh` in the dead `sdk api` debug-shell handlers, sec 5 0x607b6430.. (claim 0x607b6420-0x607b8420, 16 B stock
    guards at both ends; CODE_SPACE_SURVEY §2, CODE_SPACE_MAP "keyhook");
  - the three `sdk` sub-command words 0x60a9a918 / 920 / 928 -> kh_ret0 (`clr d0; rets`): no input reaches the shell code;
  - generic CA key handler 0x60ce011a `call 0x60cc9a05,[d2],4` -> `jmp kh` + 2 nop;
  - pl_chk's `mov pl_api,a0` -> kh_api (API v1.1: version 1, 8 words, +16 ka_sel, +20 ka_get, +24 features, +28 &selw,
    +32 ka_rep);
  - no edit, RAM only: the Fn stage byte STAGE (docs/PLUGINS.md §12), a boot-cleared .bss pad (proof in check_stage).
"""
import argparse, copy, importlib.util, json, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


PL = _load('ep7_pl_build_kh', ROOT / 'patches/plugin_loader/build.py')
ST, SB3, np = PL.ST, PL.SB3, PL.np
STOCK = PL.STOCK
BASE, SRC = 0x60020020, 'patches/keyhook'

CLAIM = (0x607b6420, 0x607b8420)               # sec 5, 8 KB: dead sdk-api handlers (A01 initializeApi on)
GUARD = 16
REGIONS = {'.kh': (CLAIM[0] + GUARD, CLAIM[1] - GUARD)}
SEC5 = 5
SUBCMD = {0x60a9a918: 0x607b4b25, 0x60a9a920: 0x607dab9f, 0x60a9a928: 0x607dac2e}   # api, starttimer, stoptimer
SITE, SITE_LEN = 0x60ce011a, 7                 # ca_key_generic: call 0x60cc9a05,[d2],4
KMAP, KBACK = 0x60cc9a05, 0x60ce0121
SITE2, KBACK2 = 0x60cebc9a, 0x60cebca1         # select-state key handler 0x60cebc89 (states 0x5800-05/08/09, 0x5c09): same call
EPI2 = 0x60cebd88                              # its ret [d2,d3,a2],48 (also at 0x60cebcca)
SELW = 0x6233b9a4                              # open select mode's action, written by 0x60ceb5b6 (12 stock refs)
SELMODE = 0x60ceb5b6                           # class-1 select-mode handler, call entry, frame [d2,d3,a2,a3],68
EPILOGUE = 0x60ce017b                          # ca_key_generic's ret [d2,a2,a3],40
ACT_TBL, ACT_N = 0x60f384f8, 92
AMIN, AMAX = 41, 67                            # SELECT_MODE_ISO .. SELECT_MODE_DIGITAL_SHIFT_SETTING
HW = 24                                        # key hook word B+24 (header reserved bytes 24..27)
API_N, FEATURES = 8, 7
D2330, DD8, DDC = 0x60cd2330, 0x61fb0dd8, 0x61fb0ddc   # stock "other key" exit of 0x60cebc89 (0x60cebcf9..0x60cebd1d)
EV_FN = 0x0100002e
# Fn stage byte: .bss pad after the movhu-only u16 0x6203bcb0, before the u32 0x6203bcb4 (boot clear 0x62038100-0x6203c934)
STAGE, STAGE_U16, STAGE_NEXT = 0x6203bcb2, 0x6203bcb0, 0x6203bcb4
SYMS = dict(ep7_ap_p=ST.AP_P, ep7_kmap=KMAP, ep7_kback=KBACK, ep7_kback2=KBACK2, ep7_selw=SELW, ep7_selmode=SELMODE,
            ep7_getter=PL.SYMS['ep7_getter'], ep7_setter=PL.SYMS['ep7_setter'], ep7_d2330=D2330, ep7_dd8=DD8, ep7_ddc=DDC)
ENTRY = {KMAP: '3c20', SELMODE: '4324', ST.AP_P: 'fcae'}   # first bytes of the entries we call or jump to
D2330_BODY = '823c50'                          # 0x60cd2330: mov d0,d2; mov sp,a0; inc4 a0 (its `call ..,[d2],12` body; see check_base)
# naive scan hits into the claim, each dis-checked (none is an address use):
FALSE_POS = {0x60607c21: 'dc7f7b60', 0x6060b35e: 'dc7f7b60', 0x60df14eb: 'dd777ba0',
             0x6015ba51: None, 0x6063ead7: None, 0x6067f978: None,          # inside mov (abs) / call d16 encodings
             0x60a5eb72: None, 0x60a5f783: None, 0x60a5f785: None,          # odd-aligned u16 tables (sec 5 data)
             0x60a61d3b: None, 0x60a62d3e: None, 0x60a63a1f: None, 0x60a63a21: None,
             0x6041993b: None}                                             # `dd` byte inside `mov a3,d1`
# the double constant 0x40e4ab40 (flash alias of 0x607cab40): 21 `mov imm32,d1/a1/d3` sites, 0x60bed9a1..0x60c3a9c4.
# Outside this claim, pinned for any later claim in the shell reserve (CODE_SPACE_SURVEY §2.2).
DOUBLE_K, DOUBLE_N = 0x40e4ab40, 21
# sources that never run once the three sub-command words point at kh_ret0 (CODE_SPACE_SURVEY §2.1-2.3): the api dispatcher,
# the handlers themselves, the api table and the handlers' switch tables
DEAD = ((0x607b4b25, 0x607b4cba), (0x607b6420, 0x607e87c5), (0x60aa2b30, 0x60aa6088), (0x60ac7c98, 0x60ac9f10))
BAD = PL.BAD
STORES_OK = ('sp',)


def u32(b):
    return struct.unpack('<I', b)[0]


def sec(stock, n):
    s, src, dst = struct.unpack_from('<3I', stock, 0x60027068 + 12 * (n - 1) - BASE)
    stub = struct.unpack_from('<I', stock, 0x60046780 + 4 * (n - 1) - BASE)[0]
    assert stock[stub - BASE:stub - BASE + 2] == b'\xfc\xcc'
    return dst, struct.unpack_from('<I', stock, stub + 2 - BASE)[0], (src - dst) & 0xffffffff


def pin_fp(stock):
    """Fill the pinned bytes from stock once (the sites are stock code/data, never edited)."""
    for a in list(FALSE_POS):
        if FALSE_POS[a] is None:
            FALSE_POS[a] = stock[a - BASE:a - BASE + 4].hex()


def double_sites(im):
    k = struct.pack('<I', DOUBLE_K)
    out, i = [], im.find(k)
    while i >= 0:
        out.append(i + BASE)
        i = im.find(k, i + 1)
    return out


def scan(im, lo, hi, off5, allow=()):
    """abs32 at every byte on the four aliases + d16/d32 call/jmp encodings into [lo, hi), minus pinned sites."""
    d = np.frombuffer(im, np.uint8).astype(np.int64)
    w = d[:-3] | (d[1:-2] << 8) | (d[2:-1] << 16) | (d[3:] << 24)
    pc = np.arange(len(d) - 8, dtype=np.int64) + BASE
    dsites = set(double_sites(im))
    bad = []
    for off in (0, 0x40000000, off5, (off5 + 0x40000000) & 0xffffffff):
        a, b = (lo + off) & 0xffffffff, (hi + off) & 0xffffffff
        for i in np.nonzero((w >= a) & (w < b))[0]:
            at = int(i) + BASE
            if any(x <= at < y for x, y in allow) or at in dsites:
                continue
            if FALSE_POS.get(at) == im[at - BASE:at - BASE + 4].hex():
                continue
            bad.append(('abs32', at))
    for op, n in ((0xdd, 4), (0xdc, 4), (0xcd, 2), (0xcc, 2)):
        m = d[:-8] == op
        disp = d[1:-7] | (d[2:-6] << 8) if n == 2 else d[1:-7] | (d[2:-6] << 8) | (d[3:-5] << 16) | (d[4:-4] << 24)
        disp = np.where(disp >= (1 << (8 * n - 1)), disp - (1 << (8 * n)), disp)
        for x in np.nonzero(m & (pc + disp >= lo) & (pc + disp < hi))[0]:
            at = int(x) + BASE
            if any(p <= at < q for p, q in allow) or FALSE_POS.get(at) == im[at - BASE:at - BASE + 4].hex():
                continue
            bad.append(('rel', at))
    return bad


def check_free(spec, stock, im):
    lo5, hi5, off5 = sec(stock, SEC5)
    if not (lo5 <= CLAIM[0] and CLAIM[1] <= hi5):
        raise SystemExit('claim not inside section 5')
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a, n = int(e['addr'], 16), len(e['new']) // 2
            if a < CLAIM[1] and CLAIM[0] < a + n:
                raise SystemExit(f'claim overlaps edit {e["addr"]}')
            for st in (SITE, SITE2):
                if a < st + SITE_LEN and st < a + n:
                    raise SystemExit(f'key site {st:#x} overlaps edit {e["addr"]}')
    if im[CLAIM[0] - BASE:CLAIM[1] - BASE] != stock[CLAIM[0] - BASE:CLAIM[1] - BASE]:
        raise SystemExit('claim not stock')
    ds = double_sites(stock)
    if len(ds) != DOUBLE_N or any(stock[a - 2 - BASE] != 0xfc for a in ds) or any(CLAIM[0] <= a - off5 + 0 < CLAIM[1] for a in ds):
        raise SystemExit(f'0x40e4ab40 pin: {len(ds)} sites')
    pin_fp(stock)
    bad = scan(im, CLAIM[0], CLAIM[1], off5, DEAD)
    if bad:
        raise SystemExit(f'reference into the claim: {[(k, hex(a)) for k, a in bad[:4]]}')
    return off5


def check_base(spec, stock, im):
    m = spec.get('plugin_loader')
    if not m:
        raise SystemExit('needs plugin_loader')
    if 'keyhook' in spec:
        raise SystemExit('keyhook already applied')
    for w, v in SUBCMD.items():
        if u32(im[w - BASE:w - BASE + 4]) != v:
            raise SystemExit(f'{w:#x} != {v:#x}')
    for st in (SITE, SITE2):
        site = im[st - BASE:st + SITE_LEN - BASE]
        if site != b'\xdd' + struct.pack('<i', KMAP - st) + b'\x80\x04':
            raise SystemExit(f'key site {st:#x} {site.hex()}')
    for ep in (EPILOGUE, EPI2):
        if im[ep - BASE:ep + 3 - BASE] != stock[ep - BASE:ep + 3 - BASE]:
            raise SystemExit(f'epilogue {ep:#x} edited')
    if stock.count(struct.pack('<I', SELW)) != 12:
        raise SystemExit('select-mode word refs')
    # the stock exit-and-replay we mirror in ka_rep: 0x60cebcf9 mov (28,sp),d0; call 0x60cd2330,[d2],12; mov 158,d0;
    # mov d0,(32,a2); mov (28,sp),d0; mov d0,(0x61fb0ddc); ... mov d0,(0x61fb0dd8)
    rep = im[0x60cebcf9 - BASE:0x60cebd1f - BASE]
    if (rep[:2].hex() != '581c' or rep[2:9] != b'\xdd' + struct.pack('<i', D2330 - 0x60cebcfb) + b'\x80\x0c'
            or rep[9:12].hex() != '2c9e00' or struct.pack('<I', DDC) not in rep or struct.pack('<I', DD8) not in rep):
        raise SystemExit('stock exit-and-replay bytes')
    if im[D2330 - BASE:D2330 - BASE + 3].hex() != D2330_BODY:
        raise SystemExit('0x60cd2330 entry')
    check_stage(im)
    for a, b in ENTRY.items():
        if im[a - BASE:a - BASE + len(b) // 2].hex() != b:
            raise SystemExit(f'{a:#x} entry bytes {im[a - BASE:a - BASE + 2].hex()}')
    for i in range(ACT_N):                         # every action AMIN..AMAX is class 1
        x, c, _ = struct.unpack_from('<3I', stock, ACT_TBL - BASE + 12 * i)
        if AMIN <= x <= AMAX and c != 1:
            raise SystemExit(f'action {x} class {c}')
    api, chk, end = (int(m['symbols'][k], 16) for k in ('pl_api', 'pl_chk', 'pl_end'))
    ver, n, ftext, get, sett = struct.unpack_from('<HH3I', im, api - BASE)
    if (ver, n, get, sett) != (1, 3, SYMS['ep7_getter'], SYMS['ep7_setter']):
        raise SystemExit('API v1 table')
    mov = b'\xfc\xdc' + struct.pack('<I', api)     # mov imm32,a0
    body = im[chk - BASE:end - BASE]
    if body.count(mov) != 1:
        raise SystemExit('pl_chk mov pl_api,a0')
    return ftext, chk + body.index(mov), api


def check_stage(im):
    """STAGE is free: no abs32 word in the image (any byte offset, cached / uncached alias) equals STAGE-1..STAGE+1
    or STAGE_U16+3, and the u16 before it is reached only by movhu abs forms (fc 83/87/8b/8f stores, fc ac..af loads), the
    rotation-pad pattern (VIDEO_ROTATION.md). Our own .kh stores are added after this check."""
    import numpy as np
    d = np.frombuffer(im, np.uint8).astype(np.int64)
    w = d[:-3] | (d[1:-2] << 8) | (d[2:-1] << 16) | (d[3:] << 24)
    for off in (0, 0x40000000):
        for a in (STAGE - 1, STAGE, STAGE + 1):
            if np.any(w == a + off):
                raise SystemExit(f'stage byte referenced: {a + off:#x}')
        for i in np.nonzero(w == STAGE_U16 + off)[0]:
            if im[i - 2] != 0xfc or im[i - 1] not in (0x83, 0x87, 0x8b, 0x8f, 0xac, 0xad, 0xae, 0xaf):
                raise SystemExit(f'u16 {STAGE_U16:#x} non-movhu ref at {int(i) + BASE:#x}')
        if not np.any(w == STAGE_NEXT + off) and off == 0:
            raise SystemExit('stage: next word not referenced (layout changed?)')


def build_code(ftext):
    sub = dict(ps=PL.PS, pb=PL.PB, rmagic=hex(u32(PL.RMAGIC)), rname=PL.RMAGIC.decode(), hw=HW,
               cneg=hex(-(PL.TO_CACHED + PL.HDR) & 0xffffffff), span=PL.BSIZE - PL.HDR, amin=AMIN, amax=AMAX,
               amax1=AMAX + 1, api_n=API_N, features=FEATURES, evfn=hex(EV_FN), stage=hex(STAGE))
    src = SB3.subst((HERE / 'kh.s.in').read_text(), sub)
    out, sy, lst = ST.assemble(src, dict(SYMS, ep7_fw_text=ftext), REGIONS)
    lo, hi = REGIONS['.kh']
    code = out['.kh']
    if lo + len(code) > hi:
        raise SystemExit(f'.kh {len(code)} B does not fit')
    if sy['kh_ret0'] != lo or sy['kh_api'] % 4 or code[:3] != bytes.fromhex('00f0fc'):
        raise SystemExit('layout')
    ins = SB3.disasm(code, lo, sy['kh_api'])
    if any(op in BAD for _, op, _ in ins) or any(op.startswith('.') or op == '(bad)' for _, op, _ in ins):
        raise SystemExit('forbidden or undecodable instruction')
    if any(code[a - lo] == 0xfb for a, _, _ in ins):
        raise SystemExit('fb-prefixed form')
    st = SB3.store_audit(ins)
    ab = sorted((tg, t.split()[0]) for _, t, kd, tg in st if kd == 'abs')
    ind = [(a, t) for a, t, kd, _ in st if kd == 'ind']
    if ab != sorted([(STAGE, 'movbu'), (DD8, 'mov'), (DDC, 'mov')]) or len(ind) != 1 or ind[0][1] != 'mov d0,(32,a2)' \
            or not sy['ka_rep'] <= ind[0][0] < sy['kh_api'] or any(kd not in ('sp', 'abs', 'ind') for _, _, kd, _ in st):
        raise SystemExit(f'stores: {st}')
    # call / jmp targets
    want = {('call', SYMS['ep7_ap_p']), ('call', KMAP), ('call', SYMS['ep7_getter']), ('call', sy['kh_chk']),
            ('call', sy['kh_chk2']), ('jmp', KBACK), ('jmp', KBACK2), ('jmp', SELMODE), ('call', D2330)}
    seen = set()
    for a, op, args in ins:
        if op in ('call', 'jmp') and args.startswith('0x'):
            seen.add((op, int(args.split(',')[0], 16)))
    if seen != want:
        raise SystemExit(f'targets {sorted((o, hex(t)) for o, t in seen)}')
    k = code[sy['kh'] - lo:]
    if k[0] != 0xcd and k[0] != 0xdd:
        raise SystemExit('kh: first insn is not a call')
    sb = STOCK.read_bytes()
    for k0, k1, epa in (('kh', 'kh_miss', EPILOGUE), ('kh2', 'kh2_miss', EPI2)):
        kret = [x for x in ins if x[1] == 'ret' and sy[k0] <= x[0] < sy[k1]]
        if len(kret) != 1 or code[kret[0][0] - lo:kret[0][0] - lo + 3] != sb[epa - BASE:epa + 3 - BASE]:
            raise SystemExit(f'{k0} handled-path epilogue differs from {epa:#x}')
    api = struct.unpack_from('<HH8I', code, sy['kh_api'] - lo)
    if api != (1, API_N, ftext, SYMS['ep7_getter'], SYMS['ep7_setter'], sy['ka_sel'], sy['ka_get'], FEATURES, SELW, sy['ka_rep']):
        raise SystemExit('API v1.1 table')
    return code, sy, lst, ins


def apply(spec, version='0.32'):
    stock = STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    im = ST.img_of(spec, stock)
    ftext, movat, old_api = check_base(spec, stock, im)
    check_free(spec, stock, im)
    code, sy, lst, ins = build_code(ftext)
    lo = REGIONS['.kh'][0]
    spec['edits'].append(dict(kind='0x100', addr=hex(lo), expect=stock[lo - BASE:lo - BASE + len(code)].hex(), new=code.hex(),
                              source=SRC, why=f'keyhook {version} .kh ({len(code)} B, sec 5 dead sdk-api handlers)'))
    for w in SUBCMD:
        PL.put(spec, stock, w, stock[w - BASE:w - BASE + 4], struct.pack('<I', sy['kh_ret0']),
               f'sdk sub-command word {w:#x} -> kh_ret0 (shell code unreachable)')
    jmp = b'\xdc' + struct.pack('<i', sy['kh'] - SITE) + b'\xcb\xcb'
    PL.put(spec, stock, SITE, stock[SITE - BASE:SITE + SITE_LEN - BASE], jmp,
           'ca_key_generic call 0x60cc9a05 -> jmp kh + 2 nop (plugin key hook)')
    jmp2 = b'\xdc' + struct.pack('<i', sy['kh2'] - SITE2) + b'\xcb\xcb'
    PL.put(spec, stock, SITE2, stock[SITE2 - BASE:SITE2 + SITE_LEN - BASE], jmp2,
           'select-state key handler call 0x60cc9a05 -> jmp kh2 + 2 nop (plugin key hook, site 1)')
    PL.put(spec, stock, movat + 2, struct.pack('<I', old_api), struct.pack('<I', sy['kh_api']),
           'pl_chk mov pl_api,a0 -> kh_api (API v1.1)')
    for e in spec['edits']:                        # tag our sites for the verifiers (PL.put writes plugin_loader tags)
        if e.get('source') == PL.SRC and e['why'].startswith('plugin_loader: ') and any(
                s in e['why'] for s in ('kh_ret0', 'jmp kh', 'kh_api')):   # 'jmp kh' also matches 'jmp kh2'
            e['source'] = SRC
            e['why'] = 'keyhook: ' + e['why'][len('plugin_loader: '):]
        elif '[plugin_loader: pl_chk mov pl_api,a0' in e['why']:
            e['why'] = e['why'].replace('[plugin_loader: pl_chk', '[keyhook: pl_chk')
    spec['keyhook'] = dict(
        built_by=SRC, version=version, claim=[hex(CLAIM[0]), hex(CLAIM[1])], region=[hex(lo), hex(lo + len(code))],
        bytes=len(code), site=hex(SITE), resume=hex(KBACK), site2=hex(SITE2), resume2=hex(KBACK2), selw=hex(SELW), stage=hex(STAGE), subcmd_words=[hex(w) for w in SUBCMD], api=hex(sy['kh_api']),
        api_v1=hex(old_api), api_mov=hex(movat), api_n=API_N, hook_word=HW, features=FEATURES,
        actions=[AMIN, AMAX], symbols={k: hex(v) for k, v in sy.items() if k.startswith(('kh', 'ka_', 'k_', 's_'))})
    return spec


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--version', default='0.32')
    a = ap.parse_args()
    spec = apply(json.loads(a.spec.read_text()), a.version)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(spec, indent=1))
    print(json.dumps({k: v for k, v in spec['keyhook'].items() if k != 'symbols'}, indent=1))
