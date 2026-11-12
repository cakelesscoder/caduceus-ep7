import struct
from pathlib import Path

bin_path = Path("/home/hertzel/projects/olympus-firmware/caduceus-ep7/em1mk2/extracted/00_0100_40560020.decoded.bin")
data = bin_path.read_bytes()
BASE_VMA = 0x60021020

# Let's search for OSD string IDs or references in Color Creator view
# Earlier we saw in 0x60ec73bf (SsMenuMain_StRColorCreator_Entry):
# It opened Screen Group 18, Key 0x13a9.
# Let's see what view class is instantiated for Key 0x13a9!
