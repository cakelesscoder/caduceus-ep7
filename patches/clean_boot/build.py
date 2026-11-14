#!/usr/bin/env python3
"""Clean restart: the card table P is cleared right after its malloc, so no mark or pointer of an earlier session survives a
crash-restart (DRAM keeps its contents, and the pools hand out the same blocks). docs/GRAIN_HANG.md "Clean restart"; cb.s.in has
the contract. Layer on the v0.33 chain, after halation_h6 (the code takes the place of h2's hl_pc, unused since h6). Offline.

  .venv/bin/python -I patches/v032/build.py releases/v0.31d/edits.json --out generated/clean_boot/edits.json --version 0.33 \\
      --extra grain_g2=patches/grain_g2/build.py --extra halation_h6=patches/halation_h6/build.py \\
      --extra crash_log=patches/crash_log/build.py --extra clean_boot=patches/clean_boot/build.py

apply(spec, version) -> spec. Edits:
  - sd_load's `mov a0,a2; cmp 0,a2; bne +5` after its `call ep7_malloc,[],4` (5 B, inside the card loader's edit) -> `jmp cb_zero`;
  - cb_zero at 0x605b7780, section 3 like the loader it is entered from: the place of halation h2's `.hlp` (hl_pc, 123 B), which
    halation_h6 left unused. The bytes after cb_zero are stock FF again; `.hlp` leaves halation_h6's reclaim list and hl_pc
    halation's symbols.
The layer reads nothing of the grain layers, so it gives the same two edits on any chain that has the card loader v3 and
halation_h6: `build.py SPEC --out OUT` on a finished spec (fw_version applied) differs from the chain's output only in where the
`clean_boot` key sits.
"""
import argparse, copy, hashlib, importlib.util, json, re, struct
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SRC = 'patches/clean_boot'


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


XP = _load('ep7_xp_build_cb', ROOT / 'patches/extras_pages/build.py')
ST, KH, B3 = XP.ST, XP.KH, XP.B3
BASE, STOCK = XP.BASE, XP.STOCK

# ---- the code: section 3 (the loader's section), where halation h2 kept hl_pc
HLP = ('.hlp', 0x605b7780, 0x605b77fb)    # its entry in halation_h6's reclaim list
HLP_SHA = '5bda2e8ed7e8d922'              # h2's hl_pc bytes: what this layer may overwrite
AT, CLAIM = HLP[1], (HLP[1], 0x605b7800)  # the claim runs to the section's load end, as `.hlp`'s did
# ---- the hook: sd_load, after `mov 1024,d0; call ep7_malloc,[],4`
SITE_OFF = 10
SITE_OLD = bytes.fromhex('92ba00c905')    # mov a0,a2; cmp 0,a2; bne +5 (over the loader's `jmp sd_out`)
CLASS1 = (0x60026df8, 0x60026e38)         # heap class 1 (129..2048 B): the pool base and block stride words of the allocator's tables
BAD = {'mul', 'mulu', 'div', 'divu', 'ext', 'setlb', 'llt', 'lne', 'leq', 'lra', 'lcc', 'lcs', 'trap', 'rti', 'rets', 'retf', 'ret', 'call', 'calls', 'movm'}


def u32(im, a):
    return struct.unpack_from('<I', im, a - BASE)[0]


def refs(im, lo, hi, off, allow=()):
    """abs32 at every byte on the four aliases + d16 / d32 call, calls and jmp encodings into [lo, hi), as patches/crash_log
    refs() and tools/ep7_xref.py. -> [(kind, address)] minus the allowed source ranges."""
    d = np.frombuffer(im, np.uint8).astype(np.int64)
    w = d[:-3] | (d[1:-2] << 8) | (d[2:-1] << 16) | (d[3:] << 24)
    pc = np.arange(len(d) - 8, dtype=np.int64) + BASE
    ok = lambda at: any(x <= at < y for x, y in allow)
    bad = []
    for o in (0, 0x40000000, off, (off + 0x40000000) & 0xffffffff):
        a, b = (lo + o) & 0xffffffff, (hi + o) & 0xffffffff
        bad += [('abs32', int(i) + BASE) for i in np.nonzero((w >= a) & (w < b))[0] if not ok(int(i) + BASE)]
    for op, at_, n in (((0xdd,), 1, 4), ((0xdc,), 1, 4), ((0xcd,), 1, 2), ((0xcc,), 1, 2), ((0xfa, 0xff), 2, 2), ((0xfc, 0xff), 2, 4)):
        m = d[:-8] == op[0]
        if len(op) == 2:
            m &= d[1:-7] == op[1]
        b = [d[at_ + k:len(d) - 8 + at_ + k] for k in range(n)]
        disp = b[0] | (b[1] << 8) if n == 2 else b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24)
        disp = np.where(disp >= (1 << (8 * n - 1)), disp - (1 << (8 * n)), disp)
        bad += [('rel', int(x) + BASE) for x in np.nonzero(m & (pc + disp >= lo) & (pc + disp < hi))[0] if not ok(int(x) + BASE)]
    return sorted(set(bad))


def check_site(spec, stock, im):
    """sd_load's first instructions as mapped -> (site, the loader's two next instructions, its symbols)."""
    m = spec.get('sd_bundles_v3')
    if not m or int(m['buf_size']) != B3.BUF_SIZE or int(m['pool'], 16) != B3.POOL:
        raise SystemExit('needs the card loader v3 with its 1024-B block P')
    B3.pool_check(stock)                                         # malloc: 129..2048 B is class 1; free: its pool bounds
    if u32(stock, CLASS1[0]) != B3.POOL or u32(stock, CLASS1[1]) < B3.BUF_SIZE:
        raise SystemExit('heap class 1: a block is shorter than the bytes we clear, or the pool moved')
    sd = {k: int(v, 16) for k, v in m['symbols'].items()}
    sv = {k: int(v, 16) for k, v in m['services'].items()}
    ld, site = sd['sd_load'], sd['sd_load'] + SITE_OFF
    cont, none = site + 8, site + 5
    at = lambda a, n: im[a - BASE:a - BASE + n]
    tgt = lambda a: a + struct.unpack_from('<i', im, a + 1 - BASE)[0]         # of a d32 call
    if at(ld, 3) != b'\x2c' + struct.pack('<H', B3.BUF_SIZE) or at(ld + 3, 1) != b'\xdd' or tgt(ld + 3) != sv['ep7_malloc'] or at(ld + 8, 2) != b'\x00\x04':
        raise SystemExit('sd_load: mov 1024,d0; call ep7_malloc,[],4 not found')
    if at(site, 5) != SITE_OLD:
        raise SystemExit(f'sd_load: site bytes {at(site, 5).hex()}')
    if at(none, 1) != b'\xcc' or none + struct.unpack('<h', at(none + 1, 2))[0] != sd['sd_out'] or at(sd['sd_out'], 3) != bytes.fromhex('dff024'):
        raise SystemExit('sd_load: jmp sd_out (ret [d2,d3,a2,a3],36) not found after the site')
    # the two registers the stub leaves changed for a moment are loaded here, before anything reads them: a0 = the path, a1 = the mode
    if at(cont, 6) != b'\xfc\xdc' + struct.pack('<I', sd['sd_path']) or at(cont + 6, 6) != b'\xfc\xdd' + struct.pack('<I', sd['sd_mode']):
        raise SystemExit('sd_load: mov sd_path,a0; mov sd_mode,a1 not found after the site')
    if at(cont + 12, 1) != b'\xdd' or tgt(cont + 12) != sv['ep7_fopen'] or at(cont + 17, 2) != b'\x00\x04':
        raise SystemExit('sd_load: call ep7_fopen,[],4 not found')
    # the loader decodes linearly with the site as three whole instructions, and nothing of it branches into them
    ins = B3.disasm(im[sd['sd_hook'] - BASE:sd['sd_path'] - BASE], sd['sd_hook'])
    addr = {a for a, _, _ in ins}
    if not {site, site + 1, site + 3, none, cont} <= addr or any(op.startswith('.') or op == '(bad)' for _, op, _ in ins):
        raise SystemExit('the card loader does not decode as mapped')
    for a, op, args in ins:
        if any(site < int(t, 16) < none or CLAIM[0] <= int(t, 16) < CLAIM[1] for t in re.findall(r'0x([0-9a-f]{8})', args)):
            raise SystemExit(f'loader branch into the site or the claim from {a:#x}: {op} {args}')
    return site, cont, none, sd


def check_claim(spec, stock, im, site):
    """h2's hl_pc is where halation_h6 left it, unused: hl_run is `jmp h6_run`, and the only references into the piece come
    from the other h2 code that h6 lists as unused."""
    hl, h6 = spec.get('halation', {}), spec.get('halation_h6')
    if not h6 or hl.get('symbols', {}).get('hl_pc') != hex(AT):
        raise SystemExit('needs halation_h6 (the code takes the place of h2\'s hl_pc, which h6 left unused)')
    rec = {r[0]: (int(r[1], 16), int(r[2], 16)) for r in h6['reclaim']}
    if rec.get(HLP[0]) != HLP[1:]:
        raise SystemExit('halation_h6 does not list hl_pc (.hlp) as unused: another layer took it')
    run, h6_run = int(hl['symbols']['hl_run'], 16), int(h6['symbols']['h6_run'], 16)
    if im[run - BASE:run - BASE + 5] != b'\xdc' + struct.pack('<i', h6_run - run):
        raise SystemExit('hl_run is not `jmp h6_run`: h2\'s passes may still run')
    if hashlib.sha256(im[HLP[1] - BASE:HLP[2] - BASE]).hexdigest()[:16] != HLP_SHA:
        raise SystemExit('hl_pc differs from h2: another layer uses these bytes')
    held = [e for e in spec['edits'] if e['kind'] == '0x100' and not e['addr'].startswith('off:') and int(e['addr'], 16) < CLAIM[1] and CLAIM[0] < int(e['addr'], 16) + len(e['new']) // 2]
    if len(held) != 1 or int(held[0]['addr'], 16) != HLP[1] or len(held[0]['new']) // 2 != HLP[2] - HLP[1] or held[0].get('source') != 'patches/halation':
        raise SystemExit('the claim is not exactly halation\'s .hlp edit')
    lo3, hi3, off3 = KH.sec(stock, 3)
    end = int(spec['sd_bundles_v3']['code_at'], 16) + int(spec['sd_bundles_v3']['code_len'])
    if not (lo3 <= site < end <= CLAIM[0] and CLAIM[1] == hi3):
        raise SystemExit('the loader and the claim are not in section 3 as mapped')
    if set(stock[end - BASE:CLAIM[1] - BASE]) != {0xff} or set(im[end - BASE:CLAIM[0] - BASE]) | set(im[HLP[2] - BASE:CLAIM[1] - BASE]) != {0xff}:
        raise SystemExit('section-3 tail: not FF where it should be')
    dead = [v for k, v in rec.items() if k != HLP[0]]
    bad = refs(im, CLAIM[0], CLAIM[1], off3, allow=dead)
    if bad:
        raise SystemExit(f'reference into the claim: {[(k, hex(a)) for k, a in bad[:8]]} ({len(bad)})')
    if refs(im, site + 1, site + 5, off3):
        raise SystemExit('reference into the site')
    return held[0]


def build_code(site, cont, none):
    code, lst, sy, _ = B3.assemble(B3.subst((HERE / 'cb.s.in').read_text(), dict(site=hex(site), size=B3.BUF_SIZE)), AT, dict(ep7_sd_cont=cont, ep7_sd_none=none))
    if sy['cb_zero'] != AT or sy['cb_end'] != AT + len(code) or len(code) > HLP[2] - HLP[1]:
        raise SystemExit('layout')
    ins = B3.disasm(code, AT)
    if any(op.startswith('.') or op == '(bad)' or op in BAD for _, op, _ in ins) or any(code[a - AT] == 0xfb for a, _, _ in ins):
        raise SystemExit('undecodable or forbidden instruction, or an fb-prefixed form')
    loop = next(a for a, op, args in ins if (op, args) == ('add', '-1,a0'))
    # the whole stub, instruction by instruction: the replay, the byte loop, the two ways back
    want = [('mov', 'a0,a2'), ('cmp', '0,a2'), ('beq', hex(sy['cb_none'])), ('mov', 'd0,a1'), ('clr', 'd0'), ('add', f'{B3.BUF_SIZE},a0'),
            ('add', '-1,a0'), ('movbu', 'd0,(a0)'), ('cmp', 'a2,a0'), ('bne', hex(loop)), ('mov', 'a1,d0'), ('cmp', '0,a2'), ('jmp', hex(cont)), ('jmp', hex(none))]
    if [(op, args) for _, op, args in ins] != want:
        raise SystemExit(f'cb_zero is not the reviewed sequence: {[(op, args) for _, op, args in ins]}')
    # and what follows from it, checked on its own: one store, a byte through a0; no stack, no word or halfword access
    st = B3.store_audit(ins)
    if [(txt, kd) for _, txt, kd, _ in st] != [('movbu d0,(a0)', 'ind')] or any('sp' in args for _, _, args in ins) or sum('(' in args for _, _, args in ins) != 1:
        raise SystemExit(f'stores / memory operands: {st}')
    if code[:3] != SITE_OLD[:3] or code[3] != 0xc8:              # the displaced bytes, the branch with its sense turned
        raise SystemExit('replay')
    return code, sy, lst


def put(spec, stock, addr, old, new, why):
    """Into the edit that covers addr (the card loader), as patches/crash_log put()."""
    im = ST.img_of(spec, stock)
    if im[addr - BASE:addr - BASE + len(old)] != old:
        raise SystemExit(f'{addr:#x}: {im[addr - BASE:addr - BASE + len(old)].hex()} != {old.hex()} ({why})')
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a, n = int(e['addr'], 16), len(e['new']) // 2
            if a <= addr and addr + len(new) <= a + n:
                b = bytearray.fromhex(e['new']); b[addr - a:addr - a + len(new)] = new; e['new'] = b.hex()
                e['why'] += f' [clean_boot: {why}]'
                return
            if a < addr + len(new) and addr < a + n:
                raise SystemExit(f'{addr:#x}: straddles edit {e["addr"]}')
    raise SystemExit(f'{addr:#x}: no edit holds it')


def apply(spec, version='0.33'):
    stock = STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    if 'clean_boot' in spec:
        raise SystemExit('clean_boot already applied')
    im = ST.img_of(spec, stock)
    site, cont, none, sd = check_site(spec, stock, im)
    held = check_claim(spec, stock, im, site)
    code, sy, lst = build_code(site, cont, none)
    # the code, in place of halation's .hlp edit: what it does not cover is stock FF again
    held.update(expect=stock[AT - BASE:AT - BASE + len(code)].hex(), new=code.hex(), source=SRC,
                why=f'clean_boot {version}: cb_zero ({len(code)} B, sec 3), the card table P cleared after its malloc. In place of halation '
                    f'h2\'s .hlp (hl_pc, {HLP[2] - HLP[1]} B, unused since halation_h6); the rest of that piece is stock FF again')
    put(spec, stock, site, SITE_OLD, b'\xdc' + struct.pack('<i', sy['cb_zero'] - site), 'sd_load: mov a0,a2; cmp 0,a2; bne -> jmp cb_zero (replays them, clears the block)')
    spec['halation_h6']['reclaim'] = [r for r in spec['halation_h6']['reclaim'] if r[0] != HLP[0]]
    spec['halation']['symbols'] = {k: v for k, v in spec['halation']['symbols'].items() if k != 'hl_pc'}   # its code is gone: the address is cb_zero's
    spec['clean_boot'] = dict(built_by=SRC, version=version, code=[hex(AT), len(code)], claim=[hex(CLAIM[0]), hex(CLAIM[1])], site=hex(site),
                              back=dict(block=hex(cont), none=hex(none)), cleared=B3.BUF_SIZE, took='halation .hlp (h2 hl_pc), unused since halation_h6',
                              symbols={k: hex(v) for k, v in sy.items() if k.startswith('cb_')})
    return spec


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--version', default='0.33')
    ap.add_argument('--listing', type=Path)
    a = ap.parse_args()
    spec = apply(json.loads(a.spec.read_text()), a.version)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(spec, indent=1))
    if a.listing:
        s = spec['clean_boot']
        a.listing.write_text(build_code(int(s['site'], 16), int(s['back']['block'], 16), int(s['back']['none'], 16))[2])
    print(json.dumps({k: v for k, v in spec['clean_boot'].items() if k != 'symbols'}))
