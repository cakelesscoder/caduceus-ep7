import struct
from pathlib import Path

bin_path = Path("/home/hertzel/projects/olympus-firmware/caduceus-ep7/em1mk2/extracted/00_0100_40560020.decoded.bin")
data = bin_path.read_bytes()
BASE_VMA = 0x60021020

# Let's search for settings IDs used by Color Creator
# In E-P7, Color Creator setting was 1645 = 21 (or sid 617, 618).
# In E-M1 Mark II, let's look at doCmd_SsMenuMain_StRawColorCreator_EvtStChgJogDial (0x60ec7353)
# and EvtStChgCtrlRing (0x60ec7387).
# Let's inspect where 0x9004, 0x9006, 0x9008, 0x900a are processed in Color Creator!
