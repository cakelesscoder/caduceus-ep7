#!/usr/bin/env python3
"""E-M1 Mark II: emulate the AF / AE display lookups for aspect ids 6/7 (aspect/build.py §14, §17) against stock.

    python3 tools/omdem1mk2_emu_af.py releases/em1mk2/<ver>/edits.json

For every hooked site, run stock and patched from the hook site to the end of its lookup, for aspect values
1,2,3,4,9,10 and 6,7, each list / key the site uses, with sentinels in every output slot. Pass when:
  * stock values give the same result on both images (patch is transparent for them);
  * on the patched image 6 and 7 give exactly the stock result for 3 (16:9);
  * on stock, 6 and 7 leave the sentinel (reproduces the bug the hook fixes).
Also checks §14: the AF target headers' 6/7 rows equal the 16:9 rows.
Not emulated: drawing itself, and the callers that consume these results.
"""
import struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'external/oly_fw_analysis/tools'))
import omdem1mk2_emu_validator as V  # noqa: E402
from penf_emulator import Region, execute  # noqa: E402

SECS = [(0x60021020, 0x600de000), (0x600de000, 0x60257800), (0x602ae000, 0x60580800), (0x60591800, 0x605d3000),
        (0x605d5000, 0x6078f000), (0x60796000, 0x60bc8800), (0x60bf1000, 0x612e7000)]
STK, OBJ = 0x9f000000, 0x9f100000
SENT = 0x5a5a5a5a
VALUES = [1, 2, 3, 4, 9, 10, 6, 7]


def u32(img, a):
    return struct.unpack_from('<I', img, a - V.B)[0]


def run(img, pc, stop, regs, stack=None, obj=None):
    stk = bytearray(struct.pack('<I', SENT) * 0x400)
    for off, val in (stack or {}).items():
        struct.pack_into('<I', stk, 0x800 + off, val)
    ob = bytearray(struct.pack('<I', SENT) * 0x100)
    for off, (fmt, val) in (obj or {}).items():
        struct.pack_into(fmt, ob, off, val)
    rg = [Region(f's{i}', lo, img[lo - V.B:hi - V.B], 'rx') for i, (lo, hi) in enumerate(SECS)]
    rg += [Region('stk', STK, bytes(stk), 'rw', True), Region('obj', OBJ, bytes(ob), 'rw', True)]
    r = execute(rg, dict({'pc': pc, 'sp': STK + 0x800}, **regs), 0xfffffff0, limit=20000, breakpoints=stop)
    if r['status'] != 'breakpoint' or r['fault']:
        return ('fault', r['registers']['pc'], r['fault'])
    m = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}
    return r['registers'], m['stk'][0x800:], m['obj']


def lists_at(img, first, n, stride):
    return [first + stride * k for k in range(n)]


# site -> (start, stop list, case builder, result extractor)
def cases(img):
    out = {}
    # sv: (8,sp) -> struct {mode, aspect}; a0 = one of 12 {aspect, layout} 6-entry lists; result (12,sp)
    sv_lists = [0x6126830c, 0x6126833c, 0x6126836c, 0x6126839c, 0x612683cc, 0x612683fc, 0x6126842c, 0x6126845c,
                0x6126848c, 0x612684bc]
    sv_lists = [a for a in sv_lists if u32(img, a) == 1]
    out['sv'] = [((0x60ea25e2, [0x60ea25fa], {'a0': lst}, {8: OBJ}, {0: ('<I', 100), 4: ('<I', v)}), lst, v)
                 for lst in sv_lists for v in VALUES]
    # ag1/ag2: a3 = obj, (248,a3) aspect, result byte (18,a3); a2 = list of {aspect, sublist, u16 n}; d0 = sub key
    for name, start, stop, firsts in (('ag1', 0x60e5f5d7, 0x60e5f618, [0x61234870, 0x612348b8, 0x61234900, 0x61234948,
                                                                          0x61234ab0, 0x61234af8]),
                                      ('ag2', 0x60e5f823, 0x60e5f864, [0x61234990, 0x612349d8, 0x61234a20, 0x61234a68,
                                                                          0x61234b70, 0x61234bd0])):
        rows = []
        for lst in firsts:
            # sub keys of the 16:9 row
            for k in range(6):
                if u32(img, lst + 12 * k) == 3:
                    sub, n = u32(img, lst + 12 * k + 4), struct.unpack_from('<H', img, lst + 12 * k + 8 - V.B)[0]
                    keys = [u32(img, sub + 8 * j) for j in range(n)]
            for key in keys[:4]:
                for v in VALUES:
                    rows.append(((start, [stop], {'a2': lst, 'a3': OBJ, 'd0': key}, {}, {248: ('<I', v)}), (lst, key), v))
        out[name] = rows
    # mt: a3 = list (12-B entries), (40,sp) aspect; result stack words 16, 20, 24, 32
    out['mt'] = [((0x60e99d28, [0x60e99d5b], {'a3': lst, 'd3': lst, 'd1': 0}, {40: v}, {}), lst, v)
                 for lst in (0x61265498, 0x612654d4, 0x61265510, 0x6126572c, 0x61265768, 0x612657a4) for v in VALUES]
    # ch1: (56,sp) aspect, (52,sp) flag, (20,sp) key; result a3, (48,sp)
    keys = [36868, 36870, 36872, 36874, 45069, 45068, 45067, 45066]
    out['ch1'] = [((0x60e3be27, [0x60e3c01f], {'a3': 0}, {56: v, 52: f, 20: k}, {}), (f, k), v)
                  for f in (0, 1) for k in keys for v in VALUES]
    # ch2: (52,sp) aspect, (48,sp) flag, (24,sp) key; result a3, d3
    out['ch2'] = [((0x60e3c9d7, [0x60e3cbcd], {'a3': 0, 'd3': 0}, {52: v, 48: f, 24: k}, {}), (f, k), v)
                  for f in (0, 1) for k in keys for v in VALUES]
    return out


def result(name, r):
    if isinstance(r, tuple) and r and r[0] == 'fault':
        return r
    regs, stk, obj = r
    if name == 'sv':
        return struct.unpack_from('<I', stk, 12)[0]
    if name in ('ag1', 'ag2'):
        return obj[18]
    if name == 'mt':
        return tuple(struct.unpack_from('<I', stk, o)[0] for o in (16, 20, 24, 32))
    if name == 'ch1':
        return regs['a3'], struct.unpack_from('<H', stk, 48)[0]
    if name == 'ch2':
        return regs['a3'], regs['d3']


def unwritten(name, res):
    if name == 'sv':
        return res == SENT
    if name in ('ag1', 'ag2'):
        return res == 0x5a
    if name == 'mt':
        return all(x == SENT for x in res)
    if name == 'ch1':
        return res[0] == 0x612141a0 or res[0] == 0        # 4:3 default table / untouched
    if name == 'ch2':
        return res[0] == 0x612141a0 or res[0] == 0


def main():
    old, new = V.image(None), V.image(sys.argv[1])
    fails, total = 0, 0
    for name, rows in cases(old).items():
        bad, ctx_res = [], {}
        for (start, stop, regs, stack, obj), ctx, v in rows:
            a = result(name, run(old, start, stop, regs, stack, obj))
            b = result(name, run(new, start, stop, regs, stack, obj))
            ctx_res[(ctx, v)] = (a, b)
        n = 0
        for (ctx, v), (a, b) in ctx_res.items():
            n += 1
            if isinstance(a, tuple) and a and a[0] == 'fault' or isinstance(b, tuple) and b and b[0] == 'fault':
                bad.append((ctx, v, a, b)); continue
            if v in (6, 7):
                want = ctx_res[(ctx, 3)][0]
                if b != want:
                    bad.append((ctx, v, 'patched', b, 'want 16:9', want))
            elif a != b:
                bad.append((ctx, v, 'stock', a, 'patched', b))
        if name in ('ch1', 'ch2'):     # stock sends 6/7 to the 4:3 default: same result as value 1
            bug = sum(1 for (ctx, v), (a, _) in ctx_res.items() if v in (6, 7) and a == ctx_res[(ctx, 1)][0])
        else:
            bug = sum(1 for (ctx, v), (a, _) in ctx_res.items() if v in (6, 7) and unwritten(name, a))
        total += n
        fails += len(bad)
        print(f'{name:4s} {n:3d} runs, stock 6/7 unwritten (sv/ag/mt) or = 4:3 (ch) in {bug}, mismatches {len(bad)}')
        for b in bad[:4]:
            print('      ', b)
    # §14 headers
    for k in range(4):
        flag, lst, n = struct.unpack_from('<III', new, 0x61212d34 + 12 * k - V.B)
        rows = {struct.unpack_from('<I', new, lst + 16 * j - V.B)[0]: struct.unpack_from('<IIII', new, lst + 16 * j - V.B)[1:]
                for j in range(n)}
        ok = rows.get(6) == rows.get(3) and rows.get(7) == rows.get(3)
        fails += not ok
        print(f'§14 header {k}: n={n} 6/7 == 16:9 row: {ok}')
    print(f'RESULT {"PASS" if not fails else "FAIL"} ({total} runs, {fails} mismatches)')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
