# Workflow

One house is one site repo. Object Manager stays the tool that talks to the CLUs; the kit
prepares and checks what Object Manager sends.

## A new house

```sh
grenton init my-house --omp "My House.omp"
cd my-house
claude          # then /onboard, or edit site.yaml yourself
```

Use a **current** project: the one that's on the CLUs. Sending an older project back
undoes everything done since. If in doubt, open the project in Object Manager and save
it now.

## Every change

```
edit site.yaml (or run a grenton omp edit)
  → grenton mygrenton build                  # only after a site.yaml change
  → git commit
  → grenton omp pack --out out/<name>_<commit>.omp
  → Object Manager: close the project without saving, File → Open the new .omp, send to the CLUs
  → grenton omp import-workspace             # while the project is still open
  → check the newest project/diagnostics/<CLU>/om.lua/*_W_om.lua diff, then git commit
```

- **Commit before packing.** Then every `.omp` corresponds to a commit, and going back is a
  `git checkout`.
- **Import after every send,** and after any change made directly in Object Manager. The
  import records what Object Manager actually did.
- **Verify with the om.lua diff.** An interface-only change leaves the CLU logic untouched.
  Any other difference in the diff deserves a look.
- When something works, tag it: `git tag good-YYYY-MM-DD`.

## Home Assistant after an interface change

```
Object Manager: send the interface to the phone (PIN)
  → HA: delete the Grenton entry, add it again (Object Manager IP, port 9998, PIN)
  → grenton ha sync            # read the plan
  → grenton ha sync --apply    # and again: it should plan nothing
```

## House logic

Button bindings, scripts and heating logic are specific to each house, so they live in
the site repo as small Python scripts. They use the library:

```python
from grenton_kit import omp
omp.add_event_command("project", "x250000001_PANEL_BUTTON_01", "OnClick", "CLU123456789->my_script(1)")
omp.add_script("project", "CLU123456789", "my_script", source, [("level", "NUMBER", "1")])
```

Write them so they can be re-run: clear what they set, then set it again. After an
import, re-run them and check `git diff`. An import of an older Object Manager state
shows up there.
