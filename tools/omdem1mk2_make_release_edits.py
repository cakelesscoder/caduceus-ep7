#!/usr/bin/env python3
"""Build declarative edits.json and seal an E-M1 Mark II release.

    python3 tools/omdem1mk2_make_release_edits.py [VERSION] [--skip aspect]   (default v0.1)

--skip <patch> leaves a feature group out (FIRMWARE_GUIDE §10 lesson 1: one feature group per flash).

Each version gets its own releases/em1mk2/<VERSION>/ so a test build never overwrites the
release that is on the camera.
"""
import hashlib
import os
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
args = sys.argv[1:]
SKIP = set()
while '--skip' in args:
    i = args.index('--skip')
    SKIP.add(args[i + 1])
    del args[i:i + 2]
assert SKIP <= {'aspect', 'debug_log'}, f'unknown --skip {SKIP}'
VERSION = args[0] if args else 'v0.1'
REL_DIR = ROOT / 'releases' / 'em1mk2' / VERSION
REL_DIR.mkdir(parents=True, exist_ok=True)

# 1. Rebuild individual patches to ensure fresh binaries
subprocess.run(["python3", str(ROOT / 'patches' / 'omdem1mk2' / 'sd_loader' / 'make_looks_bin.py'), VERSION], check=True)
subprocess.run(["python3", str(ROOT / 'patches' / 'omdem1mk2' / 'sd_loader' / 'build.py')], check=True)
# EM1_SPACE_PROBE=1: code-space probe sp1 (section 5 loaded end -> 0x61300000; banner " S+/S!/S0"). Built before the
# look editor, which then calls it (docs/OMD-EM1-II/HALATION.md step 1).
PROBE = os.environ.get('EM1_SPACE_PROBE') == '1'
if PROBE:
    subprocess.run(["python3", str(ROOT / 'patches' / 'omdem1mk2' / 'space_probe' / 'build.py')], check=True)
subprocess.run(["python3", str(ROOT / 'patches' / 'omdem1mk2' / 'color_creator_wheel' / 'build.py')], check=True)
subprocess.run(["python3", str(ROOT / 'patches' / 'omdem1mk2' / 'debug_log' / 'build.py'), VERSION], check=True)
subprocess.run(["python3", str(ROOT / 'patches' / 'omdem1mk2' / 'aspect' / 'build.py')], check=True)
subprocess.run(["python3", str(ROOT / 'patches' / 'omdem1mk2' / 'aspect_icons' / 'build.py')], check=True)

# 2. Load individual patch edits for pure Caduceus features
rec_edits = json.loads((ROOT / 'patches' / 'omdem1mk2' / 'rec_limit' / 'edits.json').read_text())['edits']
focus_edits = json.loads((ROOT / 'patches' / 'omdem1mk2' / 'focus_stacking' / 'edits.json').read_text())['edits']
sd_edits = json.loads((ROOT / 'patches' / 'omdem1mk2' / 'sd_loader' / 'edits.json').read_text())['edits']
wheel_edits = json.loads((ROOT / 'patches' / 'omdem1mk2' / 'color_creator_wheel' / 'edits.json').read_text())['edits']
debug_edits = json.loads((ROOT / 'patches' / 'omdem1mk2' / 'debug_log' / 'edits.json').read_text())['edits']
aspect_edits = json.loads((ROOT / 'patches' / 'omdem1mk2' / 'aspect' / 'edits.json').read_text())['edits']

all_edits = []
if PROBE:
    all_edits.extend(json.loads((ROOT / 'patches' / 'omdem1mk2' / 'space_probe' / 'edits.json').read_text())['edits'])
all_edits.extend(rec_edits)
all_edits.extend(focus_edits)
all_edits.extend(sd_edits)
all_edits.extend(wheel_edits)
if 'debug_log' not in SKIP:
    all_edits.extend(debug_edits)
if 'aspect' not in SKIP:
    all_edits.extend(aspect_edits)
    # 65:24 / 21:9 icons in the OSD component (0x101), referenced by the aspect lists (aspect/build.py ICON_IDS)
    all_edits.extend(json.loads((ROOT / 'patches' / 'omdem1mk2' / 'aspect_icons' / 'edits.json').read_text())['edits'])

# Bundle all 5 camera components (0x100, 0x101, 0x106, 0x10e, 0x102) for a full 93 MB image:
release_spec = {
    "camera": "em1mk2",
    "version": VERSION,
    "components": ["0x100", "0x101", "0x106", "0x10e", "0x102"],
    "edits": all_edits
}

out_path = REL_DIR / 'edits.json'
out_path.write_text(json.dumps(release_spec, indent=2) + '\n')
print(f"Wrote {len(all_edits)} edits to {out_path}")

# Refuse to seal a release with edits the camera never loads (v0.1-v0.3b1 had such a cave).
subprocess.run(["python3", str(ROOT / 'tools' / 'omdem1mk2_check_loaded.py'), str(out_path)], check=True)
# Refuse banned opcodes, absolute stores into the image and call/ret frame mismatches (v0.4 restart).
subprocess.run(["python3", str(ROOT / 'tools' / 'omdem1mk2_audit_opcodes.py')], check=True, cwd=ROOT)

# 2. Package and seal release
tmp_dir = Path("/tmp/em1_build_pkg")
if tmp_dir.exists():
    import shutil
    shutil.rmtree(tmp_dir)

subprocess.run([
    "python3", str(ROOT / "tools" / "build_package.py"),
    str(out_path),
    "--out", str(tmp_dir)
], check=True)

# The patched package is written under the card name the camera's updater looks for (copy it to DCOLYMP/ as is).
CARD_NAME = "E1259999.BIN"
for name in ["patched.pkg.bin", "restore-stock.pkg.bin", "build.json"]:
    (REL_DIR / (CARD_NAME if name == "patched.pkg.bin" else name)).write_bytes((tmp_dir / name).read_bytes())
(REL_DIR / "patched.pkg.bin").unlink(missing_ok=True)

# Copy DEBUG.TXT helper
import shutil
dbg_src = ROOT / 'patches' / 'omdem1mk2' / 'debug_log' / 'DEBUG.TXT'
if dbg_src.exists() and 'debug_log' not in SKIP:
    shutil.copyfile(dbg_src, REL_DIR / 'card' / 'EM1MOD' / 'DEBUG.TXT')
    shutil.copyfile(dbg_src, REL_DIR / 'DEBUG.TXT')
    shutil.copyfile(dbg_src, ROOT / 'card' / 'EM1MOD' / 'DEBUG.TXT')

files_to_hash = [
    "build.json",
    "card/EM1MOD/LOOKS.BIN",
    "edits.json",
    CARD_NAME,
    "restore-stock.pkg.bin",
]

if 'debug_log' not in SKIP:
    files_to_hash.append("card/EM1MOD/DEBUG.TXT")
lines = []
for rel_name in sorted(files_to_hash):
    p = REL_DIR / rel_name
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    lines.append(f"{h}  {rel_name}")

sums_content = "\n".join(lines) + "\n"
(REL_DIR / "SHA256SUMS").write_text(sums_content)
print(f"Updated SHA256SUMS in {REL_DIR}")
