import struct, re

data = open("em1mk2/extracted/00_0100_40560020.decoded.bin", "rb").read()
base = 0x60021020

addrs = [0x61f9deec, 0x61f9def0, 0x61f9dec4, 0x61f9dedc]
for a in addrs:
    print(f"\n=== References to {a:#x} ===")
    for m in re.finditer(re.escape(struct.pack("<I", a)), data):
        off = m.start()
        # show 16 bytes before and after
        start = max(0, off - 10)
        end = min(len(data), off + 14)
        print(f"at {base+off:#x}: {data[start:end].hex()}")
