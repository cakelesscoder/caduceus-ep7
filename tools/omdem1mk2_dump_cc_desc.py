import struct

data = open("em1mk2/extracted/00_0100_40560020.decoded.bin", "rb").read()
base = 0x60021020

off = 0x61279074 - base
for i in range(off - 32, off + 48, 4):
    val = struct.unpack("<I", data[i:i+4])[0]
    print(f"{base+i:#x}: {val:#010x}")
