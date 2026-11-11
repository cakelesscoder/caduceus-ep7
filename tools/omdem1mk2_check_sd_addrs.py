import struct, re

data = open("em1mk2/extracted/00_0100_40560020.decoded.bin", "rb").read()
base = 0x60021020

addrs = [0x61f9deec, 0x61f9def0, 0x61f9dec4, 0x61f9dedc]
for a in addrs:
    m = list(re.finditer(re.escape(struct.pack("<I", a)), data))
    print(f"{a:#x}: {len(m)} references in E-M1 Mark II firmware")
