# Notes for agents

**Porting Caduceus to another body, or patching the firmware?** Start with [`docs/FIRMWARE_GUIDE.md`](docs/FIRMWARE_GUIDE.md): how the E-P7 1.1 firmware is built, how to patch it safely, the lessons behind each safety rule, and a porting checklist.

## Ports: keep to the shared formats

**This matters more than any single feature.** Every port should read and write the same look format, the
same share codes (`pk1_` / look links) and the same card-file field meanings as this repo, so one look works on
every body and users never have to choose between ecosystems. If a port drifts into its own look fields, codes or
panel, looks stop moving between cameras and the work splits in two.

- **Don't invent a parallel format.** Need a new look field? Propose it here first (an issue or PR) so it lands in
  the shared format, with a default that older firmware and panels ignore safely.
- **Don't fork the Control Panel.** Add your camera as a profile and an export target in this repo's panel
  (below). **Contact the maintainer, @cakelesscoder, to merge your Control Panel export**: open an issue or PR
  and it will be reviewed and hosted here, with credit in `NOTICE`.
- **Keep field meanings identical.** A value means the same thing on every body; translate only in the export
  target, for what a body can't do.
- **Firmware stays in your own repo** (install guide, releases, bug reports). Only the look format, share codes
  and panel are shared.

## One Control Panel for every camera

The goal is **one Control Panel, one look format and one set of share codes**, hosted from this repo, with each camera as a selectable profile. Separate per-camera panels are meant to retire into this one. For the OM-3, that means `androidfanman/caduceus-om3`'s panel, once this has been agreed with its author.

Build panel work so it ends up here:

- **Add a camera, don't fork the panel.** A camera is one entry in `webapp/src/cameras.ts` (what the editor offers) and one export target in `webapp/src/targets/` (translation to its card files), listed in `targets/index.ts`.
- **Keep the pack format shared.** Camera differences belong in the profile and the export translation, not in a new look format or share code. Keep a wider value in the look until the user moves that control.
- **Keep other repos' code easy to resync.** Files copied from a port stay unchanged with a source line (`webapp/src/om3.ts`, `om3names.ts`), glue goes in `targets/`, and credit goes in `NOTICE`.
- **Firmware stays with its port.** Each port keeps its own repo, install guide and bug reports. The panel's About dialog and `docs/BODIES.md` point people to the right one.

Findings from the OM-3 port, including what's unverified, are in `docs/OM3_NOTES.md`. Don't add its features to the E-P7 until they can be tested here.

## Test in the emulator before every camera build

**Every firmware change must be run in the emulator before a build goes to the camera.** Static reading and "the
tables look right" have repeatedly produced builds that failed on the camera (E-M1 II aspect v0.4c4–c7: icons and AF
cursor). The owner's camera time is the scarce resource; the emulator is not.

- Emulator: `external/oly_fw_analysis` (fishcu, pinned; `penf_emulator` `Region`/`execute`), set up per WORKLOG
  2026-11-11. Working harnesses: `tools/omdem1mk2_emu_validator.py`, `tools/omdem1mk2_emu_rules.py` (fixtures for
  `.bss`, `.data`, CPU id, task table, boot-ROM memcpy/memset, IPC stub).
- Run the **patched** image (`release edits.json`) and stock side by side through the code path the change targets,
  and show the result differs the intended way (return values, memory written, the branch taken, the pointer read).
- Load every component the path reads, including the OSD (0x101) at its runtime addresses, so OSD edits are exercised too.
- If a path can't be emulated yet, extend the fixtures until it can. Say plainly in the release notes which parts were
  emulated and which were not. Don't hand over a build that rests on static reading alone without saying so.
- Diagnostics belong in the emulator first; a camera diagnostic build is the last resort, not the default.
