# New atlas entries from docs/PLUGINS.md §7 (Shortcut-button cycle study, E-P7 1.1 stock main). Not merged.
# Same structure as atlas_data.py: E(addr, name, kind, subsystem, conf, sig, notes, source).
# Merge by exec'ing after atlas_data.py (E and S come from there).
p = 'ui'
SRC = 'docs/PLUGINS.md §7'

# ---- CA_MAIN key path (where the Fn press is handled in shooting) ----
E(0x60f3928c, 'ca_key_events', 'table', p, 'V', '142 x 20 B {u32 ca event, u32 keycode, u32 sub (0 press, 1 release, 2/3), u32 mask, u32 send-key id}', 'Read by 0x60cc9790 (event -> keycode). Fn (keycode 15): 0x0100002e press / 0x0100002f release, send-key 0x57 / 0x58', SRC)
E(0x6113e938, 'gui_sendkey_map', 'table', p, 'V', '{u32 send-key id, u32 GUI event}', 'Send-key id n -> GUI event 0x90nn for the Fn range (0x57 -> 0x9057, 0x58 -> 0x9058); 0x7fff = none. Read by 0x60dd4ba9', SRC)
E(0x60dd4ba9, 'gui_key_sink', 'func', p, 'V', 'vtbl[0] of the object at (0x61fc18c0); vtable 0x611401c4', 'CA -> GUI key forwarder: send-key id -> GUI event, post. Registered in CA at 0x60cc7352 (0x60cfccc8: sub-object +32)', SRC)
E(0x60cf5b2c, 'ca_dispatch', 'func', p, 'V', 'a0 CA module, a1 event record, d0 event code', 'Prefilter 0x60cf6473, then sub-state table, state table (0x60cf6824: state id -> image list), default table 0x60f6ad58 (124). Records {u32 event, 1, 1, fn}, matched by 0x60cf304c, fn by `calls`. All tables are in the loaded image', SRC)
E(0x60cf6824, 'ca_state_table', 'func', p, 'V', 'd0 state id (0x50xx..0x5exx) -> table, count', 'Jump table 0x60f6b9fc by id>>8; per-group lists {u32 id, u32 table, u32 n} in the image (group 0x51 at 0x60f59668)', SRC)
E(0x60ce0108, 'ca_key_generic', 'func', p, 'V', 'calls entry; call entry 0x60ce010d', 'Generic key handler (Fn press/release in most shooting states): btn_dispatch, then action class 0x60cc87ac: 2 -> 0x60ce026a, 1 -> 0x60ceb5b6, 0 -> nothing', SRC)
E(0x60cc87ac, 'action_class', 'func', p, 'V', 'd0 action -> class', 'Table 0x60f384f8 (92 x {action, class, name}). Class 0 includes 75 LV_CTRL and 76 LV_CTRL_PROFILE', SRC)
E(0x60ccf9f3, 'ca_get_setting', 'func', p, 'V', 'd0 sid -> value (3200 on failure)', 'getSetting through interface 0x607f9062 (vtbl +8, a1 = &out). btn_dispatch reads sid 47 here', SRC)
E(0x60cd4830, 'start_profile_select', 'func', p, 'V', 'call entry, frame [d2,d3,a2,a3],92; d0 out, a0/a1 handler context', "SubAppMdlShootingCmn::startProfileSelect: CANEXEC(76) 0x60cce3dc, then CA state 0x5704 / request 183. Only caller 0x60cd2fff (startMoveToShootingReady, START_PROFILE_NEXT_PROC). The only 76 immediate in CA code 0x60cc0000-0x60d00000", SRC)

# ---- GUI HSM (the one clean data redirect found) ----
E(0x60d115c2, 'hsm_desc', 'func', p, 'V', 'a0 ctx -> a0 descriptor', 'descriptor = (*(u32 **)(ctx + 4))[ss - 1]. The ss table pointer is read only through ctx+4 (0x611317c4 has one reference, the init at 0x60dd4b21)', SRC)
E(0x60e4ba62, 'sscommon_fn_noop', 'func', p, 'V', 'clr d0; retf', 'SsCommon state 8 (StCaReqDisp, shooting) handler for 0x9057, handler word 57 of the ss-1 descriptor 0x611992c4, used by no other (event, state)', SRC)
