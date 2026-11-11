import json, subprocess, tempfile
from pathlib import Path

edits = json.loads(Path("patches/omdem1mk2/sd_loader/edits.json").read_text())["edits"]
cave = [e for e in edits if e["addr"] == "0x60580200"][0]
data = bytes.fromhex(cave["new"])

with tempfile.NamedTemporaryFile("wb", suffix=".bin") as f:
    f.write(data)
    f.flush()
    out = subprocess.check_output([
        "/home/hertzel/ep7fw-toolchains/mn10300/bin/mn10300-elf-objdump",
        "-b", "binary", "-m", "mn10300", "-D",
        "--adjust-vma=0x60580200", f.name
    ]).decode()
    print(out[:2000])
