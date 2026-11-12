data = open("em1mk2/extracted/00_0100_40560020.decoded.bin", "rb").read()
base = 0x60021020

off = 0x6127783c - base
print(f"data at 0x61277800: {data[off-60:off+60].hex()}")
import struct
for i in range(off-60, off+60, 4):
    val = struct.unpack("<I", data[i:i+4])[0]
    print(f"  {base+i:#x}: {val:#x}")
