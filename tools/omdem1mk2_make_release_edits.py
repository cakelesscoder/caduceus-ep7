#!/usr/bin/env python3
"""Build declarative edits.json and seal an E-M1 Mark II release.

    python3 em1mk2/scripts/make_release_edits.py [VERSION]   (default v0.1)

Each version gets its own releases/em1mk2/<VERSION>/ so a test build never overwrites the
release that is on the camera.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = sys.argv[1] if len(sys.argv) > 1 else 'v0.1'
REL_DIR = ROOT / 'releases' / 'em1mk2' / VERSION
REL_DIR.mkdir(parents=True, exist_ok=True)

# 1. Rebuild individual patches to ensure fresh binaries
subprocess.run(["python3", str(ROOT / 'patches' / 'omdem1mk2' / 'sd_loader' / 'make_looks_bin.py'), VERSION], check=True)
subprocess.run(["python3", str(ROOT / 'patches' / 'omdem1mk2' / 'sd_loader' / 'build.py')], check=True)
subprocess.run(["python3", str(ROOT / 'patches' / 'omdem1mk2' / 'color_creator_wheel' / 'build.py')], check=True)

# 2. Load individual patch edits for pure Caduceus features
rec_edits = json.loads((ROOT / 'patches' / 'omdem1mk2' / 'rec_limit' / 'edits.json').read_text())['edits']
focus_edits = json.loads((ROOT / 'patches' / 'omdem1mk2' / 'focus_stacking' / 'edits.json').read_text())['edits']
sd_edits = json.loads((ROOT / 'patches' / 'omdem1mk2' / 'sd_loader' / 'edits.json').read_text())['edits']
wheel_edits = json.loads((ROOT / 'patches' / 'omdem1mk2' / 'color_creator_wheel' / 'edits.json').read_text())['edits']

all_edits = []
all_edits.extend(rec_edits)
all_edits.extend(focus_edits)
all_edits.extend(sd_edits)
all_edits.extend(wheel_edits)

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

for name in ["patched.pkg.bin", "restore-stock.pkg.bin", "build.json"]:
    (REL_DIR / name).write_bytes((tmp_dir / name).read_bytes())

files_to_hash = [
    "build.json",
    "card/EM1MOD/LOOKS.BIN",
    "edits.json",
    "patched.pkg.bin",
    "restore-stock.pkg.bin",
]

lines = []
for rel_name in sorted(files_to_hash):
    p = REL_DIR / rel_name
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    lines.append(f"{h}  {rel_name}")

sums_content = "\n".join(lines) + "\n"
(REL_DIR / "SHA256SUMS").write_text(sums_content)
print(f"Updated SHA256SUMS in {REL_DIR}")
