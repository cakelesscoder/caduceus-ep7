import struct
from pathlib import Path

bin_path = Path("/home/hertzel/projects/olympus-firmware/caduceus-ep7/em1mk2/extracted/00_0100_40560020.decoded.bin")
data = bin_path.read_bytes()
BASE_VMA = 0x60021020

for key, name in [(0x13b3, "COLOR1"), (0x13b4, "COLOR2"), (0x13b5, "COLOR3"), (0x140c, "COLOR4")]:
    target = struct.pack("<H", key)
    refs = []
    idx = 0
    while True:
        pos = data.find(target, idx)
        if pos == -1: break
        refs.append(hex(BASE_VMA + pos))
        idx = pos + 1
    print(f"Key {hex(key)} ({name}): {len(refs)} matches: {refs[:5]}")
