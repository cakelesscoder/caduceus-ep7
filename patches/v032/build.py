#!/usr/bin/env python3
"""v0.32 = releases/v0.31d -> patches/scp_name (#41, Colour Profile page guide label) -> patches/split_tone (OM-3 engine at
the tone hook, slot +62/+63) -> patches/extras_pages (Extras wheel split into Effects and Colour & Light pages, split tone
on the wheel; docs/EXTRAS_MENU_V2.md "Build log") -> patches/looks_split (LOOKS.BIN record +61/+62 split, set by a Film
pick; docs/PACKS.md) -> patches/i18n_zh -> patches/lv_grid (XPan grid + 65:24 / 21:9 frame lines, data only) -> fw_version 0.32 -> patches/plugin_loader
(early test: SD plugins, EP7MOD/PLUGIN.BIN; docs/PLUGINS.md) -> patches/keyhook (plugin key hook, API v1.1) ->
patches/overlay_probe (Extras text-overlay probe; docs/EXTRAS_OVERLAY.md) -> patches/diag (camera diagnosis,
Firmware-screen L/O readout; docs/PLUGINS.md §10). Offline.

  .venv/bin/python -I patches/v032/build.py releases/v0.31d/edits.json --out generated/v032/edits.json
"""
import argparse, importlib.util, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def apply(spec, version='0.32', plugins=True, keyhook=True, overlay=True, diag=True, extras=None):
    if extras is None:                        # the release build is plugins=False (plugins shelved), which has the Extras pages
        extras = not plugins
    if extras and plugins:
        raise SystemExit('extras_pages takes the sdk shell words keyhook wants: build it with plugins=False')
    spec = _load('scp_name', ROOT / 'patches/scp_name/build.py').apply(spec, version)
    spec = _load('split_tone', ROOT / 'patches/split_tone/build.py').apply(spec, version)
    if extras:
        spec = _load('extras_pages', ROOT / 'patches/extras_pages/build.py').apply(spec, version)
        spec = _load('looks_split', ROOT / 'patches/looks_split/build.py').apply(spec, version)   # LOOKS.BIN split -> Film pick
        if spec['looks_split']['L']['size'] > 2688:    # v0.32a: split_tone keeps S at L+2688 (docs/GRAIN_HANG.md)
            raise SystemExit('L request overlaps split_tone S at L+2688')
        spec = _load('i18n_zh', ROOT / 'patches/i18n_zh/build.py').apply(spec, version)  # after every guide-word layer
    spec = _load('lv_grid', ROOT / 'patches/lv_grid/build.py').apply(spec)
    spec = _load('fw_version', ROOT / 'patches/fw_version/build.py').apply(spec, version) or spec
    if plugins:                               # last: plugin_loader needs fw_version's fw_val and refuses a re-run
        spec = _load('plugin_loader', ROOT / 'patches/plugin_loader/build.py').apply(spec, version)

    # ---- keyhook layer (patches/keyhook, docs/PLUGINS.md §9): resident plugin key hook + API v1.1 + sdk shell cut.
    # Needs plugin_loader. Sec 5 claim 0x607b6420-0x607b8420 only (0x607b8420.. is the Extras overlay's).
    if plugins and keyhook:
        spec = _load('keyhook', ROOT / 'patches/keyhook/build.py').apply(spec, version)
    # ---- end keyhook layer

    # ---- Extras text-overlay probe (patches/overlay_probe, docs/EXTRAS_OVERLAY.md): window +164 post-paint hook that
    # draws four text rows over the Colour Profile editor on the Extras page. Needs keyhook (sdk shell cut). Sec 5 claim
    # 0x607b8420-0x607c8420, after keyhook's 0x607b6420-0x607b8420. One separate layer; coordinate CODE_SPACE_MAP.
    if plugins and keyhook and overlay:
        spec = _load('overlay_probe', ROOT / 'patches/overlay_probe/build.py').apply(spec, version)
    # ---- end overlay layer

    # ---- camera diagnosis layer (patches/diag, docs/PLUGINS.md §10): loader with stage marks (P+852 cleared first),
    # overlay hook moved to the GE paint site, Firmware-screen "L/O" readout. Needs all three layers above. Stays in
    # later builds as a diagnostic.
    if plugins and keyhook and overlay and diag:
        spec = _load('diag', ROOT / 'patches/diag/build.py').apply(spec, version)
    # ---- end diag layer
    return spec


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--version', default='0.32')
    ap.add_argument('--plugins', action='store_true', help='shelved plugin layers (no Extras pages)')
    a = ap.parse_args()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(apply(json.loads(a.spec.read_text()), a.version, plugins=a.plugins), indent=1))
