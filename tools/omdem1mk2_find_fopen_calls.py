import struct, subprocess

data = open("em1mk2/extracted/00_0100_40560020.decoded.bin", "rb").read()
base = 0x60021020
target = 0x6062ce6a

# Find calls to target: dd <disp32>
print(f"Searching calls to em1_fopen ({target:#x})...")
for i in range(len(data)-7):
    if data[i] == 0xdd:
        disp = struct.unpack("<i", data[i+1:i+5])[0]
        dest = base + i + 7 + disp
        if dest == target:
            print(f"call at {base+i:#x}")
            # disassemble 30 bytes before
            out = subprocess.check_output([
                "/home/hertzel/ep7fw-toolchains/mn10300/bin/mn10300-elf-objdump",
                "-b", "binary", "-m", "mn10300", "-D",
                f"--adjust-vma={base+i-30:#x}",
                f"--start-address={base+i-30:#x}",
                f"--stop-address={base+i+7:#x}",
                "em1mk2/extracted/00_0100_40560020.decoded.bin"
            ]).decode()
            print(out)
            break
