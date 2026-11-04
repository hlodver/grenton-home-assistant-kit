# Home Assistant

The runtime link between Home Assistant and Grenton is the community integration
[sszczep/homeassistant-grenton](https://github.com/sszczep/homeassistant-grenton),
installed through HACS. This kit doesn't replace it. The kit gives it a good interface to
import, then tidies up what it creates.

## How the integration works

- When it is added, it fetches the myGrenton interface from Object Manager's "send to
  phone" server: Object Manager's IP, port 9998, and the PIN Object Manager shows.
  After that it talks to the CLUs directly.
- **It stores the interface at setup and can't reload it.** After an interface change:
  1. In Object Manager, send the interface to the phone (it shows a PIN).
  2. In HA, delete the Grenton entry, using the ⋮ in the entry's row.
  3. Add the integration again.
  4. Run `grenton ha sync --apply`.

  Deleting the entry also deletes names and areas, and the sync restores them because the
  unique ids are stable dtoIds.
- Supported widgets include `DIMMER_V2`, `ON_OFF`, `VALUE_V2`, `SLIDER`, `LED`, contact
  sensors and roller shutters. **`THERMOSTAT_V2` is not supported**, which is why the build
  adds a `VALUE_V2` (temperature) and a `SLIDER` (setpoint) for each thermostat.
- Entity names start as the widget labels, so `site.yaml` labels are what `ha sync`
  matches on.

## What `grenton ha sync` does

It's a dry run unless you pass `--apply`, and safe to run again: a second run should plan
nothing.

1. **Areas** from `site.yaml`. It removes the ones listed under `remove_areas`, such as the
   areas HA's onboarding creates.
2. **Lights:** device and entity name, area, and entity id. HA shows the device name in
   front of the entity name ("Kitchen Kitchen"), so both are set to the full name.
3. **On/off loads:** the integration creates a `switch`. The sync wraps it as a `light`
   with the switch_as_x helper, which hides the switch. switch_as_x copies the hidden
   switch's name onto the light, so the switch gets the light's name as well.
4. **Light groups** with the group helper.
5. **Thermostat units:** the integration takes unit and device class from its own options
   (per entity, stored by unique id), not from the widget. The sync sets °C / temperature,
   and the setpoint number gets the box mode.
6. **Dashboard:** a lights view with one section per area (brightness sliders for dimmers)
   and a heating view with temperatures, setpoints and a 24-hour graph. It is only written
   when it differs from what HA has.

## Practical notes

- **Token:** create a long-lived token in HA (profile → Security). Put `HA_TOKEN=...` in
  `secrets/ha.env` (mode 600), or set `homeassistant.token_command` to read it from a
  password manager. The command runs at most once per `grenton` call.
- **URL:** any form works: `http://host:8123`, `https://...`, or a bare host on port 80.
- A dashboard `url_path` must contain a hyphen.
- **Unknown lights:** `grenton ha blink <light>` flashes a light three times and then
  restores it, so someone on site can say which one it is.
