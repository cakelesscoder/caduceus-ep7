import struct, subprocess

out = subprocess.check_output([
    "/home/hertzel/ep7fw-toolchains/mn10300/bin/mn10300-elf-objdump",
    "-b", "binary", "-m", "mn10300", "-D",
    "--adjust-vma=0x60021020",
    "--start-address=0x60ec7112",
    "--stop-address=0x60ec7355",
    "em1mk2/extracted/00_0100_40560020.decoded.bin"
]).decode()
print(out)
