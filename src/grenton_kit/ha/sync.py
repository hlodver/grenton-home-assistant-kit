"""Line Home Assistant up with site.yaml: areas, names, entity ids, helpers, units, dashboard.

Works on the entities the Grenton integration (github.com/sszczep/homeassistant-grenton)
created from the myGrenton interface. They are matched by their original name, which is
the widget label. Idempotent; without apply it only prints what it would change.

Steps:
  1. areas from site.yaml (and remove the ones listed under remove_areas)
  2. dimmers: device + entity name, area, entity id
  3. on/off loads: the Grenton switch is wrapped as a light (switch_as_x helper)
  4. light groups
  5. thermostats: temperature sensor + setpoint number, unit °C through the integration's
     options flow (stored by unique id, so renaming is safe)
  6. dashboard with a lights view and a heating view

Naming: HA puts the device name in front of the entity name ("Braut A Braut A"), so both
the device's name_by_user and the entity's name are set to the full name.
"""
from ..mygrenton import project_index
from ..site import slugify
from .client import HA


def split_lights(site):
    """(dimmable lights, on/off lights) in page order, using the module types in the project."""
    idx = project_index(site.project_dir)
    dimmers, onoff = [], []
    for lt in site.lights:
        typ = idx[lt.object][2] if lt.object in idx else None
        (onoff if lt.kind(typ) == "onoff" else dimmers).append(lt)
    return dimmers, onoff


def dashboard_config(site):
    s, dash = site.strings, site.ha["dashboard"]
    dimmers, onoff = split_lights(site)
    by_area = {}
    for lt in [*dimmers, *onoff]:
        by_area.setdefault(lt.area, []).append(lt.entity_id)
    for g in site.groups:
        by_area.setdefault(g.area, []).insert(0, g.entity_id)
    dimmable = {lt.entity_id for lt in dimmers}
    light_sections = []
    for area, (title, icon) in site.areas.items():
        if area not in by_area:
            continue
        light_sections.append({"type": "grid", "cards": [
            {"type": "heading", "heading": title, "icon": icon},
            *[{"type": "tile", "entity": e, "vertical": False, "features_position": "bottom",
               **({"features": [{"type": "light-brightness"}]} if e in dimmable else {})}
              for e in by_area[area]],
        ]})
    views = [{"title": s["lights_view"], "path": slugify(s["lights_view"]), "icon": "mdi:lightbulb-group",
              "type": "sections", "max_columns": 4, "sections": light_sections}]
    if site.thermostats:
        heat_cards = []
        for t in site.thermostats:
            heat_cards.append({"type": "tile", "entity": site.temp_entity(t), "name": t.name,
                               "icon": "mdi:home-thermometer" if t.area is None else "mdi:thermometer",
                               "vertical": False})
            heat_cards.append({"type": "tile", "entity": site.setpoint_entity(t),
                               "name": f"{t.name} {s['setpoint']}",
                               "vertical": False, "features_position": "bottom",
                               "features": [{"type": "numeric-input", "style": "buttons"}]})
        head = [{"type": "heading", "heading": s["heat_view"], "icon": "mdi:thermometer"}]
        if s.get("heat_note"):
            head.append({"type": "markdown", "content": s["heat_note"]})
        views.append({"title": s["heat_view"], "path": slugify(s["heat_view"]), "icon": "mdi:thermometer",
                      "type": "sections", "max_columns": 4, "sections": [
                          {"type": "grid", "cards": [*head, *heat_cards]},
                          {"type": "grid", "cards": [
                              {"type": "history-graph", "title": s["history_title"], "hours_to_show": 24,
                               "entities": [site.temp_entity(t) for t in site.thermostats]}]}]})
    return {"title": dash["title"], "views": views}


async def sync(site, apply=False):
    dimmers, onoff = split_lights(site)
    lights = {lt.label: lt for lt in dimmers}
    switches = {lt.label: lt for lt in onoff}
    thermo = {}
    for t in site.thermostats:
        thermo[site.temp_label(t)] = (t, "sensor", site.strings["temperature"])
        thermo[site.setpoint_label(t)] = (t, "number", site.strings["setpoint"])
    area_name = lambda a: site.areas[a][0] if a else "-"  # noqa: E731

    async with HA(site.ha) as ha:
        changes = []

        async def do(desc, msg=None, fn=None):
            changes.append(desc)
            print(("  " if apply else "  would: ") + desc)
            if apply:
                return await ha.call(msg) if msg else fn()

        async def registry():
            ents = await ha.call({"type": "config/entity_registry/list"})
            return ents, {d["id"]: d for d in await ha.call({"type": "config/device_registry/list"})}

        # 1. areas
        areas = {a["area_id"]: a for a in await ha.call({"type": "config/area_registry/list"})}
        for aid in site.remove_areas:
            if aid in areas:
                await do(f"delete area {aid}", {"type": "config/area_registry/delete", "area_id": aid})
        for aid, (name, icon) in site.areas.items():
            if aid not in areas:
                await do(f"create area {name}", {"type": "config/area_registry/create", "name": name, "icon": icon})
            elif areas[aid]["name"] != name or areas[aid].get("icon") != icon:
                await do(f"update area {name}", {"type": "config/area_registry/update", "area_id": aid,
                                                 "name": name, "icon": icon})
        if apply:
            by_name = {a["name"]: a["area_id"] for a in await ha.call({"type": "config/area_registry/list"})}
            area_id = {aid: by_name[name] for aid, (name, _) in site.areas.items()}
        else:
            area_id = {aid: aid for aid in site.areas}
        area_id[None] = None

        async def place(e, devs, area, name, eid, device_name=None):
            """Name and place the device and entity; rename the entity id."""
            d = devs.get(e.get("device_id"))
            dn = device_name or name
            if d and (d.get("name_by_user") != dn or d.get("area_id") != area_id[area]):
                await do(f"device {dn!r}: area {area_name(area)}",
                         {"type": "config/device_registry/update", "device_id": d["id"],
                          "name_by_user": dn, "area_id": area_id[area]})
            upd = {}
            if e["entity_id"] != eid:
                upd["new_entity_id"] = eid
            if e.get("name") != name:
                upd["name"] = name
            if e.get("area_id"):
                upd["area_id"] = None  # follow the device
            if upd:
                await do(f"entity {e['entity_id']} -> {eid} {name!r}",
                         {"type": "config/entity_registry/update", "entity_id": e["entity_id"], **upd})

        # 2./3./5. Grenton entities
        ents, devs = await registry()
        seen = set()
        for e in [e for e in ents if e["platform"] == "grenton"]:
            orig, dom = e.get("original_name"), e["entity_id"].split(".")[0]
            seen.add(orig)
            if dom == "light" and orig in lights:
                lt = lights[orig]
                await place(e, devs, lt.area, lt.name, lt.entity_id)
            elif dom == "switch" and orig in switches:
                lt = switches[orig]
                # same name as the light: switch_as_x copies the (hidden) switch's name
                await place(e, devs, lt.area, lt.name, site.switch_entity(lt))
            elif dom in ("sensor", "number") and orig in thermo and thermo[orig][1] == dom:
                t, _, word = thermo[orig]
                eid = site.temp_entity(t) if dom == "sensor" else site.setpoint_entity(t)
                await place(e, devs, t.area, f"{t.name} {word}", eid, device_name=f"{t.name} {word}")
            else:
                print(f"  ! not in site.yaml: {e['entity_id']} ({orig!r})")
        for orig in [*lights, *switches, *thermo]:
            if orig not in seen:
                print(f"  ! missing in HA: {orig!r} (re-import the interface?)")

        # 3. switch_as_x wrappers
        def grenton_switch(ents, label):
            return next((e for e in ents if e["platform"] == "grenton" and e.get("original_name") == label
                         and e["entity_id"].startswith("switch.")), None)

        ents, devs = await registry()
        sax = {e["device_id"]: e for e in ents if e["platform"] == "switch_as_x"}
        for label in switches:
            sw = grenton_switch(ents, label)
            if sw and sw["device_id"] not in sax:
                await do(f"switch_as_x {sw['entity_id']} -> light",
                         fn=lambda s=sw: ha.run_flow("flow", {"handler": "switch_as_x"},
                                                     [{"entity_id": s["entity_id"], "target_domain": "light"}]))
        if apply:
            ents, devs = await registry()
            sax = {e["device_id"]: e for e in ents if e["platform"] == "switch_as_x"}
        for label, lt in switches.items():
            sw = grenton_switch(ents, label)
            if sw and sw["device_id"] in sax:
                le = sax[sw["device_id"]]
                upd = {}
                if le["entity_id"] != lt.entity_id:
                    upd["new_entity_id"] = lt.entity_id
                if le.get("name") != lt.name:
                    upd["name"] = lt.name
                if upd:
                    await do(f"entity {le['entity_id']} -> {lt.entity_id}",
                             {"type": "config/entity_registry/update", "entity_id": le["entity_id"], **upd})

        # 4. light groups
        ents, _ = await registry()
        by_eid = {e["entity_id"]: e for e in ents}
        for g in site.groups:
            if g.entity_id not in by_eid:
                await do(f"create light group {g.name}",
                         fn=lambda g=g: ha.run_flow("flow", {"handler": "group"},
                                                    [{"next_step_id": "light"},
                                                     {"name": g.name, "entities": g.members,
                                                      "hide_members": False, "all": False}]))
        if apply:
            ents, _ = await registry()
            by_eid = {e["entity_id"]: e for e in ents}
        for g in site.groups:
            e = by_eid.get(g.entity_id) or next((e for e in ents if e["platform"] == "group"
                                                 and e.get("original_name") == g.name), None)
            if e and (e["entity_id"] != g.entity_id or e.get("area_id") != area_id[g.area]):
                await do(f"group {e['entity_id']} -> {g.entity_id}, area {area_name(g.area)}",
                         {"type": "config/entity_registry/update", "entity_id": e["entity_id"],
                          "new_entity_id": g.entity_id, "area_id": area_id[g.area]})

        # 5. units through the integration's options flow (skip entities that already have °C)
        if thermo:
            entry = (await ha.call({"type": "config_entries/get", "domain": "grenton"}))[0]["entry_id"]
            states = {s["entity_id"]: s for s in ha.rest("GET", "/api/states")}
            ents, _ = await registry()
            for e in ents:
                if e["platform"] != "grenton" or e["entity_id"].split(".")[0] not in ("sensor", "number"):
                    continue
                if e.get("original_name") not in thermo:
                    continue
                if states.get(e["entity_id"], {}).get("attributes", {}).get("unit_of_measurement") == "°C":
                    continue
                steps = [{"entity": e["entity_id"]}]
                if e["entity_id"].startswith("number."):
                    steps.append({"mode": "box"})
                steps += [{"device_class": "temperature"}, {"unit_of_measurement": "°C"}]
                await do(f"unit °C on {e['entity_id']}",
                         fn=lambda s=steps: ha.run_flow("options/flow", {"handler": entry}, s))

        # 6. dashboard
        dash = site.ha.get("dashboard")
        if dash:
            url = dash["url_path"]
            dashes = {d["url_path"]: d for d in await ha.call({"type": "lovelace/dashboards/list"})}
            if url not in dashes:
                await do(f"create dashboard {url}", {"type": "lovelace/dashboards/create", "url_path": url,
                                                     "title": dash["title"], "icon": dash.get("icon", "mdi:home"),
                                                     "show_in_sidebar": True, "require_admin": False,
                                                     "mode": "storage"})
            want = dashboard_config(site)
            have = await ha.raw({"type": "lovelace/config", "url_path": url}) if url in dashes else None
            if not (have and have.get("success") and have["result"] == want):
                await do(f"write dashboard {url}",
                         {"type": "lovelace/config/save", "url_path": url, "config": want})
        print(f"{len(changes)} changes {'applied' if apply else 'planned'}")
        return changes
