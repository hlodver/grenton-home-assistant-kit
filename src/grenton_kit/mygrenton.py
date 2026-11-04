"""Generate a myGrenton interface from site.yaml into an unpacked OM project.

OM stores an interface in two places:
  - system.xml: a MYGRENTON_INTERFACE TreeObject under the "myGrenton" folder
  - nodes/<tree id>/data.json: pages and widgets

Every binding uses the CLU's nameOnCLU and the object's nameOnCLU. OM rejects a widget
that uses the CLU's display name ("Validation failed for cluId"), and the two differ on
CLUs that were renamed or replaced.

Widget dtoIds are derived from the object name, so regenerating keeps them; Home Assistant
uses them as unique ids. Re-running rewrites data.json and adds the tree entry only once.
"""
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

LIGHT_TYPES = ("DIMM", "DALI_GEAR")
KEY_ORDER = ["pages", "pushNotifications", "lightLogoPath", "icon", "blockCloud", "theme",
             "id", "label", "cloudSharing", "darkLogoPath"]


def project_index(d):
    """Object name -> (CLU nameOnCLU, object nameOnCLU, type) for modules and thermostats."""
    gm = json.loads((Path(d) / "system-gm.json").read_text(encoding="utf-8"))
    idx = {}
    for c in gm["clus"]:
        for m in c["modules"]:
            idx[m["name"]] = (c["nameOnCLU"], m["nameOnCLU"], m["type"])
        for p in c.get("peripheries", []):
            idx[p["name"]] = (c["nameOnCLU"], p["nameOnCLU"], p.get("typeName", "").upper())
    return idx


def dto_id(key):
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    h = int(hashlib.sha1(key.encode()).hexdigest(), 16)
    return "".join(alphabet[(h >> (6 * i)) % 62] for i in range(8))


def state(clu, obj, index):
    return {"cluId": clu, "objectName": obj, "index": index, "callType": "ATTRIBUTE"}


def action(kind, call, clu, obj, index, value):
    return {"cluId": clu, "valueFormattedForDto": value, "objectName": obj, "index": index,
            "type": kind, "value": value, "callType": call}


def dimmer_widget(wid, label, clu, obj, dali=False):
    if dali:  # DALI gear: Value attr 2 (0..254), SetValue(value, ramp), SwitchOn/SwitchOff
        o = {"value": state(clu, obj, "2"),
             "setValueAction": action("CLICK", "METHOD", clu, obj, "1", "$value$, 0"),
             "onAction": action("ON", "METHOD", clu, obj, "3", "0"),
             "offAction": action("OFF", "METHOD", clu, obj, "4", "0")}
        mx, prec = 254.0, 0
    else:  # DIMM: Value attr 0 (0..1), set through the Value pseudo-method
        o = {"value": state(clu, obj, "0"),
             "setValueAction": action("CLICK", "PSEUDO_METHOD", clu, obj, "0", "$value$"),
             "onAction": action("ON", "PSEUDO_METHOD", clu, obj, "0", "1"),
             "offAction": action("OFF", "PSEUDO_METHOD", clu, obj, "0", "0")}
        mx, prec = 1.0, 2
    return {"label": label, "icon": "dimmer", "min": 0.0, "max": mx, "precision": prec,
            "id": wid, "type": "DIMMER_V2", "dtoId": dto_id(obj), "object": o}


def onoff_widget(wid, label, clu, obj):
    """Relay (DOUT) or a dimmer channel used as a switch: Value 0/1."""
    return {"id": wid, "type": "ON_OFF", "dtoId": dto_id("onoff:" + obj), "buttonBistable": {
        "rowId": 0, "type": "BUTTON_BISTABLE", "label": label, "image": "bulb",
        "onIndication": "On", "offIndication": "Off", "state": state(clu, obj, "0"),
        "actionOn": action("ON", "PSEUDO_METHOD", clu, obj, "0", "1"),
        "actionOff": action("OFF", "PSEUDO_METHOD", clu, obj, "0", "0")}}


# Thermostat attribute indices: PointValue 3, State 6, Mode 8, Schedule 9, Min 10, Max 11,
# TargetTemp 12, ControlOutValue 13, CurrentTemp 14.
def thermostat_widget(wid, label, clu, obj):
    none = {"cluId": None, "objectName": None, "index": None, "callType": "ATTRIBUTE"}
    set_none = {"cluId": None, "valueFormattedForDto": "1", "objectName": None, "index": None,
                "type": "CLICK", "value": "1", "callType": "ATTRIBUTE"}
    st = lambda i: state(clu, obj, i)  # noqa: E731
    act = lambda i: action("CLICK", "PSEUDO_METHOD", clu, obj, i, "$value$")  # noqa: E731
    return {"icon": "temperature", "id": wid, "label": label, "type": "THERMOSTAT_V2",
            "noOfFanSpeeds": 0, "dtoId": dto_id("thermostat:" + obj), "object": {
                "maxTemperature": st("11"), "setMaxTemperatureAction": act("11"),
                "fanControlOutValue": dict(none), "currentTemperature": st("14"),
                "fanMode": dict(none), "setTargetTemperatureAction": act("3"),
                "setFanMode": dict(set_none), "controlDirection": dict(none),
                "setModeAction": act("8"), "mode": st("8"), "controlOutValue": st("13"),
                "setMinTemperatureAction": act("10"), "targetTemperature": st("12"),
                "minTemperature": st("10"), "setScheduleDataAction": act("9"),
                "setStateAction": act("6"), "state": st("6"),
                "setControlDirection": dict(set_none), "scheduleData": st("9")}}


def temp_widget(wid, label, clu, obj):
    """CurrentTemp as a plain value: Home Assistant has no thermostat widget support."""
    return {"unit": "DEGREE", "valueType": "FLOAT", "precision": 1, "icon": "temperature",
            "id": wid, "label": label, "type": "VALUE_V2", "dtoId": dto_id("temp:" + obj),
            "value": state(clu, obj, "14")}


def setpoint_widget(wid, label, clu, obj, lo, hi):
    return {"label": label, "icon": "temperature", "min": lo, "max": hi,
            "unit": "DEGREE", "precision": 1, "id": wid, "type": "SLIDER",
            "dtoId": dto_id("set:" + obj), "object": {
                "value": state(clu, obj, "3"),
                "setValueAction": action("CLICK", "PSEUDO_METHOD", clu, obj, "3", "$value$")}}


def _adopted_thermostats(site):
    """THERMOSTAT_V2 widgets from an interface made in OM, by OM object name.

    Keeping them keeps their ids and dtoIds, so the phone app doesn't see new widgets.
    OM labels them with the object name.
    """
    if not site.adopt:
        return {}
    data = json.loads(site.adopt.read_text(encoding="utf-8"))
    return {w["label"]: w for p in data["pages"] for w in p["widgets"] or []
            if w["type"] == "THERMOSTAT_V2"}


def build(site):
    """Return (interface dict, widget count). Raises SystemExit on a mismatch with the project."""
    idx = project_index(site.project_dir)
    next_id = [site.interface["first_widget_id"]]

    def new_id():
        next_id[0] += 1
        return next_id[0]

    def lookup(obj, what):
        if obj not in idx:
            raise SystemExit(f"{what} {obj!r} is not in the project ({site.project_dir})")
        return idx[obj]

    pages, used = [], set()
    for page in site.pages:
        widgets = []
        for lt in page.lights:
            clu, obj, typ = lookup(lt.object, "light")
            used.add(lt.object)
            kind = lt.kind(typ)
            if kind == "onoff":
                widgets.append(onoff_widget(new_id(), lt.label, clu, obj))
            else:
                widgets.append(dimmer_widget(new_id(), lt.label, clu, obj, dali=kind == "dali"))
        pid = new_id()
        pages.append({"icon": page.icon, "id": pid, "label": page.label, "widgets": widgets, "pageId": pid})

    missing = [n for n, (_, _, t) in idx.items()
               if t in LIGHT_TYPES and n not in used and n not in site.not_connected]
    if missing:
        raise SystemExit("lights on no page and not listed under not_connected:\n  " + "\n  ".join(missing))

    if site.thermostats and site.thermostat_page:
        adopted = _adopted_thermostats(site)
        thermo = []
        for t in site.thermostats:
            clu, obj, _ = lookup(t.object, "thermostat")
            w = adopted.get(t.object)
            thermo.append(dict(w, label=t.label) if w else thermostat_widget(new_id(), t.label, clu, obj))
        pid = new_id()
        tp = site.thermostat_page
        pages.insert(0, {"icon": tp.get("icon", "default"), "id": pid, "label": tp["label"],
                         "widgets": thermo, "pageId": pid})
    if site.thermostats and site.values_page:
        lo, hi = site.setpoint_range
        values = []
        for t in site.thermostats:
            clu, obj, _ = lookup(t.object, "thermostat")
            values.append(temp_widget(new_id(), site.temp_label(t), clu, obj))
            values.append(setpoint_widget(new_id(), site.setpoint_label(t), clu, obj, lo, hi))
        pid = new_id()
        vp = site.values_page
        pages.insert(1 if site.thermostat_page else 0,
                     {"icon": vp.get("icon", "default"), "id": pid, "label": vp["label"],
                      "widgets": values, "pageId": pid})

    i = site.interface
    out = {"pages": pages, "pushNotifications": None, "lightLogoPath": None, "icon": i["icon"],
           "blockCloud": False, "theme": i["theme"], "id": i["id"], "label": i["label"],
           "cloudSharing": None, "darkLogoPath": None}
    return {k: out[k] for k in KEY_ORDER}, sum(len(p["widgets"]) for p in pages)


def ensure_tree_entry(d, name):
    """Add the MYGRENTON_INTERFACE TreeObject once; return (tree id, added)."""
    p = Path(d) / "system.xml"
    xml = p.read_text(encoding="utf-8")
    m = re.search(r"<name>" + re.escape(name) + r"</name>.*?<type>MYGRENTON_INTERFACE</type>\s*<id>(\d+)</id>", xml, re.S)
    if m:
        return int(m.group(1)), False
    folder = re.search(r'<TreeObject id="(\d+)">\s*<name>myGrenton</name>\s*<parent reference="\d+"/>\s*'
                       r'(<children id="(\d+)"/>)\s*<type>MYGRENTON_INTERFACES</type>', xml)
    if not folder:
        raise SystemExit("system.xml: empty myGrenton folder not found. Another interface exists; "
                         "give mygrenton.label the same name to update it")
    xs = max(int(x) for x in re.findall(r' id="(\d+)"', xml))
    tree_id = max(int(x) for x in re.findall(r"<id>(\d+)</id>", xml)) + 1
    ind = " " * 10
    entry = (f'<children id="{folder.group(3)}">\n'
             f'{ind}<TreeObject id="{xs + 1}">\n'
             f'{ind}  <name>{name}</name>\n'
             f'{ind}  <parent reference="{folder.group(1)}"/>\n'
             f'{ind}  <children id="{xs + 2}"/>\n'
             f'{ind}  <type>MYGRENTON_INTERFACE</type>\n'
             f'{ind}  <id>{tree_id}</id>\n'
             f'{ind}  <specificObject class="com.grenton.om.mobile.gui.MobileInterfaceTreeObject" id="{xs + 3}"/>\n'
             f'{ind}  <selected>false</selected>\n'
             f'{ind}  <link>false</link>\n'
             f'{ind}  <removedLink>false</removedLink>\n'
             f'{ind}  <isDirty>false</isDirty>\n'
             f'{ind}</TreeObject>\n'
             f'        </children>')
    p.write_text(xml[:folder.start(2)] + entry + xml[folder.end(2):], encoding="utf-8")
    return tree_id, True


def ensure_manifest(d, tree_id):
    mp = Path(d) / ".omp-manifest.json"
    man = json.loads(mp.read_text())
    known = {e["name"] for e in man["entries"]}
    proto = next(e for e in man["entries"] if not e["name"].endswith("/"))
    now = list(datetime.now().timetuple()[:6])
    for name in ("nodes/", f"nodes/{tree_id}/"):
        if name not in known:
            man["entries"].append(dict(proto, name=name, compress_type=0, date_time=now))
    if f"nodes/{tree_id}/data.json" not in known:
        man["entries"].append(dict(proto, name=f"nodes/{tree_id}/data.json", date_time=now))
    mp.write_text(json.dumps(man, indent=1) + "\n")


def write(site):
    data, n = build(site)
    d = site.project_dir
    tree_id, added = ensure_tree_entry(d, site.interface["label"])
    target = d / "nodes" / str(tree_id) / "data.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=4, ensure_ascii=False))
    ensure_manifest(d, tree_id)
    print(f"{'added' if added else 'kept'} tree entry {tree_id}; wrote {target}: "
          f"{len(data['pages'])} pages, {n} widgets")
    for p in data["pages"]:
        print(f"  {p['label']}: " + ", ".join(
            w.get("label") or w["buttonBistable"]["label"] + " (on/off)" for w in p["widgets"]))
