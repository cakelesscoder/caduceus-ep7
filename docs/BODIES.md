# Which other Olympus bodies could run Caduceus?

Status: the **PEN E-P7** is tested here. Other people have ported Caduceus, or built mods in the same family, for
other bodies; each one lives in its owner's repo, with its own install guide, releases and bug reports. **Never flash an
E-P7 build on any other body.** Use the port made for your camera, and report problems there. This page is a map of
what we know, updated as we learn more (last checked 2026-11-16).

## Ports and family projects

**Port owners:** please add your camera to the one shared Control Panel rather than building your own look editor or
code format, so looks and share codes work on every body. See [`CONTROL_PANEL.md`](CONTROL_PANEL.md).

| Body | Project | Owner | Where it stands |
|---|---|---|---|
| **OM-3** | [Caduceus for OM-3](https://github.com/androidfanman/caduceus-om3) | androidfanman | **Released and camera-tested.** Films, HSL on COLOR 1-4, grain, halation and more. Control Panel export supported (`docs/OM3_NOTES.md`) |
| **E-M10 Mark I** | [om10mi-mods](https://github.com/Meghnus/om10mi-mods) | Meghnus | **Released, tested by its owner.** Film looks with their own colour, a 12-sector colour editor and a 60-minute video limit. Its own builder; uses Caduceus as a design reference |
| **E-M1 Mark II** | [emudojo/caduceus](https://github.com/emudojo/caduceus/tree/omdem12-implement-colors-more) (branch `omdem12-implement-colors-more`) | emudojo | **In progress, first camera runs.** Looks from the card, focus stacking on every lens, longer video, 65:24 and 21:9. No public release yet |
| **OM-5** | [tadejs/caduceus-om5](https://github.com/tadejs/caduceus-om5/tree/om5-port) (branch `om5-port`) | tadejs | **Paused.** The first five safety steps passed on a camera; no features yet. Notes: [przestaw/OM-5-firmware-patches](https://github.com/przestaw/OM-5-firmware-patches) (research only) |
| **E-PL9** | [epl9-lab](https://github.com/RemeraLl1/epl9-lab) | RemeraLl1 | **Research build, not camera-tested.** Film looks in place of the Watercolor Art Filters |
| **E-PL9** | [JuiceLee999/caduceus-epl9](https://github.com/JuiceLee999/caduceus-epl9) | JuiceLee999 | **Stalled.** A look patch is built, but the camera's updater refuses the file |
| **E-M5 Mark III** | [olympus-firmware-notes](https://github.com/nsud-dev/olympus-firmware-notes) | nsud-dev | **Research only.** Firmware notes and tools; test builds not yet run. The owner has offered to help with a port ([issue #45](https://github.com/cakelesscoder/caduceus-ep7/issues/45)) |
| **PEN-F** | [oly_fw_analysis](https://github.com/fishcu/oly_fw_analysis) | fishcu | **Alpha releases.** The PEN-F HSL mod that inspired Caduceus, plus shared firmware research and tools |

Related, not Caduceus ports: [EPM2Mod](https://github.com/cfu288/EPM2Mod) by cfu288 (PEN E-PM2: film looks in the Art
Filters, interval shooting, level gauge, focus peaking; tested on the camera by its owner) and
[em10_1](https://github.com/matozoid/em10_1) by matozoid (E-M10 Mark I firmware and Wi-Fi research).

We haven't tested any of these on our camera and can't vouch for them. Read each project's own safety notes first.

## Where each body stands here

| Body | Closeness to the E-P7 | Home for looks | Status |
|---|---|---|---|
| **E-M10 IV** | Closest: same file size and load address, 47% of edits match by signature | No COLOR profiles, so looks need a new home | **Our first target.** In development, not yet run on a camera. **Needs a volunteer to test and report issues:** [issue #21](https://github.com/cakelesscoder/caduceus-ep7/issues/21) (`docs/PORT_EM10IV.md`) |
| **E-M5 III** | 36% match; SD loader and log hook don't match | None | Second choice (`docs/PORT_EM5III.md`); see nsud-dev's notes above |
| **E-M1 III** | Larger file and different load address; match not worked out | None | Firmware analysed on disk only |
| **E-M1 II** | Not run here | Color Creator | Port by emudojo (above) |
| **E-M10 III, E-PL9** | Same main size; match not run | E-PL9: COLOR engine present, per JuiceLee999's fork | E-PL9 ports above; E-M10 III not analysed |
| **PEN-F** | Older generation | **Yes, it has COLOR profiles** | Served by fishcu's PEN-F HSL mod |
| **OM-3** | Same kind of firmware; 26% of edits match | **Yes, it has COLOR profiles** | Working port by androidfanman (above) |
| **OM-1, OM-1 II, OM-5** | Same kind of firmware; 22-28% of edits match across the OM series | Partial profile settings, no profile screens | Quick check only; OM-5 port paused (above) |
| **E-M10 II** | Closer to PEN-F by layout | Has Color Creator, but predates COLOR profiles | Research only |

"Match" is a static check (`tools/port_sigmatch.py`): how many E-P7 edits can be found in another body's firmware by their surrounding bytes. A match says the code looks alike. It does not say the edit is correct or safe on that body.

## How a new body gets tested

Nothing goes to another camera until each step has passed on that body, in this order, with an owner who has read the risks:

1. The official OM firmware file through the camera's own updater.
2. A stock restore round trip.
3. A small harmless text change on the firmware screen, plus restoring stock.
4. A small data edit.
5. A hook that does nothing, then real features one at a time.

**The honest risk:** the camera's SD updater recovered the E-P7 from a boot loop once (battery out, then OK + power, then a stock restore). That is proven only on the E-P7, and only once. A fault early enough in boot might stop the updater from starting on any body, so a failed flash could mean a repair.

## One Control Panel for every camera

Looks stay in one format, made and shared through the same [Control Panel](https://cakelesscoder.github.io/caduceus-ep7/) and share codes. Differences between cameras are handled by a translation step on export, so a look made for one camera can be exported for another, including non-Olympus ones (such as Canon Picture Styles, `docs/PORT_CANON_1100D.md`).

Today the panel exports for the E-P7 and the OM-3. **Port owners:** to add your camera, open an issue or PR here with a camera profile and an export target (`AGENTS.md`), rather than a separate panel or look format.

## Credit

This project exists because of [u/fischgurke](https://www.reddit.com/user/fischgurke/) and their PEN-F HSL firmware mod, which showed an Olympus body could get in-camera HSL editing.

**Ports:** each port owns its firmware, but builds on Caduceus's research, tools and formats. Ports are asked to keep
our `NOTICE` and to say "Based on Caduceus for the Olympus PEN E-P7 by cakelesscoder" in their README and About text
([`AGENTS.md`](../AGENTS.md)).
