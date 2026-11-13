#!/usr/bin/env python3
"""Camera diagnosis layer (E-P7 1.1, v0.32+). Offline. docs/PLUGINS.md §10; dg.s.in has the contract.

  .venv/bin/python -I patches/diag/build.py generated/v032/edits.json --out OUT.json

apply(spec, version) -> spec. Layer LAST (after plugin_loader, keyhook and overlay_probe). Code `.dg` in the overlay
claim (sec 5, dead sdk-api handlers) after `.ov`. Edits:
  - pl_ap's first instruction (CALL16 ap_load, 5 B) -> `jmp dg_ap`: the loader with stage marks (pl_ap / pl_chk bodies
    become unreachable, the API table stays keyhook's kh_api);
  - the Firmware screen's two Body value calls (pl_fw) -> dg_fw: the "L/OK" readout (K = keyhook Fn stage byte);
  - Colour Profile view +0 word (ov_upd) -> dg_upd, view +4 word (stock dtor) -> dg_dtor;
  - GE paint routine 0x60d005ef `mov (164,a2),a2; calls (a2)` (6 B) -> `jmp dg_paint` + nop, and the two window +164
    words go back to stock (the site sees every window's post-paint, not only those two classes).
  - TRACE (PLUGINS §13): site jmps 0x60ce011a / 0x60cebc9a -> dg_key0 / dg_key1 (log, then kh_chk / kh_chk2), the
    twin's kmap call 0x60ce0190 -> dg_twin (log, replay), ap_post's half-press block 0x601df6fa -> dg_half (dump to
    EP7MOD/TRACE.TXT). Log block pointer in P+860/864/868, gated on the .bss pad 0x6203bcb3.
"""
import argparse, copy, importlib.util, json, struct, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


OV = _load('ep7_overlay_dg', ROOT / 'patches/overlay_probe/build.py')
KH, PL, ST, SB3, np = OV.KH, OV.PL, OV.ST, OV.SB3, OV.np
STOCK = OV.STOCK
BASE, SRC = 0x60020020, 'patches/diag'

CLAIM = OV.CLAIM                                  # overlay claim 0x607b8420-0x607c8420 (sec 5)
AT, END = 0x607b8700, OV.END                      # after .ov (ends 0x607b868c)
BOOT = 0x6203c8bb                                 # ap_custom boot byte: bit 0 marks cleared, bits 4-7 retries; 1-3 = L
FLAG, CNT = 0x622ab792, 0x622ab793                # overlay .bss pad, cached alias
VIEW_W, VIEW_BODY = OV.VIEW_W, OV.VIEW_BODY       # view +0
DTOR_W, VIEW_DTOR = OV.VIEW_W + 4, 0x60dec697     # view +4
WIN_W, WIN_STOCK = OV.WIN_W, OV.WIN_STOCK
PAINT, PAINT_LEN, PAINT_BACK = 0x60d005ef, 6, 0x60d005f5
PAINT_STOCK = bytes.fromhex('fa2aa400f0f2')       # mov (164,a2),a2; calls (a2)
FW_SITES, FW_FRAME = PL.FW_SITES, PL.FW_FRAME
BAD = PL.BAD
KSTAGE = 0x6203bcb2                               # keyhook Fn stage byte (PLUGINS §12; keyhook check_stage proves the pad)
SETFONT, CURWIN = 0x60d0fce0, 0x61fb3138          # gc_set_font (call [a2],8); current window (.bss, stock getter 0x60d3379b)

# ---- key-event TRACE (PLUGINS §13): ring log + per-half-press card dump ----
SITE0 = 0x60ce011a                                # site-0 jmp (keyhook kh): log here then chain to kh
SITE1 = 0x60cebc9a                                # site-1 jmp (keyhook kh2)
TWIN, TWIN_BACK = 0x60ce0190, 0x60ce0197          # unhooked twin's kmap call (same copy-loop shape); log-only
TWIN_STOCK = bytes.fromhex('dd7598feff8004')      # call 0x60cc9a05,[d2],4 (7 B)
HALF, HALF_BACK = 0x601df6fa, 0x601df6ff          # ap_post's gated prologue: runs on every half-press, before the EP7U gate
HALF_STOCK = bytes.fromhex('cff0f8fefc')          # movm [d2,d3,a2,a3],(sp); add -4,sp (5 B)
KMAP = 0x60cc9a05                                 # kmap (ca_key_generic's input mapper); the twin replays it
WMODE, FWRITE = 0x60a65d37, 0x60635041            # fopen mode "w" (stock card-write 0x60765cc8); fwrite [d2,d3,a2,a3],24
PLOG, PHEAD, PCNT = 860, 864, 868                # ring-log slots in the real P: base, bytes ever logged, paints since dump
                                                  # (+860..927 has no user: SPLIT_TONE P+848 list; loader +852/856)
LSIZE = 16384                                     # class-2 block for the ring log (1024 x 16-B entries)
LOGON = 0x6203bcb3                                # boot-cleared .bss pad: 1 = this power-on's log block is in P (dg_ap only)
PCAP = 64                                         # PT entries per dump (keeps the key events in the ring)
FREL = 0x60d10708                                 # font release after a text draw (every stock 0x60d0fce0 user calls it)
TITLE = b'CADUCEUS TRACE 1\n'
POOL2, POOL2_END = 0xa1dd8d40, 0xa1e85800         # class-2 pool (malloc 2049..16384 B): the log base must lie inside it
T_KEY0, T_KEY1, T_KEYT, T_PAINT, T_PD, T_PS, T_DEC0, T_DEC1 = 0, 1, 2, 3, 4, 5, 6, 7   # entry tags (low byte)


def u32(b):
    return struct.unpack('<I', b)[0]


def check_base(spec, stock, im):
    for k in ('plugin_loader', 'keyhook', 'overlay_probe'):
        if k not in spec:
            raise SystemExit(f'needs {k}')
    if int(spec['keyhook'].get('stage', '0'), 16) != KSTAGE:
        raise SystemExit('keyhook has no Fn stage byte at 0x6203bcb2 (needs the PLUGINS §12 keyhook)')
    if 'diag' in spec:
        raise SystemExit('diag already applied')
    pl, ov = spec['plugin_loader'], spec['overlay_probe']
    pl_ap, pl_fw = int(pl['symbols']['pl_ap'], 16), int(pl['symbols']['pl_fw'], 16)
    apl = int(pl['ap_load'], 16)
    if im[pl_ap - BASE:pl_ap + 5 - BASE] != PL.call16_bytes(pl_ap, apl, PL.AP_FRAME):
        raise SystemExit('pl_ap does not start with call ap_load')
    for s in FW_SITES:
        if im[s - BASE:s + 7 - BASE] != PL.call_bytes(s, pl_fw, FW_FRAME):
            raise SystemExit(f'{s:#x} is not call pl_fw')
    if u32(im[VIEW_W - BASE:VIEW_W + 4 - BASE]) != int(ov['symbols']['ov_upd'], 16):
        raise SystemExit('view +0 is not ov_upd')
    if u32(im[DTOR_W - BASE:DTOR_W + 4 - BASE]) != VIEW_DTOR or stock[VIEW_DTOR - BASE:VIEW_DTOR + 2 - BASE] != b'\xcf\x30':
        raise SystemExit('view +4 is not the stock dtor 0x60dec697 (movm [a2,a3])')
    for w in WIN_W:
        if u32(im[w - BASE:w + 4 - BASE]) != int(ov['symbols']['ov_post'], 16):
            raise SystemExit(f'{w:#x} is not ov_post')
    if im[PAINT - BASE:PAINT + PAINT_LEN - BASE] != PAINT_STOCK or stock[PAINT - BASE:PAINT + PAINT_LEN - BASE] != PAINT_STOCK:
        raise SystemExit('paint site bytes differ')
    if int(ov['region'][1], 16) > AT:
        raise SystemExit('.ov reaches .dg')
    # the .bss bytes: BOOT only through ap_custom's code (already in the image), FLAG / CNT not referenced at all
    d = np.frombuffer(im, np.uint8).astype(np.int64)
    w = d[:-3] | (d[1:-2] << 8) | (d[2:-1] << 16) | (d[3:] << 24)
    for a in (FLAG, CNT, FLAG + 0x40000000, CNT + 0x40000000, BOOT + 0x40000000):
        hits = [int(i) + BASE for i in np.nonzero(w == a)[0]]
        ovr = (int(ov['region'][0], 16), int(ov['region'][1], 16))
        if [h for h in hits if not (ovr[0] <= h < ovr[1])]:
            raise SystemExit(f'{a:#x} referenced outside .ov: {[hex(h) for h in hits]}')
    syms = dict(ep7_ap_load=apl, ep7_api=int(spec['keyhook']['api'], 16), ep7_fw_val=int(pl['fw_val'], 16),
                ep7_upd_body=VIEW_BODY, ep7_view_dtor=VIEW_DTOR, ep7_paint_back=PAINT_BACK,
                ep7_drawtext=OV.DRAWTEXT, ep7_setcol=OV.SETCOL, ep7_setfont=SETFONT)
    # font fallback (PLUGINS §11): current window 0x61fb3138 (getter 0x60d3379b), its +488 = 0x60d00f90 (u16 +108),
    # 0x60d0fce0 (gc, style id) -> a0 font; checked against the stock bytes
    if stock[0x60d3379b - BASE:0x60d3379b - BASE + 9] != bytes.fromhex('fca03831fb61de0000'):
        raise SystemExit('current-window getter differs')
    for vt in (0x60f9477c, 0x60fac34c):
        if u32(stock[vt + 488 - BASE:vt + 492 - BASE]) != 0x60d00f90:
            raise SystemExit('window +488 differs')
    if stock[0x60d00f90 - BASE:0x60d00f90 - BASE + 6] != bytes.fromhex('f8606cde0000'):
        raise SystemExit('window +488 body differs')
    if stock[SETFONT - BASE:SETFONT - BASE + 2] != b'\x92\x1c':
        raise SystemExit('0x60d0fce0 differs')
    for k in ('ep7_malloc', 'ep7_free', 'ep7_fopen', 'ep7_fclose', 'ep7_fread', 'ep7_fseek', 'ep7_ftell',
              'ep7_fm_crc', 'ep7_fm_mode', 'ep7_setter', 'ep7_ap_p'):
        syms[k] = PL.SYMS[k]
    # ---- TRACE sites (PLUGINS §13): the two key jmps now reach kh / kh2; the twin and ap_post prologue are stock ----
    kh0, kh1 = (int(spec['keyhook']['symbols'][k], 16) for k in ('kh', 'kh2'))
    jmp5 = lambda at, t: b'\xdc' + struct.pack('<i', t - at)
    if im[SITE0 - BASE:SITE0 + 5 - BASE] != jmp5(SITE0, kh0):
        raise SystemExit('site 0 is not jmp kh')
    if im[SITE1 - BASE:SITE1 + 5 - BASE] != jmp5(SITE1, kh1):
        raise SystemExit('site 1 is not jmp kh2')
    if im[TWIN - BASE:TWIN + 7 - BASE] != TWIN_STOCK or stock[TWIN - BASE:TWIN + 7 - BASE] != TWIN_STOCK:
        raise SystemExit('twin kmap call bytes differ')
    if im[HALF - BASE:HALF + 5 - BASE] != HALF_STOCK:          # ap_post is ap_custom code (in the image, not in stock)
        raise SystemExit('ap_post gated prologue bytes differ')
    if stock[WMODE - BASE] != 0x77 or stock[WMODE + 1 - BASE] != 0:
        raise SystemExit('fopen "w" mode string differs')
    if stock[FWRITE - BASE:FWRITE + 2 - BASE] != b'\x47\x04' or stock[KMAP - BASE:KMAP + 2 - BASE] != b'\x3c\x20':
        raise SystemExit('fwrite / kmap head bytes differ')
    if stock[FREL - BASE:FREL + 4 - BASE] != bytes.fromhex('b000c80e'):
        raise SystemExit('font release 0x60d10708 differs')
    # LOGON: the one pad byte keyhook's check_stage left free (no abs32 word equals it in either alias)
    for a in (LOGON, LOGON + 0x40000000):
        if np.nonzero(w == a)[0].size:
            raise SystemExit(f'{a:#x} is referenced')
    khs = spec['keyhook']['symbols']
    syms.update(ep7_khchk=int(khs['kh_chk'], 16), ep7_khchk2=int(khs['kh_chk2'], 16), ep7_khmiss=int(khs['kh_miss'], 16),
                ep7_kh2miss=int(khs['kh2_miss'], 16), ep7_frel=FREL)
    syms.update(ep7_kh0=kh0, ep7_kh1=kh1, ep7_kmap=KMAP, ep7_twin_back=TWIN_BACK, ep7_half_back=HALF_BACK,
                ep7_wmode=WMODE, ep7_fwrite=FWRITE)
    return syms, pl_ap


def build_code(syms):
    sub = dict(PL.sub_table(), boot=hex(BOOT), flag=hex(FLAG), cnt=hex(CNT), view_body=hex(VIEW_BODY),
               view_dtor=hex(VIEW_DTOR), state=hex(SB3.STATE), pool=hex(SB3.POOL), lim=hex(SB3.LIM),
               bmagic=hex(SB3.MAGIC), curwin=hex(CURWIN), kstage=hex(KSTAGE), emark=680, emagic=hex(int.from_bytes(b'EP7E', 'little')), axis=684, x_axis=4,
               plog=PLOG, phead=PHEAD, pcnt=PCNT, pcap=PCAP, lsize=LSIZE, lsize1=LSIZE + 1, lmask=hex(LSIZE - 16),
               neg_pool2=hex((-POOL2) & 0xffffffff), pool2_span=hex(POOL2_END - POOL2), logon=hex(LOGON),
               tpaint=T_PAINT, tpd=T_PD, tps=T_PS, tkey0=T_KEY0, tkey1=T_KEY1, tkeyt=T_KEYT, tdec0=T_DEC0, tdec1=T_DEC1,
               tlen=len(TITLE))
    tmpl = (HERE / 'dg.s.in').read_text()
    sub['buildid'] = hex(zlib.crc32((tmpl + repr(sorted(sub.items())) + repr(sorted(syms.items()))).encode()))
    src = SB3.subst(tmpl, sub)
    code, lst, sy, dis = SB3.assemble(src, AT, syms)
    if sy['_start'] != AT or sy['dg_ap'] != AT or AT + len(code) > END:
        raise SystemExit('layout')
    ins = SB3.disasm(code, AT, sy['dg_sA'])
    if any(op in BAD for _, op, _ in ins) or any(op.startswith('.') or op == '(bad)' for _, op, _ in ins):
        raise SystemExit('forbidden or undecodable instruction')
    if any(code[a - AT] == 0xfb for a, _, _ in ins):
        raise SystemExit('fb-prefixed form')
    st = SB3.store_audit(ins)
    if any(k == 'abs' for _, _, k, _ in st):
        raise SystemExit(f'absolute store: {[s for s in st if s[2] == "abs"]}')
    ext = {syms[k] for k in syms}
    for a, op, args in ins:
        if op in ('call', 'jmp') and args.startswith('0x'):
            t = int(args.split(',')[0], 16)
            if t not in ext and not (AT <= t < AT + len(code)):
                raise SystemExit(f'unexpected target {op} {t:#x} at {a:#x}')
    if code[sy['dg_path'] - AT:][:21] != b'C:\\EP7MOD\\PLUGIN.BIN\0':
        raise SystemExit('path')
    if code[sy['dg_tpath'] - AT:][:20] != b'C:\\EP7MOD\\TRACE.TXT\0' or code[sy['dg_title'] - AT:][:len(TITLE)] != TITLE:
        raise SystemExit('trace path / title')
    return code, sy, lst, int(sub['buildid'], 16)


def drop_noops(spec):
    """Only the two window +164 words, now back to stock (other layers' no-op edits stay as they were)."""
    spec['edits'] = [e for e in spec['edits'] if not (e['kind'] == '0x100' and e['addr'] in {hex(w) for w in WIN_W}
                                                      and e.get('expect') == e['new'])]


def apply(spec, version='0.32'):
    stock = STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    im = ST.img_of(spec, stock)
    syms, pl_ap = check_base(spec, stock, im)
    code, sy, lst, bid = build_code(syms)
    spec['edits'].append(dict(kind='0x100', addr=hex(AT), expect=stock[AT - BASE:AT - BASE + len(code)].hex(),
                              new=code.hex(), source=SRC, why=f'diag {version} .dg ({len(code)} B, sec 5 overlay claim)'))
    jmp = lambda at, t: b'\xdc' + struct.pack('<i', t - at)
    apl = syms['ep7_ap_load']
    PL.put(spec, stock, pl_ap, PL.call16_bytes(pl_ap, apl, PL.AP_FRAME), jmp(pl_ap, sy['dg_ap']),
           'diag: pl_ap -> jmp dg_ap (loader with stage marks, P+852 cleared first)')
    pl_fw = int(spec['plugin_loader']['symbols']['pl_fw'], 16)
    for s in FW_SITES:
        PL.put(spec, stock, s, PL.call_bytes(s, pl_fw, FW_FRAME), PL.call_bytes(s, sy['dg_fw'], FW_FRAME),
               f'diag: Firmware Body value call {s:#x} -> dg_fw (L/O readout)')
    ov_upd, ov_post = (int(spec['overlay_probe']['symbols'][k], 16) for k in ('ov_upd', 'ov_post'))
    PL.put(spec, stock, VIEW_W, struct.pack('<I', ov_upd), struct.pack('<I', sy['dg_upd']), 'diag: view +0 -> dg_upd')
    PL.put(spec, stock, DTOR_W, struct.pack('<I', VIEW_DTOR), struct.pack('<I', sy['dg_dtor']), 'diag: view +4 -> dg_dtor')
    for w in WIN_W:
        PL.put(spec, stock, w, struct.pack('<I', ov_post), struct.pack('<I', WIN_STOCK), f'diag: window +164 {w:#x} back to stock')
    PL.put(spec, stock, PAINT, PAINT_STOCK, jmp(PAINT, sy['dg_paint']) + b'\xcb',
           'diag: GE paint post-paint call -> jmp dg_paint + nop')
    # ---- key-event TRACE (PLUGINS §13): log at the three key sites, dump on a later half-press ----
    PL.put(spec, stock, SITE0, jmp(SITE0, syms['ep7_kh0']), jmp(SITE0, sy['dg_key0']),
           'diag: site 0 jmp -> dg_key0 (log) -> kh')
    PL.put(spec, stock, SITE1, jmp(SITE1, syms['ep7_kh1']), jmp(SITE1, sy['dg_key1']),
           'diag: site 1 jmp -> dg_key1 (log) -> kh2')
    PL.put(spec, stock, TWIN, TWIN_STOCK, jmp(TWIN, sy['dg_twin']) + b'\xcb\xcb',
           'diag: twin kmap call -> jmp dg_twin (log-only; replays the call)')
    PL.put(spec, stock, HALF, HALF_STOCK, jmp(HALF, sy['dg_half']),
           'diag: ap_post gated prologue -> jmp dg_half (TRACE.TXT dump each half-press)')
    drop_noops(spec)
    for e in spec['edits']:
        if e.get('source') == PL.SRC and e['why'].startswith('plugin_loader: diag: '):
            e['source'], e['why'] = SRC, e['why'][len('plugin_loader: '):]
    final = ST.img_of(spec, stock)
    lo5, hi5, off5 = KH.sec(stock, OV.SEC5)
    if not (lo5 <= AT and AT + len(code) <= hi5):
        raise SystemExit('not inside section 5')
    new = OV.refs_into(final, (AT, END), off5) - OV.refs_into(im, (AT, END), off5)
    allowed = {pl_ap, VIEW_W, DTOR_W, PAINT, SITE0, SITE1, TWIN, HALF} | set(FW_SITES)
    bad = [a for a in new if not (AT <= a < AT + len(code)) and a not in allowed]
    if bad:
        raise SystemExit(f'new reference into .dg from {[hex(a) for a in sorted(bad)]}')
    spec['diag'] = dict(
        built_by=SRC, version=version, region=[hex(AT), hex(AT + len(code))], bytes=len(code), boot=hex(BOOT),
        flag=hex(FLAG), cnt=hex(CNT), paint_site=hex(PAINT), view_words=[hex(VIEW_W), hex(DTOR_W)],
        readout='Firmware Body value "L/OK": L loader stage 0-7, O overlay stage 0-5, K Fn stage 0-6', kstage=hex(KSTAGE),
        trace=dict(path='EP7MOD/TRACE.TXT', build_id=hex(bid), plog=PLOG, phead=PHEAD, pcnt=PCNT, pcap=PCAP, logon=hex(LOGON),
                   size=LSIZE, entry_bytes=16,
                   sites={'K0': hex(SITE0), 'K1': hex(SITE1), 'KT': hex(TWIN), 'PT': hex(PAINT)},
                   half_press=hex(HALF), tags={'K0': T_KEY0, 'K1': T_KEY1, 'KT': T_KEYT, 'PT': T_PAINT, 'PD': T_PD, 'PS': T_PS,
                         'D0': T_DEC0, 'D1': T_DEC1, 'header': -1}),
        symbols={k: hex(v) for k, v in sy.items() if k.startswith(('dg_', 'a_', 'f_', 'p_', 'd_', 'lw_', 'h_', 'du_', 'n_'))})
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
    print(json.dumps({k: v for k, v in spec['diag'].items() if k != 'symbols'}, indent=1))
