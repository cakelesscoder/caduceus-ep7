import struct
from pathlib import Path

bin_path = Path("/home/hertzel/projects/olympus-firmware/caduceus-ep7/em1mk2/extracted/00_0100_40560020.decoded.bin")
data = bin_path.read_bytes()
BASE_VMA = 0x60021020

# Search for Tone control or Highlight/Shadow strings and setting descriptors
for s in [b"Highlight", b"Shadow", b"Midtone", b"ToneControl", b"ColorCreator", b"Vivid"]:
    for m in __import__("re").finditer(s, data):
        off = m.start()
        print(f"Found {s.decode()} at {hex(BASE_VMA + off)}")
