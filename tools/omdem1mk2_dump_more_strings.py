from pathlib import Path
bin_path = Path("/home/hertzel/projects/olympus-firmware/caduceus-ep7/em1mk2/extracted/00_0100_40560020.decoded.bin")
data = bin_path.read_bytes()
BASE_VMA = 0x60021020

start = 0x6127a300 - BASE_VMA
end = 0x6127a500 - BASE_VMA

i = start
while i < end:
    if data[i] != 0:
        nul = data.find(b"\0", i)
        s = data[i:nul]
        if all(32 <= b < 127 for b in s) and len(s) > 3:
            print(hex(BASE_VMA + i), s.decode())
            i = nul
    i += 1
