#!/usr/bin/env python3
"""AP Custom: on the mode dial's AP position, picture mode Vivid is its own INFO Custom slot (EP7MOD/AP.BIN). docs/AP_CUSTOM.md. Offline.

  .venv/bin/python -I patches/ap_custom/build.py generated/v029a/edits.json --out generated/ap_custom/edits.json

apply(spec, version='0.30a1') -> spec. A layer over v0.29a: the v0.26 Movie slot code stays as it is; ap_* run in front of its hooks and fall through.
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


MV = _load('ep7_v026_movie', ROOT / 'patches/v026_movie/build.py')
FV = _load('fw_version_build', ROOT / 'patches/fw_version/build.py')
SB3, STOCK = MV.SB3, MV.STOCK
BASE, SRC = 0x60020020, 'patches/ap_custom'
AT, END = 0x601df0e0, 0x601dfc2c           # dead EVF gamma step-table entries 0x601e3ba0..0x601e3bd8 (tables 0x601df03c..0x601dfc3c; start past the false positive 0xa01df0cc read at 0x606c1305); 16 B stock before grain
REFS = (0x601e3bd4, 0x601e3bd8, 0x601e3bc0, 0x601e3bc4, 0x601e3bc8, 0x601e3bb0, 0x601e3bb4, 0x601e3bb8, 0x601e3ba0, 0x601e3ba4, 0x601e3ba8)
AM, AP3, ATR, PEND, ARM = 984, 988, 992, 808, 809 
RETRIES = 4                                # extra BUNDLES.BIN attempts per power-on after a failed one (a card still mounting after a crash)
BOOT = 0x6203c8bb                          # .bss padding byte after rotation's latch 0x6203c8ba (v026_rot: 0x6203c8b8 is u16-only, 0x6203c8bc a u32); 0 at power-on
              # heap P: 'EP7A', P3, 'EP7U' (free: movie +960..983, grain +1000, mono +1004.., film +1016..)
AMAGIC, ATMAGIC = struct.unpack('<2I', b'EP7AEP7U')
K44, K24 = 0x8551, 0xc011                  # sid 44 (movie), sid 24 (shooting / AP mode)
GETTER, SGET = 0x6005e971, 0x602af887
CAP_SITES = [0x602a8577, 0x602a85b7, 0x602a85cd] + [0x602a85e5 + 0x14 * i for i in range(11)]   # capture population: pm, COLOR profile, S 0..11
SCP_CALL, WBP_CALL = 0x601e3a5c, 0x6055e79b  # sc_prop / wb_prop getter calls
TBLX, TBLX_OLD = 0x6055e7e7, 'f16cdfc008'
MVT_TAIL = 0x601e0bdf                      # mv_trig: jmp ed_trig
CCG_CALL = 0x601e202d                      # mv_get: call mv_ccg,[],4
LB_HIT, LB_HIT_OLD = 0x601e0fe1, 'c9338005f073'   # mv_lb after its gate (bne; mov 5,d0; movhu d0,(a3))
BAD = MV.BAD
AP_ZC, ZC_OLD = 0x601df8e2, 'fad06403800c04'   # ap_load `add {fb}+16+52,a0; mov 12,d0`: patches/halation rewrites it here
VKEY = 0x77                                # SCP Saturation cell (sid 119; shares its -2..2 list with sid 186, Custom-on-Vivid saturation; MOVIE_COLOUR "Buttons")
SCR, SCR_OLD, SCR_RES = 0x60e4cea8, 'f8972004461c', 0x60e4ceae      # screen lookups (as v0.15 mc)
SCR2, SCR2_OLD, SCR2_RES = 0x60e4cf21, '431cf1d6f89b22', 0x60e4cf28
# SsMenuLv machine (descriptor 0x611a3bc8 = {29 states, 112 events, 138 handlers}; dispatcher 0x60d11448): events 0x611a2888 {u32 code,
# u32 index}, handler words 0x611a2c08, u8 matrix 0x611a2e30 indexed EVENT-major: handler = word[matrix[event_index * 29 + state - 1]]
SM_DESC, SM_EV, SM_FN, SM_MX, SM_NST, SM_NEV = 0x611a3bc8, 0x611a2888, 0x611a2c08, 0x611a2e30, 29, 112
SCP_STATE, SC_REL = 3, 0x60e56f3f          # state 3 = the SCP (OK -> DtlScp 0x60e56a7f); its INFO release handler (cycles sid 281, leaves)
SCP_HOLD, SCP_KEY, CELL = 0x61fc4328, 0x61fc4370, 0x60e4d144          # SCP screen holder, state-7 key word, focused cell sid getter
INIT_WORDS = (0x61185be0, 0x61185c18, 0x61185c50, 0x61185c88)        # COLOR1-4 parent records +4


def put(spec, stock, addr, old, new, why):
    im = MV.img_of(spec, stock)
    if im[addr - BASE:addr - BASE + len(old)] != old:
        raise SystemExit(f'{addr:#x}: {im[addr - BASE:addr - BASE + len(old)].hex()} != {old.hex()} ({why})')
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a, n = int(e['addr'], 16), len(e['new']) // 2
            if a <= addr and addr + len(new) <= a + n:
                b = bytearray.fromhex(e['new']); b[addr - a:addr - a + len(new)] = new; e['new'] = b.hex(); e['why'] += f' [ap_custom: {why}]'
                return
            if a < addr + len(new) and addr < a + n:
                raise SystemExit(f'{addr:#x}: straddles edit {e["addr"]}')
    spec['edits'].append(dict(kind='0x100', addr=hex(addr), expect=stock[addr - BASE:addr - BASE + len(new)].hex(), new=new.hex(), source=SRC, why=f'ap_custom: {why}'))


def check_free(spec, stock, im):
    import numpy as np
    for x in spec['edits']:
        if not x['addr'].startswith('off:'):
            a, n = int(x['addr'], 16), len(x['new']) // 2
            if a < END and AT < a + n:
                raise SystemExit(f'overlap with edit {x["addr"]}')
    for name, d in (('stock', stock), ('v0.29a', im)):
        for off in range(4):
            w = np.frombuffer(d[off:off + (len(d) - off) // 4 * 4], dtype='<u4')
            for k in np.nonzero(((w >= AT) & (w < END + 16)) | ((w >= AT + 0x40000000) & (w < END + 0x40000000 + 16)))[0]:
                at = BASE + off + 4 * int(k)
                if at not in REFS:
                    raise SystemExit(f'{name}: reference into {AT:#x}..{END:#x} at {at:#x}')
    for r in REFS:
        if not AT <= struct.unpack_from('<I', stock, r - BASE)[0] < END + 16:
            raise SystemExit(f'step-table word {r:#x} differs')


def tgt(im, a):
    return a + struct.unpack_from('<i', im, a + 1 - BASE)[0]


def apply(spec, version='0.30a1'):
    stock = STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    im = MV.img_of(spec, stock)
    check_free(spec, stock, im)
    mv, mw, ml = spec['v026_movie']['symbols'], spec['v026_movie']['wheel_symbols'], spec['v026_movie']['label_symbols']
    h = lambda d, k: int(d[k], 16)
    le, st_ = spec['look_editor']['symbols'], spec['look_editor']['stock']
    sh_msg = h(spec['sharp_off']['symbols'], 'sh_msg')
    # previous owners: each hook must still point where v0.29a has it
    owners = {MV.KEY_SITE: h(mv, 'mv_key'), MV.MSG_SITE: sh_msg, MV.S_SITE: h(mv, 'mv_s'), MV.TBL_SITES[0]: h(mw, 'mv_tbl'), MV.TBL_SITES[1]: h(mw, 'mv_tbl'),
              MV.LC: h(mw, 'mv_lc'), CCG_CALL: h(mw, 'mv_ccg'), MV.LB_A: h(ml, 'mv_la'), MV.LB_B: h(ml, 'mv_lc2'), MV.SD_BACK: h(mw, 'mv_trig'), MVT_TAIL: h(le, 'ed_trig'),
              SCP_CALL: GETTER, WBP_CALL: GETTER, **{s: GETTER for s in CAP_SITES}}
    for a, t in owners.items():
        if im[a - BASE] not in (0xdc, 0xdd, 0xcd) or tgt(im, a) != t:
            raise SystemExit(f'{a:#x}: not a call / jmp to {t:#x}')
    for s in CAP_SITES + [SCP_CALL, WBP_CALL]:
        if im[s - BASE] != 0xdd or im[s + 5 - BASE:s + 7 - BASE] != b'\xc0\x0c' or b'\x90\x00' not in im[s - 6 - BASE:s - BASE]:
            raise SystemExit(f'{s:#x}: not `mov 0,a0 .. call getter,[d2,d3],12`')
    for i, s in enumerate(CAP_SITES):
        key = {0: 38017, 1: 63153}.get(i, 63210)
        if struct.pack('<I', key)[:2] not in stock[s - (24 if i == 1 else 14) - BASE:s - BASE]:
            raise SystemExit(f'{s:#x}: key {key} not loaded before the call')
    for i, s in enumerate(CAP_SITES[2:]):
        pre = stock[s - 3 - BASE:s - BASE]
        if (i == 0 and pre[-1:] != b'\x04') or (i > 0 and pre[1:] != bytes([0x85, i])):
            raise SystemExit(f'{s:#x}: S index {i} not set before the call')
    if im[TBLX - BASE:TBLX + 5 - BASE].hex() != TBLX_OLD or im[LB_HIT - 2 - BASE:LB_HIT + 4 - BASE].hex() != LB_HIT_OLD:
        raise SystemExit('tbl_x or mv_lb hit point differs')
    if im[MV.KEY_SITE + 5 - BASE:MV.KEY_SITE + 7 - BASE] != b'\xcb\xcb' or im[MV.MSG_SITE + 5 - BASE:MV.MSG_SITE + 8 - BASE] != b'\xcb\xcb\xcb' or im[MV.LC + 5 - BASE] != 0xcb:
        raise SystemExit('jmp padding differs')
    u32 = lambda a: struct.unpack_from('<I', im, a - BASE)[0]
    po_init = u32(INIT_WORDS[0])
    po = spec['page_order']['po_init']
    if any(u32(w) != po_init for w in INIT_WORDS) or po_init != int(po[0] if isinstance(po, list) else po, 16):
        raise SystemExit('COLOR1-4 init words differ')
    if im[SCR - BASE:SCR + 6 - BASE].hex() != SCR_OLD or im[SCR2 - BASE:SCR2 + 7 - BASE].hex() != SCR2_OLD:
        raise SystemExit('screen lookup entries not stock')
    evix = {struct.unpack_from('<I', im, SM_EV + 8 * i - BASE)[0]: struct.unpack_from('<I', im, SM_EV + 8 * i + 4 - BASE)[0] for i in range(SM_NEV)}
    mx = lambda st, e: im[SM_MX + e * SM_NST + st - 1 - BASE]
    fn = lambda k: u32(SM_FN + 4 * k)
    if u32(SM_DESC) != 0x70001d or u32(SM_DESC + 4) != 0x70008a or (u32(SM_DESC + 8), u32(SM_DESC + 12), u32(SM_DESC + 16)) != (SM_MX, SM_FN, SM_EV):
        raise SystemExit('SsMenuLv descriptor differs')
    info_codes = [c for c in evix if c in (0x9014, 0x9015)]
    rel_ix = mx(SCP_STATE, evix[0x9015])
    users = [(st, e) for st in range(1, SM_NST + 1) for e in range(SM_NEV) if mx(st, e) == rel_ix]
    if sorted(info_codes) != [0x9014, 0x9015] or fn(mx(SCP_STATE, evix[0x900c])) != 0x60e56a7f or fn(rel_ix) != SC_REL or users != [(SCP_STATE, evix[0x9015])]:
        raise SystemExit('SCP state / INFO release handler differs')
    sc_word = SM_FN + 4 * rel_ix
    sub = dict(state=hex(MV.STATE), lim=hex(MV.LIM), pool=hex(MV.POOL), neg_pool=hex((-MV.POOL) & 0xffffffff), bmagic=hex(MV.BMAGIC),
               vm=MV.VM, vp=MV.VP, vh=MV.VH, va=MV.VA, vt=MV.VT, fb=MV.FB, vmagic=hex(MV.VMAGIC), vtmagic=hex(MV.VTMAGIC), vfile=hex(MV.VFILE), pmark=hex(MV.PMARK),
               am=AM, ap3=AP3, atr=ATR, pend=PEND, arm=ARM, boot=hex(BOOT), retries=RETRIES, vkey=hex(VKEY), ev_info=hex(0x9015), scp_hold=hex(SCP_HOLD), scp_key=hex(SCP_KEY), amagic=hex(AMAGIC), atmagic=hex(ATMAGIC), k44=hex(K44), k24=hex(K24), dirty=MV.DIRTY, status=MV.STATUS, old=MV.OLD,
               all0=MV.ALL0, all1=MV.ALL1, ckey=hex(MV.CKEY), ev_press=hex(SB3.EV_PRESS), nmagic=hex(struct.unpack('<I', b'EP7N')[0]), fmagic=hex(MV.FMAGIC), lsize=MV.LSIZE)
    syms = dict(ep7_getter=GETTER, ep7_sget=SGET, ep7_mv_s=h(mv, 'mv_s'), ep7_mv_key=h(mv, 'mv_key'), ep7_key_ret=MV.KEY_RET, ep7_msg_ret=MV.MSG_RET, ep7_sh_msg=sh_msg,
                ep7_mv_tbl=h(mw, 'mv_tbl'), ep7_lc_no=MV.LC_NO, ep7_lc_open=MV.LC_OPEN, ep7_mv_lc=h(mw, 'mv_lc'), ep7_mv_ccg=h(mw, 'mv_ccg'), ep7_mv_la=h(ml, 'mv_la'),
                ep7_mv_lc2=h(ml, 'mv_lc2'), ep7_ret_a=MV.RET_A, ep7_ret_b=MV.RET_B, ep7_lb_hit=LB_HIT, ep7_mv_trig=h(mw, 'mv_trig'), ep7_trig=h(le, 'ed_trig'),
                ep7_mv_rng=h(mw, 'mv_rng'), ep7_scr_resume=SCR_RES, ep7_scr2_resume=SCR2_RES, ep7_po_init=po_init, ep7_sc_rel=SC_REL, ep7_cell=CELL, ep7_crc=h(le, 'ed_crc'), ep7_wfile=h(le, 'ed_wfile'), ep7_m_r=h(le, 'ed_m_r'),
                **{k: int(st_[k], 16) for k in ('ep7_malloc', 'ep7_free', 'ep7_fopen', 'ep7_fclose', 'ep7_fread')})
    # patches/halation edits ap_load's zero check at a fixed address (AP_ZC): keep it there with nops after ap_pre's call
    src = (HERE / 'ap.s.in').read_text()
    code, lst, s, _ = SB3.assemble(SB3.subst(src, dict(sub, pad='')), AT, syms)
    pad = AP_ZC - (AT + code.index(bytes.fromhex(ZC_OLD)))
    if pad < 0 or code.count(bytes.fromhex(ZC_OLD)) != 1:
        raise SystemExit(f'ap_load zero check would move off {AP_ZC:#x} ({pad})')
    code, lst, s, _ = SB3.assemble(SB3.subst(src, dict(sub, pad=' .fill %d,1,0xcb' % pad if pad else '')), AT, syms)
    if code[AP_ZC - AT:AP_ZC - AT + 7].hex() != ZC_OLD:
        raise SystemExit('ap_load zero check not at its fixed address')
    if AT + len(code) > END:
        raise SystemExit(f'{len(code)} B does not fit {END - AT}')
    ins = SB3.disasm(code, AT, s['ap_end'])
    if any(op in BAD for _, op, _ in ins) or any(k == 'abs' for _, _, k, _ in SB3.store_audit(ins)) or any(code[a - AT] == 0xfb for a, _, _ in ins):
        raise SystemExit('forbidden instruction, fb form or absolute store')
    spec['edits'].append(dict(kind='0x100', addr=hex(AT), expect=stock[AT - BASE:AT - BASE + len(code)].hex(), new=code.hex(), source=SRC,
                              why=f'ap_custom: AP Vivid slot ({len(code)} B, dead EVF gamma tables 0x601df13c..)'))
    rel = lambda a, d: struct.pack('<i', d - a)
    for a, t in owners.items():
        new = {MV.KEY_SITE: 'ap_key', MV.MSG_SITE: 'ap_msg', MV.S_SITE: 'ap_s', MV.TBL_SITES[0]: 'ap_tb', MV.TBL_SITES[1]: 'ap_tb', MV.LC: 'ap_lc', CCG_CALL: 'ap_ccg',
               MV.LB_A: 'ap_la', MV.LB_B: 'ap_lb2', MV.SD_BACK: 'ap_pre', MVT_TAIL: 'ap_post'}.get(a, 'ap_get')
        put(spec, stock, a + 1, rel(a, t), rel(a, s[new]), f'{a:#x} -> {new} (was {t:#x})')
    put(spec, stock, TBLX, bytes.fromhex(TBLX_OLD), MV.jmp(TBLX, s['ap_tx'], 5), 'tbl_x -> ap_tx')
    put(spec, stock, SCR, bytes.fromhex(SCR_OLD), MV.jmp(SCR, s['ap_scr'], 6), 'screen lookup entry -> ap_scr')
    put(spec, stock, SCR2, bytes.fromhex(SCR2_OLD), MV.jmp(SCR2, s['ap_scr2'], 7), 'screen lookup 2 entry -> ap_scr2')
    put(spec, stock, sc_word, struct.pack('<I', SC_REL), struct.pack('<I', s['ap_sinfo']), f'SCP (state 3) INFO release handler word {rel_ix} -> ap_sinfo')
    for w in INIT_WORDS:
        put(spec, stock, w, struct.pack('<I', po_init), struct.pack('<I', s['ap_init']), f'COLOR record +4 {w:#x} -> ap_init (was {po_init:#x})')
    if version:
        spec = FV.apply(spec, version)
    spec['ap_custom'] = dict(built_by=SRC, version=version, code_at=hex(AT), code_len=len(code), claim=[hex(AT), hex(END)], heap=dict(am=AM, ap3=AP3, atr=ATR, pend_p3=PEND, arm_p3=ARM),
                             ap_values=[14] + list(range(209, 217)), card='EP7MOD/AP.BIN (96 B, MOVIE.BIN format)',
                             sites={hex(a): hex(t) for a, t in owners.items()}, symbols={k: hex(v) for k, v in s.items() if k.startswith('ap_')})
    return spec


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--version', default='0.30a1')
    a = ap.parse_args()
    spec = apply(json.loads(a.spec.read_text()), a.version)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(spec, indent=1))
    print(json.dumps({k: v for k, v in spec['ap_custom'].items() if k not in ('symbols', 'sites')}), spec['fw_version']['value'])
