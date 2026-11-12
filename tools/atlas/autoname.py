#!/usr/bin/env python3
"""Propose function names for a stock Olympus/OM main image. Our own script (Caduceus, tools/atlas/).

Inputs (none of them are published):
  --index    index.tsv   from DecompileAll.java (addr, size, name, ncallers, ncallees, callers, callees, strings)
  --strings  strings.tsv from DecompileAll.java (func, str_addr, string)
  --atlas    atlas.json  (public; authoritative names)
  --bin      decoded main image + --base, only for --task-desc/--task-names (optional task-table parse)

Output: --out autonames.json, public: one row per name {addr, name, method, confidence}. No code, no strings.

Methods, in priority order (a higher one wins an address, and a name taken by a higher one is not reused):
  atlas    atlas.json symbol of kind func                                      confidence high
  task     static task table entry (descriptor + name table)                   confidence high
  cppmethod "Class::method" in trace/log strings (C++ layers)               high (2+ hits, one function),
                                                                                else medium; low if 3+ share it
  funcstr  the only bare identifier string of a function, used by it alone,     medium (never high)
           next to a "%s:" / "[%s]" format: the __func__ pattern
  prefix   "<ident>: message" / "<ident> : message" log prefixes                medium (2+ strings agree, or
                                                                                one string, unique), low if shared
  thunk    small function with exactly one callee that has a name:             low (only with --thunks)
           thunk_<callee> (<= 12 B, call+ret) or wrap_<callee> (<= --thunk-max-size B)
  srcfile  "<module>.c" source-file string -> "<module>_<addr>" module tag     low (only with --srcfile)

Usage (E-P7 1.1):
  tools/atlas/autoname.py --index ~/ep7fw-private/decomp/full/index.tsv \\
      --strings ~/ep7fw-private/decomp/full/strings.tsv --atlas docs/atlas.json --out docs/autonames.json \\
      --bin analysis/ep7_1100/00_0100_406a0020.decoded.bin --base 0x60020020 \\
      --task-desc 0x600389d0 --task-names 0x613ff240 --thunks
"""
import argparse, collections, json, re, struct, sys

IDENT = r'[A-Za-z_][A-Za-z0-9_]*'
# Words that look like identifiers but are generic log vocabulary, not function names.
STOP = set('''error err warning warn info debug dbg trace fatal assert assertion ok ng fail failed failure
 start stop end begin done result status state mode size addr address len length data param value val
 id tid ret return type kind name file line func function usage cmd command time count num index idx
 src dst buf buffer ptr pointer read write open close init exit main test check bad null none true false
 yes no on off min max get set next prev top bottom left right width height new old in out sum total'''.split())

def unesc(s):
    return s.replace('\\n', '\n').replace('\\t', '\t').replace('\\r', '\r').replace('\\\\', '\\')

def plausible(ident):
    """A string that could be a C function name: has an underscore or a lower->Upper hump, not all caps."""
    if len(ident) < 4 or len(ident) > 48: return False
    low = ident.lower()
    if low in STOP: return False
    if ident.isupper() or ident.isdigit(): return False           # constants, setting names, task names
    if re.fullmatch(r'[0-9a-fA-F_x]+', ident): return False         # hex-ish
    if '_' not in ident and not re.search(r'[a-z][A-Z]', ident): return False
    if '__' in ident.strip('_'): return False
    return True

def load_index(path):
    funcs = {}
    with open(path, encoding='utf-8') as f:
        next(f)
        for line in f:
            c = line.rstrip('\n').split('\t')
            if len(c) < 7: continue
            funcs[int(c[0], 16)] = dict(size=int(c[1]), name=c[2], ncallers=int(c[3]), ncallees=int(c[4]),
                                        callers=[int(x, 16) for x in c[5].split(',') if x],
                                        callees=[int(x, 16) for x in c[6].split(',') if x])
    return funcs

def load_strings(path):
    by_func = collections.defaultdict(list)   # func -> [(str_addr, string)]
    users = collections.defaultdict(set)      # str_addr -> {func}
    with open(path, encoding='utf-8') as f:
        next(f)
        for line in f:
            c = line.rstrip('\n').split('\t', 2)
            if len(c) < 3: continue
            fa, sa, s = int(c[0], 16), int(c[1], 16), unesc(c[2])
            by_func[fa].append((sa, s)); users[sa].add(fa)
    return by_func, users

def tasks_from_bin(binpath, base, desc, names):
    d = open(binpath, 'rb').read()
    out, p = {}, names - base
    while 0 <= p < len(d) - 26:
        nm = d[p:p + 24].split(b'\0')[0]
        if not re.fullmatch(rb'[A-Z0-9_]{2,23}', nm): break
        tid = struct.unpack_from('<H', d, p + 24)[0]
        q = desc + tid * 28 - base
        if 0 <= q < len(d) - 28:
            w = struct.unpack_from('<7I', d, q)
            if w[0] == tid and base <= w[3] < base + len(d): out[w[3]] = 'task_' + nm.decode()
        p += 26
    return out

FMT = re.compile(r'%[-+ 0#]*\d*(?:\.\d+)?[lhz]*[sdiuxXcpf]')
PREFIX = re.compile(r'^[\s\[\]<>*#=-]*(' + IDENT + r')\s?(?:\(\))?\s*:(?!:)')   # "name: ..." / "name() : ..."
# "foo() failed" / "foo() Error ret=" / "... in foo()" names a callee or another function, not this one
CALLEE_ERR = re.compile(r'((?:' + IDENT + r'::)?' + IDENT + r')\(\)\s*(?:[Ee]rror|ERR|NG|[Ff]ail|ret|returned|arguments)')
CPP = re.compile(r'(?<![\w:])(' + IDENT + r')::(~?' + IDENT + r')(\(\))?')

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--index', required=True); ap.add_argument('--strings', required=True)
    ap.add_argument('--atlas'); ap.add_argument('--out', required=True)
    ap.add_argument('--bin'); ap.add_argument('--base', type=lambda x: int(x, 0), default=0x60020020)
    ap.add_argument('--task-desc', type=lambda x: int(x, 0)); ap.add_argument('--task-names', type=lambda x: int(x, 0))
    ap.add_argument('--thunks', action='store_true'); ap.add_argument('--srcfile', action='store_true')
    ap.add_argument('--thunk-max-size', type=int, default=24)
    ap.add_argument('--firmware', default='Olympus PEN E-P7 1.1 (build 1100), main component 0x100')
    ap.add_argument('--debug', help='write a private TSV with the evidence per proposal (never publish it)')
    a = ap.parse_args()

    funcs = load_index(a.index)
    by_func, users = load_strings(a.strings)
    names = {}        # addr -> (name, method, confidence)
    taken = {}        # name -> addr
    evidence = {}

    def claim(addr, name, method, conf, ev=''):
        if addr in names: return False
        if name in taken and taken[name] != addr: return False
        names[addr] = (name, method, conf); taken[name] = addr; evidence[addr] = ev
        return True

    # (a) atlas: authoritative. Only func symbols name functions; others are labels for apply_names.
    atlas_funcs = {}
    if a.atlas:
        for s in json.load(open(a.atlas, encoding='utf-8'))['symbols']:
            if s['kind'] != 'func': continue
            ad = int(s['addr'], 16)
            atlas_funcs[ad] = s['name']
            names[ad] = (s['name'], 'atlas', 'high'); taken.setdefault(s['name'], ad); evidence[ad] = 'atlas ' + s.get('confidence', '')

    # (c) task table
    if a.bin and a.task_desc and a.task_names:
        for ad, nm in sorted(tasks_from_bin(a.bin, a.base, a.task_desc, a.task_names).items()):
            if ad in funcs: claim(ad, nm, 'task', 'high', 'task table')

    # (b) strings. Collect candidates per function.
    cand = {}  # addr -> list of (name, method, score, why)
    for fa, lst in by_func.items():
        if fa not in funcs: continue
        has_fmt = any(FMT.search(s) for _, s in lst)
        has_line = any(re.search(r'%s\s*\(?\s*(?:line\s*)?%d', s) or re.search(r'%s\s*:\s*%d', s) for _, s in lst)
        callee_words = set()
        for _, s in lst: callee_words.update(CALLEE_ERR.findall(s))
        c = []
        # cppmethod: "Class::method" trace strings (OM's C++ UI/app layers log their own method name)
        meth = collections.Counter()
        for sa, s in lst:
            for m in CPP.finditer(s):
                full = m.group(1) + '::' + m.group(2)
                if m.group(1).lower() in ('function', 'func', 'fn'): full = m.group(2)   # "DbgSup-function::x" tag
                if full in callee_words: continue
                if re.fullmatch(r'[A-Z0-9_]+', m.group(2)): continue            # Class::ENUM_CONSTANT
                if s[m.end():m.end() + 2] == '->' or s[m.end():m.end() + 4] == '()->': continue   # call chain
                if re.search(r'=\s*$', s[:m.start()]): continue                # "x = Class::value" 
                meth[full] += 1 if m.group(3) else 2
        for nm, k in meth.items():
            c.append((nm, 'cppmethod', 4 if k >= 2 else 3, 'cpp x%d' % k))
        # funcstr: whole string is one identifier, used by this function only, next to a format that prints a
        # name ("%s: ...", "[%s]"): the __func__ pattern. Functions with several bare identifiers are
        # command/state tables (spot check R1.5: 0/3 there), so exactly one is required.
        bare = [s for sa, s in lst if re.fullmatch(IDENT, s) and plausible(s) and len(users[sa]) == 1
                and s not in callee_words and (s[0].islower() or '_' in s)]
        name_fmt = any(re.match(r'\s*(?:%s\s*[:(]|\[%s\]\s*[^\[]|%s\s*\(%d\))', s) for _, s in lst)
        allbare = [s for _, s in lst if re.fullmatch(IDENT, s)]
        if len(bare) == 1 and len(allbare) == 1 and name_fmt:
            c.append((bare[0], 'funcstr', 3 if has_line else 2, 'bare ident + name fmt'))
        # prefix: "name: message". A function that prints 3+ different "word:" labels is a field dump, skip it.
        prefixes = collections.Counter()
        for sa, s in lst:
            m = PREFIX.match(s)
            if not m or '::' in s[:m.end()]: continue
            rest = s[m.end():]
            if not re.search(r'[A-Za-z]{3,}|\w+\s*=\s*%', rest): continue     # "name:   %x" is a field label
            g = m.group(1)
            # C names: need an underscore, or lowerCamel ("MultiExpose:" was a feature tag, not a function)
            if not ('_' in g or g[0].islower()): continue
            if plausible(g) and g not in callee_words and re.search(r'[a-z]', g):
                prefixes[m.group(1)] += 1
        labels = {m.group(1) for _, s in lst for m in [PREFIX.match(s)] if m}
        if len(labels) < 3 or len(prefixes) == 1 and sum(prefixes.values()) >= 2:
            for p, k in prefixes.items():
                c.append((p, 'prefix', 2 if k >= 2 else 1, 'prefix x%d' % k))
        if c: cand[fa] = c

    # How many functions propose each name: a name proposed by many functions is a shared logger tag or a
    # callee name, not this function's own name.
    proposers = collections.defaultdict(set)
    for fa, c in cand.items():
        for nm, _, _, _ in c: proposers[nm].add(fa)

    ranked = []
    for fa, c in cand.items():
        best = {}
        for nm, meth, score, why in c:
            k = best.get(nm)
            if k is None or score > k[1]: best[nm] = (meth, score, why)
        opts = sorted(best.items(), key=lambda kv: (-kv[1][1], kv[0]))
        nm, (meth, score, why) = opts[0]
        # ambiguous: two different names with the same top score in one function
        ambiguous = len(opts) > 1 and opts[1][1][1] == score and opts[1][0] != nm
        shared = len(proposers[nm])
        if meth == 'cppmethod': conf = 'high' if score >= 4 and shared == 1 and not ambiguous else 'medium'
        elif meth == 'funcstr': conf = 'medium' if not ambiguous else 'low'   # never high: see spot checks
        else: conf = 'medium' if (shared == 1 and not ambiguous) else 'low'
        if shared > 1 and meth != 'cppmethod':
            conf = 'low'
        elif shared > 2:
            conf = 'low'
        ranked.append((({'high': 0, 'medium': 1, 'low': 2}[conf], -score), fa, nm, meth, conf,
                       '%s; proposers=%d%s' % (why, shared, '; ambiguous' if ambiguous else '')))
    ranked.sort()
    dup_suffix = collections.Counter()
    for _, fa, nm, meth, conf, why in ranked:
        if fa in names: continue
        if nm in atlas_funcs.values() or nm in taken:
            # name already used by a better claim: keep a suffixed low-confidence variant
            dup_suffix[nm] += 1
            claim(fa, '%s_%d' % (nm, dup_suffix[nm] + 1), meth, 'low', why + '; dup')
        else:
            claim(fa, nm, meth, conf, why)

    # (e) optional module tags from "<module>.c" strings
    if a.srcfile:
        for fa, lst in by_func.items():
            if fa in names or fa not in funcs: continue
            mods = {m.group(1) for _, s in lst for m in [re.search(r'\b(' + IDENT + r')\.c\b', s)] if m}
            if len(mods) == 1:
                mod = mods.pop()
                claim(fa, '%s_%08x' % (mod, fa), 'srcfile', 'low', 'module string')

    # (d) optional thunks: small, one callee, callee named; iterate so wrapper-of-wrapper resolves
    if a.thunks:
        for _ in range(4):
            changed = False
            for fa, f in funcs.items():
                if fa in names or f['ncallees'] != 1 or f['size'] > a.thunk_max_size: continue
                ce = f['callees'][0]
                if ce in names and ce != fa:
                    base = names[ce][0]
                    if base.count('thunk_') + base.count('wrap_') >= 2: continue
                    # <= 12 B is a bare call+ret; up to --thunk-max-size it may also set a field or two
                    nm = ('thunk_' if f['size'] <= 12 else 'wrap_') + base.replace('::', '__')
                    if nm in taken: nm = '%s_%08x' % (nm, fa)
                    if claim(fa, nm, 'thunk', 'low', 'size %d -> %s' % (f['size'], base)): changed = True
            if not changed: break

    rows = [dict(addr='0x%08x' % ad, name=nm, method=m, confidence=c) for ad, (nm, m, c) in sorted(names.items())]
    stats = collections.Counter((r['method'], r['confidence']) for r in rows)
    meta = dict(firmware=a.firmware, generated_by='tools/atlas/autoname.py',
                total_functions=len(funcs),
                methods=dict(atlas='docs/atlas.json (authoritative)', task='static task table',
                             cppmethod='"Class::method" trace string', funcstr='the only bare identifier string of a function, next to a "%s:"/"[%s]" format (__func__ style)',
                             prefix='"name: message" log prefix', thunk='single-callee function of <= 24 B calling a named function: thunk_ (<= 12 B) / wrap_',
                             srcfile='module tag from a source-file string'),
                note='Names and addresses only. Apply with tools/atlas/apply_names.py (or ApplyNames.java) to your own import.',
                stats={'%s/%s' % k: v for k, v in sorted(stats.items())},
                names=rows)
    with open(a.out, 'w', encoding='utf-8') as f:   # one name per line: greppable, small diffs
        head = json.dumps(dict((k, v) for k, v in meta.items() if k != 'names'), indent=1, ensure_ascii=False)
        f.write(head[:-2] + ',\n "names": [\n')
        f.write(',\n'.join('  ' + json.dumps(r, ensure_ascii=False) for r in rows))
        f.write('\n ]\n}\n')
    if a.debug:
        with open(a.debug, 'w', encoding='utf-8') as f:
            f.write('addr\tname\tmethod\tconfidence\tevidence\toriginal\n')
            for ad, (nm, m, c) in sorted(names.items()):
                f.write('0x%08x\t%s\t%s\t%s\t%s\t%s\n' % (ad, nm, m, c, evidence.get(ad, ''), funcs.get(ad, {}).get('name', '-')))
    nf = sum(1 for ad in names if ad in funcs)
    print('named %d / %d functions (%.1f%%)' % (nf, len(funcs), 100.0 * nf / max(1, len(funcs))), file=sys.stderr)
    for k, v in sorted(stats.items()): print('  %-8s %-6s %6d' % (k[0], k[1], v), file=sys.stderr)

if __name__ == '__main__':
    main()
