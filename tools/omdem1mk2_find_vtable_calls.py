import subprocess

# In Genifa, screen HandleEvent is called through the screen manager dispatcher.
# Let's search where (32, a0) or (32, a1) or (32, a2) is called: calls (aX)
data = open("em1mk2/extracted/00_0100_40560020.decoded.bin", "rb").read()
base = 0x60021020

# Search calls to 0x60ec7112 or calls (aX) with offset 32 (0x20)
for i in range(len(data)-4):
    # f8 2a 20: mov (32, a2), a2
    # f8 29 20: mov (32, a1), a1
    # f8 28 20: mov (32, a0), a0
    if data[i] == 0xf8 and data[i+2] == 0x20 and data[i+1] in [0x28, 0x29, 0x2a]:
        print(f"vtable[8] call at {base+i:#x}: {data[i:i+6].hex()}")
