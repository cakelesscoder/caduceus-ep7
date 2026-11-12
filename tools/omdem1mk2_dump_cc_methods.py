import subprocess, tempfile

data = open("em1mk2/extracted/00_0100_40560020.decoded.bin", "rb").read()
base = 0x60021020

funcs = [
    ("func_7000", 0x60ec7000),
    ("func_7017", 0x60ec7017),
    ("func_7112", 0x60ec7112),
    ("func_7353", 0x60ec7353),
    ("func_7387", 0x60ec7387),
    ("func_742e", 0x60ec742e),
]

for name, addr in funcs:
    print(f"\n================ {name} ({addr:#x}) ================")
    off = addr - base
    chunk = data[off:off+48]
    with tempfile.NamedTemporaryFile("wb", suffix=".bin") as f:
        f.write(chunk)
        f.flush()
        out = subprocess.check_output([
            "/home/hertzel/ep7fw-toolchains/mn10300/bin/mn10300-elf-objdump",
            "-b", "binary", "-m", "mn10300", "-D",
            f"--adjust-vma={addr:#x}",
            f.name
        ]).decode()
        print(out)
