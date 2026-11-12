import struct
from pathlib import Path

bin_path = Path("/home/hertzel/projects/olympus-firmware/caduceus-ep7/em1mk2/extracted/00_0100_40560020.decoded.bin")
data = bin_path.read_bytes()
BASE_VMA = 0x60021020

# Search for 56-byte records where +0 is 0x13a9
idx = 0
while True:
    pos = data.find(bytes.fromhex("a913"), idx)
    if pos == -1: break
    vma = BASE_VMA + pos
    # check if pos+4 has a valid function pointer
    if pos + 56 <= len(data):
        init_fn = struct.unpack_from("<I", data, pos + 4)[0]
        if 0x60000000 <= init_fn <= 0x61000000:
            print(f"Found parent controller record for 0x13a9 at {hex(vma)}:")
            for off in range(0, 56, 4):
                val = struct.unpack_from("<I", data, pos + off)[0]
                print(f"  +{off}: {hex(val)}")
    idx = pos + 1
