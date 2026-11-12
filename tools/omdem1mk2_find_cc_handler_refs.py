import struct, re

data = open("em1mk2/extracted/00_0100_40560020.decoded.bin", "rb").read()
base = 0x60021020

target = 0x60ec7112
print(f"References to 0x60ec7112:")
for m in re.finditer(re.escape(struct.pack("<I", target)), data):
    print(f"  at {base+m.start():#x}")
