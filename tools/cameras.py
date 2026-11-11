"""Camera definitions and registry for the Caduceus firmware mod framework.

Supports multiple Olympus / OM System bodies (E-P7, OM-D E-M1 Mark II, E-M10 Mark IV, etc.).
Standard library only.
"""
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Camera:
    id: str                         # Short canonical identifier, e.g. 'ep7', 'em1mk2'
    name: str                       # Human-readable name
    model_id: str                   # 4-character hex string, e.g. '1420', '1250'
    model_code: int                 # Numeric model code, e.g. 0x1420, 0x1250
    version: str                    # Human version string, e.g. '1.1', '3.70'
    version_code: int               # Hex version code, e.g. 0x1100, 0x3700
    main_base: int                  # CPU base address for main component (0x100)
    card_name: str                  # Update payload name on SD card, e.g. 'E1429999.BIN'
    mod_dir: str                    # Mod settings folder on SD card, e.g. 'EP7MOD', 'EM1MOD'
    stock_name: str                 # Official stock firmware file name from OM catalog
    stock_sha: str                  # SHA-256 of the official stock firmware file
    stock_size: int                 # Byte size of the stock firmware file
    catalog_hard_code: str          # Hardware info code used in OM catalog requests
    catalog_firmware_version: str   # Firmware version used in OM catalog requests
    alt_stock_names: Tuple[str, ...] = ()

    @property
    def update_path(self) -> str:
        """SD card path for the update payload."""
        return f"DCOLYMP/{self.card_name}"

    @property
    def restore_path(self) -> str:
        """Restore file path relative to output directory."""
        return f"restore/{self.card_name}"


# Master Camera Registry
CAMERAS: Dict[str, Camera] = {
    'ep7': Camera(
        id='ep7',
        name='Olympus PEN E-P7',
        model_id='1420',
        model_code=0x1420,
        version='1.1',
        version_code=0x1100,
        main_base=0x60020020,
        card_name='E1429999.BIN',
        mod_dir='EP7MOD',
        stock_name='OLY_E_142_1100_0000_0000.BIN',
        stock_sha='9d1610124ad98f6edae4540182205f06c9c703d9033ef0c4f19847193f95eaeb',
        stock_size=111017984,
        catalog_hard_code='OLYE142000000000',
        catalog_firmware_version='00001000',
        alt_stock_names=('E1429999.BIN',),
    ),
    'em1mk2': Camera(
        id='em1mk2',
        name='Olympus OM-D E-M1 Mark II',
        model_id='1250',
        model_code=0x1250,
        version='3.70',
        version_code=0x3700,
        main_base=0x60021020,
        card_name='E1259999.BIN',
        mod_dir='EM1MOD',
        stock_name='OLY_E_125_3700_0000_0000.BIN',
        stock_sha='f0c25dd80e3fe2f38af0bc515f250692c47c42758eef411dfaef1f9674dd66dc',
        stock_size=93050944,
        catalog_hard_code='OLYE125000000000',
        catalog_firmware_version='00003000',
        alt_stock_names=('E1259999.BIN',),
    ),
    'em10iv': Camera(
        id='em10iv',
        name='Olympus OM-D E-M10 Mark IV',
        model_id='1400',
        model_code=0x1400,
        version='1.1',
        version_code=0x1100,
        main_base=0x60020020,
        card_name='E1409999.BIN',
        mod_dir='EM10MOD',
        stock_name='OLY_E_140_1100_0000_0000.BIN',
        stock_sha='4f9ea315a6b7d2db3cb8c11e74f88e404bfda3b76921bc1e3cb6441bf97e9aac',
        stock_size=111017984,
        catalog_hard_code='OLYE140000000000',
        catalog_firmware_version='00001000',
        alt_stock_names=('E1409999.BIN',),
    ),
}

DEFAULT_CAMERA_ID = 'ep7'


def get_camera(cam_id: Optional[str] = None) -> Camera:
    """Retrieve camera definition by ID, defaulting to ep7."""
    key = (cam_id or DEFAULT_CAMERA_ID).lower().strip()
    # Handle common aliases
    aliases = {
        'e-p7': 'ep7',
        'e-m1mk2': 'em1mk2',
        'em1-mk2': 'em1mk2',
        'em1ii': 'em1mk2',
        'e-m1ii': 'em1mk2',
        'em1mark2': 'em1mk2',
        'e-m10iv': 'em10iv',
        'em10-iv': 'em10iv',
    }
    key = aliases.get(key, key)
    if key not in CAMERAS:
        valid = ', '.join(CAMERAS.keys())
        raise ValueError(f"Unknown camera: {cam_id!r}. Supported cameras: {valid}")
    return CAMERAS[key]


def detect_camera_from_stock(stock_bytes: bytes) -> Optional[Camera]:
    """Detect camera profile by stock firmware SHA-256."""
    h = hashlib.sha256(stock_bytes).hexdigest()
    for cam in CAMERAS.values():
        if h == cam.stock_sha:
            return cam
    return None


def detect_camera_from_model(model_bytes: bytes) -> Optional[Camera]:
    """Detect camera profile from 2-byte model header in OE container (e.g. b'\\x12\\x50')."""
    if len(model_bytes) >= 2:
        code = int.from_bytes(model_bytes[:2], 'little')
        for cam in CAMERAS.values():
            if cam.model_code == code:
                return cam
    return None
