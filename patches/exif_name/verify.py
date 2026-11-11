#!/usr/bin/env python3
"""exif_name checks (emulator, real firmware code from the built package). Offline. Minimal + anti-brick.

  .venv/bin/python -I patches/exif_name/verify.py releases/v0.31c/edits.json generated/v031d/edits.json [generated/v031d/rel]

  X  the real site 0x6030288d -> ex_get -> sc_slot (v0.31c's, through ap_custom's getter wrapper) -> the real getter, v0.31c vs 0.31d.
     The caller's (8,sp) holds cap. COLOR k with a loaded table, 'EP7N' and a name: cap+1448 = name + NULs (32 B), cap+1668 =
     "Caduceus <name>" + spaces (117 B), cap+1660..1667 untouched; nothing else in cap changes. Any miss (MONO, other modes,
     flashed table, no 'EP7N', empty name, bad handle) leaves cap byte-identical. d0..a3, sp and the caller's stack == v0.31c.
  P  anti-brick: package decodes to stock + edits (the image X ran), restore == stock, bytes differing from v0.31c are only
     the ex_get block, the site's rel32 and the fw_version label.
"""
import json, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'external/oly_fw_analysis/tools'))
import build_package as BP  # noqa: E402
import oly_container as oc  # noqa: E402
import importlib.util  # noqa: E402


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


W = _load('ep7_wb_v', ROOT / 'tools/ep7_verify_wb.py')
Region, execute = W.Region, W.execute
BASE, SITE = 0x60020020, 0x6030288d
CAP, CAP_LEN = 0x13000000, 2048
POOL, HANDLE = 0xa1f8d800, 0x41
P = POOL + HANDLE - 1
PM, PM6, COL, KEY = 38017, 40209, 63153, 0x5ef1
REGS0 = dict(d2=0x2222, d3=0x3333, a1=0xa1a1, a2=0xa2a2, a3=0xa3a3)
REG = ('d0', 'd1', 'd2', 'd3', 'a0', 'a1', 'a2', 'a3', 'sp', 'pc')
NAMES = [b'Kodachrome 64', b'', b'Portra 400 Warm', b'X']
L = 0xa1dd8d40 + 0x4040 * 3                                          # a class-2 block (LOOKS.BIN + film-menu tail)
POS = [2, 1, 0, 3]                                                   # slot k sits on look pos (0 = own)


def image(spec):
    pkg, rst, info = BP.build(spec, BP.STOCK.read_bytes())
    return [b for b in oc.parse(pkg) if b.kind == 0x100][0].payload, pkg, rst, info


def cap0():
    c = bytearray(b'\xcc' * CAP_LEN)
    c[1448:1480] = bytes(32)
    c[1660:1668] = bytes(8)
    c[1668:1785] = b' ' * 117
    return c


def p_block(mark=b'EP7N', magic=b'EP7B', edit=None, looks=True):
    p = bytearray(1024)
    p[0:4] = magic
    for k in range(8):
        p[32 + 64 * k] = k + 1
        p[32 + 64 * k + 7] = 3
    if edit:                                                         # (slot, byte): changed on camera
        p[32 + 64 * edit[0] + edit[1]] += 1
    if looks:
        p[1016:1024] = struct.pack('<I', L) + b'EP7F'
    for k, n in enumerate(NAMES):
        p[544 + 16 * k:544 + 16 * k + len(n)] = n
    p[672:676] = mark
    return bytes(p)


def l_block():
    b = bytearray(2560)
    for k, pos in enumerate(POS):                                    # record pos-1 at L + 64 pos = place() of slot k
        if pos:
            b[64 * pos] = k + 1
            b[64 * pos + 7] = 3
            b[64 * pos + 48:64 * pos + 52] = b'Look'
    b[2112:2121] = b'EP7L' + struct.pack('<I', P) + bytes([3])
    b[2121:2125] = bytes(POS)
    return bytes(b)


def run(im, mode, m6, col, handle=HANDLE, mark=b'EP7N', magic=b'EP7B', enable=1, edit=None, looks=True):
    sl = lambda lo, hi: im[lo - BASE:hi - BASE]
    st = bytearray([W.STACK_FILL] * 0x2000)
    struct.pack_into('<I', st, 0x1800 + 8, CAP)                       # caller's (8,sp) = cap
    pr = {KEY: bytes([enable]), PM: bytes([mode]), PM6: bytes([m6]), COL: bytes([col])}
    rg = [Region('site', SITE - 16, sl(SITE - 16, SITE + 16), 'rx'),
          Region('getter', W.GETTER_CODE[0], sl(*W.GETTER_CODE), 'rx'), Region('xlate', W.XLATE[0], sl(*W.XLATE)),
          Region('cpuid', W.CPUID, bytes(4)), *W.registry(pr),
          Region('evf', 0x601de000, sl(0x601de000, 0x601e3d80), 'rx'),
          Region('acc', 0x6055e700, sl(0x6055e700, 0x6055e800), 'rx'),
          Region('sec7', 0x61378c00, sl(0x61378c00, 0x61379000), 'rx'),
          Region('flashtab', 0x60210900, bytes(512), 'r'),
          Region('state', 0x622cbcc0, struct.pack('<HHI', 0, handle, 0), 'r'),
          Region('bss', 0x6203c8b8, bytes(8), 'r'),
          Region('pool', P, p_block(mark, magic, edit, looks), 'r'), Region('lblk', L, l_block(), 'r'),
          Region('stack', W.STACK, bytes(st), 'rw', True),
          Region('cap', CAP, bytes(cap0()), 'rw', True)]
    r = execute(rg, dict(pc=SITE, sp=W.SP0, d0=KEY, d1=0, a0=0, **REGS0), SITE + 7, limit=20000)
    m = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}
    return r['fault'], r['registers'], m['cap'], m['stack'][0x1800 - 8:]


def want_cap(name, star=False):
    c = cap0()
    name += b'*' if name and star else b''
    if name:
        c[1448:1448 + len(name)] = name
        t = b'Caduceus ' + name
        c[1668:1668 + len(t)] = t
    return bytes(c)


def t_x(base, new):
    n, bad, hits, stars = 0, [], 0, 0
    cases = []
    for mode, m6 in ((11, 0), (6, 11), (12, 0), (6, 12), (0, 0), (10, 0)):
        for col in (0, 1, 2, 3, 4, 5):
            for enable in (0, 1):
                cases.append(dict(mode=mode, m6=m6, col=col, enable=enable))
    for col in (1, 3):
        cases += [dict(mode=11, m6=0, col=col, handle=0), dict(mode=11, m6=0, col=col, handle=0xffff), dict(mode=11, m6=0, col=col, handle=HANDLE + 2),
                  dict(mode=11, m6=0, col=col, mark=b'EP7X'), dict(mode=11, m6=0, col=col, magic=b'EP7Q')]
    for col in (1, 2, 3, 4):                                         # '*': edited slot on a look; +24 and +49 don't count; own never
        for e in ((0,), (7,), (24,), (30,), (48,), (49,), (52,)):
            cases.append(dict(mode=11, m6=0, col=col, edit=(col - 1, e[0])))
        cases.append(dict(mode=11, m6=0, col=col, edit=(col - 1, 0), looks=False))
        cases.append(dict(mode=11, m6=0, col=col, edit=((col % 4), 0)))   # another slot edited
    for c in cases:
        f0, r0, c0, s0 = run(base, **c)
        f1, r1, c1, s1 = run(new, **c)
        on = (c['m6'] if c['mode'] == 6 else c['mode']) == 11 and 1 <= c['col'] <= 4 and c.get('handle', HANDLE) == HANDLE \
            and c.get('mark', b'EP7N') == b'EP7N' and c.get('magic', b'EP7B') == b'EP7B'
        name = NAMES[c['col'] - 1] if on else b''
        hits += bool(name)
        ed = c.get('edit')
        star = bool(ed) and ed[0] == c['col'] - 1 and ed[1] not in (24, 49, 52) and c.get('looks', True) and POS[ed[0]] != 0
        stars += star and bool(name)
        n += 1
        if f0 or f1 or c0 != bytes(cap0()) or c1 != want_cap(name, star) or s0 != s1 or any(r0[k] != r1[k] for k in REG):
            bad.append((c, f0, f1, [k for k in REG if r0[k] != r1[k]], c1[1448:1480], c1[1668:1700]))
    ok = not bad and hits == 12 + 3 * 9 and stars == 2 * 4
    return ok, f'{n} cases, {hits} named writes, {stars} with *; bad {bad[:3]}'


def t_pkg(base_s, new_s, base, new, pkg, rst, info, disk):
    sb = {b.kind: b for b in oc.parse(BP.STOCK.read_bytes())}
    good = True
    for b in oc.parse(pkg):
        exp = bytearray(sb[b.kind].payload)
        for e in new_s['edits']:
            if int(e['kind'], 16) == b.kind:
                o = BP.resolve(b.kind, e['addr']); nb = bytes.fromhex(e['new']); exp[o:o + len(nb)] = nb
        good &= bytes(exp) == b.payload
        if b.kind == 0x100:
            good &= b.payload == new
    for b in oc.parse(rst):
        good &= b.payload == sb[b.kind].payload
    x = new_s['exif_name']
    ours = [(int(x['code_at'], 16), x['code_len']), (int(x['site'], 16) + 1, 4)] + \
        [(int(e['addr'], 16), len(e['new']) // 2) for e in new_s['edits'] if e.get('source') == 'patches/fw_version']
    diff = [BASE + i for i in range(len(base)) if base[i] != new[i]]
    stray = [hex(a) for a in diff if not any(s_ <= a < s_ + k for s_, k in ours)]
    good &= not stray and len(new_s['edits']) == len(base_s['edits']) + 2
    if disk:
        good &= (disk / 'patched.pkg.bin').read_bytes() == pkg and (disk / 'restore-stock.pkg.bin').read_bytes() == rst
    return good, f'{info["edits"]} edits, {info["changed_payload_bytes"]} B; {len(diff)} B differ from v0.31c; stray {stray[:6]}'


def main():
    base_s, new_s = (json.loads(Path(p).read_text()) for p in sys.argv[1:3])
    disk = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    base, *_ = image(base_s)
    new, pkg, rst, info = image(new_s)
    ok = True
    for tag, (g, txt) in (('X', t_x(base, new)), ('P', t_pkg(base_s, new_s, base, new, pkg, rst, info, disk))):
        print(f"{'PASS' if g else 'FAIL'} {tag} {txt}")
        ok &= g
    print('ALL PASS' if ok else 'FAILURES')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
