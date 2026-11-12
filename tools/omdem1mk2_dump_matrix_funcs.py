from pathlib import Path
import subprocess

objdump = "/home/hertzel/ep7fw-toolchains/mn10300/bin/mn10300-elf-objdump"
bin_file = "/home/hertzel/projects/olympus-firmware/caduceus-ep7/em1mk2/extracted/00_0100_40560020.decoded.bin"

cmd = [
    objdump, "-b", "binary", "-m", "am33-2", "-D", bin_file,
    "--adjust-vma=0x60021020",
    "--start-address=0x603eb300",
    "--stop-address=0x603eb420"
]
res = subprocess.run(cmd, capture_output=True, text=True)
print(res.stdout)
