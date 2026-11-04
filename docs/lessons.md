# Lessons

These were learned the hard way on a real installation (Object Manager 1.13.1, two CLUs,
touch panels, floor heating). Each one cost time once.

## Object Manager

- **Object Manager deletes its workspace when the project closes.** Import while it's open.
- **Object Manager renumbers all XStream ids on save.** Re-apply edits with the tools;
  never merge text.
- **Sending is decided by `isDirty` flags.** Without them, Object Manager says
  "up-to-date". Answer Yes to resend everything.
- **An open project shows stale errors.** Before opening a newly packed `.omp`, close the
  current project without saving, then use File → Open.
- **Every send restarts the CLU** and runs `OnInit`. State that's only held at runtime,
  such as a thermostat's start/stop and mode, has to be set again in `OnInit`.
- **Changing a script parameter's "value to run" uploads the configuration,** which
  restarts the CLU. "Run script" only runs what is already on the CLU. Use scripts
  without parameters for anything that must not be interrupted.
- **Initial value and live value differ** in Object Manager's property view. The initial
  value is what the CLU gets at boot. To verify behaviour, look at the live value.

## Scripts

- **Never write `->` in a script comment.** Object Manager parses it as an object call and
  rejects the whole configuration ("Invalid command … in the script").
- **Calls to an object on another CLU pass arguments as literal text.**
  `->SetValue(level)` reaches the other CLU as the string `level`, which doesn't exist
  there. Pass literal values, or run the script on the CLU that owns the object.
- **Reading from another CLU works.** Read the value into a local on its own line, then
  convert it: `local v = CLU…->obj->Value` then `v = tonumber(v) or 0`.
- **A dimmer at 100 % doesn't read back as exactly 1.** Compare against ranges.
- ⌘S in a script editor doesn't save the project. Use the project save.

## Panels

- **Screen panels only apply their button configuration when a page is opened.** After a
  send or power-up, buttons on a panel with a single page never start working. Give the
  panel a second page (a copy) and flip pages, for example on hand approach.
- **Bistable panel buttons keep their own on/off state,** which drifts away from the
  light's real state. Prefer momentary buttons that call a script, which reads the light
  and toggles it.
- A page with `PageType 0` is inactive and shows no labels.

## myGrenton and Home Assistant

- Widgets bind to the CLU's **nameOnCLU**, not its display name.
- The HA integration **stores the interface at setup**. Re-add it after every interface
  change; stable dtoIds bring back names and areas.
- HA puts the device name in front of the entity name. Set both.
- switch_as_x copies the hidden switch's name, so name the switch like the light.
- Units for sensors and sliders come from the integration's options, not from the widget.

## Working method

- **Confirm which physical thing an object is before changing it.** A visible change, such
  as a label or a blink, settles it. Object names in old projects are often wrong.
- **Ask what a workaround is for before removing it.** A "useless" second panel page may be
  what makes the buttons work.
- **Revert by commit hash,** never `HEAD~1`.
- **Keep three documents current in the site repo:** STATUS (where things are), LOG (what
  happened) and LESSONS. Read STATUS first in every session.
