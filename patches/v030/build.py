#!/usr/bin/env python3
"""v0.30 test = v0.29a + minimum shutter menu (patches/min_ss) + AP Custom slot (patches/ap_custom) + Live ND2/ND4 AP entries (patches/live_nd). Offline.

  .venv/bin/python -I patches/v030/build.py releases/v0.28/edits.json --out generated/v030/edits.json [--version 0.30b1]
"""
import argparse, importlib.util, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def apply(spec, version='0.30'):
    spec = _load('v029a', ROOT / 'patches/v029a/build.py').apply(spec)
    spec = _load('min_ss', ROOT / 'patches/min_ss/build.py').apply(spec, '0.29a')
    spec = _load('ap_custom', ROOT / 'patches/ap_custom/build.py').apply(spec, None)
    return _load('live_nd', ROOT / 'patches/live_nd/build.py').apply(spec, version)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--version', default='0.30')
    a = ap.parse_args()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(apply(json.loads(a.spec.read_text()), a.version), indent=1))
