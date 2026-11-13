#!/usr/bin/env python3
"""keyhook checks (emulator, offline): the resident plugin key hook + API v1.1 against v0.32 without it. Minimal + anti-brick.

  .venv/bin/python -I patches/keyhook/verify.py releases/v0.31d/edits.json generated/v032/edits.json \
      [generated/v032/rel] [generated/plugins/shortcut_cycle/EP7MOD/PLUGIN.BIN]

BASE = patches/v032 apply(v0.31d, keyhook=False); NEW = the built spec (must equal keyhook.apply(BASE)).
Runs: the whole generic key handler 0x60ce0108 from its `calls` entry to the caller's return address, on the whole patched
main image (rx). Real code: the handler, kh / kh_chk, ap_P 0x601df03c, ka_sel / ka_get and the plugin (cached alias of B).
Stubbed by jmp trampolines (both images alike, fixture-driven, entries logged from the trace): kmap 0x60cc9a05,
btn_dispatch 0x60cc872f, 0x60cd423b, action_class 0x60cc87ac, class-2 0x60ce026a, class-1 select mode 0x60ceb5b6,
prop_get 0x6005e971. Equal = registers (all but MDR), the handler frame and the caller's stack, CA module, event record,
P, B, the stub call log (each stub's entry registers) and the fixture/log memory.
  S  static: NEW differs from BASE only inside the keyhook edits; keyhook.apply(BASE) == NEW; three sdk words -> kh_ret0.
  N  all 142 CA key events (table 0x60f3928c: Fn, REC, arrows, OK, MENU, INFO, dials, ...), rotating handler paths
     (btn 0 / 20 early exit / class 0, 1, 2 / record+4 == 152): no plugin (P invalid, P without EP7K), hello loaded by
     the real loader (hook word 0) and bad hook words (header, end of B, uncached B, stock code, -1) == BASE.
  H  test plugins: return 1 -> leaves through `ret [d2,a2,a3],40`: pc = return address, sp, d2, d3, a2, a3 as entered,
     hook entered once with d0 = event, d1 = B, a0 = CA, a1 = record, no stock callee runs. Return 0 / 2 / 0 with
     d0..a1 clobbered -> == BASE.
  C  shortcut_cycle PLUGIN.BIN through the real loader: Fn press in a still mode -> ka_sel -> select mode 50 (a0 CA,
     a1 record), handled exit, twice; movie, AP 14 / 209..216, record+4 == 152, Fn release, every other event == BASE.
     Setup > Firmware "0.32S".
  D  the three sdk sub-command words -> `clr d0; rets`: d0 = 0, pc = return address, everything else as entered.
  R  plugin_loader regression: its N / R / V / F on NEW (V with the v1.1 table address).
  P  anti-brick: package decodes to stock + edits, restore == stock, decoded main == emulated image, files on disk
     match; PLUGIN.BIN == shortcut_cycle rebuild.
"""
import hashlib, importlib.util, json, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'external/oly_fw_analysis/tools'))
from penf_emulator import Region, execute  # noqa: E402


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


PLV = _load('ep7_plv_kh', ROOT / 'patches/plugin_loader/verify.py')
KH = _load('ep7_kh_build_v', ROOT / 'patches/keyhook/build.py')
SC = _load('ep7_sc_build_v', ROOT / 'tools/plugins/shortcut_cycle/build.py')
PL, V32, HB, SB3 = PLV.PL, PLV.V32, PLV.HB, PLV.SB3
BASE = 0x60020020
STOCK = PLV.STOCK

ENTRY = 0x60ce0108                          # ca_key_generic, calls entry
KMAP, BTN, B0, CLS, ACT2, SEL, GET = 0x60cc9a05, 0x60cc872f, 0x60cd423b, 0x60cc87ac, 0x60ce026a, 0x60ceb5b6, 0x6005e971
# site 1 (select-state handler 0x60cebc89) callees, and the keycode-28 handler's getSetting
B3C6, D2330, D793B, D564C, C8929, LOGF, GSET = 0x60ceb3c6, 0x60cd2330, 0x60cd793b, 0x60cd564c, 0x60cc8929, 0x60cfbc8a, 0x60ccf9f3
STUBBED = (('kmap', KMAP), ('btn', BTN), ('b0', B0), ('cls', CLS), ('act2', ACT2), ('sel', SEL), ('get', GET),
           ('b3c6', B3C6), ('d2330', D2330), ('d793b', D793B), ('d564c', D564C), ('c8929', C8929), ('logf', LOGF),
           ('gset', GSET))
ENTRIES = {'gen': 0x60ce0108, 'sel': 0x60cebc89, 'k28': 0x60cec1f3}   # calls entries: site 0, site 1, site 1 via `call 0x60cebc8e`
G1, G2 = 0x6233b9a0, 0x61fb0dd0             # +4 open select mode, +8, +12 (0x6233b9ac) / +8 dd8, +12 ddc
STG = KH.STAGE & ~3                         # the Fn stage byte's word (byte at +2), docs/PLUGINS.md §12
HANDLE, P_AT, BLK, BLKC = PLV.HANDLE, PLV.P_AT, PLV.BLK, PLV.BLKC
CA, REC, FIX = 0x13000000, 0x13010000, 0x13020000
STKR, SP0 = 0x18010000, 0x18010800
STUBS = 0x18100000
EV_TBL, EV_N = 0x60f3928c, 142
EV_FN, EV_FN_UP = 0x0100002e, 0x0100002f
K44, K24 = SC.DEFS['K44'], SC.DEFS['K24']
KEEP = ('d0', 'd1', 'd2', 'd3', 'a0', 'a1', 'a2', 'a3', 'sp', 'pc', 'psw', 'lir', 'lar')   # mdr: dead (differs on the miss path)
LOGR = ('d0', 'd1', 'd2', 'd3', 'a0', 'a1', 'a2', 'a3', 'sp')
FRAME = 40                                  # handler frame [d2,a2,a3],40
# FIX words: 0 btn_dispatch result, 1 action class, 2 prop 0x8551 (movie), 3 prop 0xc011 (shooting mode),
#            4 0x60ceb3c6, 5 0x60cd793b, 6 0x60cc8929, 7 getSetting 1138 results


def stub_src():
    F = lambda i: f'({4 * i},a0)'
    return f""" .am33_2
 .text
 .global _start
_start:
s_ret:                             /* landing pad = the handler's caller */
 nop
 nop
 .balign 4
s_kmap:                            /* call ..,[d2],4: input-dependent result, d2 clobbered (ret restores it) */
 add 0x100,d0
 mov 0x77,d1
 mov 0x5555,d2
 ret [d2],4
 .balign 4
s_btn:                             /* call ..,[d2,d3],16 */
 mov {FIX:#x},a0
 mov {F(0)},d0
 mov 0x99,d3
 ret [d2,d3],16
 .balign 4
s_b0:                              /* call ..,[],4 */
 clr d0
 ret [],4
 .balign 4
s_cls:                             /* call ..,[d2,d3],8 */
 mov {FIX:#x},a0
 mov {F(1)},d0
 ret [d2,d3],8
 .balign 4
s_act2:                            /* call ..,[d2,d3,a2,a3],60 */
 mov 0x1234,a2
 clr d0
 ret [d2,d3,a2,a3],60
 .balign 4
s_sel:                             /* call ..,[d2,d3,a2,a3],68 */
 mov 0x4321,a3
 mov 7,d0
 ret [d2,d3,a2,a3],68
 .balign 4
s_b3c6:                            /* call ..,[],0 */
 mov {FIX:#x},a0
 mov {F(4)},d0
 ret [],0
 .balign 4
s_d2330:                           /* call ..,[d2],12 */
 mov 0x2330,d1
 ret [d2],12
 .balign 4
s_d793b:                           /* call ..,[d2],12 */
 mov {FIX:#x},a0
 mov {F(5)},d0
 ret [d2],12
 .balign 4
s_d564c:                           /* call ..,[],0 */
 ret [],0
 .balign 4
s_c8929:                           /* call ..,[d2,d3],12 */
 mov {FIX:#x},a0
 mov {F(6)},d0
 ret [d2,d3],12
 .balign 4
s_logf:                            /* call ..,[d2,a2,a3],152 (trace print) */
 ret [d2,a2,a3],152
 .balign 4
s_gset:                            /* call ..,[d2,a2],24: getSetting */
 mov {FIX:#x},a0
 mov {F(7)},d0
 ret [d2,a2],24
 .balign 4
s_get:                             /* call ..,[d2,d3],12: d0 key */
 mov {FIX:#x},a1
 cmp {K44:#x},d0
 bne 1f
 mov {F(2).replace('a0', 'a1')},d0
 ret [d2,d3],12
1:
 cmp {K24:#x},d0
 bne 2f
 mov {F(3).replace('a0', 'a1')},d0
 ret [d2,d3],12
2:
 clr d0
 ret [d2,d3],12
"""


def prepare(m):
    code, _, sy, _ = SB3.assemble(stub_src(), STUBS, {})
    im = bytearray(m)
    for k, a in STUBBED:
        im[a - BASE:a - BASE + 5] = PLV.tramp(a, sy['s_' + k])
    return bytes(im), code, sy


def run_key(prep, ev, *, rec4=0, btn=50, cls=1, movie=0, mode=0, ca196=0, p=None, blk=None, handle=HANDLE, limit=20000,
            entry='gen', cur=0, b9a8=0, b9ac=0, r188=0, b3c6=0, d793b=0, c8929=0, gset=0, rec=None, stage=0):
    """One key event through a key handler (ENTRIES). -> (result, mem, calls) ; calls = [(stub, {reg: v})] in order."""
    im, code, sy = prep
    if rec is None:
        rec = bytearray(0x200)               # event record / CA context; +196 the state word of the btn 20 early exit
        struct.pack_into('<8I', rec, 0, ev, rec4, 0x1111 + ev, 0x2222, 0x3333, 0x4444, 0x5555, 0x6666)
        struct.pack_into('<I', rec, 196, ca196)
        struct.pack_into('<II', rec, 32, 1, 0x77)
        struct.pack_into('<I', rec, 188, r188)
    ca = bytes(range(256)) * 4
    stk = bytearray(0x1000)
    struct.pack_into('<I', stk, SP0 - STKR, sy['s_ret'])
    for i in range(1, 16):
        struct.pack_into('<I', stk, SP0 - STKR + 4 * i, 0xc0de0000 + i)
    b = blk or bytes(16384)
    rg = [Region('img', BASE, im, 'rx'), Region('stubs', STUBS, code, 'rx'),
          Region('state', 0x622cbcc0, struct.pack('<HHI', 0, handle, 0), 'rw', True),
          Region('pool', P_AT, p or PLV.pblock(), 'rw', True),
          Region('blk', BLK, b, 'rw', True), Region('blkc', BLKC, b, 'rx', alias_of='blk'),
          Region('ca', CA, bytes(ca), 'rw', True), Region('rec', REC, bytes(rec), 'rw', True),
          Region('fix', FIX, struct.pack('<8I', btn, cls, movie, mode, b3c6, d793b, c8929, gset).ljust(0x40, b'\0'), 'rw', True),
          Region('g1', G1, struct.pack('<4I', 0x9a0, cur, b9a8, b9ac), 'rw', True),
          Region('g2', G2, struct.pack('<4I', 0xdd0, 0xdd4, 0x1dd8, 0x1ddc), 'rw', True),
          Region('stage', STG, struct.pack('<HBB', 0x5a5a, stage, 0xa5), 'rw', True),
          Region('stack', STKR, bytes(stk), 'rw', True)]
    regs = dict(d0=ev, d1=0x1d1, d2=0xd2d2, d3=0xd3d3, a0=CA, a1=REC, a2=0xa2a2, a3=0xa3a3, mdr=sy['s_ret'], pc=ENTRIES[entry], sp=SP0)
    r = execute(rg, regs, sy['s_ret'], limit=limit, trace_limit=limit, timeout=120)
    mem = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}
    at = {sy['s_' + k]: k for k, _ in STUBBED}
    hook = {}
    if blk:
        hw = struct.unpack_from('<I', blk, KH.HW)[0]
        if BLKC <= hw < BLKC + 16384:
            at[hw] = 'hook'
    calls = [(at[t['pc']], {k: t[k] for k in LOGR}) for t in r['trace'] if t['pc'] in at]
    return r, mem, calls


def ok_run(r, sy):
    return not r['fault'] and r['registers']['pc'] == sy['s_ret'] and not r.get('trace_truncated')


MEMS = ('state', 'pool', 'blk', 'ca', 'rec', 'fix', 'g1', 'g2')


def same(rb, rn, sy_b, sy_n, skip=()):
    """Everything after the handler == BASE: registers but MDR, the frame and caller stack, memory, stub call log."""
    (r0, m0, c0), (r1, m1, c1) = rb, rn
    if not (ok_run(r0, sy_b) and ok_run(r1, sy_n)):
        return False, 'fault / no return'
    g0, g1 = r0['registers'], r1['registers']
    d = [k for k in KEEP if g0[k] != g1[k]]
    lo = SP0 - 48 - STKR                    # the deeper handler frame (site 1: 48; site 0: 40) and the caller's stack
    if m0['stack'][lo:] != m1['stack'][lo:]:
        d.append('stack')
    d += [k for k in MEMS if k not in skip and m0[k] != m1[k]]
    plug = ('hook', 'get')                  # the plugin's own calls (hook, prop_get through ka_get); stock makes none
    if any(c in plug for c, _ in c0) or [x for x in c0] != [x for x in c1 if x[0] not in plug]:
        d.append(f'calls {[c for c, _ in c0]} / {[c for c, _ in c1]}')
    return not d, d


def t_s(base, new, base_s, new_s):
    import numpy as np
    ours = [(int(e['addr'], 16), len(e['new']) // 2) for e in new_s['edits']
            if e['kind'] == '0x100' and not e['addr'].startswith('off:') and e.get('source') == KH.SRC]
    ours.append((int(new_s['keyhook']['api_mov'], 16) + 2, 4))     # pl_chk mov imm32 (merged into plugin_loader's edit)
    ov = 'overlay_probe' in new_s                  # the Extras overlay layer, after keyhook (its own verify.py)
    if ov:
        ours += [(int(e['addr'], 16), len(e['new']) // 2) for e in new_s['edits']
                 if e['kind'] == '0x100' and not e['addr'].startswith('off:') and e.get('source') == 'patches/overlay_probe']
    diff = [BASE + int(i) for i in np.nonzero(np.frombuffer(base, np.uint8) != np.frombuffer(new, np.uint8))[0]]
    stray = [hex(a) for a in diff if not any(s <= a < s + n for s, n in ours)]
    kh_s = KH.apply(base_s)
    if ov:
        kh_s = _load('ep7_ov_build_v', ROOT / 'patches/overlay_probe/build.py').apply(kh_s, new_s['keyhook']['version'])
    rebuilt = PLV.ST_img(kh_s) == new
    k0 = int(new_s['keyhook']['symbols']['kh_ret0'], 16)
    words = all(struct.unpack_from('<I', new, w - BASE)[0] == k0 for w in KH.SUBCMD)
    words &= all(struct.unpack_from('<I', base, w - BASE)[0] == v for w, v in KH.SUBCMD.items())
    lo, hi = KH.CLAIM
    claim = base[lo - BASE:hi - BASE] == STOCK[lo - BASE:hi - BASE]
    return not stray and rebuilt and words and claim, \
        f'{len(diff)} B differ, all inside {len(ours)} keyhook{" + overlay" if ov else ""} sites (stray {stray[:3]}); rebuilt from BASE == NEW; sdk words -> {k0:#x}'


PATHS = (dict(btn=50, cls=1), dict(btn=33, cls=2), dict(btn=12, cls=0), dict(btn=0, cls=1),
         dict(btn=20, ca196=23043), dict(btn=20, ca196=23553), dict(btn=20, ca196=0, cls=2), dict(rec4=152, cls=1))
# site 1 (0x60cebc89) paths: no-op actions, out of range, same-mode close (43/44/51/52/62), 12/39 with state 0x5802,
# 18 (re-mapped key), 26 (0x60ceb3c6 / 0x60cd793b branches), 0x6233b9ac != 0 early return
PATHS1 = (dict(btn=50), dict(btn=49, cur=49), dict(btn=5), dict(btn=70), dict(btn=43, cur=43), dict(btn=43, cur=44),
          dict(btn=62, cur=62), dict(btn=51, cur=52), dict(btn=12, r188=22530), dict(btn=12), dict(btn=39, r188=22530),
          dict(btn=18, b9a8=7, c8929=0x30, cur=0x30), dict(btn=18, c8929=1, cur=2), dict(btn=26),
          dict(btn=26, d793b=1, cur=5), dict(btn=26, b3c6=1), dict(btn=26, b3c6=2), dict(btn=26, d793b=1, cur=26),
          dict(b9ac=1, btn=43, cur=43))
ENTRY_PATHS = (('gen', PATHS), ('sel', PATHS1), ('k28', tuple(dict(x, gset=0) for x in PATHS1) + (dict(gset=1),)))


def events():
    return [struct.unpack_from('<5I', STOCK, EV_TBL - BASE + 20 * i) for i in range(EV_N)]


def with_hook(blk, hw):
    b = bytearray(blk)
    struct.pack_into('<I', b, KH.HW, hw & 0xffffffff)
    return bytes(b)


def ready_p():
    return PLV.pblock(int.from_bytes(b'EP7K', 'little'), BLK)


def n_cases(hello_blk):
    """(name, kw) states that must run stock: no plugin, hello (hook word 0), bad hook words."""
    hb = hello_blk
    c = [('P invalid', dict(handle=0)), ('no EP7K', dict(p=PLV.pblock())),
         ('ready, blank B', dict(p=ready_p(), blk=bytes(16384))), ('hello', dict(p=ready_p(), blk=hb))]
    for name, hw in (('header', BLKC + 16), ('header end', BLKC + 31), ('end of B', BLKC + 16384),
                     ('uncached B', BLK + 32), ('stock code', ENTRY), ('-1', -1)):
        c.append((f'bad hook {name}', dict(p=ready_p(), blk=with_hook(hb, hw))))
    return c


def t_n(pb, pn, hello_blk, entries=('gen', 'sel', 'k28')):
    bad, n, per = [], 0, []
    assert struct.unpack_from('<I', hello_blk, KH.HW)[0] == 0
    cases = n_cases(hello_blk)
    for entry, paths in ENTRY_PATHS:
        if entry not in entries:
            continue
        m = 0
        for i, (ev, kc, sub, _, _) in enumerate(events()):
            for j, (name, kw) in enumerate(cases):
                path = paths[(i + j) % len(paths)]
                g, d = same(run_key(pb, ev, entry=entry, **path, **kw), run_key(pn, ev, entry=entry, **path, **kw), pb[2], pn[2])
                m += 1
                if not g:
                    bad.append((entry, hex(ev), kc, name, path, d))
        n += m
        per.append(f'{entry} {m} ({len(paths)} paths)')
    return not bad, (f'{n} runs: {EV_N} events x {len(cases)} states (no plugin x3, hello, 6 bad hook words) per entry, '
                     f'{", ".join(per)} == BASE; bad {len(bad)} {bad[:3]}')


def load_plugin(post_prep, apf, f):
    """Real loader (ap_post, plugin_loader verify harness) -> (P, B) after the first half-press."""
    r, mem, lg = PLV.run_post(post_prep, ap=apf, plugin=f)
    if not PLV.ok_run(r) or mem['pool'][PL.PS:PL.PS + 4] != b'EP7K' or lg[8] != 0:
        raise SystemExit(f'loader did not publish the plugin: {r["fault"]} {lg}')
    return mem['pool'], mem['blk']


TESTS = 'SNCP'                               # H, D, R: --only=HDR (H's handled path is also covered by C presses 2-4)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--only=')]
    only = next((a[7:] for a in sys.argv[1:] if a.startswith('--only=')), TESTS)
    v031d, new_s = (json.loads(Path(p).read_text()) for p in args[:2])
    disk = Path(args[2]) if len(args) > 2 else None
    card = Path(args[3]) if len(args) > 3 else None
    base_s = V32.apply(v031d, keyhook=False)
    if 'keyhook' not in new_s or 'keyhook' in base_s:
        raise SystemExit('NEW must be the keyhook=True build')
    base, new = PLV.ST_img(base_s), PLV.ST_img(new_s)
    pb, pn = prepare(base), prepare(new)
    post_n = PLV.prepare(new, new_s)
    apf = PLV.AV.apfile()
    ph, bh = load_plugin(post_n, apf, HB.build()[0])
    ctx = dict(v031d=v031d, base=base, new=new, base_s=base_s, new_s=new_s, pb=pb, pn=pn, post_n=post_n, apf=apf, hello=(ph, bh),
               disk=disk, card=card)
    ok = True
    for tag in only:
        g, txt = globals()['t_' + tag.lower() + '_run'](ctx)
        print(f"{'PASS' if g else 'FAIL'} {tag} {txt}", flush=True)
        ok &= g
    print('ALL PASS' if ok and only == TESTS else ('PASS (subset ' + only + ')' if ok else 'FAILURES'))
    sys.exit(0 if ok else 1)


def t_s_run(c):
    return t_s(c['base'], c['new'], c['base_s'], c['new_s'])


def t_n_run(c):
    return t_n(c['pb'], c['pn'], c['hello'][1])


HOOK_OFF = 36                                # test plugins: init at 32 (clr d0; rets), hook at 36
TEST_HOOKS = {
    'ret 1': ' mov 1,d0\n rets\n',
    'ret 1, clobbers': ' movm [d2,d3,a2,a3],(sp)\n add -64,sp\n mov 0x5a5a,d2\n mov d2,(8,sp)\n mov 0x11,d1\n mov 0x22,a0\n'
                       ' mov 0x33,a1\n add 64,sp\n movm (sp),[d2,d3,a2,a3]\n mov 1,d0\n rets\n',
    'ret 0': ' clr d0\n rets\n',
    'ret 2': ' mov 2,d0\n rets\n',
    'ret 0, clobbers': ' mov 0x11,d1\n mov 0x22,a0\n mov 0x33,a1\n mov -1,d0\n add 1,d0\n rets\n',
}


def test_plugin(body):
    src = f""" .am33_2
 .text
 .global _start
_start:
 .space 32
 clr d0
 rets
 .balign 4
{body}"""
    code, dis = HB.assemble(src)
    HB.check(code, dis)
    f = bytearray(HB.make(code))
    if f[32:34] != b'\x00\xf0' or len(f) <= HOOK_OFF:
        raise SystemExit('test plugin layout')
    b = bytearray(16384)
    b[:len(f)] = f
    struct.pack_into('<I', b, KH.HW, BLKC + HOOK_OFF)
    return bytes(b)


def handled(rb, rn, sy_n, ev, want_calls=('hook',), site=0, skip=()):
    """rn left through the handler's own epilogue after one hook call; memory and caller stack == the stock run rb."""
    (r0, m0, _), (r1, m1, c1) = rb, rn
    g = r1['registers']
    d = []
    if r1['fault'] or g['pc'] != sy_n['s_ret'] or r1.get('trace_truncated'):
        return False, [f'no return {r1["fault"]} {g["pc"]:#x}']
    want = dict(d2=0xd2d2, d3=0xd3d3, a2=0xa2a2, a3=0xa3a3, sp=SP0)
    d += [k for k, v in want.items() if g[k] != v]
    if tuple(c for c, _ in c1) != tuple(want_calls):
        d.append(f'calls {[c for c, _ in c1]}')
    else:
        h = c1[0][1]
        if (h['d0'], h['d1'], h['d2'], h['a0'], h['a1']) != (ev, BLK, site, CA if site == 0 else 0, REC):
            d.append(f'hook args {h}')
    if m0['stack'][SP0 - STKR:] != m1['stack'][SP0 - STKR:]:
        d.append('caller stack')
    d += [k for k in MEMS if k not in skip and m0[k] != m1[k]]
    return not d, d


def t_h(pb, pn):
    evs = [e[0] for e in events()][::9] + [EV_FN, EV_FN_UP]
    bad, n = [], 0
    for entry, paths in ENTRY_PATHS:
      site = 0 if entry == 'gen' else 1
      for name, body in TEST_HOOKS.items():
        blk = test_plugin(body)
        for i, ev in enumerate(evs):
            path = dict(paths[i % len(paths)], entry=entry)
            if name.startswith('ret 1') and site == 1:
                path = dict(btn=50, entry=entry)  # a stock path that stores nothing: the reference for "handled"
            if entry == 'k28':
                path['gset'] = 0                 # reach the site
            kw = dict(p=ready_p(), blk=blk, **path)
            rb, rn = run_key(pb, ev, **kw), run_key(pn, ev, **kw)
            g, d = handled(rb, rn, pn[2], ev, site=site) if name.startswith('ret 1') else same(rb, rn, pb[2], pn[2])
            if name.startswith('ret 1') and entry == 'k28':
                g, d = handled(rb, rn, pn[2], ev, want_calls=('gset', 'hook'), site=1)
            if name.startswith('ret 0') or name == 'ret 2':
                g &= [c for c, _ in rn[2]].count('hook') == 1
            n += 1
            if not g:
                bad.append((entry, name, hex(ev), d))
    return not bad, (f'{n} runs (entries gen / sel / k28): return 1 (plain / clobbering d0..a1 + own frame) -> handler epilogue, pc / sp / d2 d3 a2 a3 '
                     f'as entered, one hook call (d0 ev, d1 B, a0 CA, a1 record), no stock callee; return 0 / 2 / 0 + clobbers '
                     f'-> == BASE; bad {len(bad)} {bad[:3]}')


def t_h_run(c):
    return t_h(c['pb'], c['pn'])


SC_PATH = ROOT / 'generated/plugins/shortcut_cycle/EP7MOD/PLUGIN.BIN'
GETS = ('hook', 'get', 'get')
AP_MODES = (14,) + tuple(range(209, 217))


def t_c(c):
    """shortcut_cycle through the real loader: 1 stock, 2 stock exit + arm, 3 aspect, 4 stock exit; resets; movie/AP."""
    pn, pb, new, base = c['pn'], c['pb'], c['new'], c['base']
    f = (c['card'] or SC_PATH).read_bytes()
    p, blk0 = load_plugin(c['post_n'], c['apf'], f)
    api = int(c['new_s']['keyhook']['api'], 16)
    hw = struct.unpack_from('<I', blk0, KH.HW)[0]
    k = blk0.find(struct.pack('<I', api), 32, len(f))
    if not (BLKC + 32 <= hw < BLKC + len(f)) or k < 0:
        raise SystemExit(f'shortcut hook word {hw:#x} / API slot {k}')
    ST = k + 4
    bad, n = [], [0]

    def with_st(st):
        b = bytearray(blk0); b[ST] = st; return bytes(b)

    def run(st, entry, ev, **kw):
        kw = dict(kw, p=p, blk=with_st(st), entry=entry)
        n[0] += 1
        return run_key(pb, ev, **kw), run_key(pn, ev, **kw)

    def stock(tag, st, want_st, entry, ev, **kw):
        rb, rn = run(st, entry, ev, **kw)
        g, d = same(rb, rn, pb[2], pn[2], skip=('blk',))
        b = rn[1]['blk']
        g &= b[ST] == want_st and b[:ST] + b[ST + 1:] == blk0[:ST] + blk0[ST + 1:]
        if not g:
            bad.append((tag, st, entry, hex(ev), kw, d, b[ST]))

    def stage_ok(rn, site, dec, before=0):
        m = rn[1]['stage']
        return m[2] == ((((before >> 4) + 1) << 4) | (dec << 2) | (site + 1)) & 0xff and m[:2] + m[3:] == b'\x5a\x5a\xa5'

    def press(tag, st, want_st, entry, calls, req, replay=None, **kw):
        rb, rn = run(st, entry, EV_FN, btn=50, rec4=0x0100002e, stage=0x70, **kw)   # base: the no-op stock path
        site = 0 if entry == 'gen' else 1
        g, d = handled(rb, rn, pn[2], EV_FN, calls, site=site, skip=('blk', 'rec', 'g2'))
        g2b, g2n = rb[1]['g2'], rn[1]['g2']
        want_g2 = g2b if replay is None else g2b[:8] + struct.pack('<II', replay, replay)
        if g2n != want_g2:
            d.append(f'g2 {g2n.hex()}')
            g = False
        if not stage_ok(rn, site, 2, 0x70):
            d.append(f'stage {rn[1]["stage"].hex()}')
            g = False
        b, r0, r1 = rn[1]['blk'], rb[1]['rec'], rn[1]['rec']
        g &= b[ST] == want_st and b[:ST] + b[ST + 1:] == blk0[:ST] + blk0[ST + 1:]
        g &= (r1[:32] + r1[36:] == r0[:32] + r0[36:]) and struct.unpack_from('<I', r1, 32)[0] == (req or 1)
        if 'sel' in calls:
            sel = dict((x, v) for x, v in rn[2] if x == 'sel')['sel']
            g &= (sel['d0'], sel['a0'], sel['a1']) == (50, CA, REC)
        if not g:
            bad.append((tag, st, entry, kw, d, b[ST], struct.unpack_from('<I', r1, 32)[0]))

    # one pass of the cycle (still mode): 2 = stock exit + replay of the press (ka_rep), the replay = site 0 with ST 2
    stock('1 stock', 0, 1, 'gen', EV_FN)
    rb, rn = run(0, 'gen', EV_FN)
    if not stage_ok(rn, 0, 1):
        bad.append(('stage after press 1', rn[1]['stage'].hex()))
    press('2 exit+replay', 1, 2, 'sel', GETS + ('d2330',), 158, replay=0x0100002e, cur=49)
    press('2r aspect', 2, 3, 'gen', GETS + ('sel',), None)
    press('3 exit', 3, 0, 'sel', GETS, 158, cur=50)
    stock('key held: stock', 1, 0, 'sel', EV_FN, cur=49, b9ac=1)
    # stage with no plugin: site 1, not called
    rb, rn = run_key(pb, EV_FN, entry='sel', btn=50), run_key(pn, EV_FN, entry='sel', btn=50)
    if not same(rb, rn, pb[2], pn[2])[0] or rn[1]['stage'][2] != 0x12 or rb[1]['stage'][2] != 0:
        bad.append(('stage, no plugin', rn[1]['stage'].hex()))
    n[0] += 1
    # one reset: aspect closed some other way (OK / half-press) -> the next Fn is press 1 again
    stock('reset: closed by OK after 3', 3, 1, 'gen', EV_FN)
    # movie / AP chain to stock at both sites, from every state
    for st in range(4):
        stock('movie, site 0', st, 0, 'gen', EV_FN, movie=1)
        stock('movie, site 1', st, 0, 'sel', EV_FN, movie=1, cur=49)
        for m in AP_MODES:
            stock(f'AP {m}, site 0', st, 0, 'gen', EV_FN, mode=m)
            stock(f'AP {m}, site 1', st, 0, 'sel', EV_FN, mode=m, cur=50)
    # Setup > Firmware
    shown = []
    for site in PL.FW_SITES:
        fb, tb, *_ = PLV.fw_run(base, site, '1.1', p, blk0)
        fn, tn, *_ = PLV.fw_run(new, site, '1.1', p, blk0)
        shown.append(tn)
        if fb or fn or tb != tn or tn != '0.32S':          # BASE has the B+28 hook too: same text
            bad.append(('firmware', hex(site), tn, tb))
    return not bad, (f'{n[0]} runs: cycle 1 stock -> 2 exit + replay (ka_rep: 158, dd8 = ddc = record+4, 0x60cd2330) -> '
                     f'replay at site 0 -> aspect (ka_sel 50) -> 3 exit; key-held flag -> stock; stage byte per press; reset after a close by OK; '
                     f'movie / AP 14, 209..216 at both sites from every state == BASE; Firmware {shown}; bad {len(bad)} {bad[:3]}')


def t_c_run(c):
    return t_c(c)


def t_d(c):
    im, code, sy = c['pn']
    bad = []
    for w in KH.SUBCMD:
        tgt = struct.unpack_from('<I', im, w - BASE)[0]
        stk = bytearray(0x1000)
        struct.pack_into('<I', stk, SP0 - STKR, sy['s_ret'])
        rg = [Region('img', BASE, im, 'rx'), Region('stubs', STUBS, code, 'rx'), Region('stack', STKR, bytes(stk), 'rw', True)]
        regs = dict(d0=0x5a5a, d1=0x1d1, d2=0xd2d2, d3=0xd3d3, a0=0xa0a0, a1=w, a2=0xa2a2, a3=0xa3a3, mdr=sy['s_ret'],
                    pc=tgt, sp=SP0)
        r = execute(rg, regs, sy['s_ret'], limit=100, timeout=60)
        g = r['registers']
        want = dict(regs, d0=0, pc=sy['s_ret'])
        diff = [k for k in want if k != 'mdr' and g[k] != want[k]]
        st = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}['stack'] == bytes(stk)
        if r['fault'] or diff or not st or r['completed'] != 2:
            bad.append((hex(w), hex(tgt), r['fault'], diff, r['completed']))
    return not bad, f'sdk api / starttimer / stoptimer words -> clr d0; rets: d0 = 0, back to the caller in 2 insns, rest as entered; bad {bad}'


def t_d_run(c):
    return t_d(c)


def t_r_run(c):
    """plugin_loader's verifier on NEW where it applies: N / R / V (init gets the v1.1 table) / F; S is BASE-specific."""
    base_pl = V32.apply(c['v031d'], plugins=False)
    pb = PLV.prepare(PLV.ST_img(base_pl), base_pl)
    pn = c['post_n']
    PLV.PL_SYMS.clear()
    PLV.PL_SYMS.update(c['new_s']['plugin_loader']['symbols'])
    PLV.PL_SYMS['pl_api'] = c['new_s']['keyhook']['api']
    out, ok = [], True
    g, t = PLV.t_n(pb, pn, c['apf']); out.append(('N', g)); ok &= g
    g, t = PLV.t_r(pb, pn, c['apf']); out.append(('R', g)); ok &= g
    g, t, hs = PLV.t_v(pb, pn, c['apf']); out.append(('V', g)); ok &= g
    g, t = PLV.t_f(PLV.ST_img(base_pl), c['new'], hs); out.append(('F', g)); ok &= g
    return ok, 'plugin_loader on the keyhook build: ' + ', '.join(f"{k} {'pass' if v else 'FAIL'}" for k, v in out) + \
        ' (its S / P run on the keyhook=False spec separately)'


def t_p_run(c):
    g, txt = PLV.t_p(c['new_s'], c['new'], c['disk'], None)
    f = c['card'] or SC_PATH
    data = f.read_bytes()
    g &= data == SC.build()[0]
    return g, txt + f'; {f.name} == shortcut_cycle rebuild ({len(data)} B, sha256 {hashlib.sha256(data).hexdigest()[:16]})'


if __name__ == '__main__':
    main()
