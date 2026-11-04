# Lessons

Things that cost time to find out. Add to this whenever something surprises you.

## Object Manager

- **OM deletes its workspace folder when the project is closed.** Import (`grenton omp import-workspace`) while the project is open.
- When OM saves, it renumbers all XStream ids. Don't text-merge an OM save with your own edits: import OM's version, then replay your edits with `grenton omp`.
- OM decides what to send from the `<isDirty>` flags. `grenton omp` sets them; if OM still says "configuration up-to-date", answer Yes to resend everything.
- Script text lives in `scripts/<CLU>/<name>.lua`. The base64 copy in `system-gm.json` alone opens as an empty script.
- To verify a send, diff the newest `project/diagnostics/<CLU>/om.lua/*_W_om.lua` against the previous one. It is exactly what OM uploaded.

## myGrenton

- **Widgets must use the CLU's `nameOnCLU`,** not its display name. `inventory.md` flags renamed CLUs. Using the wrong one gives a red ! and "Validation failed for cluId" in OM's log.
- Opening a generated `.omp` while OM still has the old one open shows stale errors. Close without saving, then File → Open.

## Home Assistant

- The Grenton integration stores the interface when it is added. After an interface change: OM → send to phone (PIN) → delete the integration entry → add it again → `grenton ha sync --apply`. Names come back because unique ids (dtoIds) are stable.
- HA puts the device name in front of the entity name; `ha sync` sets both to avoid "Kitchen Kitchen".
- Thermostats: the integration has no THERMOSTAT_V2. The values page gives a temperature sensor and a setpoint number per thermostat.
