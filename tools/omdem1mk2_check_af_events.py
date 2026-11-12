import struct, re

data = open("em1mk2/extracted/00_0100_40560020.decoded.bin", "rb").read()
base = 0x60021020

# Search for 0xaf00, 0xaf01, 0xaf02, 0xaf03
for code in [0xaf00, 0xaf01, 0xaf02, 0xaf03]:
    pat = b"\xfc[\xc8-\xcf]" + struct.pack("<I", code)[:2] + b"\x00\x00"
    m_list = list(re.finditer(pat, data))
    print(f"code {code:#06x}: {len(m_list)} occurrences, at {[hex(base+m.start()) for m in m_list]}")
