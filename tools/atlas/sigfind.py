#!/usr/bin/env python3
"""Transfer E-P7 atlas names to another Olympus/OM body's main image by masked byte signatures.

Our own code (Caduceus, Apache-2.0). Read-only, offline, no camera. Nothing here contains firmware bytes: the
signatures are made at run time from YOUR copy of the E-P7 1.1 main image (anyone can download the stock file
from OM; `caduceus.py` and docs/RE_HANDOFF.md show how) and they are kept in memory, or in a private cache file
you name with --cache. See docs/RE_HANDOFF.md for the method, the validation and the legal boundary.

For every E-P7 function name (atlas.json `func` rows, optionally autonames.json rows):
  1. disassemble from the entry with GNU objdump (mn10300-elf, -m am33-2) and find the function's extent
     (linear walk until a return/tail jump past the furthest internal branch);
  2. mask every relocatable operand: call/jump/branch displacements that leave the function, and immediates or
     absolute addresses that point into the image, RAM or flash (0x4…, 0x6…, 0xa…). Small constants, struct
     offsets, setting ids and MMIO addresses stay, because they tend to be the same on every body;
  3. note string anchors (immediates that point at a C string) and the call list.
Then, on the other body's image:
  sig      the masked signature (up to --sig-len bytes) is unique in the E-P7 image AND occurs exactly once in
           the target. Shorter prefixes (64/48/32 B) are tried when the full one doesn't match.
  anchor   a string the function loads is found in the target; its references give a candidate entry at the
           same offset, kept if the masked bytes there are similar enough.
  call     a matched caller calls this function at the aligned call site (instruction-level alignment of the
           two listings), and the bytes at the target look like the function.
Every candidate gets a structural score: the similarity of the two mnemonic sequences (difflib ratio).

Output (--out): {"src", "dst", "dst_base", "stats", "candidates": [{ep7_addr, name, other_addr, score, method,
confidence, struct, detail}]}. --names-out writes the accepted rows in autonames.json format, so
tools/atlas/ApplyNames.java (or apply_names.py) can apply them to the target's Ghidra project as proposals.

Usage:
  sigfind.py map  --src EP7_MAIN --dst OTHER_MAIN [--dst-base 0x60020020] [--atlas docs/atlas.json]
                  [--autonames docs/autonames.json --auto-conf high] --out cand.json [--names-out names.json]
  sigfind.py base OTHER_MAIN [CANDIDATE_BASE ...]     # check which CPU base makes string pointers line up
  sigfind.py seeds OTHER_MAIN --base B --out seeds.tsv [--extra names.json]   # Ghidra function seeds
  sigfind.py check cand.json --dst OTHER_MAIN [--truth known.json]   # independent checks per method
  sigfind.py show cand.json [--name N | --sample 15 --seed 1]   # print side-by-side listings for review
"""
import argparse, difflib, json, os, random, re, struct, subprocess, sys
from bisect import bisect_right
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OBJDUMP = os.environ.get('OBJDUMP', str(Path.home() / 'ep7fw-toolchains/mn10300/bin/mn10300-elf-objdump'))
EP7_BASE = 0x60020020
EP7_MAIN_SHA = '5dd9af16'  # prefix of sha256 of the E-P7 1.1 decoded main (00_0100_406a0020.decoded.bin)
MAXLEN = 4096              # longest extent walked
BRANCH = re.compile(r'^(b(?!set|clr|tst|sch)\w*|call|calls|jmp|jsr)$')
STOP = {'ret', 'retf', 'rets', 'rti', 'rtm'}
NUM = re.compile(r'(?<![\w.])-?(?:0x[0-9a-f]+|\d+)(?![\w])')
LINE = re.compile(r'^\s*([0-9a-f]+):\t((?:[0-9a-f]{2} )+)\s*(?:\t(\S+)\s*(.*))?$')


def reloc(v):
    """Values that differ between bodies: pointers into the image, RAM, flash, uncached RAM."""
    v &= 0xFFFFFFFF
    return 0x40000000 <= v < 0x48000000 or 0x60000000 <= v < 0x64000000 or 0xa0000000 <= v < 0xa4000000


class Image:
    def __init__(self, path, base):
        self.path, self.base = str(path), base
        self.data = Path(path).read_bytes()
        self.end = base + len(self.data)

    def has(self, a):
        return self.base <= a < self.end

    def u(self, a, n):
        o = a - self.base
        return self.data[o:o + n]

    def dis(self, start, stop):
        """[(addr, bytes, mnemonic, operands)] from objdump, continuation lines folded in."""
        stop = min(stop, self.end)
        r = subprocess.run([OBJDUMP, '-b', 'binary', '-m', 'am33-2', '-D', '--insn-width=8', f'--adjust-vma={self.base:#x}',
                            f'--start-address={start:#x}', f'--stop-address={stop:#x}', self.path],
                           capture_output=True, text=True, check=True)
        out = []
        for ln in r.stdout.splitlines():
            m = LINE.match(ln)
            if not m:
                continue
            a, b, mn, ops = int(m[1], 16), bytes.fromhex(m[2].replace(' ', '')), m[3], (m[4] or '').strip()
            if mn is None and out and out[-1][0] + len(out[-1][1]) == a:
                p = out[-1]
                out[-1] = (p[0], p[1] + b, p[2], p[3])
            elif mn:
                out.append((a, b, mn, ops))
        return out

    def cstring(self, a, minlen=6):
        """The C string starting at a (printable, NUL-terminated, preceded by NUL or a non-printable), or None."""
        if not self.has(a) or a - 1 < self.base:
            return None
        o = a - self.base
        prev = self.data[o - 1]
        if 0x20 <= prev < 0x7f:
            return None
        e = self.data.find(b'\0', o, o + 512)
        if e < 0 or e - o < minlen:
            return None
        s = self.data[o:e]
        if all(0x20 <= c < 0x7f or c in (9, 10, 13) for c in s) and sum(chr(c).isalpha() for c in s) >= 3:
            return s
        return None


def enc_span(b, val, widths=(4, 3, 2, 1), start=1):
    """Byte span [i, i+w) in instruction bytes b that encodes val little-endian, or None."""
    for w in widths:
        x = (val & ((1 << (8 * w)) - 1)).to_bytes(w, 'little')
        i = b.find(x, start)
        if i >= 0:
            return i, i + w
    return None


def walk(img, entry):
    """Instructions of the function at entry: stop at a return or an exit jump once past every internal branch."""
    ins = img.dis(entry, entry + MAXLEN)
    if not ins or ins[0][0] != entry:
        return []
    out, reach = [], entry
    for i, (a, b, mn, ops) in enumerate(ins):
        if mn in ('.byte', '(bad)') or mn.startswith('.'):
            break
        out.append((a, b, mn, ops))
        end = a + len(b)
        if BRANCH.match(mn) and mn not in ('call', 'calls'):
            m = re.match(r'(0x[0-9a-f]+)', ops)
            if m:
                t = int(m[1], 16)
                if entry < t < entry + MAXLEN and t > reach:
                    reach = t
                if mn in ('jmp', 'bra') and end > reach:
                    break
            elif mn == 'jmp' and end > reach:  # jmp (aN): computed tail or switch
                break
        if mn in STOP and end > reach:
            break
    return out


def make_sig(img, entry):
    """-> dict(pat=[int|None], mn=[...], calls=[(off, target, insn_index)], anchors=[(imm_off, string)], size)."""
    ins = walk(img, entry)
    if not ins:
        return None
    end = ins[-1][0] + len(ins[-1][1])
    pat, calls, anchors = [], [], []
    for k, (a, b, mn, ops) in enumerate(ins):
        m = list(b)
        if BRANCH.match(mn):
            mt = re.match(r'(0x[0-9a-f]+)', ops)
            if mt:
                t = int(mt[1], 16)
                if not (entry <= t < end):
                    sp = enc_span(b, t - a)
                    if sp:
                        for j in range(*sp):
                            m[j] = None
                    else:
                        m[1:] = [None] * (len(m) - 1)
                if mn in ('call', 'calls'):
                    calls.append((a - entry, t, k))
        else:
            for tok in NUM.findall(ops):
                v = int(tok, 0) & 0xFFFFFFFF
                if not reloc(v):
                    continue
                sp = enc_span(b, v, (4, 3)) or enc_span(b, v, (2,))
                if sp:
                    for j in range(*sp):
                        m[j] = None
                    s = img.cstring(v)
                    if s:
                        anchors.append((a - entry + sp[0], s))
                else:
                    m[1:] = [None] * (len(m) - 1)
        pat += m
    return dict(entry=entry, size=end - entry, pat=pat, mn=[x[2] for x in ins], ins=[(x[0] - entry) for x in ins],
                calls=calls, anchors=anchors)


def fixed(p):
    return sum(x is not None for x in p)


def best_run(p):
    """Longest run of fixed bytes: (offset, bytes)."""
    bo, bl, o = 0, 0, None
    for i, x in enumerate(p + [None]):
        if x is not None and o is None:
            o = i
        elif x is None and o is not None:
            if i - o > bl:
                bo, bl = o, i - o
            o = None
    return bo, bytes(p[bo:bo + bl])


def find_all(data, p, limit=3):
    """Offsets where masked pattern p matches, up to limit."""
    ro, run = best_run(p)
    if len(run) < 3:
        return None
    # regex from the longest fixed run onward (a literal start, so the C engine scans fast); prefix checked by hand
    rx = re.compile(b''.join(b'.' if x is None else re.escape(bytes([x])) for x in p[ro:]), re.S)
    pre = p[:ro]
    hits, pos = [], ro
    while True:
        m = rx.search(data, pos)
        if not m:
            break
        s = m.start() - ro
        if all(x is None or data[s + j] == x for j, x in enumerate(pre)):
            hits.append(s)
            if len(hits) >= limit:
                break
        pos = m.start() + 1
    return hits


def similar(data, off, p, n=96):
    """Fraction of fixed bytes in the first n of p that match data at off."""
    q = p[:n]
    f = [(j, x) for j, x in enumerate(q) if x is not None]
    if off < 0 or off + len(q) > len(data) or not f:
        return 0.0
    return sum(data[off + j] == x for j, x in f) / len(f)


def struct_ratio(sig, dsig):
    if not sig or not dsig:
        return 0.0
    return difflib.SequenceMatcher(None, sig['mn'], dsig['mn'], autojunk=False).ratio()


def call_targets(img, min_sites=2):
    """Entry candidates: targets of `call d16/d32` (cd / dd) found by a byte sweep; a target hit min_sites times or more."""
    d, cnt = img.data, {}
    for op, w in ((0xcd, 2), (0xdd, 4)):
        i = d.find(bytes([op]))
        while i >= 0:
            if i + 1 + w <= len(d):
                disp = int.from_bytes(d[i + 1:i + 1 + w], 'little', signed=True)
                t = img.base + i + disp
                if img.has(t):
                    cnt[t] = cnt.get(t, 0) + 1
            i = d.find(bytes([op]), i + 1)
    return sorted(t for t, c in cnt.items() if c >= min_sites)


def follows_end(img, ad):
    """True when the bytes just before ad are padding or one return / unconditional jump: ad starts a function."""
    if not img.has(ad - 1) or img.data[ad - img.base - 1] in (0xff, 0xcb):
        return True
    for k in range(1, 8):
        ins = img.dis(ad - k, ad)
        if len(ins) == 1 and ins[0][0] + len(ins[0][1]) == ad and (ins[0][2] in STOP or ins[0][2] in ('jmp', 'bra')):
            return True
    return False


def load_names(atlas, autonames, conf, src):
    rank = {'low': 0, 'medium': 1, 'high': 2}
    names = {}
    if atlas:
        for s in json.load(open(atlas))['symbols']:
            if s['kind'] == 'func':
                a = int(s['addr'], 16)
                if src.has(a):
                    names.setdefault(a, (s['name'], 'atlas'))
    if autonames:
        for s in json.load(open(autonames))['names']:
            if s['method'] != 'atlas' and rank[s['confidence']] >= rank[conf]:
                a = int(s['addr'], 16)
                if src.has(a):
                    names.setdefault(a, (s['name'], 'auto/' + s['method']))
    return names


def conf_of(score):
    return 'high' if score >= 0.9 else 'medium' if score >= 0.75 else 'low'


def cmd_map(a):
    src, dst = Image(a.src, a.src_base), Image(a.dst, a.dst_base)
    names = load_names(a.atlas, a.autonames, a.auto_conf, src)
    print(f'{len(names)} source names; making signatures…', file=sys.stderr)
    sigs = {}
    if a.cache and Path(a.cache).exists():
        for k, v in json.load(open(a.cache)).items():
            v['calls'] = [tuple(c) for c in v['calls']]
            v['anchors'] = [(o, bytes.fromhex(s)) for o, s in v['anchors']]
            sigs[int(k, 16)] = v
    for ad in sorted(names):
        if ad not in sigs:
            s = make_sig(src, ad)
            if s:
                sigs[ad] = s
    if a.cache:
        Path(a.cache).write_text(json.dumps({hex(k): dict(v, anchors=[(o, s.hex()) for o, s in v['anchors']])
                                             for k, v in sigs.items()}))
    cand, stat = {}, {}

    def bump(k):
        stat[k] = stat.get(k, 0) + 1

    def take(ad, other, score, method, detail=''):
        old = cand.get(ad)
        if old is None or score > old['score']:
            cand[ad] = dict(other=other, score=round(score, 3), method=method, detail=detail)

    # 1. unique masked signature
    for ad, s in sorted(sigs.items()):
        p = s['pat'][:a.sig_len]
        if fixed(p) < a.min_fixed:
            bump('skip: too few fixed bytes')
            continue
        for L in (a.sig_len, 64, 48, 32):
            q = p[:L]
            if L < a.sig_len and (len(p) <= L or fixed(q) < a.min_fixed):
                continue
            sh = find_all(src.data, q, 2)
            if sh is None or len(sh) != 1:
                continue  # not unique on the E-P7 itself: longer is no better, shorter is worse
            dh = find_all(dst.data, q, 2)
            if dh and len(dh) == 1:
                full = L >= len(s['pat'][:a.sig_len])
                score = (0.97 if full else 0.88 - (64 - L) / 400) * min(1.0, fixed(q) / 24)
                take(ad, dh[0] + dst.base, score, 'sig' if full else f'sig{L}', f'fixed={fixed(q)}')
                break
            if dh and len(dh) > 1:
                s.setdefault('multi', [h + dst.base for h in dh])
                break
    print(f'sig: {len(cand)}', file=sys.stderr)

    # 2. string anchors
    entries = call_targets(dst)
    for ad, s in sorted(sigs.items()):
        if ad in cand or not s['anchors']:
            continue
        votes = {}
        for imm_off, st in s['anchors']:
            hits, i = [], dst.data.find(st + b'\0')
            while i >= 0 and len(hits) < 4:
                if i == 0 or not (0x20 <= dst.data[i - 1] < 0x7f):
                    hits.append(i + dst.base)
                i = dst.data.find(st + b'\0', i + 1)
            for sa in hits:
                ref = struct.pack('<I', sa)
                r = dst.data.find(ref)
                n = 0
                while r >= 0 and n < 8:
                    n += 1
                    c = r - imm_off + dst.base
                    sc = similar(dst.data, c - dst.base, s['pat'])
                    if sc < 0.6:  # code before the reference changed: nearest call target before it
                        j = bisect_right(entries, r + dst.base) - 1
                        if j >= 0 and r + dst.base - entries[j] < 4096:
                            c2 = entries[j]
                            sc2 = similar(dst.data, c2 - dst.base, s['pat'])
                            if sc2 > sc:
                                c, sc = c2, sc2
                    if sc >= 0.6:
                        v = votes.setdefault(c, [0, 0.0])
                        v[0] += 1
                        v[1] = max(v[1], sc)
                    r = dst.data.find(ref, r + 1)
        if votes:
            c, (n, sc) = max(votes.items(), key=lambda kv: (kv[1][0], kv[1][1]))
            if len(votes) == 1 or n > max(v[0] for k, v in votes.items() if k != c):
                take(ad, c, min(0.95, 0.55 + 0.3 * sc + 0.05 * min(n, 2)), 'anchor', f'strings={n} sim={sc:.2f}')
    print(f'+anchor: {len(cand)}', file=sys.stderr)

    # 3. call graph: align matched callers' listings, follow their calls
    dsig_cache = {}

    def dsig(x):
        if x not in dsig_cache:
            dsig_cache[x] = make_sig(dst, x)
        return dsig_cache[x]

    for rnd in range(3):
        votes = {}
        for ad, c in list(cand.items()):
            if c['score'] < 0.75:
                continue
            s, ds = sigs.get(ad), dsig(c['other'])
            if not s or not ds or not s['calls']:
                continue
            sm = difflib.SequenceMatcher(None, s['mn'], ds['mn'], autojunk=False)
            imap = {}
            for i, j, n in sm.get_matching_blocks():
                for k in range(n):
                    imap[i + k] = j + k
            dcalls = {k: t for _, t, k in ds['calls']}
            for _, t, k in s['calls']:
                if t in sigs and k in imap and imap[k] in dcalls:
                    votes.setdefault(t, {}).setdefault(dcalls[imap[k]], []).append(c['score'])
        added = 0
        for t, opts in votes.items():
            other, sc = max(opts.items(), key=lambda kv: len(kv[1]))
            if len(opts) > 1 and len(sc) <= max(len(v) for k, v in opts.items() if k != other):
                bump('call: conflicting votes')
                continue
            sim = similar(dst.data, other - dst.base, sigs[t]['pat'])
            if sim < 0.5 and len(sc) < 2:
                continue
            score = min(0.94, 0.45 + 0.35 * sim + 0.05 * min(len(sc), 3))
            if t in cand:
                if cand[t]['other'] == other:
                    cand[t]['callers'] = len(sc)
                else:
                    cand[t].setdefault('conflict', other)
                continue
            take(t, other, score, 'call', f'callers={len(sc)} sim={sim:.2f}')
            added += 1
        print(f'+call round {rnd + 1}: {len(cand)}', file=sys.stderr)
        if not added:
            break

    # 4. structure score, conflicts, confidence
    by_other = {}
    for ad, c in cand.items():
        by_other.setdefault(c['other'], []).append(ad)
    rows = []
    src_entries = set(call_targets(src, 1))  # a mid-function atlas site is (almost) never a call target
    for ad, c in sorted(cand.items()):
        st = struct_ratio(sigs[ad], dsig(c['other']))
        if st < a.min_struct:  # the listings don't line up at all: a wrong entry (both sample misses were this)
            bump('dropped: structure below --min-struct')
            continue
        score = c['score'] * (0.6 + 0.4 * st)
        if 'conflict' in c:
            score *= 0.8
        if len(by_other[c['other']]) > 1:
            score *= 0.7
        nm, origin = names[ad]
        rows.append(dict(ep7_addr=hex(ad), name=nm, entry=origin != 'atlas' or nm.startswith('task_') or ad in src_entries or follows_end(src, ad), other_addr=hex(c['other']), score=round(score, 3), method=c['method'],
                         confidence=conf_of(score), struct=round(st, 3), shift=c['other'] - ad, origin=origin,
                         detail=c['detail'] + (f" conflict={c['conflict']:#x}" if 'conflict' in c else '')
                         + (' dup-target' if len(by_other[c['other']]) > 1 else '')))
    for k in ('sig', 'sig64', 'sig48', 'sig32', 'anchor', 'call'):
        stat[f'method {k}'] = sum(r['method'] == k for r in rows)
    for k in ('high', 'medium', 'low'):
        stat[f'conf {k}'] = sum(r['confidence'] == k for r in rows)
    stat['names'] = len(names)
    stat['signatures'] = len(sigs)
    stat['ambiguous (sig matched 2+ places)'] = sum(1 for ad, s in sigs.items() if 'multi' in s and ad not in cand)
    out = dict(src=os.path.basename(a.src), dst=os.path.basename(a.dst), dst_base=hex(a.dst_base), stats=stat,
               candidates=rows)
    Path(a.out).write_text(json.dumps(out, indent=0) + '\n')
    print(json.dumps(stat, indent=1))
    if a.names_out:
        rank = {'low': 0, 'medium': 1, 'high': 2}
        keep = [r for r in rows if rank[r['confidence']] >= rank[a.min_conf]]
        hdr = dict(firmware=a.firmware or os.path.basename(a.dst), generated_by='tools/atlas/sigfind.py',
                   note='Names transferred from the E-P7 1.1 atlas by masked signatures. Proposals: check before relying on them.')
        body = [dict(addr=r['other_addr'], name=r['name'], method='sig_' + r['method'], confidence=r['confidence'])
                for r in keep if r['entry']]
        write_rows(a.names_out, hdr, 'names', body)
        print(f"{len(body)} entry names (>= {a.min_conf}) -> {a.names_out}", file=sys.stderr)
        if a.sites_out:  # mid-function sites: atlas format, kind 'site', so ApplyNames makes labels, not functions
            body = [dict(addr=r['other_addr'], name=r['name'], kind='site', sig='',
                         notes=f"sigfind {r['method']} {r['confidence']} from E-P7 {r['ep7_addr']}") for r in keep if not r['entry']]
            write_rows(a.sites_out, hdr, 'symbols', body)
            print(f'{len(body)} site labels -> {a.sites_out}', file=sys.stderr)


def write_rows(path, hdr, key, body):
    """One row per line, like docs/autonames.json, so the files grep and diff cleanly."""
    Path(path).write_text('{\n' + ',\n'.join(f' {json.dumps(k)}: {json.dumps(v)}' for k, v in hdr.items())
                          + f',\n "{key}": [\n' + ',\n'.join('  ' + json.dumps(x) for x in body) + '\n ]\n}\n')


def cmd_seeds(a):
    """Function seeds for a Ghidra import, the way the E-P7 project was built: an objdump linear sweep, keeping
    `call` targets with 2+ call sites and every `calls imm` target, plus the entry and any --extra addresses."""
    img = Image(a.image, a.base)
    p = subprocess.Popen([OBJDUMP, '-b', 'binary', '-m', 'am33-2', '-D', f'--adjust-vma={a.base:#x}', a.image],
                         stdout=subprocess.PIPE, text=True, bufsize=1 << 20)
    cnt, imm = {}, set()
    rx = re.compile(r'\t(calls?)\s+0x([0-9a-f]+)')
    for ln in p.stdout:
        m = rx.search(ln)
        if m:
            t = int(m[2], 16)
            if img.has(t):
                cnt[t] = cnt.get(t, 0) + 1
                if m[1] == 'calls':
                    imm.add(t)
    p.wait()
    seeds = {t for t, n in cnt.items() if n >= 2} | imm | {a.base}
    for x in a.extra or []:
        rows = json.load(open(x))
        seeds |= {int(r['addr'], 16) for r in rows.get('names', [])}
    with open(a.out, 'w') as f:
        f.write(f'# {os.path.basename(a.image)} at {a.base:#x}: entry + objdump linear-sweep call targets with >=2 call sites,'
                ' plus all calls imm targets (tools/atlas/sigfind.py seeds)\n')
        for t in sorted(seeds):
            f.write(f'{t:#010x}\tfunction\n')
    print(f'{len(seeds)} seeds -> {a.out}', file=sys.stderr)


def cmd_base(a):
    img = Image(a.image, 0)
    d = img.data
    vals = []
    for op in (b'\xfc\xdc', b'\xfc\xdd', b'\xfc\xde', b'\xfc\xdf'):  # mov imm32,a0..a3
        i = d.find(op)
        while i >= 0 and len(vals) < 200000:
            vals.append(struct.unpack_from('<I', d, i + 2)[0])
            i = d.find(op, i + 1)
    bases = [int(x, 0) for x in a.bases]
    if not bases:  # scan 0x60000000-0x60080000 in steps of 0x10 on a sample of pointers to string starts
        starts = bytearray(len(d))
        for m in re.finditer(rb'(?<=[\x00-\x1f\x7f-\xff])[\x20-\x7e]{6,}\x00', d):
            starts[m.start()] = 1
        rnd = random.Random(1)
        sample = rnd.sample(vals, min(800, len(vals)))
        score = []
        for b in range(0x60000000, 0x60080000, 0x10):
            n = 0
            for v in sample:
                o = v - b
                if 0 <= o < len(d) and starts[o]:
                    n += 1
            score.append((n, b))
        score.sort(reverse=True)
        bases = [b for _, b in score[:3]]
        print('best bases by scan:', ', '.join(f'{b:#x} ({n}/{len(sample)})' for n, b in score[:3]))
    for b in bases:
        img.base, img.end = b, b + len(d)
        inside = [v for v in vals if img.has(v)]
        hits = sum(1 for v in inside if img.cstring(v, 4))
        print(f'base {b:#010x}: {len(inside)} mov-imm32 pointers inside the image, {hits} land on a string start '
              f'({100.0 * hits / max(1, len(inside)):.1f}%)')


def cmd_check(a):
    """Independent checks of a candidate map, per method/confidence:
    strings  the E-P7 function loads C strings and the target function loads the same ones. The signature masks
             string pointers, so this is independent of how the match was made (a 'sig' row can fail it).
    shift    the shift (other - ep7) is within 32 KB of the median of its 8 address neighbours (code keeps its order
             within a region; a layout change between bodies makes true rows fail this too, so it's a weak check).
    truth    rows of --truth {ep7_addr: other_addr} (known-good addresses from your own work) that agree."""
    import statistics
    c = json.load(open(a.cand))
    src, dst = Image(a.src, a.src_base), Image(a.dst, int(c['dst_base'], 16))
    rows = sorted(c['candidates'], key=lambda r: int(r['ep7_addr'], 16))
    truth = {int(k, 16): int(v, 16) for k, v in json.load(open(a.truth)).items()} if a.truth else {}
    sh = [r['shift'] for r in rows]
    tab = {}
    for i, r in enumerate(rows):
        key = (r['method'] if r['method'] in ('sig', 'anchor', 'call') else 'sigN', r['confidence'])
        t = tab.setdefault(key, dict(n=0, str_n=0, str_ok=0, shift_ok=0, truth_n=0, truth_ok=0))
        t['n'] += 1
        nb = [sh[j] for j in range(max(0, i - 4), min(len(rows), i + 5)) if j != i]
        t['shift_ok'] += bool(nb) and abs(r['shift'] - statistics.median(nb)) <= 0x8000
        e, o = int(r['ep7_addr'], 16), int(r['other_addr'], 16)
        s = make_sig(src, e)
        if s and s['anchors']:
            d = make_sig(dst, o)
            mine = {x for _, x in s['anchors']}
            t['str_n'] += 1
            t['str_ok'] += bool(d and mine & {x for _, x in d['anchors']})
        if e in truth:
            t['truth_n'] += 1
            t['truth_ok'] += truth[e] == o
    print(f"{'method/conf':14s} {'rows':>5s} {'strings ok':>12s} {'shift ok':>10s} {'truth ok':>9s}")
    for (m, cf), t in sorted(tab.items()):
        print(f"{m + '/' + cf:14s} {t['n']:5d} {t['str_ok']:5d}/{t['str_n']:<6d} {t['shift_ok']:5d}/{t['n']:<4d} "
              f"{t['truth_ok']:3d}/{t['truth_n']:<3d}")


def cmd_show(a):
    c = json.load(open(a.cand))
    src = Image(a.src, a.src_base)
    dst = Image(a.dst, int(c['dst_base'], 16))
    rows = c['candidates']
    if a.name:
        rows = [r for r in rows if r['name'] == a.name]
    elif a.sample:
        random.seed(a.seed)
        rows = random.sample(rows, min(a.sample, len(rows)))
    for r in rows:
        s, d = make_sig(src, int(r['ep7_addr'], 16)), make_sig(dst, int(r['other_addr'], 16))
        print(f"== {r['name']} {r['ep7_addr']} -> {r['other_addr']} {r['method']} score {r['score']} struct {r['struct']}")
        if a.brief:
            continue
        si = src.dis(s['entry'], s['entry'] + s['size']) if s else []
        di = dst.dis(d['entry'], d['entry'] + d['size']) if d else []
        for k in range(min(a.lines, max(len(si), len(di)))):
            l = f'{si[k][2]:7s} {si[k][3][:34]:34s}' if k < len(si) else ' ' * 42
            rr = f'{di[k][2]:7s} {di[k][3][:34]}' if k < len(di) else ''
            print(f'  {l} | {rr}')
        if s:
            print('  anchors:', [x.decode('latin1')[:40] for _, x in s['anchors']][:4])
            if d:
                print('  anchors (other):', [x.decode('latin1')[:40] for _, x in d['anchors']][:4])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    m = sub.add_parser('map', help='make the candidate map')
    m.add_argument('--src', default=str(ROOT / 'analysis/ep7_1100/00_0100_406a0020.decoded.bin'), help='E-P7 1.1 decoded main')
    m.add_argument('--src-base', type=lambda x: int(x, 0), default=EP7_BASE)
    m.add_argument('--dst', required=True, help="the other body's decoded main")
    m.add_argument('--dst-base', type=lambda x: int(x, 0), default=EP7_BASE)
    m.add_argument('--atlas', default=str(ROOT / 'docs/atlas.json'))
    m.add_argument('--autonames', help='also transfer autonames.json rows (method != atlas)')
    m.add_argument('--auto-conf', default='high', choices=('low', 'medium', 'high'))
    m.add_argument('--sig-len', type=int, default=96, help='bytes of masked signature used (default 96)')
    m.add_argument('--min-fixed', type=int, default=12, help='fixed (unmasked) bytes a signature needs (default 12)')
    m.add_argument('--cache', help='PRIVATE cache of the E-P7 signatures (contains firmware bytes: never publish)')
    m.add_argument('--out', required=True)
    m.add_argument('--names-out', help='accepted rows in autonames.json format, for ApplyNames')
    m.add_argument('--sites-out', help='with --names-out: mid-function sites as atlas-format labels')
    m.add_argument('--min-conf', default='medium', choices=('low', 'medium', 'high'))
    m.add_argument('--min-struct', type=float, default=0.3, help='drop candidates whose mnemonic similarity is lower')
    m.add_argument('--firmware', help='label for --names-out, e.g. "E-M10 IV 1.1"')
    m.set_defaults(fn=cmd_map)
    e = sub.add_parser('seeds', help='function seeds TSV for a Ghidra import (objdump linear sweep)')
    e.add_argument('image')
    e.add_argument('--base', type=lambda x: int(x, 0), required=True)
    e.add_argument('--extra', action='append', help='names.json from map: add its addresses as seeds')
    e.add_argument('--out', required=True)
    e.set_defaults(fn=cmd_seeds)
    b = sub.add_parser('base', help='check candidate CPU bases for a decoded main')
    b.add_argument('image')
    b.add_argument('bases', nargs='*')
    b.set_defaults(fn=cmd_base)
    k = sub.add_parser('check', help='independent checks of a candidate map (strings, shift, known addresses)')
    k.add_argument('cand')
    k.add_argument('--src', default=str(ROOT / 'analysis/ep7_1100/00_0100_406a0020.decoded.bin'))
    k.add_argument('--src-base', type=lambda x: int(x, 0), default=EP7_BASE)
    k.add_argument('--dst', required=True)
    k.add_argument('--truth', help='JSON {ep7_addr: other_addr} of addresses you already trust')
    k.set_defaults(fn=cmd_check)
    s = sub.add_parser('show', help='side-by-side listings of candidates, for review')
    s.add_argument('cand')
    s.add_argument('--src', default=str(ROOT / 'analysis/ep7_1100/00_0100_406a0020.decoded.bin'))
    s.add_argument('--src-base', type=lambda x: int(x, 0), default=EP7_BASE)
    s.add_argument('--dst', required=True)
    s.add_argument('--name')
    s.add_argument('--sample', type=int)
    s.add_argument('--seed', type=int, default=1)
    s.add_argument('--lines', type=int, default=24)
    s.add_argument('--brief', action='store_true')
    s.set_defaults(fn=cmd_show)
    a = ap.parse_args()
    if not Path(OBJDUMP).exists():
        sys.exit(f'objdump not found: {OBJDUMP} (build it with tools/setup_toolchain.sh, or set OBJDUMP)')
    return a.fn(a)


if __name__ == '__main__':
    sys.exit(main())
