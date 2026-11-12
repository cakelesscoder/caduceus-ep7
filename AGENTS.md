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
- **Credit Caduceus as your groundwork.** A port owns its firmware, but builds on this repo's research, tools and formats. Keep our `NOTICE` (Apache-2.0 requires it when you reuse our code or docs). Also say near the top of your README and in your About text: "Based on Caduceus for the Olympus PEN E-P7 by cakelesscoder (github.com/cakelesscoder/caduceus-ep7)".
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
