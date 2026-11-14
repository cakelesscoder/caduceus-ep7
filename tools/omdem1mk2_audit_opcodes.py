import json
import os
import re
import subprocess
import sys

FAILS = 0

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

    # Absolute stores into the loaded image (FIRMWARE_GUIDE §10 lesson 2: crashed at the first half-press).
    # Calls into this cave must use the same [regs],frame as the callee's ret (v0.4 debug_log restart).
    insns = []
    for line in res.stdout.splitlines():
        parts = line.strip().split(':\t')
        if len(parts) == 2:
            rest = parts[1].split('\t')
            if len(rest) > 1 and rest[1].strip():
                insns.append((int(parts[0], 16), " ".join(x.strip() for x in rest[1:] if x.strip())))
    end = stop_addr or vma + len(code_bytes)
    store_lines = []
    for a, inst in insns:
        m = re.match(r'mov\w*\s+[ad][0-3],\((0x[0-9a-f]+)\)$', inst)
        if m and 0x60020020 <= int(m.group(1), 16) < 0x61920000:
            store_lines.append((a, inst))
    call_bad = []
    for a, inst in insns:
        m = re.match(r'call\s+(0x[0-9a-f]+),(\[[^\]]*\],\d+)$', inst)
        if not m:
            continue
        tgt = int(m.group(1), 16)
        if not (vma <= tgt < end):
            continue
        ret = next(((ra, ri) for ra, ri in insns if ra >= tgt and re.match(r'ret[f]?\s', ri)), None)
        want = m.group(2)
        got = re.sub(r'^retf?\s+', '', ret[1]) if ret else None
        if got != want:
            call_bad.append((a, inst, ret))

    print(f"[{name}] at {hex(vma)} (len {len(code_bytes)}):")
    print(f"  0xFB opcodes: {len(fb_lines)}")
    for a, h, i in fb_lines:
        print(f"    {a}: {' '.join(h)} -> {i}")
    print(f"  mul/div opcodes: {len(mul_div_lines)}")
    for a, h, i in mul_div_lines:
        print(f"    {a}: {' '.join(h)} -> {i}")
    print(f"  hardware loop opcodes: {len(loop_lines)}")
    print(f"  absolute stores into the loaded image: {len(store_lines)}")
    for a, i in store_lines:
        print(f"    {a:#x}: {i}")
    # `clr aN` assembles to an AM33-2 extended op (f9 6x ..) that the stock code never uses and the emulator rejects
    # (sd_loader 0x605802df, found 2026-11-13; that path had never run on the camera). Use `mov 0,aN`.
    clr_a = [(a, inst) for a, inst in insns if re.match(r'clr\s+a[0-3]$', inst)]
    print(f"  clr aN (extended op): {len(clr_a)}")
    for a, i in clr_a:
        print(f"    {a:#x}: {i}")
    print(f"  internal call/ret frame mismatches: {len(call_bad)}")
    for a, i, r in call_bad:
        print(f"    {a:#x}: {i}  first ret after target: {r[1] if r else 'none'}" + (f" at {r[0]:#x}" if r else ''))
    global FAILS
    FAILS += len(fb_lines) + len(mul_div_lines) + len(loop_lines) + len(store_lines) + len(call_bad) + len(clr_a)

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

# Audit debug_log
d = json.loads(open('patches/omdem1mk2/debug_log/edits.json').read())
cave_edit = [e for e in d['edits'] if e['addr'] == '0x6078e8c0'][0]
b = bytes.fromhex(cave_edit['new'])
data_start_offset = b.find(b"C:\\EM1MOD\\")
stop_addr = 0x6078e8c0 + data_start_offset if data_start_offset != -1 else None
audit_code('debug_log_cave', 0x6078e8c0, b, stop_addr=stop_addr)

# Audit aspect
d = json.loads(open('patches/omdem1mk2/aspect/edits.json').read())
cave_edit = [e for e in d['edits'] if e['addr'] == '0x60257580'][0]
b = bytes.fromhex(cave_edit['new'])
code_start = 8 + 96 + 84
code_len = 122
audit_code('aspect_switch_cases', 0x6025763c, b[code_start:code_start+code_len])

if FAILS:
    print(f'AUDIT FAILED: {FAILS} finding(s)')
    sys.exit(1)
print('AUDIT OK')
