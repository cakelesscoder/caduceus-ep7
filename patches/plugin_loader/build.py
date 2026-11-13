#!/usr/bin/env python3
"""SD-card plugin layer v1 (EP7MOD/PLUGIN.BIN): resident loader, API table v1, Firmware-screen text hook. Offline.
docs/PLUGINS.md; pl.s.in has the contract.

  .venv/bin/python -I patches/plugin_loader/build.py generated/v032/edits.json --out OUT.json

apply(spec, version) -> spec. Layer LAST, after fw_version (fw_version's own guard refuses any later re-run, because
.pla sits in its dead table): edits
  - ap_post's `call ap_load,[d2,d3,a2,a3],24` (ap_custom, first half-press, once per power-on, a2 = the real P) -> pl_ap,
    which runs ap_load first and then the plugin step;
  - the Firmware screen's two Body value setter calls (0x60d7f271, 0x60d7f2cd; fw_val, frame 88) -> pl_fw;
  - code: .pla in the unclaimed tail of the dead EVF step-10 B table (after fw_version's claim), .plb in mono presets
    part B's unused dead EVF tail. Both section 1, both stock bytes before, only step-table words refer to them.
Heap P+852 ('EP7K' ready) and P+856 (block B), the real P only.
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


ST = _load('split_tone_build_pl', ROOT / 'patches/split_tone/build.py')
SB3 = ST.SB3
np = ST.np
STOCK = ROOT / 'analysis/ep7_1100/00_0100_406a0020.decoded.bin'
BASE, SRC = 0x60020020, 'patches/plugin_loader'

REGIONS = {'.pla': (0x601e1c68, 0x601e1d3c),   # dead EVF step-10 B table 0x601e1c3c..0x601e1d3c after fw_val (36 B, ends 0x601e1c64)
           '.plb': (0x601e1a8c, 0x601e1b3c)}   # dead EVF tail after mono presets part B (mp_end 0x601e1a8c), before ex_rs 0x601e1b3c
SEC1 = (0x60020020, None)                      # section 1 starts at the image base; end read from the descriptor table
STEP_WORDS = ST.STEP_WORDS
FALSE_POS = {0x608ebe66: 'b41c1ea0'}           # inside `mov (7708,sp),d0; cmp 0,d0` (fa b4 1c 1e | a0 00), dis-checked: 0xa01e1cb4

AP_FRAME = 24                                  # ap_post: call ap_load,[d2,d3,a2,a3],24 (d16 form; the only call to ap_load)
FW_SITES = (0x60d7f271, 0x60d7f2cd)            # fw_version: call fw_val,[d2,d3,a2,a3],88
FW_FRAME = 88
SYMS = dict(ep7_fm_crc=0x6143a688, ep7_fm_mode=0x6143a746, ep7_ap_p=ST.AP_P,
            ep7_malloc=0x60022782, ep7_free=0x600227b4, ep7_fopen=0x60634fbc, ep7_fclose=0x60634fc5,
            ep7_fread=0x6063514b, ep7_fseek=0x60635243, ep7_ftell=0x606351d9,
            ep7_getter=0x6005e971, ep7_setter=0x60d4c9df)
# expected first bytes of the entries we call (v0.32 image)
ENTRY = {'ep7_fm_crc': 'f048'}

POOL2, POOL2_END = ST.POOL2, ST.POOL2_END
BSIZE = 16384                                  # one class-2 block, the whole power-on
HDR = 32
MINSZ = HDR + 2                                # header + `clr d0; rets` at the least
PS, PB = 852, 856                              # heap P+852 state, P+856 block
ATR, ATMAGIC = 992, b'EP7U'                    # ap_custom: AP.BIN load tried (set by ap_post before ed_trig)
PMAGIC, RMAGIC = b'EP7P', b'EP7K'
ABI_VER, API_N = 1, 3
FW_ID = bytes.fromhex('5dd9af16')              # stock main SHA-256 bytes 0..3 (as BUNDLES.BIN +20)
TO_CACHED = 0xc0000000                         # + = -0x40000000: uncached 0xa.. -> cached 0x6..
BAD = {'mul', 'mulu', 'div', 'divu', 'setlb', 'llt', 'lne', 'leq', 'lra', 'lcc', 'lcs', 'trap'}
STORES = ['mov a0,(4,sp)', 'mov a3,(856,a2)', 'mov d0,(4,sp)', 'mov d0,(852,a2)']


def u32(b):
    return struct.unpack('<I', b)[0]


def sub_table():
    return dict(atr=ATR, atname=ATMAGIC.decode(), ps=PS, pb=PB, rmagic=hex(u32(RMAGIC)), rname=RMAGIC.decode(),
                bsize=BSIZE, bsize1=BSIZE + 1, minsz=MINSZ, pmagic=hex(u32(PMAGIC)), abi=hex(ABI_VER),
                fwid=hex(u32(FW_ID)), entry=hex((TO_CACHED + HDR) & 0xffffffff), abi_ver=ABI_VER, api_n=API_N)


def fw_text(im, fv):
    """The wide version string inside fw_val (its last bytes)."""
    at, n = int(fv['code_at'], 16), fv['code_len']
    w = (fv['value'] + '\0').encode('utf-16-le')
    i = im[at - BASE:at + n - BASE].rfind(w)
    if i < 0 or (at + i) % 2:
        raise SystemExit('fw_val wide string not found')
    return at + i


def call_bytes(at, target, imm):
    return bytes([0xdd]) + struct.pack('<i', target - at) + bytes([0xf0, imm])


def call16_bytes(at, target, imm):                 # call d16,[d2,d3,a2,a3],imm (5 B)
    return bytes([0xcd]) + struct.pack('<h', target - at) + bytes([0xf0, imm])


def put(spec, stock, addr, old, new, why):
    im = ST.img_of(spec, stock)
    if im[addr - BASE:addr - BASE + len(old)] != old:
        raise SystemExit(f'{addr:#x}: {im[addr - BASE:addr - BASE + len(old)].hex()} != {old.hex()} ({why})')
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a, n = int(e['addr'], 16), len(e['new']) // 2
            if a <= addr and addr + len(new) <= a + n:
                b = bytearray.fromhex(e['new']); b[addr - a:addr - a + len(new)] = new; e['new'] = b.hex()
                e['why'] += f' [plugin_loader: {why}]'
                return
            if a < addr + len(new) and addr < a + n:
                raise SystemExit(f'{addr:#x}: straddles edit {e["addr"]}')
    spec['edits'].append(dict(kind='0x100', addr=hex(addr), expect=stock[addr - BASE:addr - BASE + len(new)].hex(),
                              new=new.hex(), why=f'plugin_loader: {why}', source=SRC))


def sec1_end(stock):
    stub = struct.unpack_from('<I', stock, 0x60046780 - BASE)[0]
    assert stock[stub - BASE:stub - BASE + 2] == b'\xfc\xcc'
    return struct.unpack_from('<I', stock, stub + 2 - BASE)[0]


def check_free(spec, stock, im):
    """Each placement: no edit in it, stock bytes (dead EVF tables), inside section 1, and no reference into it from the
    patched image (abs32 on every alias; d16/d32 call/jmp encodings) except the dead tables' step-table words."""
    end1 = sec1_end(stock)
    for k, (lo, hi) in REGIONS.items():
        if not (0x60020020 <= lo and hi <= end1):
            raise SystemExit(f'{k}: not inside section 1 (ends {end1:#x})')
        for e in spec['edits']:
            if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
                a, n = int(e['addr'], 16), len(e['new']) // 2
                if a < hi and lo < a + n:
                    raise SystemExit(f'{k}: overlaps edit {e["addr"]}')
        if im[lo - BASE:hi - BASE] != stock[lo - BASE:hi - BASE]:
            raise SystemExit(f'{k}: not stock')
    d = np.frombuffer(im, np.uint8).astype(np.int64)
    w = d[:-3] | (d[1:-2] << 8) | (d[2:-1] << 16) | (d[3:] << 24)
    pc = np.arange(len(d) - 8, dtype=np.int64) + BASE
    _, src, dst = struct.unpack_from('<3I', stock, 0x60027068 - BASE)
    for k, (lo, hi) in REGIONS.items():
        for off in (0, 0x40000000, (src - dst) & 0xffffffff, (src - dst + 0x40000000) & 0xffffffff):
            a, b = (lo + off) & 0xffffffff, (hi + off) & 0xffffffff
            for i in np.nonzero((w >= a) & (w < b))[0]:
                at = int(i) + BASE
                if STEP_WORDS[0] <= at < STEP_WORDS[1] or im[at - BASE:at - BASE + 4].hex() == FALSE_POS.get(at):
                    continue
                if True:
                    raise SystemExit(f'{k}: abs32 reference at {at:#x}')
        for op, n in ((0xdd, 4), (0xdc, 4), (0xcd, 2), (0xcc, 2)):
            m = d[:-8] == op
            disp = d[1:-7] | (d[2:-6] << 8) if n == 2 else d[1:-7] | (d[2:-6] << 8) | (d[3:-5] << 16) | (d[4:-4] << 24)
            disp = np.where(disp >= (1 << (8 * n - 1)), disp - (1 << (8 * n)), disp)
            bad = [int(x) + BASE for x in np.nonzero(m & (pc + disp >= lo) & (pc + disp < hi))[0]]
            if bad:
                raise SystemExit(f'{k}: call/jmp encoding into it from {bad[0]:#x}')


def check_base(spec, stock, im):
    fv = spec.get('fw_version')
    if not fv or 'ap_custom' not in spec or 'look_editor' not in spec:
        raise SystemExit('needs the fw_version, ap_custom and look_editor layers')
    if 'plugin_loader' in spec:
        raise SystemExit('plugin_loader already applied')
    sym = {k: int(v, 16) for k, v in spec['ap_custom']['symbols'].items()}
    apl, app = sym['ap_load'], sym['ap_post']
    raw = np.frombuffer(im, np.uint8).astype(np.int64)
    pc = np.arange(len(raw) - 8, dtype=np.int64) + BASE
    calls = []
    for op, n in ((0xdd, 4), (0xcd, 2), (0xdc, 4), (0xcc, 2)):
        m = raw[:-8] == op
        disp = raw[1:-7] | (raw[2:-6] << 8) if n == 2 else raw[1:-7] | (raw[2:-6] << 8) | (raw[3:-5] << 16) | (raw[4:-4] << 24)
        disp = np.where(disp >= (1 << (8 * n - 1)), disp - (1 << (8 * n)), disp)
        calls += [int(x) + BASE for x in np.nonzero(m & (pc + disp == apl))[0]]
    site = [c for c in calls if app <= c < apl]
    if len(site) != 1 or im[site[0] - BASE:site[0] + 5 - BASE] != call16_bytes(site[0], apl, AP_FRAME):
        raise SystemExit(f'ap_post call ap_load not found: {[hex(c) for c in calls]}')
    others = [c for c in calls if c != site[0] and im[c - BASE] in (0xdd, 0xcd)]
    if others:
        raise SystemExit(f'other calls to ap_load: {[hex(c) for c in others]}')
    w = raw[:-3] | (raw[1:-2] << 8) | (raw[2:-1] << 16) | (raw[3:] << 24)
    if len(np.nonzero((w == apl) | (w == apl + 0x40000000))[0]):
        raise SystemExit('ap_load address taken')
    SYMS['ep7_ap_load'] = apl
    for k, b in ENTRY.items():
        if im[SYMS[k] - BASE:SYMS[k] - BASE + len(b) // 2].hex() != b:
            raise SystemExit(f'{k} entry bytes differ')
    if im[SYMS['ep7_fm_mode'] - BASE:SYMS['ep7_fm_mode'] - BASE + 2] != b'r\0' or \
            im[SYMS['ep7_fm_mode'] - 20 - BASE:SYMS['ep7_fm_mode'] - BASE] != b'C:\\EP7MOD\\LOOKS.BIN\0':
        raise SystemExit('fm_mode is not the "r" after LOOKS.BIN')
    if sym['ap_P'] != ST.AP_P:
        raise SystemExit('ap_P moved')
    fva = int(fv['code_at'], 16)
    for s in FW_SITES:
        if im[s - BASE:s + 7 - BASE] != call_bytes(s, fva, FW_FRAME):
            raise SystemExit(f'{s:#x} is not call fw_val,[..],{FW_FRAME}')
    return fva, fw_text(im, fv), site[0], apl


def build_code(fva, ftext):
    syms = dict(SYMS, ep7_fw_val=fva, ep7_fw_text=ftext)
    src = SB3.subst((HERE / 'pl.s.in').read_text(), sub_table())
    out, sy, lst = ST.assemble(src, syms, REGIONS)
    for k, (lo, hi) in REGIONS.items():
        if lo + len(out[k]) > hi:
            raise SystemExit(f'{k}: {len(out[k])} B does not fit {hi - lo}')
    if sy['pl_ap'] != REGIONS['.pla'][0] or sy['pl_chk'] != REGIONS['.plb'][0] or sy['pl_api'] % 4:
        raise SystemExit('layout')
    ins = SB3.disasm(out['.pla'], REGIONS['.pla'][0], sy['pl_api']) + SB3.disasm(out['.plb'], REGIONS['.plb'][0], sy['pl_end'])
    if any(op in BAD for _, op, _ in ins) or any(op.startswith('.') or op == '(bad)' for _, op, _ in ins):
        raise SystemExit('forbidden or undecodable instruction')
    for k in REGIONS:
        lo = REGIONS[k][0]
        stop = sy['pl_end'] if k == '.plb' else sy['pl_api']
        if any(out[k][a - lo] == 0xfb for a, _, _ in ins if lo <= a < stop):
            raise SystemExit('fb-prefixed form')
    st = SB3.store_audit(ins)
    if any(kd == 'abs' for _, _, kd, _ in st):
        raise SystemExit(f'absolute store: {st}')
    ind = sorted({t for _, t, kd, _ in st})
    if ind != STORES:
        raise SystemExit(f'unexpected stores: {ind}')
    api = out['.pla'][sy['pl_api'] - REGIONS['.pla'][0]:][:4 + 4 * API_N]
    if out['.pla'][sy['pl_path'] - REGIONS['.pla'][0]:][:21] != b'C:\\EP7MOD\\PLUGIN.BIN\0':
        raise SystemExit('path')
    near = {'ep7_ap_load': (0xf0, 24), 'ep7_ap_p': (0x80, 8)}
    seen = []
    for a, op, args in ins:
        if op == 'call':
            t = int(args.split(',')[0], 16)
            for k, (rg, imm) in near.items():
                if t == syms[k]:
                    reg = out['.pla'] if a < REGIONS['.plb'][0] or a >= REGIONS['.pla'][0] else out['.plb']
                    lo = REGIONS['.pla'][0] if reg is out['.pla'] else REGIONS['.plb'][0]
                    if reg[a - lo:a - lo + 5] != bytes([0xcd]) + struct.pack('<h', t - a) + bytes([rg, imm]):
                        raise SystemExit(f'CALL16 {k} at {a:#x}')
                    seen.append(k)
    if sorted(seen) != ['ep7_ap_load', 'ep7_ap_p']:
        raise SystemExit(f'near calls {seen}')
    if struct.unpack('<HH3I', api) != (ABI_VER, API_N, ftext, SYMS['ep7_getter'], SYMS['ep7_setter']):
        raise SystemExit('API table')
    return out, sy, lst, ins


def apply(spec, version='0.32'):
    stock = STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    im = ST.img_of(spec, stock)
    fva, ftext, apsite, apl = check_base(spec, stock, im)
    check_free(spec, stock, im)
    out, sy, lst, ins = build_code(fva, ftext)
    for k, (lo, hi) in REGIONS.items():
        spec['edits'].append(dict(kind='0x100', addr=hex(lo), expect=stock[lo - BASE:lo - BASE + len(out[k])].hex(),
                                  new=out[k].hex(), source=SRC,
                                  why=f'plugin_loader {version} {k} ({len(out[k])} B, section 1 dead EVF gamma table)'))
    put(spec, stock, apsite, call16_bytes(apsite, apl, AP_FRAME), call16_bytes(apsite, sy['pl_ap'], AP_FRAME),
        f'ap_post call ap_load {apsite:#x} -> pl_ap (ap_load, then PLUGIN.BIN; once per power-on)')
    for s in FW_SITES:
        put(spec, stock, s, call_bytes(s, fva, FW_FRAME), call_bytes(s, sy['pl_fw'], FW_FRAME),
            f'Firmware screen Body value call {s:#x} fw_val -> pl_fw (plugin text, else fw_val)')
    used = sum(len(v) for v in out.values())
    spec['plugin_loader'] = dict(
        built_by=SRC, version=version, abi=ABI_VER, api_n=API_N, card='EP7MOD/PLUGIN.BIN',
        regions={k: [hex(lo), hex(hi), len(out[k])] for k, (lo, hi) in REGIONS.items()}, bytes=used,
        heap=dict(state=PS, block=PB, ready=RMAGIC.decode()), block_size=BSIZE,
        header=dict(magic=PMAGIC.decode(), size=HDR, init=HDR, fw_id=FW_ID.hex(), min_size=MINSZ, max_size=BSIZE),
        ap_site=hex(apsite), ap_load=hex(apl), fw_sites=[hex(s) for s in FW_SITES], fw_val=hex(fva), fw_text=hex(ftext),
        exec='cached alias (B - 0x40000000), fresh block, loaded once, never freed after init: no I-cache maintenance',
        symbols={k: hex(v) for k, v in sy.items() if k.startswith(('pl_', 'a_', 'b_', 'f_'))})
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
    m = spec['plugin_loader']
    print(json.dumps({k: v for k, v in m.items() if k != 'symbols'}, indent=1))
