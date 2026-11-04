"""Read an unpacked OM project and describe what is in it.

inventory() collects the CLUs (and their nameOnCLU), lights, relays, thermostats,
panels, scripts and existing myGrenton interfaces. For each light and relay it also
records who controls it: which buttons, panels, thermostats and scripts reference it.
That is usually the best clue to where it is.

draft_site() turns the inventory into a first site.yaml: rooms are guessed from the
controlling panel's name, else from the object name. It is a starting point for the
onboarding interview, not an answer. Every guess is marked.
"""
import base64
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from .site import slugify

LIGHT_TYPES = ("DIMM", "DALI_GEAR")
REF = re.compile(r"->(\w+)")
SCRIPT_CALL = re.compile(r"->(\w+)\(")


def _suffix(name, marker):
    """'x320000001_DIMM_01_Kitchen_A' -> 'Kitchen_A' (empty if the object has no name part)."""
    m = re.match(rf"x\w+?_{marker}_\d+_?(.*)$", name)
    return m.group(1) if m else ""


def _serial(name):
    return name.split("_", 1)[0]


def _pretty(text):
    return text.replace("_", " ").strip()


def inventory(project_dir):
    d = Path(project_dir)
    gm = json.loads((d / "system-gm.json").read_text(encoding="utf-8"))
    inv = {"label": gm.get("label"), "clus": [], "lights": [], "relays": [], "thermostats": [],
           "panels": {}, "scripts": [], "interfaces": [], "other": Counter()}

    # panels by device serial, so a button can be traced to its panel's (room) name
    for c in gm["clus"]:
        for m in c["modules"]:
            if m["type"] == "PANEL":
                name = _pretty(_suffix(m["name"], "PANEL"))
                words = name.split()
                while len(words) > 1 and len(words[-1]) == 1:  # "Hjonaherb H" / "V": left and right panel
                    words.pop()
                inv["panels"][_serial(m["name"])] = " ".join(words) or m["name"]

    def who(owner):
        s = _serial(owner)
        return f"panel {inv['panels'][s]}" if s in inv["panels"] else owner

    refs = defaultdict(set)          # object -> {who}
    script_objs = defaultdict(set)   # script -> {objects it references}
    script_callers = defaultdict(set)
    for c in gm["clus"]:
        for s in c.get("scripts", []):
            try:
                text = base64.b64decode(s["content"]).decode("utf-8", "replace")
            except Exception:
                text = ""
            script_objs[s["name"]] |= set(REF.findall(text))
            inv["scripts"].append({"clu": c["name"], "name": s["name"],
                                   "params": [p["name"] for p in s.get("scriptParams", [])]})

        owners = [(c["name"], c.get("events", []))]
        owners += [(m["name"], m.get("events", [])) for m in c["modules"]]
        owners += [(p["name"], p.get("events", [])) for p in c.get("peripheries", [])]
        for owner, events in owners:
            for e in events:
                for cmd in e.get("command", []):
                    for obj in REF.findall(cmd):
                        refs[obj].add(who(owner))
                    for sc in SCRIPT_CALL.findall(cmd):
                        script_callers[sc].add(who(owner))
    for sc, objs in script_objs.items():
        for obj in objs:
            refs[obj] |= {f"script {sc}"} | {f"{w} via {sc}" for w in script_callers.get(sc, ())}

    heating_out = {}
    for c in gm["clus"]:
        renamed = c["name"] != c["nameOnCLU"]
        inv["clus"].append({"name": c["name"], "nameOnCLU": c["nameOnCLU"], "ip": c.get("ipAddress"),
                            "renamed": renamed,
                            "modules": dict(Counter(m["type"] for m in c["modules"]).most_common())})
        for p in c.get("peripheries", []):
            if p.get("typeName") != "Thermostat":
                continue
            feats = {f.get("name"): f.get("initValue") for f in p.get("embeddedFeatures", [])}
            src, out = feats.get("Source") or "", feats.get("Target") or ""
            if not out:  # older projects: the output is the feature at index 1
                out = next((f.get("initValue") or "" for f in p.get("embeddedFeatures", [])
                            if f.get("index") == 1), "")
            out_obj = (REF.findall(out) or [None])[0]
            if out_obj:
                heating_out[out_obj] = p["name"]
            inv["thermostats"].append({"object": p["name"], "nameOnCLU": p["nameOnCLU"], "clu": c["name"],
                                       "sensor": (REF.findall(src) or [None])[0], "output": out_obj,
                                       "refs": sorted(refs.get(p["name"], ()))})

    for c in gm["clus"]:
        for m in c["modules"]:
            t, n = m["type"], m["name"]
            if t in LIGHT_TYPES:
                inv["lights"].append({"object": n, "type": t, "clu": c["name"],
                                      "name": _pretty(_suffix(n, "DIMM" if t == "DIMM" else "DALI_GEAR")),
                                      "refs": sorted(refs.get(n, ()))})
            elif t == "DOUT":
                by_button = [r for r in refs.get(n, ()) if not r.startswith("script ")]
                heat_modules = {_serial(o) for o in heating_out}
                use = (f"heating ({heating_out[n]})" if n in heating_out
                       else "switched" if by_button
                       else "probably heating (same module as heating relays)" if _serial(n) in heat_modules
                       else "scripts only" if refs.get(n) else "unused")
                inv["relays"].append({"object": n, "clu": c["name"], "use": use,
                                      "name": _pretty(_suffix(n, "DOUT")), "refs": sorted(refs.get(n, ()))})
            else:
                inv["other"][t] += 1

    xml = (d / "system.xml").read_text(encoding="utf-8")
    for f in sorted(d.glob("nodes/*/data.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        tree = f.parent.name
        entry = re.search(rf"<type>MYGRENTON_INTERFACE</type>\s*<id>{tree}</id>", xml)
        named = None
        if entry:  # the TreeObject's own <name> is the last one before its <type>
            start = xml.rfind("<name>", 0, entry.start())
            named = xml[start + 6:xml.find("</name>", start)] if start >= 0 else None
        inv["interfaces"].append({"tree_id": int(tree), "path": str(f.relative_to(d.parent)) if d.parent in f.parents else str(f),
                                  "name": named or data.get("label"),
                                  "id": data.get("id"), "pages": [p.get("label") for p in data.get("pages", [])],
                                  "widgets": sum(len(p.get("widgets") or []) for p in data.get("pages", [])),
                                  "labels": _widget_labels(data)})
    inv["other"] = dict(inv["other"].most_common())
    return inv


def _widget_labels(data):
    """nameOnCLU -> label for every widget bound to an object (the names people already chose)."""
    out = {}
    for p in data.get("pages", []):
        for w in p.get("widgets") or []:
            label = w.get("label") or (w.get("buttonBistable") or {}).get("label")
            o = w.get("object") or {}
            st = o.get("value") or o.get("state") or w.get("value") or (w.get("buttonBistable") or {}).get("state") or {}
            if st.get("objectName") and label:
                out.setdefault(st["objectName"], label)
    return out


def guess_room(item, panel_names=()):
    """Room guess and why: the controlling panel's name wins over the object name."""
    direct = Counter(r.removeprefix("panel ") for r in item["refs"]
                     if r.startswith("panel ") and " via " not in r)
    grouped = Counter(r.split(" via ")[0].removeprefix("panel ") for r in item["refs"]
                      if r.startswith("panel ") and " via " in r)
    if direct:  # a panel button switching this light directly
        room, _ = direct.most_common(1)[0]
        return room, f"panel {room}"
    words = item["name"].split()
    if words:
        room = words[0]
        if len(words) > 1 and len(room) <= 5 and len(words[1]) > 1 and words[1].isalpha():
            room = f"{room} {words[1]}"
        # an object name that starts a panel's name ("Fataherb" -> panel "Fataherbergi",
        # "Herb 3" -> "Herb 3 Barnaherb"): the panel names the room better
        key = slugify(" ".join(words[:2])) if len(words) > 1 and words[1].isdigit() else slugify(room)
        for pn in panel_names:
            if key and slugify(pn).startswith(key):
                return pn, f"object name, panel {pn}"
        return room, "object name"
    if grouped:  # only through a group script: weakest clue (group panels often span rooms)
        room, _ = grouped.most_common(1)[0]
        return room, f"panel {room} (group)"
    return None, "no name, nothing controls it"


def _refs(refs, limit=4):
    scripts = [r for r in refs if r.startswith("script ")]
    rest = [r for r in refs if not r.startswith("script ")]
    if len(scripts) > limit:
        scripts = [f"{len(scripts)} scripts"]
    return ", ".join(rest + scripts)


def report(inv):
    """inventory.md: what the project contains, for the owner and the onboarding agent."""
    L = [f"# Inventory: {inv['label']}", "",
         "Generated by `grenton discover` from `project/`. Re-run it after the project changes.", "",
         "## CLUs", "", "| CLU | nameOnCLU | IP | Modules |", "|---|---|---|---|"]
    for c in inv["clus"]:
        mods = ", ".join(f"{k} {v}" for k, v in c["modules"].items())
        flag = " ⚠ renamed: widgets must use the nameOnCLU" if c["renamed"] else ""
        L.append(f"| {c['name']} | {c['nameOnCLU']}{flag} | {c['ip'] or ''} | {mods} |")
    L += ["", f"## Lights ({len(inv['lights'])})", "",
          "| Object | Type | Name | Room guess | Controlled by |", "|---|---|---|---|---|"]
    for lt in inv["lights"]:
        room, why = guess_room(lt, inv["panels"].values())
        L.append(f"| `{lt['object']}` | {lt['type']} | {lt['name'] or '—'} | {room or '?'} ({why}) | "
                 f"{_refs(lt['refs']) or 'nothing'} |")
    L += ["", f"## Relays ({len(inv['relays'])})", "",
          "Heating relays are driven by a thermostat. A switched relay may be a light or another load. "
          "An unused relay is probably not connected.", "",
          "| Object | Use | Controlled by |", "|---|---|---|"]
    for r in inv["relays"]:
        L.append(f"| `{r['object']}` | {r['use']} | {_refs(r['refs']) or '—'} |")
    L += ["", f"## Thermostats ({len(inv['thermostats'])})", "",
          "| Object | nameOnCLU | Sensor | Output | Referenced by |", "|---|---|---|---|---|"]
    for t in inv["thermostats"]:
        L.append(f"| `{t['object']}` | {t['nameOnCLU']} | `{t['sensor']}` | `{t['output']}` | {', '.join(t['refs']) or '—'} |")
    L += ["", f"## Panels ({len(inv['panels'])})", ""]
    L += [f"- {serial}: {name}" for serial, name in sorted(inv["panels"].items(), key=lambda x: x[1])]
    L += ["", f"## Scripts ({len(inv['scripts'])})", ""]
    L += [f"- {s['clu']}: `{s['name']}({', '.join(s['params'])})`" for s in inv["scripts"]]
    L += ["", "## myGrenton interfaces", ""]
    if inv["interfaces"]:
        for i in inv["interfaces"]:
            L.append(f"- **{i['name']}** (tree id {i['tree_id']}, id `{i['id']}`): {i['widgets']} widgets on "
                     f"{len(i['pages'])} pages: {', '.join(p or '?' for p in i['pages'])}")
    else:
        L.append("- none")
    L += ["", "## Other modules", "", ", ".join(f"{k} {v}" for k, v in inv["other"].items()) or "none", ""]
    return "\n".join(L)


def _q(v):
    import yaml
    if v is None:
        return "null"
    s = yaml.safe_dump(v, allow_unicode=True, default_flow_style=True, width=10000).strip()
    return s.removesuffix("\n...").removesuffix(" ...").strip()


def draft_site(inv, project_dir="project"):
    """A first site.yaml. Labels and rooms are guesses, marked with '# guess' comments."""
    iface = inv["interfaces"][0] if inv["interfaces"] else None
    known = iface["labels"] if iface else {}
    name_on = {}
    # nameOnCLU per object, to reuse labels people already gave widgets in OM
    gm = json.loads((Path(project_dir) / "system-gm.json").read_text(encoding="utf-8"))
    for c in gm["clus"]:
        for m in c["modules"]:
            name_on[m["name"]] = m["nameOnCLU"]
        for p in c.get("peripheries", []):
            name_on[p["name"]] = p["nameOnCLU"]

    rooms, items = {}, []
    for lt in inv["lights"]:
        room, why = guess_room(lt, inv["panels"].values())
        key = slugify(room) if room else "unsorted"
        rooms.setdefault(key, room or "Unsorted")
        label = known.get(name_on.get(lt["object"])) or lt["name"] or f"Unknown {_serial(lt['object'])[1:]}"
        items.append((key, lt, label, why))
    switched = [r for r in inv["relays"] if r["use"] == "switched"]

    L = [f"# First draft from `grenton discover`, {inv['label']}. Rooms and labels are guesses;",
         "# the onboarding interview (or you) corrects them. See examples/site.example.yaml in the kit.",
         f"name: {_q(inv['label'])}", "",
         "project:", "  dir: project", "  secrets: secrets/grenton.env",
         f"  default_clu: {inv['clus'][0]['name']}" if inv["clus"] else "", "",
         "homeassistant:", "  url: null                 # e.g. http://homeassistant.local:8123",
         "  token_file: secrets/ha.env", "  dashboard: {url_path: home-lights, title: Home}", "",
         "areas:"]
    for key, room in rooms.items():
        L.append(f"  {key}: {_q(room)}   # guess")
    L += ["", "mygrenton:",
          f"  label: {_q(iface['name'] if iface else inv['label'])}",
          f"  id: {iface['id'] if iface else _new_uuid()}" + ("   # existing interface: keep its id" if iface else ""),
          ]
    if iface:
        L.append(f"  adopt: {iface['path']}   # keep the THERMOSTAT_V2 widgets made in OM")
    L.append("  pages:")
    by_room = defaultdict(list)
    for key, lt, label, why in items:
        by_room[key].append((lt, label, why))
    for key, lights in by_room.items():
        L += [f"    - label: {_q(rooms[key])}", f"      area: {key}", "      lights:"]
        for lt, label, why in lights:
            L.append(f"        - {{object: {lt['object']}, label: {_q(label)}}}   # guess: {why}")
    if switched:
        L += ["", "  # Relays switched by buttons. Lights? Add them to a page (DOUT = on/off)."]
        for r in switched:
            L.append(f"  #   {r['object']}: {', '.join(r['refs'])}")
    L += ["", "not_connected: {}             # object: note", "",
          "thermostats:", "  page: {label: Heating}", "  values_page: {label: Temperatures}",
          "  setpoint_range: [10, 28]", "  list:"]
    for t in inv["thermostats"]:
        label = known.get(t["nameOnCLU"]) or _pretty(re.sub(r"^(Thermo|Termo|Thermostat)_?", "", t["object"])) or t["object"]
        room = inv["panels"].get(_serial(t["sensor"] or ""))
        hint = f"sensor in panel {room}" if room else "sensor not in a panel"
        L.append(f"    - {{object: {t['object']}, label: {_q(label)}}}   # guess; {hint}; add area: <key>")
    return "\n".join(x for x in L if x is not None) + "\n"


def _new_uuid():
    import uuid
    return str(uuid.uuid4())
