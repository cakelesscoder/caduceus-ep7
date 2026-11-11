data = open("em1mk2/extracted/00_0100_40560020.decoded.bin", "rb").read()
base = 0x60021020

off = 0x61277800 - base
# Look backwards for screen key or structure header
print(f"data before 0x61277800: {data[off-128:off].hex()}")
# Let's inspect strings nearby
import re
print("nearby strings:")
for m in re.finditer(b"[A-Za-z0-9_]{4,}", data[off-500:off+500]):
    print(m.group().decode(errors='ignore'))
