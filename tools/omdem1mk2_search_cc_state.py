from pathlib import Path
import re

bin_path = Path("/home/hertzel/projects/olympus-firmware/caduceus-ep7/em1mk2/extracted/00_0100_40560020.decoded.bin")
data = bin_path.read_bytes()
BASE_VMA = 0x60021020

# Search for references to SsMenuMain_StRawColorCreator vtable or state descriptor
for m in re.finditer(b"SsMenuMain_StR", data):
    off = m.start()
    end = data.find(b"\0", off)
    print(hex(BASE_VMA + off), data[off:end])
