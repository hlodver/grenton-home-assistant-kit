# {name}: Grenton site repo

This repo describes one Grenton house for [grenton-home-assistant-kit](https://github.com/hlodver/grenton-home-assistant-kit).

- `site.yaml`: rooms, lights, names, thermostats and Home Assistant settings
- `project/`: the Object Manager project, unpacked, so every change is a git diff
- `inventory.md`: what `grenton discover` found in the project
- `secrets/`: project key and HA token (gitignored, never commit)
- `docs/STATUS.md`: where things stand; `docs/LOG.md`: history; `docs/LESSONS.md`: lessons learned

## Workflow

    grenton mygrenton build                       # after editing site.yaml
    git add -A && git commit -m "..."
    grenton omp pack --out out/{slug}_$(git rev-parse --short HEAD).omp

Open the `.omp` in Object Manager and send it to the CLUs. Then, with the project still open in OM:

    grenton omp import-workspace
    git add -A project && git commit -m "OM: sent ..."

Home Assistant, after the interface is in it:

    grenton ha sync            # dry run
    grenton ha sync --apply

With Claude Code, run `/onboard` to be guided through the setup.
