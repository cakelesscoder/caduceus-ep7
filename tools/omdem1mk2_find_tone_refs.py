import struct
from pathlib import Path

bin_path = Path("/home/hertzel/projects/olympus-firmware/caduceus-ep7/em1mk2/extracted/00_0100_40560020.decoded.bin")
data = bin_path.read_bytes()
BASE_VMA = 0x60021020

for s_name, addr in [
    ("ToneControlLow", 0x6145085a),
    ("ToneControlMiddle", 0x6145087a),
    ("ToneControlHigh", 0x6145089a)
]:
    target = struct.pack("<I", addr)
    idx = 0
    refs = []
    while True:
        pos = data.find(target, idx)
        if pos == -1: break
        refs.append(hex(BASE_VMA + pos))
        idx = pos + 1
    print(f"{s_name} ({hex(addr)}): {refs}")
