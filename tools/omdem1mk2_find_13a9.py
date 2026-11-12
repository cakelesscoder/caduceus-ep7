import struct
from pathlib import Path

bin_path = Path("/home/hertzel/projects/olympus-firmware/caduceus-ep7/em1mk2/extracted/00_0100_40560020.decoded.bin")
data = bin_path.read_bytes()
BASE_VMA = 0x60021020

# Search for 0x13a9 (little endian: a9 13)
pattern = bytes.fromhex("a913")
idx = 0
while True:
    pos = data.find(pattern, idx)
    if pos == -1: break
    vma = BASE_VMA + pos
    # check if it looks like an editor record: {u16 key, u16 n, u32 child_list}
    if pos + 8 <= len(data):
        key, n, child_list = struct.unpack_from("<HHI", data, pos)
        if key == 0x13a9 and 1 <= n <= 20 and 0x60000000 <= child_list <= 0x62000000:
            print(f"Found editor descriptor for 0x13a9 at {hex(vma)}: n={n}, child_list={hex(child_list)}")
    idx = pos + 1
