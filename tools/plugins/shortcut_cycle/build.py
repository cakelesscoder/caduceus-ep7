#!/usr/bin/env python3
"""Build the "shortcut_cycle" plugin -> PLUGIN.BIN (Caduceus plugin ABI 1.1, E-P7 1.1, needs the v0.32 key hook). Offline.
docs/PLUGINS.md §7-§9.

  .venv/bin/python -I tools/plugins/shortcut_cycle/build.py --out generated/plugins/shortcut_cycle/EP7MOD/PLUGIN.BIN

Fn (Shortcut) in a still mode: press 1 stock (assigned function, e.g. the colour profile popup), press 2 closes it and
opens the aspect popup (select mode 50) through the stock exit-and-replay (API word +32, ka_rep; on an API without it,
press 2 only closes and press 3 opens aspect), the next press closes aspect. docs/PLUGINS.md §12. Setup > Firmware shows
"Caduceus: 0.32S" once loaded (first half-press). Firmware without the two-site key hook (API < 7 words or feature bit 1 clear) declines it: no "S".
"""
import argparse, importlib.util, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


HB = _load('ep7_hello_build_sc', ROOT / 'tools/plugins/hello/build.py')
DEFS = dict(MAXC=HB.MAXC, SUFFIX=ord('S'), EV_FN=0x0100002e, K44=0x8551, K24=0xc011, MODE=50)


def build():
    code, dis = HB.assemble((HERE / 'sc.s').read_text(), DEFS)
    HB.check(code, dis)
    return HB.make(code), dis


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    data, _ = build()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(data)
    print(f'{a.out}: {len(data)} B, crc {struct.unpack_from("<I", data, 4)[0]:#010x}')
