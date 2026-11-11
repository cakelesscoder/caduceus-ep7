import struct, re

data = open("em1mk2/extracted/00_0100_40560020.decoded.bin", "rb").read()
base = 0x60021020

for a in [0x61277800, 0x6127783c, 0x612777fc]:
    m = list(re.finditer(re.escape(struct.pack("<I", a)), data))
    print(f"ref to {a:#x}: {[hex(base+x.start()) for x in m]}")
