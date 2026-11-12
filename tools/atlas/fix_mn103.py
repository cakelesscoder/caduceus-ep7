#!/usr/bin/env python3
"""Make nsud-dev/ghidra-mn103 (the MN103/AM33-2 Ghidra processor module) build and run on Ghidra 12.

Our own script (Caduceus, Apache-2.0). It contains no code from the module: it edits YOUR checkout in place.
The module itself is GPL-3.0 (https://github.com/nsud-dev/ghidra-mn103); your edited copy stays under the GPL.

The published module lost every empty "()" somewhere in its publishing path. That breaks:
  - the SLEIGH spec: 5 no-argument pcodeop calls (`getchx;`, `getclx;`, `trap;`, `rtm;`, `breakpoint;`), which
    Ghidra 12's SLEIGH compiler refuses;
  - the Java scripts in ghidra_scripts/: every no-argument method call and constructor.
This script puts them back. It changes no decoding and no semantics. Tested against upstream e07c0d0: the result
is identical to the module Caduceus uses (all 11 scripts compile, the language builds).

Usage:
  fix_mn103.py MODULE_DIR [--ghidra GHIDRA_INSTALL_DIR] [--javac PATH]
MODULE_DIR is the folder that holds data/ and ghidra_scripts/ (the repo's MN103/ folder, or the installed copy in
<ghidra>/Ghidra/Processors/MN103). With --ghidra, the scripts are then compiled against Ghidra's jars and any
remaining "symbol not found" errors of the same kind are fixed one by one (javac loop).
"""
import argparse, glob, os, re, subprocess, sys, tempfile
from pathlib import Path

NOARG = (r'(?:get\w*|is\w*|has\w*|to\w*|next|size|entrySet|keySet|values|trim|intValue|longValue|checkCancelled|'
         r'decompileCompleted|getC|run|clear|iterator|incrementAndGet|lowerCase|close|flush|isBlank|isEmpty|toPath|'
         r'toString|length|hashCode|getFirst|getLast|exists|delete|save|mkdirs)')


def fix_sleigh(path):
    t = Path(path).read_text()
    ops = set(re.findall(r'define\s+pcodeop\s+(\w+)\s*;', t))
    out, n = [], 0
    for line in t.split('\n'):
        if line.startswith(':') and '{' in line:
            head, body = line.split('{', 1)
            new = re.sub(r'\b(' + '|'.join(sorted(ops)) + r')\s*;', r'\1();', body)
            n += new != body
            line = head + '{' + new
        out.append(line)
    Path(path).write_text('\n'.join(out))
    return n


def fix_java_text(s):
    out = []
    for line in s.split('\n'):
        if line.lstrip().startswith(('import ', '//', 'package ')):
            out.append(line)
            continue
        code, sep, comment = line.partition('//') if '"' not in line else (line, '', '')
        code = re.sub(r'\bvoid run throws', 'void run() throws', code)
        code = re.sub(r'\bnew ((?:[a-z]\w*\.)*[A-Z][\w.]*(?:<[^;()\[\]]*>)?)(?=\s*[;),])', r'new \1()', code)
        code = re.sub(r'^(\s*[\w.]+\.\w+)\s*;', r'\1();', code)  # `a.b;` is never a Java statement: a lost call
        code = re.sub(r'\.(' + NOARG + r')\b(?![\w(])', r'.\1()', code)
        code = re.sub(r'(?<![\w.])(getScriptArgs|getCurrentProgram|getState)\b(?!\s*\()', r'\1()', code)
        out.append(code + sep + comment)
    return '\n'.join(out)


def javac_loop(scripts, ghidra, javac):
    jars = glob.glob(os.path.join(ghidra, 'Ghidra', '**', 'lib', '*.jar'), recursive=True)
    cp = os.pathsep.join(jars)
    with tempfile.TemporaryDirectory() as out:
        for it in range(30):
            files = sorted(glob.glob(os.path.join(scripts, '*.java')))
            r = subprocess.run([javac, '-nowarn', '-proc:none', '-Xmaxerrs', '1000', '-cp', cp, '-d', out] + files,
                               capture_output=True, text=True)
            if r.returncode == 0:
                return it
            errs = re.findall(r'^(\S+\.java):(\d+): error: (.*)\n(.*)\n([ \t]*)\^\n(?:\s+symbol:\s+(\w+) (\S+))?', r.stderr, re.M)
            edits, changed = {}, False
            for f, ln, msg, src, pad, kind, sym in errs:
                edits.setdefault((f, int(ln)), []).append((len(pad), kind, sym))
            for (f, ln), es in edits.items():
                lines = Path(f).read_text().split('\n')
                s = lines[ln - 1]
                for col, kind, sym in sorted(es, reverse=True):
                    col += 1
                    if kind == 'variable' and s[col:col + len(sym)] == sym:  # a lost "()" on a call
                        s, changed = s[:col + len(sym)] + '()' + s[col + len(sym):], True
                    elif kind == 'method' and sym == 'length()' and s[col:col + 8] == 'length()':  # array .length
                        s, changed = s[:col + 6] + s[col + 8:], True
                lines[ln - 1] = s
                Path(f).write_text('\n'.join(lines))
            if not changed:
                sys.stderr.write(r.stderr[:4000])
                return None
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('module')
    ap.add_argument('--ghidra', help='Ghidra install dir: compile the scripts and fix what javac still reports')
    ap.add_argument('--javac', default='javac')
    a = ap.parse_args()
    m = Path(a.module)
    sl = m / 'data/languages/mn103.slaspec'
    if not sl.exists():
        sys.exit(f'{sl} not found: point at the folder holding data/ and ghidra_scripts/')
    print(f'slaspec: {fix_sleigh(sl)} lines fixed')
    for p in sorted((m / 'ghidra_scripts').glob('*.java')):
        t = p.read_text()
        u = fix_java_text(t)
        if u != t:
            p.write_text(u)
    if a.ghidra:
        it = javac_loop(str(m / 'ghidra_scripts'), a.ghidra, a.javac)
        if it is None:
            sys.exit('javac still fails: see the errors above')
        print(f'scripts compile (javac passes: {it + 1})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
