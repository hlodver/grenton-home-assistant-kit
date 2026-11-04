# Roadmap

There are two kinds of repo. This one is public and holds generic tools and documentation.
Each house has its own private **site repo**: `site.yaml`, the unpacked OM project, the
house's own Lua scripts, and its notes. A site repo uses this package; nothing
house-specific lives here.

## Phase 1: extract the code (done 2026-11-04)

- [x] `grenton_kit` package with the `grenton` CLI (uv)
- [x] `omp`: unpack, pack, import-workspace, event, script and feature edits; the project
      key is kept out of git
- [x] `mygrenton build`: pages, dimmers (DIMM, DALI), on/off (DOUT, or a dimmer with an
      on/off load), THERMOSTAT_V2, temperature values, setpoint sliders, from `site.yaml`
- [x] `ha call` and `ha sync`: areas, names, entity ids, switch_as_x, groups, °C,
      dashboard (written only when it differs)
- [x] Acceptance on the first house:
  - the interface is byte-identical
  - `.omp` packing is byte-identical
  - the HA dry run plans one change, a thermostat order on the dashboard that now
    follows `site.yaml`
- [x] Tests on a synthetic house (`tests/fixtures/house`)

## Phase 2: switch the first site repo over (done 2026-11-04)

- [x] The site repo depends on this package through a uv path dependency (`../grenton-home-assistant-kit`).
- [x] Its copies of the tools are deleted.
- [x] House logic (button bindings, heating scripts) stays in the site repo and imports
      `grenton_kit.omp`. Re-running it leaves the project byte-identical. It may later
      become a config-driven "event commands" feature here.

## Phase 3: onboarding

- `grenton discover`: reads the project and writes `inventory.md`, listing CLUs with
  their nameOnCLU, modules and outputs by type, thermostats, scripts and existing
  interfaces. It also writes a first draft of `site.yaml` with rooms guessed from
  object names.
- `grenton init <folder>`: creates a new site repo with `.gitignore`, `secrets/`, a
  `site.yaml` skeleton and `docs/STATUS.md`, `LOG.md` and `LESSONS.md`.
- `/onboard` skill (`.claude/skills/onboard/`) for an AI-guided session:
  1. Check prerequisites.
  2. Import the project and commit it.
  3. Discover.
  4. Interview: house, floors, optional drawings, rooms, which loads are dimmable or
     on/off, what isn't connected, odd names.
  5. Blink test for unknown outputs, only with the person on site and their
     confirmation before each blink.
  6. Generate; the person sends from OM.
  7. Home Assistant: token, adding the integration, sync.
  8. Hand-off: status docs and a known-good tag.

  Progress is kept in `docs/STATUS.md`, so the session can be resumed.
- Acceptance: onboard the first house from scratch in a temporary folder and compare the
  result with its hand-made `site.yaml`.

## Phase 4: documentation

Everything in English and in our own words; nothing is copied from Object Manager.

- `omp-format.md`: the zip, `system.xml` and `system-gm.json`, the manifest.
- `mygrenton-format.md`: interface storage, widget bindings and indices, nameOnCLU.
- `home-assistant.md`: the integration and its limits, re-import, naming.
- `workflow.md`: OM → git → generate → send → HA.
- `lessons.md`.
- `CLAUDE.md`: rules for an agent working on a Grenton house.

## Phase 5: tests and CI

- More fixtures: event edits, scripts, import-workspace.
- GitHub Actions.

## Phase 6: publish

- Make the repo public and post on the HA community and Grenton forums.
- Separately, contribute THERMOSTAT_V2 support to the HA Grenton integration.

## Known limits

- Tested with one Object Manager version and one house.
- The HA Grenton integration has no reconfigure. After an interface change, delete the
  integration entry and add it again. Entity unique ids are the widget dtoIds, which are
  stable, so names and areas survive.
