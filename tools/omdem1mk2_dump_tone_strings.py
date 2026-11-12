from pathlib import Path
bin_path = Path("/home/hertzel/projects/olympus-firmware/caduceus-ep7/em1mk2/extracted/00_0100_40560020.decoded.bin")
data = bin_path.read_bytes()
BASE_VMA = 0x60021020

off = 0x61450800 - BASE_VMA
print(data[off:off+200])
