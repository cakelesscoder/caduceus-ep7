import struct
from pathlib import Path

bin_path = Path("/home/hertzel/projects/olympus-firmware/caduceus-ep7/em1mk2/extracted/00_0100_40560020.decoded.bin")
data = bin_path.read_bytes()
BASE_VMA = 0x60021020

def u32(vma):
    off = vma - BASE_VMA
    return struct.unpack_from("<I", data, off)[0]

def u16(vma):
    off = vma - BASE_VMA
    return struct.unpack_from("<H", data, off)[0]

# Child list at 0x61259ff8:
print(f"Child list at 0x61259ff8:")
for i in range(4):
    addr = 0x61259ff8 + i * 4
    val = u32(addr)
    kind = u16(addr)
    sid = u16(addr + 2)
    print(f"  [{i}] {hex(addr)}: {hex(val)} (kind={kind}, sid={sid})")

# Let's inspect the entire descriptor table around 0x6125a118
print("\nDescriptor table around 0x6125a118:")
for addr in range(0x6125a0e0, 0x6125a150, 8):
    key, n, clist = struct.unpack_from("<HHI", data, addr - BASE_VMA)
    print(f"  {hex(addr)}: key={hex(key)} ({key}), n={n}, child_list={hex(clist)}")
