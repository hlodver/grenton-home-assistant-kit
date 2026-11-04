# grenton-home-assistant-kit: development notes

This repo is the generic kit. Houses live in their own site repos (see `docs/workflow.md`).

## Rules

- **No house data here:** no IPs, serial numbers, real object names, PINs, keys or interface
  ids. Tests use the synthetic house in `tests/fixtures/house/`. Before every push, grep the
  history for the data of any house you have been working on.
- **Nothing copied from Object Manager.** Describe formats in our own words, from projects and
  interfaces we made ourselves. Don't include Object Manager's templates or code.
- **Round trips stay byte-identical.** `pack(unpack(x)) == x`. A real site must give the same
  interface and `.omp` before and after a refactor. Check that against a real site repo
  before merging changes to `omp.py` or `mygrenton.py`.
- `uv run pytest` must pass.
- New `site.yaml` keys go into `examples/site.example.yaml`, with their default.
- Facts about Object Manager or the CLUs go into `docs/`, marked with the Object Manager
  version they were observed with.

## Layout

- `src/grenton_kit/omp.py`: the `.omp` format, unpack/pack, safe edits
- `src/grenton_kit/site.py`: `site.yaml` loading and defaults
- `src/grenton_kit/mygrenton.py`: interface generation
- `src/grenton_kit/discover.py`: inventory and draft `site.yaml`
- `src/grenton_kit/init.py` + `templates/`: new site repos, including the `/onboard` skill
- `src/grenton_kit/ha/`: HA client, sync and blink
- `docs/`: formats, workflow, Home Assistant, lessons, roadmap
