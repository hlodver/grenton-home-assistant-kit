# myGrenton interfaces in the project

Observed with Object Manager 1.13.1 and checked against interfaces built in Object
Manager's editor. This is what `grenton mygrenton build` writes.

## Where an interface lives

Each interface is stored in two places:

1. **`system.xml`**: a tree node of type `MYGRENTON_INTERFACE` under the folder node
   `myGrenton` (type `MYGRENTON_INTERFACES`). The node has a numeric `<id>` and a
   `specificObject` of class `com.grenton.om.mobile.gui.MobileInterfaceTreeObject`.
2. **`nodes/<id>/data.json`**: the content, under the same `<id>`. The build also adds the
   new entries to the `.omp` manifest so `pack` includes them.

`data.json`:

```json
{ "pages": [ { "icon": "kitchen", "id": 1793740100008, "label": "Kitchen",
               "widgets": [ ... ], "pageId": 1793740100008 } ],
  "pushNotifications": null, "lightLogoPath": null, "icon": "home_1", "blockCloud": false,
  "theme": "blue", "id": "<uuid>", "label": "My House", "cloudSharing": null, "darkLogoPath": null }
```

Page and widget ids are numbers that are unique within the interface. The build counts
them up from `mygrenton.first_widget_id`.

## Bindings

Every widget binds to CLU objects through small records:

```json
{ "cluId": "CLU555555", "objectName": "DIM0001", "index": "0", "callType": "ATTRIBUTE" }
```

An action adds `type` (`CLICK`, `ON`, `OFF`), `value` and `valueFormattedForDto`.
`$value$` stands for the value chosen in the app. `callType` is `ATTRIBUTE` (read a
feature), `PSEUDO_METHOD` (set a feature) or `METHOD` (call a method by index).

**`cluId` must be the CLU's `nameOnCLU`**, not the name shown in Object Manager's tree, and
`objectName` is the object's `nameOnCLU` (`DIM0001`, `THE0001`), not its project name. On a
CLU that was replaced or renamed, the two names differ. Object Manager then marks the
widget with a red ! and logs "Validation failed for cluId". `grenton discover` flags
renamed CLUs.

## Widgets the build writes

| Object | Widget | Bindings |
|---|---|---|
| Dimmer (`DIMM`) | `DIMMER_V2`, 0–1, precision 2 | value: attr 0; set: pseudo-method 0 `$value$`; on/off: pseudo-method 0 `1`/`0` |
| DALI gear (`DALI_GEAR`) | `DIMMER_V2`, 0–254, precision 0 | value: attr 2; set: method 1 `"$value$, 0"`; on: method 3; off: method 4 |
| Relay (`DOUT`), or a dimmer with `onoff: true` | `ON_OFF` with a bistable button | state: attr 0; on/off: pseudo-method 0 `1`/`0` |
| Thermostat | `THERMOSTAT_V2` | see below |
| Thermostat | `VALUE_V2`, °C, float | attr 14 (current temperature) |
| Thermostat | `SLIDER`, °C | value and set: attr / pseudo-method 3 (setpoint) |

Thermostat attribute indices used by `THERMOSTAT_V2`:

| Index | Meaning |
|---|---|
| 3 | setpoint (PointValue) |
| 6 | state (running or stopped) |
| 8 | mode |
| 9 | schedule |
| 10 / 11 | minimum / maximum temperature |
| 12 | target temperature |
| 13 | control output |
| 14 | current temperature |

The `THERMOSTAT_V2` widget the build writes is identical to one made in Object
Manager's editor, apart from its ids.

## dtoId

Every widget has an 8-character `dtoId`. Object Manager picks one at random. The build
derives it from the object name (a hash of `onoff:<obj>`, `temp:<obj>` and so on), so
regenerating an interface keeps every dtoId. This matters for Home Assistant, which uses
the dtoId as the entity's unique id. To keep widgets made in Object Manager, including
their ids and dtoIds, point `mygrenton.adopt` at that interface's `data.json`.
