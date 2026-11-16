<!-- Adding or updating a camera in the Control Panel? Read docs/CONTROL_PANEL.md first. -->

**Control Panel / port checklist** (delete if not relevant)

- [ ] Only `webapp/src/cameras.ts`, `webapp/src/targets/<cam>.ts`, `targets/index.ts`, vendored `webapp/src/<cam>.ts` (unchanged, source line), tests, `NOTICE`, `docs/BODIES.md`
- [ ] No firmware, patches or build tools for another body (those stay in the port's repo)
- [ ] No new look field or share-code change without an agreed issue (see "New features that need new look fields" in docs/CONTROL_PANEL.md)
- [ ] Clamped / left-out values are reported to the user on export
- [ ] `cd webapp && npm test && npm run build` pass
