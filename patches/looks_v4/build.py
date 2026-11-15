#!/usr/bin/env python3
"""looks_v4: LOOKS.BIN v4 carries each look's base curve and colour mix to a Film pick (slot +53..+60). Layer after look_hw_ui
(needs looks_split and look_hw). Offline. lx.s.in has the contract, docs/LOOK_FORMAT_V4.md "LOOKS.BIN v4" the format.

  .venv/bin/python -I patches/v032/build.py releases/v0.31d/edits.json --out <spec> --version 0.34e ... \\
      --extra look_hw_ui=patches/look_hw_ui/build.py --extra movie_quality=patches/movie_quality/build.py \\
      --extra looks_v4=patches/looks_v4/build.py

apply(spec, version) -> spec. Edits (each old byte checked to be what the chain put there):
  H1 fm_load 0x6143a49c `mov d0,d3; mov d3,d1; and 63,d1` (5 B, after ftell) -> jmp lx_h1;
  H2 fm_load 0x6143a4db `mov d0,d2; mov (4,sp),a0; call fclose,[d2,a2,a3],16` (10 B, after fread) -> jmp lx_h2 + 5 nop;
  C  fm_load 0x6143a4ed `jmp ls_chk` (looks_split) -> jmp lx_chk (which calls ls_sc and fm_check as ls_chk did);
  P  sl_pick's tail 0x601e3a16 `jmp lh_pick` (look_hw) -> jmp lx_pick (lh_pk, lx_pk, then ls_pick as lh_pick did);
  code in a sec-5 claim of the dead `sdk api` handlers (CODE_SPACE_SURVEY section 2).
State: heap P+872 = the extension block (class-1 malloc 520 B, 'EP7H', back pointer P, 8 B per look). L is unchanged.
P+872 is free: check_p872() below (no instruction of any edit uses a displacement 869..875; the card loader writes
P+0..815, clean_boot clears all 1024 B at the malloc; P2 / P3 use +800..959 of their own blocks).
"""
import argparse, copy, importlib.util, json, re, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SRC = 'patches/looks_v4'


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


LH = _load('ep7_lh_build_lx', ROOT / 'patches/look_hw/build.py')
LS, CL, ST, KH, B3, V3B = LH.LS, LH.CL, LH.ST, LH.KH, LH.B3, LH.V3B
FB = LS.FB
BASE, STOCK = LH.BASE, LH.STOCK

CLAIM = (0x607dba00, 0x607dbf00)      # sec 5, 1280 B inside the run 0x607db9dc..0x607dbfdd into which no outside reference points
GUARD = 16
AT = CLAIM[0] + GUARD
FM_LOAD, FM_CHECK = LS.FM_LOAD, LS.FM_CHECK
H1, H1_OLD, FL_V3, FL_V4 = 0x6143a49c, '838df8e13f', 0x6143a4a1, 0x6143a4b8
H2, H2_OLD, FL_H2 = 0x6143a4db, '825c04dde7aa1fffb010', 0x6143a4e5
FM_CALL, FM_AFTER = LS.FM_CALL, LS.FM_AFTER
PICK_TAIL = LH.PICK_TAIL
POOL1, POOL1_END = 0xa1f8d800, 0xa1f98540            # class-1 pool (sd_bundles_v3 POOL / POOL_END)
EXT_ASK, EXT_USED = 520, 8 + 8 * FB.MAX_LOOKS        # malloc size (16 n read in place) / bytes the pick may read
PWORD = 872
XMAGIC = struct.unpack('<I', b'EP7H')[0]
SVC = dict(ep7_malloc=0x60022782, ep7_free=0x600227b4, ep7_fclose=0x60634fc5, ep7_fread=0x6063514b, ep7_fseek=0x60635243)
BAD = LH.BAD | {'mul', 'mulu'}
STORES = {'mov d1,(12,sp)', 'mov d0,(8,sp)', 'mov d0,(12,sp)',                       # fm_load's frame
          'mov d0,(a0)', 'mov a2,(4,a0)', 'movbu d0,(d1,a0)', 'movbu d0,(7,a0)', 'mov d0,(a2)',   # the block
          'movbu d0,(4,a3)', 'mov d0,(32,a3)', 'movhu d0,(36,a3)', 'mov d0,(16,a3)',  # L's header
          'mov a0,(872,a2)', *{f'movbu d0,({85 + i},a0)' for i in range(8)}}           # P+872, slot +53..+60


def u32(m, a):
    return struct.unpack_from('<I', m, a - BASE)[0]


def check_p872(spec):
    """No instruction of any edit (linear decode of every edit's new bytes, data included: false positives only make this
    stricter) addresses a displacement that overlaps P+872..875 through a register."""
    hits = []
    for e in spec['edits']:
        if e['kind'] != '0x100' or e['addr'].startswith('off:') or len(e['new']) < 4:
            continue
        a = int(e['addr'], 16)
        for x, op, args in B3.disasm(bytes.fromhex(e['new']), a):
            m = re.search(r'\((\d+),(a\d|d\d|r\d+)\)', args)
            if m and 869 <= int(m.group(1)) <= 875:
                hits.append((hex(x), op, args))
    if hits:
        raise SystemExit(f'P+{PWORD} has a user: {hits[:4]}')


def check_sites(spec, stock, im):
    at = lambda a, n: im[a - BASE:a - BASE + n]
    if at(H1, 5).hex() != H1_OLD or at(H2, 10).hex() != H2_OLD:
        raise SystemExit('fm_load after ftell / fread differs')
    if H2 + 3 + struct.unpack_from('<i', im, H2 + 4 - BASE)[0] != SVC['ep7_fclose']:
        raise SystemExit('fm_load: the call after fread is not fclose')
    if at(FL_V3, 2) != b'\xc8\x05' or at(FL_V4, 2) != b'\x4e\x08' or at(FL_H2, 2) != b'\x5b\x08':
        raise SystemExit('fm_load continuation bytes differ')
    if at(H1 - 7, 4) != b'\xdd\x44\xad\x1f' or H1 - 7 + struct.unpack_from('<i', im, H1 - 6 - BASE)[0] != 0x606351d9:
        raise SystemExit('fm_load: the call before H1 is not ftell')
    ls = {k: int(v, 16) for k, v in spec['looks_split']['symbols'].items()}
    lh = {k: int(v, 16) for k, v in spec['look_hw']['symbols'].items()}
    if at(FM_CALL, 1) != b'\xdc' or FM_CALL + struct.unpack_from('<i', im, FM_CALL + 1 - BASE)[0] != ls['ls_chk']:
        raise SystemExit('fm_load fm_check site is not jmp ls_chk')
    if at(PICK_TAIL, 1) != b'\xdc' or PICK_TAIL + struct.unpack_from('<i', im, PICK_TAIL + 1 - BASE)[0] != lh['lh_pick']:
        raise SystemExit('sl_pick tail is not jmp lh_pick')
    ins = B3.disasm(at(lh['lh_pick'], 12), lh['lh_pick'])
    if [(op, args.split(',')[0]) for _, op, args in ins[:2]] != [('call', hex(lh['lh_pk'])), ('jmp', hex(ls['ls_pick']))]:
        raise SystemExit(f'lh_pick is not call lh_pk; jmp ls_pick: {ins[:2]}')
    ins = B3.disasm(at(ls['ls_chk'], 17), ls['ls_chk'])
    if [(op, args.split(',')[0]) for _, op, args in ins[:3]] != [('call', hex(ls['ls_sc'])), ('call', hex(FM_CHECK)), ('jmp', hex(FM_AFTER))]:
        raise SystemExit(f'ls_chk is not call ls_sc; call fm_check; jmp fm_after: {ins[:3]}')
    if (FB.OFF['lptr'], FB.OFF['fmark'], FB.OFF['ltag'], FB.OFF['lback'], FB.OFF['n'], FB.OFF['pos']) != (1016, 1020, 2112, 2116, 2120, 2121):
        raise SystemExit('L layout differs')
    # branch-target scans on fm_load's linear decode: both sites are whole instructions, nothing lands inside them
    return {hex(s): site_scan(im, stock, s, n) for s, n in ((H1, 5), (H2, 10))}, ls, lh


def site_scan(im, stock, site, n):
    """The n displaced bytes are whole instructions of fm_load's linear decode (its code runs 0x6143a410..fm_check), no
    decoded branch / call / jmp of fm_load and fm_check lands on site+1..site+n-1, and no d16 / d32 / abs32 encoding in the
    image points there (crash_log refs: both aliases + section 9's flash alias)."""
    ins = B3.disasm(im[FM_LOAD - BASE:LS.FM_CRC - BASE], FM_LOAD, LS.FM_CRC)
    at = {a for a, _, _ in ins}
    if site not in at or site + n not in at:
        raise SystemExit(f'{site:#x}: the displaced bytes are not whole instructions')
    hits = [(hex(a), op, args) for a, op, args in ins for t in re.findall(r'0x([0-9a-f]{8})', args)
            if (op[0] in 'bjl' or op.startswith('call')) and site < int(t, 16) < site + n]
    far = CL.refs(im, site + 1, site + n, KH.sec(stock, 9)[2])
    if hits or far:
        raise SystemExit(f'{site:#x}: references into the displaced bytes: {hits[:4]} {[(k, hex(a)) for k, a in far[:4]]}')
    return len(ins)


def check_claim(spec, stock, im):
    lo5, hi5, off5 = KH.sec(stock, 5)
    if not (lo5 <= CLAIM[0] and CLAIM[1] <= hi5 and KH.DEAD[1][0] <= CLAIM[0] and CLAIM[1] <= KH.DEAD[1][1]):
        raise SystemExit('claim not inside the dead handler range of section 5')
    if V3B.overlaps(spec, *CLAIM) or im[CLAIM[0] - BASE:CLAIM[1] - BASE] != stock[CLAIM[0] - BASE:CLAIM[1] - BASE]:
        raise SystemExit('claim is edited / not stock')
    bad = CL.refs(im, CLAIM[0], CLAIM[1], off5, allow=list(KH.DEAD))
    if bad:
        raise SystemExit(f'reference into the sec-5 claim: {[(k, hex(a)) for k, a in bad[:6]]}')


def build_code(syms):
    sub = dict(lmagic=hex(FB.LMAGIC), fmagic=hex(FB.FMAGIC), xmagic=hex(XMAGIC), npool=hex(-FB.POOL2 & 0xffffffff),
               llim=hex(LS.LLIM), npool1=hex(-POOL1 & 0xffffffff), elim=hex(POOL1_END - POOL1 - EXT_ASK + 1),
               plim=hex(POOL1_END - POOL1 - EXT_USED + 1))
    src = B3.subst((HERE / 'lx.s.in').read_text(), sub)
    code, lst, sy, _ = B3.assemble(src, AT, syms)
    if sy['lx_h1'] != AT or AT + len(code) > CLAIM[1] - GUARD:
        raise SystemExit(f'{len(code)} B does not fit')
    ins = B3.disasm(code, AT, sy['lx_end'])
    if any(op in BAD for _, op, _ in ins) or any(op.startswith('.') or op == '(bad)' for _, op, _ in ins):
        raise SystemExit(f'forbidden or undecodable instruction: {[x for x in ins if x[1] in BAD or x[1].startswith(".")][:3]}')
    if any(code[a - AT] == 0xfb for a, _, _ in ins):
        raise SystemExit('fb-prefixed form')
    for a, txt, kd, _ in B3.store_audit(ins):
        if kd == 'abs' or (kd in ('ind', 'sp') and txt not in STORES and not txt.startswith('movm')):
            raise SystemExit(f'store at {a:#x}: {txt} ({kd})')
    tg = {(op, int(args.split(',')[0], 16)) for _, op, args in ins if op in ('call', 'calls', 'jmp') and args.startswith('0x')}
    tg = {(o, t) for o, t in tg if not (o == 'jmp' and AT <= t < sy['lx_end'])}
    want = {('call', syms['ep7_fseek']), ('call', syms['ep7_fread']), ('call', syms['ep7_fclose']), ('call', syms['ep7_malloc']),
            ('call', syms['ep7_free']), ('call', syms['ep7_fm_crc']), ('call', syms['ep7_ls_sc']), ('call', syms['ep7_fm_check']),
            ('call', syms['ep7_lh_pk']), ('call', syms['ep7_ap_p']), ('call', sy['lx_ext']), ('call', sy['lx_hdr']),
            ('call', sy['lx_pk']), ('jmp', syms['ep7_fl_v3']), ('jmp', syms['ep7_fl_v4']), ('jmp', syms['ep7_fl_h2']),
            ('jmp', syms['ep7_fm_after']), ('jmp', syms['ep7_ls_pick'])}
    if tg != want:
        raise SystemExit(f'call targets differ: extra {sorted((o, hex(t)) for o, t in tg - want)} missing {sorted((o, hex(t)) for o, t in want - tg)}')
    return code, sy, lst


def apply(spec, version='0.34e'):
    stock = STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    if 'looks_v4' in spec:
        raise SystemExit('looks_v4 already applied')
    for need in ('looks_split', 'look_hw', 'look_hw_ui', 'clean_boot'):
        if need not in spec:
            raise SystemExit(f'needs {need}')
    im = ST.img_of(spec, stock)
    scans, ls, lh = check_sites(spec, stock, im)
    check_claim(spec, stock, im)
    check_p872(spec)
    syms = dict(SVC, ep7_fm_crc=LS.FM_CRC, ep7_fm_check=FM_CHECK, ep7_fm_after=FM_AFTER, ep7_ls_sc=ls['ls_sc'],
                ep7_ls_pick=ls['ls_pick'], ep7_lh_pk=lh['lh_pk'], ep7_ap_p=LS.AP_P, ep7_fl_v3=FL_V3, ep7_fl_v4=FL_V4, ep7_fl_h2=FL_H2)
    code, sy, lst = build_code(syms)
    spec['edits'].append(dict(kind='0x100', addr=hex(AT), expect=stock[AT - BASE:AT - BASE + len(code)].hex(), new=code.hex(),
                              source=SRC, why=f'looks_v4 {version}: lx_h1 / lx_h2 / lx_ext / lx_chk / lx_hdr / lx_pick / lx_pk '
                                              f'({len(code)} B, sec-5 dead sdk-api handlers, claim {CLAIM[0]:#x}..{CLAIM[1]:#x})'))
    jmp = lambda site, t: b'\xdc' + struct.pack('<i', t - site)
    ST.put(spec, stock, H1, bytes.fromhex(H1_OLD), jmp(H1, sy['lx_h1']), 'looks_v4 H1: fm_load after ftell -> jmp lx_h1')
    ST.put(spec, stock, H2, bytes.fromhex(H2_OLD), jmp(H2, sy['lx_h2']) + b'\xcb' * 5, 'looks_v4 H2: fm_load after fread -> jmp lx_h2')
    ST.put(spec, stock, FM_CALL + 1, struct.pack('<i', ls['ls_chk'] - FM_CALL), struct.pack('<i', sy['lx_chk'] - FM_CALL),
           'looks_v4 C: fm_load jmp ls_chk -> jmp lx_chk')
    ST.put(spec, stock, PICK_TAIL + 1, struct.pack('<i', lh['lh_pick'] - PICK_TAIL), struct.pack('<i', sy['lx_pick'] - PICK_TAIL),
           'looks_v4 P: sl_pick tail jmp lh_pick -> jmp lx_pick')
    for ed in spec['edits']:
        ed['why'] = ed['why'].replace(' [split_tone: looks_v4', ' [looks_v4: looks_v4')
    spec['looks_v4'] = dict(built_by=SRC, version=version, claim=[hex(CLAIM[0]), hex(CLAIM[1])], code=[hex(AT), len(code)],
                            sites=dict(H1=hex(H1), H2=hex(H2), C=hex(FM_CALL), P=hex(PICK_TAIL)), site_scans=scans,
                            p_word=PWORD, block=dict(malloc=EXT_ASK, magic='EP7H', back=4, looks=8, stride=8),
                            file=dict(version=4, ext_crc=32, ext_len=36, ext_record=16),
                            symbols={k: hex(v) for k, v in sy.items() if k.startswith(('lx_', 'h1_', 'h2_', 'e_'))})
    return spec


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--version', default='0.34e')
    a = ap.parse_args()
    spec = apply(json.loads(a.spec.read_text()), a.version)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(spec, indent=1))
    print(json.dumps({k: v for k, v in spec['looks_v4'].items() if k != 'symbols'}))
