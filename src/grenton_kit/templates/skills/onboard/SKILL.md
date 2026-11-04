---
name: onboard
description: Guide the owner through setting up their Grenton house with grenton-home-assistant-kit. Covers importing the Object Manager project, building site.yaml from an interview, identifying unknown outputs, generating the myGrenton interface, and lining up Home Assistant. Resumable from docs/STATUS.md.
---

# Onboarding a Grenton house

You are helping the owner of a Grenton installation. They know their house; you know
the tools. The goal is a `site.yaml` that is right, a myGrenton interface that works,
and Home Assistant set up with good names. Throughout, git records every step and the
owner stays in control of the CLUs.

## Before you start

1. Read `docs/STATUS.md`. The **Onboarding** checklist tells you where to resume; skip
   the steps already ticked, and say so in one line.
2. Check the tools: `grenton --help` must work. If it doesn't, install the kit with
   `uv tool install git+https://github.com/hlodver/grenton-home-assistant-kit`.
3. Talk in the owner's language. Labels and room names go in their language too.

## Principles

- **The owner decides; you propose.** Bring a concrete proposal (a table, a short list)
  and ask them to correct it. Don't ask open questions you could answer from the
  inventory.
- **Ask in batches,** grouped by room or by question type. Never one light at a time.
- **Only the owner sends to the CLUs,** from Object Manager. You prepare `.omp` files; they
  open and send them, then you import and verify.
- **Commit after every step,** with a message that says what changed. Update the
  checklist in `docs/STATUS.md` and add a line to `docs/LOG.md`.
- **Ask before anything that switches something in the house** (a blink test) or that is
  hard to undo (deleting HA config, the first `ha sync --apply`).

## Step 1: import the project

The owner needs an `.omp` from Object Manager. In OM, saving the project or making a backup
writes one; OM's `projects/` folder often already has a recent backup. Ask which file is
current. **A project older than what is on the CLUs must not be sent back.** If unsure,
ask them to open the project in OM and save it now.

If the site repo doesn't exist yet: `grenton init <folder> --omp <file>`. This creates the
repo, extracts the key into `secrets/grenton.env`, unpacks the project, runs discover and
commits. Then continue inside the new folder.

## Step 2: discover

`grenton discover` writes `inventory.md` and, if missing, `site.yaml` (otherwise
`site.draft.yaml`). Read `inventory.md` fully, then give the owner a short summary:
- the CLUs, and whether one is renamed (nameOnCLU differs)
- how many dimmers, DALI lights, relays and thermostats there are
- the panels and scripts
- any existing myGrenton interface

The draft puts each light in a room guessed from the panel that controls it, or from its
object name. Expect it to be rough: the guess often makes one room per object name.

## Step 3: interview

Work through these in order, each as one proposal for the owner to correct:

1. **The house:** its name, and the language for labels. Floors, if the house has
   several. Drawings or a floor plan help (PDF or photo); read them if offered.
2. **Rooms:** merge the guessed rooms into the real ones and propose a list of areas with
   ids (`slugify` style), names and mdi icons. Panel names and object names are your
   clues. Ask about rooms you can't place.
3. **Lights per room:** a table with object, current name, proposed label, and room.
   Propose readable labels in the owner's language: fix transliterations ("Eldhus" →
   "Eldhús"), expand abbreviations, keep letters and numbers that identify a light.
4. **Load type:** which loads can't be dimmed. These are dimmer channels driving
   non-dimmable loads, such as cabinet lights or some LED drivers; they get `onoff: true`.
   Relays (DOUT) are always on/off.
5. **Relays:** for each relay switched by buttons (see the inventory), ask whether it is a
   light. Ignore heating relays.
6. **Not connected:** lights with no name that nothing controls are candidates. Never
   assume; ask. Anything not connected goes under `not_connected` with a note.
7. **Thermostats:** label, HA name, and area. The temperature sensor's panel is a hint.
   One thermostat may be a whole-house one (`area: null`).
8. **Home Assistant names:** usually the label. Shorter names and the entity ids
   (`light.<room>_<name>`) are proposed by you and confirmed by them.

Write `site.yaml`, then run `grenton mygrenton build`. The build fails on any light that is
on no page and not under `not_connected`, which catches anything forgotten. Commit.

## Step 4: unknown outputs (blink test)

For a light nobody can place, the blink test flashes it so someone on site can say which
one it is. It needs Home Assistant (step 6) with the light in it, and **someone on site**.
Ask first ("Can I flash dimmer 320000123 now? Watch the lights."). Then:

    grenton ha blink light.<entity> --times 3

Ask what blinked, then update `site.yaml`. Without HA yet, leave the light on an
"Unknown" page and come back to it after step 6.

## Step 5: interface into Object Manager

    grenton mygrenton build
    git add -A && git commit -m "myGrenton interface from site.yaml"
    grenton omp pack --out out/<name>_$(git rev-parse --short HEAD).omp

The owner opens it in OM. If OM already has the project open, they **close it without
saving** first, then use File → Open. Widgets with a red ! mean a binding error; OM's log
says "Validation failed for cluId", which usually means a wrong nameOnCLU. Then they
send to the CLUs and try the interface in the myGrenton app. Afterwards, with the project
still open:

    grenton omp import-workspace
    git add -A project && git commit -m "OM: interface sent"

Verify the send: the newest `project/diagnostics/<CLU>/om.lua/*_W_om.lua` should differ
from the previous one only where expected. An interface-only change leaves the CLU logic
unchanged.

## Step 6: Home Assistant

1. HACS → custom repository `https://github.com/sszczep/homeassistant-grenton` →
   install, then restart HA. The owner does this.
2. A long-lived token (HA profile → Security). Store it in `secrets/ha.env` as
   `HA_TOKEN=...` with mode 600, or set `homeassistant.token_command` to read it from a
   password manager. Set `homeassistant.url` in `site.yaml`.
3. In OM: send the interface to the phone, which shows a PIN. In HA: add the Grenton
   integration with OM's IP, port 9998 and the PIN.
4. `grenton ha sync` (dry run). Show the owner the plan and summarize it; don't paste it
   all. After their OK: `grenton ha sync --apply`, then run it again; it should plan
   nothing.
5. Ask them to open the dashboard and switch one light and one setpoint from HA.

## Step 7: hand-off

Tag the verified state (`git tag good-YYYY-MM-DD`) and finish `docs/STATUS.md`:
- what runs where
- the open items (unknown outputs, wishes)
- how to continue

Tell the owner how future changes work: edit `site.yaml` → build → pack → send →
import, and for HA → re-add the integration → `ha sync --apply`. This is in the README.
