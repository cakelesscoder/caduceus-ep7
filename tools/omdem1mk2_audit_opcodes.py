import json
import subprocess
import os

def audit_code(name, vma, code_bytes, stop_addr=None):
    tmp = f'/tmp/audit_{name}.bin'
    with open(tmp, 'wb') as f:
        f.write(code_bytes)
    cmd = [
        '/home/hertzel/ep7fw-toolchains/mn10300/bin/mn10300-elf-objdump',
        '-D', '-b', 'binary', '-m', 'am33-2',
        f'--adjust-vma={hex(vma)}',
    ]
    if stop_addr:
        cmd.append(f'--stop-address={hex(stop_addr)}')
    cmd.append(tmp)
    res = subprocess.run(cmd, capture_output=True, text=True)
    os.remove(tmp)
    
    fb_lines = []
    mul_div_lines = []
    loop_lines = []
    
    for line in res.stdout.splitlines():
        parts = line.strip().split(':\t')
        if len(parts) == 2:
            addr = parts[0]
            rest = parts[1].split('\t')
            hex_bytes = rest[0].strip().split()
            inst = rest[1] if len(rest) > 1 else ''
            # Only test actual instructions, not continuation lines of hex bytes
            if inst and hex_bytes and hex_bytes[0].lower() == 'fb':
                fb_lines.append((addr, hex_bytes, inst))
            if inst:
                mnemonic = inst.split()[0].lower()
                if any(mnemonic.startswith(k) for k in ['mul', 'div']):
                    mul_div_lines.append((addr, hex_bytes, inst))
                if mnemonic == 'setlb':
                    loop_lines.append((addr, hex_bytes, inst))

    print(f"[{name}] at {hex(vma)} (len {len(code_bytes)}):")
    print(f"  0xFB opcodes: {len(fb_lines)}")
    for a, h, i in fb_lines:
        print(f"    {a}: {' '.join(h)} -> {i}")
    print(f"  mul/div opcodes: {len(mul_div_lines)}")
    for a, h, i in mul_div_lines:
        print(f"    {a}: {' '.join(h)} -> {i}")
    print(f"  hardware loop opcodes: {len(loop_lines)}")

# Audit color_creator_wheel
d = json.loads(open('patches/omdem1mk2/color_creator_wheel/edits.json').read())
cave_edit = [e for e in d['edits'] if e['addr'] == '0x612e6900'][0]
b = bytes.fromhex(cave_edit['new'])
data_start_offset = b.find(b"Chroma: ")
stop_addr = 0x612e6900 + data_start_offset if data_start_offset != -1 else None
audit_code('color_creator_cave', 0x612e6900, b, stop_addr=stop_addr)

# Audit sd_loader
d = json.loads(open('patches/omdem1mk2/sd_loader/edits.json').read())
cave_edit = [e for e in d['edits'] if e['addr'] == '0x60580200'][0]
b = bytes.fromhex(cave_edit['new'])
audit_code('sd_loader_cave', 0x60580200, b)





