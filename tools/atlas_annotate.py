#!/usr/bin/env python3
"""Annotate E-P7 disassembly with names from docs/atlas.json.

  tools/atlas_annotate.py 0x603b0252 0x603b0300        # runs tools/dis.sh, annotates
  tools/dis.sh 0x603b0252 0x603b0300 | tools/atlas_annotate.py   # or pipe it in

Adds `<name>:` above a line whose address is an atlas symbol, and `; name` after any
call/jmp/branch target or immediate (hex or objdump's decimal) that is one. Only stock
symbols are in the atlas; our code-space claims are in docs/CODE_SPACE_MAP.md.
"""
import json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
atlas = json.load(open(os.path.join(ROOT, 'docs', 'atlas.json')))
names = {int(s['addr'], 16): s['name'] for s in atlas['symbols']}

if len(sys.argv) == 3:
    src = subprocess.run([os.path.join(ROOT, 'tools', 'dis.sh'), sys.argv[1], sys.argv[2]],
                         capture_output=True, text=True, check=True).stdout.splitlines()
else:
    src = sys.stdin.read().splitlines()

line_re = re.compile(r'^\s*([0-9a-f]{8}):')
hex_re = re.compile(r'0x([0-9a-f]{6,8})\b')
dec_re = re.compile(r'(?<![\w(])(\d{9,10})(?=[,\s)]|$)')

for line in src:
    m = line_re.match(line)
    if m and int(m.group(1), 16) in names:
        print('%s:' % names[int(m.group(1), 16)])
    hits = []
    body = line.split('\t', 2)[-1] if m else line
    for h in hex_re.findall(body):
        a = int(h, 16)
        if a in names and (not m or a != int(m.group(1), 16)):
            hits.append(names[a])
    for dnum in dec_re.findall(body):
        a = int(dnum) & 0xffffffff
        if a in names:
            hits.append('%s (0x%08x)' % (names[a], a))
    print(line + ('    ; ' + ', '.join(dict.fromkeys(hits)) if hits else ''))
