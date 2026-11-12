data = open("em1mk2/extracted/00_0100_40560020.decoded.bin", "rb").read()
base = 0x60021020

rear_off = 0x60ec7353 - base
front_off = 0x60ec7387 - base

print(f"Rear dial (0x60ec7353) stock bytes: {data[rear_off:rear_off+10].hex()}")
print(f"Front dial (0x60ec7387) stock bytes: {data[front_off:front_off+10].hex()}")
