# Grenton site repo

This repo is one Grenton house. The tools come from grenton-home-assistant-kit: the `grenton` command.

**Read `docs/STATUS.md` first.** If its Onboarding checklist is not done, continue it with the `/onboard` skill.

## Rules

- **Only the owner sends to the CLUs,** from Object Manager. Never claim something works on the CLUs until the owner has sent it and it has been verified.
- **Commit before every pack, and import after every send** (`grenton omp import-workspace` while OM has the project open). Git is the undo button.
- Never pack from an old project. Import the live workspace first, so you start from what OM has.
- Secrets stay in `secrets/` (gitignored). Never print the project key or HA token, and never commit an `.omp`.
- `site.yaml` is the source of truth for names, rooms and pages. Change it, then run `grenton mygrenton build`; don't edit `project/nodes/*/data.json` by hand.
- Ask before anything you can't undo: deleting HA config, a blink test (someone must be on site), `ha sync --apply` the first time.
- Keep `docs/STATUS.md`, `docs/LOG.md` and `docs/LESSONS.md` current, every session.
