data = open("em1mk2/extracted/00_0100_40560020.decoded.bin", "rb").read()
base = 0x60021020

# Search for f8 2X 24 (mov (36, aX), aX) and f8 2X 28 (mov (40, aX), aX)
for i in range(len(data)-4):
    if data[i] == 0xf8 and data[i+2] in [0x24, 0x28]:
        reg = data[i+1]
        print(f"offset {data[i+2]:#x} call at {base+i:#x}: {data[i:i+6].hex()}")
