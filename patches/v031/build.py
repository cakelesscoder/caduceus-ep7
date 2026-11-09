#!/usr/bin/env python3
"""v0.31 test = patches/v030 chain (v0.29a + min_ss + ap_custom + live_nd 0.31n2: per-press floor; the Custom Self-timer one-press of 0.31t2 hung,
built only with selftimer=True) -> patches/recview (applies patches/grain_kind first) -> patches/halation. Offline.

  .venv/bin/python -I patches/v031/build.py releases/v0.28/edits.json --out generated/v031/edits.json [--version 0.31t2]
"""
import argparse, importlib.util, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def apply(spec, version='0.31a'):
    spec = _load('v030', ROOT / 'patches/v030/build.py').apply(spec, version)
    spec = _load('recview', ROOT / 'patches/recview/build.py').apply(spec, version)   # grain_kind, then rv_gate
    return _load('halation', ROOT / 'patches/halation/build.py').apply(spec, version)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--version', default='0.31a')
    a = ap.parse_args()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(apply(json.loads(a.spec.read_text()), a.version), indent=1))
