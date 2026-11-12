import struct, re

data = open("em1mk2/extracted/00_0100_40560020.decoded.bin", "rb").read()
base = 0x60021020

# Search strings between 0x60ebe000 and 0x60ebf500
start = 0x60ebe000 - base
end = 0x60ebf500 - base
chunk = data[start:end]

# Also search references to addresses around 0x60ebee00
for a in range(0x60ebee00, 0x60ebef20, 4):
    m = list(re.finditer(re.escape(struct.pack("<I", a)), data))
    if m:
        print(f"ref to {a:#x} at {[hex(base+x.start()) for x in m]}")
