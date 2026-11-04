# grenton-home-assistant-kit

Keep a [Grenton](https://www.grenton.com) Object Manager project in git. Generate the
myGrenton interface from one file. Use it to set up Home Assistant with sensible rooms,
names and entity ids.

> Status: early. Extracted from a working house setup (Object Manager 1.x, CLU Z-Wave and
> FM, Home Assistant 2026.10 with the
> [Grenton integration](https://github.com/sszczep/homeassistant-grenton)). Expect rough edges.

## Idea

One house is one **site folder**:

```
my-house/
  site.yaml        rooms, lights, thermostats, names: what only you know
  project/         the Object Manager project, unpacked (git diffs instead of a zip)
  secrets/         project key and HA token (gitignored)
```

The `grenton` command reads the project for what it already contains: CLUs, modules and
object types. It reads `site.yaml` for the rest.

- `grenton omp unpack|pack|import-workspace`: move the project between Object Manager
  and git. Packing gives back a byte-identical `.omp` when nothing changed. The
  project key is replaced with a placeholder in git and only restored in the `.omp`.
- `grenton omp add-event-command|set-feature|add-script ...`: small, reviewable edits.
- `grenton mygrenton build`: writes the myGrenton interface (pages, dimmers, on/off,
  thermostats, temperature values, setpoint sliders) into the project. Open it in OM and
  send.
- `grenton ha sync [--apply]`: after the HA Grenton integration has imported the interface,
  it sets areas, device and entity names, and entity ids. It also wraps on/off loads as
  lights, creates light groups, sets thermostat units, and writes a dashboard. It's a dry
  run unless you pass `--apply`.

See [`examples/site.example.yaml`](examples/site.example.yaml) for every key.

## Install

```sh
uv tool install git+https://github.com/hlodver/grenton-home-assistant-kit   # or: uv run --project <clone> grenton ...
```

## License

MIT. Not affiliated with Grenton.
