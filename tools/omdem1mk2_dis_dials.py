import subprocess

for addr, length in [(0x60ec7353, 52), (0x60ec7387, 80)]:
    out = subprocess.check_output([
        "/home/hertzel/ep7fw-toolchains/mn10300/bin/mn10300-elf-objdump",
        "-b", "binary", "-m", "mn10300", "-D",
        f"--adjust-vma={addr:#x}",
        f"--start-address={addr:#x}",
        f"--stop-address={addr+length:#x}",
        "em1mk2/extracted/00_0100_40560020.decoded.bin"
    ]).decode()
    print(out)
