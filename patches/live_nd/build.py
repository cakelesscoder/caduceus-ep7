#!/usr/bin/env python3
"""Live ND inside Multiple Exposure, test n8 (n7 floor + hold for N). Offline. docs/LIVE_ND.md "As built".

  .venv/bin/python -I patches/v029a/build.py releases/v0.28/edits.json --out generated/v029a/edits.json
  .venv/bin/python -I patches/live_nd/build.py generated/v029a/edits.json --out generated/live_nd/n8/edits.json
  .venv/bin/python -I tools/build_package.py generated/live_nd/n8/edits.json --out generated/live_nd/n8/pkg
  .venv/bin/python -I patches/live_nd/verify.py generated/v029a/edits.json generated/live_nd/n8/edits.json generated/live_nd/n8/pkg

apply(spec, version='0.30n8') -> spec. n1 (AP tiles) broke the AP screen and is gone. n2 put ND in Number of Frames,
but AP Multiple Exposure forces 267 = 2 and the menu grey-out table greys the row there. n8 = n7 + lnd_cont: the stock continuous ME route requests one continue only (2 frames by design); while ND3/ND4 in AP
ME and the shutter is still held, each continuous frame done issues the stock sendTakePictureContinue (capped at N). Release
handling stays stock. n7 = the safe floor: n6/n5's continuous route and release latch are removed (camera 0.30b7: Sequential L took
2 frames and hung until reboot; the latch blocked the release that stock uses to end a stalled burst). ND3/ND4 take a
frame per press in every drive mode, continuous stays as the AP ME preset forces it (off). Was: n6 = n5 with real continuous drive (sid 1487 = 1 while ND3/ND4 in AP ME: lnd_pw preset apply, lnd_cb 267 change,
lnd_sv mode-save containment) instead of n5's sequence-only lnd_c. n5 = n4 plus one-press ND (lnd_off) and the popup label lists (descriptor +28/+32). n4 = n3 plus the grey-out fix:
  * menu grey-out table 0x60adf518: id 267's condition 24 (sid 24 == 211, AP Multiple Exposure) -> 23 (already listed)
  * Shooting Menu row summary list (0x6117b154) -> Off / 2f / ND3 / ND4
n3 parts:
  * Multiple Exposure > Number of Frames (sid 267, validator record 438) offers Off / 2f / ND3 / ND4 = values 0, 2, 3, 4,
    real frame counts the ME machinery reads natively (array cap 5); both label lists -> 4 entries (ND3/ND4 kind 5)
  * capture Auto Gain (+24141, 0x602a8378) reads 1 while frames >= 3, so 3/4 frames always average
  * AP Multiple Exposure preset block (index 0x6047a800 -> 0x60475e88, the values forced on entering the mode) loses
    its 267 = 2 pair, so Number of Frames is selectable and takes effect in AP Multiple Exposure
  * guards: 267 reads in the ME machinery, capture +24140 and the app layer return 2 when the value is 0/1 and sid
    24 == 211, so Off/2f in AP Multiple Exposure behaves as the stock 2 frames
No setting is added and nothing is stored at run time.
"""
import argparse, copy, importlib.util, json, re, struct
from pathlib import Path

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
BASE, SRC = 0x60020020, 'patches/live_nd'

# code space: dead EVF gamma tables in section 1 (same claim as n1, much smaller now)
AT, END = 0x601de540, 0x601de980
STEP_LO, STEP_HI = 0x601e3b40, 0x601e3d6c           # EVF step-table words: the only allowed refs into the block
SEC1, SEC1_SRC = 0x600d7800, 0x40757800             # descriptor 0x60027068 entry 0: flash source alias
FALSE_POS = {0x605ff26c: 'dde61da0',            # call d32 bytes (dis-checked), read as 0xa01de6dd
             0x60681605: '82e68540',            # mov d0,d2; add d1,d2; mov 64,d1 (flash-alias read)
             0x60f09dd0: '5de78540',            # float table (0x4085e75d ~ 4.18f), flash-alias read
             0x60f0ad34: '2fe78540',            # float table, flash-alias read
             0x613c5d94: 'dce58540'}            # inside mov 0x614085e5,a0 at 0x613c5d92 (misaligned read)

GET, PROP, APPGET, OFF = 0x602cbc0a, 0x6005e971, 0x60ccf9f3, 0x6096b28c
WR, RD, CB = 0x602cc122, 0x602cc0fc, 0x602b5407
FLAG, KEYST, RELCHK, CONT = 0x60947b55, 0x60955fa2, 0x6094ca4e, 0x6096b73c   # status flag, key state, release check, sendTakePictureContinue   # current-value write / read (preset apply, mode save), sid-267 callback
CB_WORDS = (0x604345b4, 0x6043ad10)                # sid 267 registry records 0x6043459c / 0x6043acf8, +24 callback
SID_N = 267
VALUES = [0, 2, 3, 4]
LABELS = {3: ('ND3', 1430), 4: ('ND4', 1431)}       # kind 5 text, stock "3f" / "4f" ids as fallback
VAL_REC, VAL_LIST = 0x604cebc4, 0x604cb73c          # validator record 438 (sid 267), stock list {0, 2}
MENUS = [0x611bf200, 0x611cc96c]                    # Number of Frames descriptors: +0 sid, +12 list, +16 count
ROW_SUM = 0x6117b154                                # Shooting Menu row summary {u16 sid 267, u16 count, u32 list}
CANEXEC, CANEXEC_N = 0x60adf518, 611                # menu grey-out table {u16 id, u16 0, u32 cond bytes, u8 n} (0x608290c8)
CX_ID_REC, CX_CONDS, CX_N = 0x60adfa1c, 0x60ade957, 39   # id 267: OR of 39 predicates (index -> 0x60ade144 table)
CX_APME, CX_DUP = 24, 23                            # predicate 24 = sid 24 == 211 (AP ME, 0x608296e8) -> 23 (sid 24 == 210, already listed)
SITES = [(0x602a8378, PROP, 'c00c', 'lnd_kg', 'capture +24141 Auto Gain (key 0x1851)'),
         (0x602a838b, PROP, 'c00c', 'lnd_kn', 'capture +24140 frames (key 0x1841)'),
         (0x608296d7, GET, '0004', 'lnd_n', 'ME on (267 != 0)'),
         (0x60919ec7, GET, '0004', 'lnd_n', 'ME controller take count cap (267)'),
         (0x6091a847, GET, '0004', 'lnd_n', 'ME controller finish (267)'),
         (0x6091b067, GET, '0004', 'lnd_n', 'ME controller frame array fill (267)'),
         (0x6096b2ca, GET, '0004', 'lnd_n', 'ME sequence parts (224) = frames (267)'),
         (0x6096ca1c, GET, '0004', 'lnd_n', 'ME sequence parts frames left (267)'),
         (0x60cdcd26, APPGET, 'a018', 'lnd_a', 'app 267 read'),
         (0x60cddb17, APPGET, 'a018', 'lnd_a', 'app 267 read'),
         (0x60cde34b, APPGET, 'a018', 'lnd_a', 'app 267 read'),
         (0x60cea730, APPGET, 'a018', 'lnd_a', 'app 267 read'),
         (0x6096b019, FLAG, '8004', 'lnd_cont', 'ME parts continuous frame done (one more continue while ND and held)')]
M1487 = b'\x2c\xcf\x05'
VT_OFF = 0x60b4ffac                                 # ME sequence parts vtable: rcvTrig2KeyOffIn_TAKE_PICTURE_CONT
M267 = b'\x2c\x0b\x01'
PRE = {0x602a8378: b'\x2c\x51\x18\x90\x00\x04', 0x602a838b: b'\x2c\x41\x18\x90\x00\x04'}
PRE.update({x[0]: M267 for x in SITES if x[1] in (GET, APPGET)})
PRE.update({0x6096b019: bytes.fromhex('fccc0000004898')})
# AP Multiple Exposure preset block (forced values on mode entry; also what greys the menu): drop the 267 = 2 pair
PRESET_IDX = 0x6047a800                             # index entry {u16 mode 211, u16 sub 0, u32 block, u16 count}
AP_ME, ME_BLOCK, ME_COUNT = 211, 0x60475e88, 227

BAD = {'mul', 'mulu', 'div', 'divu', 'setlb', 'llt', 'lne', 'leq', 'lra', 'lcc', 'lcs', 'trap'}


def u32(b, a):
    return struct.unpack_from('<I', b, a - BASE)[0]


def rel(at, dst):
    return struct.pack('<i', dst - at)


def img_of(spec, stock):
    im = bytearray(stock)
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a = int(e['addr'], 16) - BASE; n = bytes.fromhex(e['new']); im[a:a + len(n)] = n
    return bytes(im)


def entries(im, at, n):
    return [im[at - BASE + 12 * k:at - BASE + 12 * k + 12] for k in range(n)]


def value(e):
    return struct.unpack_from('<I', e, 0)[0]


def check_free(spec, stock, end):
    import numpy as np
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a, n = int(e['addr'], 16), len(e['new']) // 2
            if a < end and AT - 4 < a + n:
                raise SystemExit(f'code block overlaps edit {e["addr"]}')
    d = np.frombuffer(stock, np.uint8).astype(np.int64)
    w = d[:-3] | (d[1:-2] << 8) | (d[2:-1] << 16) | (d[3:] << 24)
    hits = []
    for off in (0, 0x40000000, SEC1_SRC - SEC1):
        lo, hi = (AT + off) & 0xffffffff, (end + off) & 0xffffffff
        hits += [int(i) + BASE for i in np.nonzero((w >= lo) & (w < hi))[0]]
    for at in hits:
        if STEP_LO <= at < STEP_HI and (u32(stock, at) - 0x601de13c) % 0x100 == 0:   # a step-table word -> table start
            continue
        if at in FALSE_POS and stock[at - BASE:at - BASE + 4].hex() == FALSE_POS[at]:
            continue
        raise SystemExit(f'reference into {AT:#x}..{end:#x} at {at:#x}')
    # call / jmp displacements into the block (d16 and d32 forms), on the composed image (other layers' code
    # included); stock bytes of the dead EVF gamma tables are byte ramps, not code, so they are not sources
    im = np.frombuffer(img_of(spec, stock), np.uint8).astype(np.int64)
    same = np.ones(len(d), bool)
    same[:] = im == d
    d = im
    pc = np.arange(len(d) - 8, dtype=np.int64) + BASE
    evf = (pc >= 0x601de13c) & (pc < 0x601e3b3c) & same[:-8] & same[1:-7] & same[2:-6] & same[3:-5] & same[4:-4]
    for op, n in ((0xdd, 4), (0xdc, 4), (0xcd, 2), (0xcc, 2)):
        m = (d[:-8] == op) & ~evf
        disp = d[1:-7] | (d[2:-6] << 8) if n == 2 else d[1:-7] | (d[2:-6] << 8) | (d[3:-5] << 16) | (d[4:-4] << 24)
        disp = np.where(disp >= (1 << (8 * n - 1)), disp - (1 << (8 * n)), disp)
        t = pc + disp
        bad = np.nonzero(m & (t >= AT) & (t < end))[0]
        if len(bad):
            raise SystemExit(f'branch into the block from {hex(int(bad[0]) + BASE)}')


def data_alignment(src, syms):
    bad, label = [], None
    for line in src.splitlines():
        m = re.match(r'^(\w+):', line)
        if m:
            label = m.group(1)
            continue
        dd = line.split('/*')[0].strip()
        if label and dd:
            need = 4 if dd.startswith('.long') or dd.startswith('.word') else 2 if (dd.startswith('.hword') or dd.startswith('.short')) else 0
            if need and syms.get(label, 0) % need:
                bad.append((label, hex(syms[label])))
            label = None
    return bad


def source():
    return SB3.subst((HERE / 'lnd.s.in').read_text(), dict(get='ep7_get', prop='ep7_prop', appget='ep7_appget', off='ep7_off', wr='ep7_wr', rd='ep7_rd', cb='ep7_cb',
                                                                 flag='ep7_flag', keyst='ep7_keyst', relchk='ep7_relchk', cont='ep7_cont',
                                                                 blk=hex(ME_BLOCK), blk_end=hex(ME_BLOCK + 8 * (ME_COUNT - 1))))



def build_data(stock, data_at):
    """-> (data bytes, {name: addr}): strings, validator list, one 4-entry label list per menu descriptor."""
    out, addr = bytearray(), {}
    for v, (t, _) in LABELS.items():
        addr[f's{v}'] = data_at + len(out)
        out += t.encode('ascii') + b'\0'
    addr['val'] = data_at + len(out)
    out += bytes(VALUES)
    for i, (m, lo) in enumerate([(m, 12) for m in MENUS] + [(m, 28) for m in MENUS]):
        sid, lp, cnt = struct.unpack_from('<I', stock, m - BASE)[0], u32(stock, m + lo), u32(stock, m + lo + 4)
        es = entries(stock, lp, cnt)
        if (sid, cnt, [value(e) for e in es]) != (SID_N, 2, [0, 2]) or any(struct.unpack_from('<H', e, 4)[0] != 4 for e in es):
            raise SystemExit(f'menu {m:#x} differs')
        txt = struct.unpack_from('<I', es[0], 8)[0]
        new = list(es) + [struct.pack('<IHHI', v, 5, sid_id, addr[f's{v}']) for v, (_, sid_id) in LABELS.items()]
        while (data_at + len(out)) % 4:
            out.append(0)
        addr[f'list{i}'] = data_at + len(out)
        out += b''.join(new)
    # Shooting Menu row summary list (same 12-B entries)
    sid, cnt = struct.unpack_from('<HH', stock, ROW_SUM - BASE)
    lp = u32(stock, ROW_SUM + 4)
    es = entries(stock, lp, cnt)
    if (sid, cnt, [value(e) for e in es]) != (SID_N, 2, [0, 2]) or any(struct.unpack_from('<H', e, 4)[0] != 4 for e in es):
        raise SystemExit('row summary list differs')
    new = list(es) + [struct.pack('<IHHI', v, 5, sid_id, addr[f's{v}']) for v, (_, sid_id) in LABELS.items()]
    while (data_at + len(out)) % 4:
        out.append(0)
    addr['list_row'] = data_at + len(out)
    out += b''.join(new)
    return bytes(out), addr


def put_edit(spec, stock, addr, old, new, why):
    im = img_of(spec, stock)
    if im[addr - BASE:addr - BASE + len(old)] != old or stock[addr - BASE:addr - BASE + len(old)] != old:
        raise SystemExit(f'{addr:#x}: not stock ({why})')
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a, n = int(e['addr'], 16), len(e['new']) // 2
            if a < addr + len(new) and addr < a + n:
                raise SystemExit(f'{addr:#x}: overlaps edit {e["addr"]} ({why})')
    spec['edits'].append(dict(kind='0x100', addr=hex(addr), expect=old.hex(), new=new.hex(), source=SRC, why=f'live_nd {why}'))


def strip(spec):
    spec.pop('live_nd', None)
    spec['edits'] = [e for e in spec['edits'] if e.get('source') != SRC]
    return spec




def apply(spec, version='0.30n8'):
    stock = STOCK.read_bytes()
    spec = strip(copy.deepcopy(spec))
    spec = FV.apply(spec, version)
    syms = dict(ep7_get=GET, ep7_prop=PROP, ep7_appget=APPGET, ep7_off=OFF, ep7_wr=WR, ep7_rd=RD, ep7_cb=CB,
                ep7_flag=FLAG, ep7_keyst=KEYST, ep7_relchk=RELCHK, ep7_cont=CONT)
    src = source()
    code, lst, s, _ = SB3.assemble(src, AT, syms)
    ins = SB3.disasm(code, AT, s['lnd_end'])
    if any(op in BAD for _, op, _ in ins) or any(k != 'sp' for _, _, k, _ in SB3.store_audit(ins)) or any(code[a - AT] == 0xfb for a, _, _ in ins):
        raise SystemExit('forbidden instruction, fb-prefixed form or a non-stack store')
    if data_alignment(src, s) or AT % 4 or s['lnd_end'] % 4:
        raise SystemExit('misaligned')
    data_at = s['lnd_end']
    data, d = build_data(stock, data_at)
    blob = code[:data_at - AT] + data
    end = AT + len(blob)
    claim = (end + 15) // 16 * 16 + 16
    if claim > END:
        raise SystemExit(f'{len(blob)} B does not fit {END - AT}')
    check_free(spec, stock, claim)
    spec['edits'].append(dict(kind='0x100', addr=hex(AT), expect=stock[AT - BASE:end - BASE].hex(), new=blob.hex(), source=SRC,
                              why=f'live_nd n8 code + Number of Frames lists ({len(blob)} B, dead EVF gamma table; refs only step-table words)'))
    for site, tgt, fr, stub, why in SITES:
        old = b'\xdd' + rel(site, tgt) + bytes.fromhex(fr)
        pre = PRE[site]
        if stock[site - len(pre) - BASE:site - BASE] != pre or stock[site - BASE:site + 7 - BASE] != old:
            raise SystemExit(f'{site:#x}: site differs')
        put_edit(spec, stock, site + 1, old[1:5], rel(site, s[stub]), f'{why} -> {stub}')
    rec = stock[VAL_REC - BASE:VAL_REC - BASE + 20]
    sid, attr, lp, alt, nb, el = struct.unpack_from('<HHIIHH', rec, 0)
    if (sid, lp, alt, nb, el) != (SID_N, VAL_LIST, 0, 2, 1) or list(stock[VAL_LIST - BASE:VAL_LIST + 2 - BASE]) != [0, 2]:
        raise SystemExit('validator record 438 differs')
    put_edit(spec, stock, VAL_REC + 4, rec[4:14], struct.pack('<IIH', d['val'], 0, len(VALUES)), 'sid 267 validator list -> Off/2f/ND3/ND4')
    for i, (m, lo) in enumerate([(m, 12) for m in MENUS] + [(m, 28) for m in MENUS]):
        put_edit(spec, stock, m + lo, stock[m + lo - BASE:m + lo + 8 - BASE], struct.pack('<II', d[f'list{i}'], len(VALUES)),
                 f'Number of Frames descriptor {m:#x} +{lo} -> 4 labels ({"row" if lo == 12 else "popup"})')
    # safe floor (n7): continuous drive is never touched. The AP ME preset must still force 1487 = 0 and nothing of ours
    # may hook the sequencer, the release handler or the 267 change callbacks.
    pairs = dict(struct.unpack_from('<II', stock, ME_BLOCK + 8 * j - BASE) for j in range(ME_COUNT))
    if pairs.get(1487) != 0 or u32(stock, VT_OFF) != OFF or any(u32(stock, w) != CB for w in CB_WORDS):
        raise SystemExit('safe-floor preconditions differ')
    put_edit(spec, stock, ROW_SUM + 2, stock[ROW_SUM + 2 - BASE:ROW_SUM + 8 - BASE], struct.pack('<HI', len(VALUES), d['list_row']),
             'Shooting Menu row summary (sid 267) -> 4 labels')
    # menu grey-out: id 267 is greyed by predicate 24 (AP Multiple Exposure); replace that one condition byte
    iid, z, cp, n = struct.unpack_from('<HHIB', stock, CX_ID_REC - BASE)
    conds = list(stock[CX_CONDS - BASE:CX_CONDS + CX_N - BASE])
    if (iid, cp, n) != (SID_N, CX_CONDS, CX_N) or conds.count(CX_APME) != 1 or CX_DUP not in conds:
        raise SystemExit('grey-out record for 267 differs')
    for k in range(CANEXEC_N):
        e = CANEXEC + 12 * k
        i2, _, p2, n2 = struct.unpack_from('<HHIB', stock, e - BASE)
        if i2 != SID_N and p2 < CX_CONDS + CX_N and CX_CONDS < p2 + n2:
            raise SystemExit(f'condition bytes shared with id {i2}')
    at = CX_CONDS + conds.index(CX_APME)
    put_edit(spec, stock, at, bytes([CX_APME]), bytes([CX_DUP]), 'grey-out of id 267: drop predicate 24 (AP Multiple Exposure)')
    # unlock 267 in AP Multiple Exposure: remove its pair from the mode's preset block, count 227 -> 226
    mode, sub, bp, cnt = struct.unpack_from('<HHIH', stock, PRESET_IDX - BASE)
    pairs = [struct.unpack_from('<II', stock, ME_BLOCK + 8 * k - BASE) for k in range(ME_COUNT)]
    hit = [k for k, (sid_, v) in enumerate(pairs) if sid_ == SID_N]
    if (mode, sub, bp, cnt) != (AP_ME, 0, ME_BLOCK, ME_COUNT) or len(hit) != 1 or pairs[hit[0]][1] != 2 or dict(pairs).get(24) != AP_ME:
        raise SystemExit('AP Multiple Exposure preset block differs')
    k = hit[0]
    old = stock[ME_BLOCK + 8 * k - BASE:ME_BLOCK + 8 * ME_COUNT - BASE]
    new = old[8:] + old[-8:]                         # shift down; the last slot (now past the count) keeps its bytes
    put_edit(spec, stock, ME_BLOCK + 8 * k, old, new, f'AP Multiple Exposure preset block: drop pair {SID_N} = 2 (unlock Number of Frames)')
    put_edit(spec, stock, PRESET_IDX + 8, struct.pack('<H', ME_COUNT), struct.pack('<H', ME_COUNT - 1), 'AP Multiple Exposure preset count 227 -> 226')
    spec['live_nd'] = dict(built_by=SRC, test='n8', version=version, code_at=hex(AT), code_len=data_at - AT, block_end=hex(end), claim_end=hex(claim),
                           values=VALUES, labels={str(v): t for v, (t, _) in LABELS.items()},
                           symbols={k: hex(v) for k, v in s.items() if k.startswith('lnd_')}, data={k: hex(v) for k, v in d.items()},
                           sites=[hex(x[0] + 1) for x in SITES], data_edits=[hex(VAL_REC + 4)] + [hex(m + lo) for lo in (12, 28) for m in MENUS] + [hex(ROW_SUM + 2), hex(at), hex(ME_BLOCK + 8 * k), hex(PRESET_IDX + 8)])
    return spec


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--version', default='0.30n8')
    a = ap.parse_args()
    spec = apply(json.loads(a.spec.read_text()), a.version)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(spec, indent=1))
    print(json.dumps({k: v for k, v in spec['live_nd'].items() if k not in ('symbols', 'data')}, indent=1))
