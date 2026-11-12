import json
from pathlib import Path

edits = json.loads(Path("patches/omdem1mk2/sd_loader/edits.json").read_text())["edits"]
cave = [e for e in edits if e["addr"] == "0x60580200"][0]
data = bytes.fromhex(cave["new"])

# cave is at 0x60580200
for off in [0x605803a1 - 0x60580200, 0x605803c9 - 0x60580200]:
    print(f"data at {off:#x}: {data[off:off+30]}")
