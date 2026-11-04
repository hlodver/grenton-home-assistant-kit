"""site.yaml: everything specific to one house, in one file.

The tools read the Object Manager project for what it already knows (CLUs, modules,
object types) and site.yaml for what only the owner knows: which page and room a light
belongs to, its name, which loads are on/off only, what is not connected.

Paths in site.yaml are relative to the folder that holds it. See
examples/site.example.yaml for every key.
"""
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_STRINGS = {
    "temperature": "temperature",    # widget/entity suffix: "<thermostat> temperature"
    "setpoint": "setpoint",          # "<thermostat> setpoint"
    "switch_suffix": "switch",       # hidden switch behind an on/off light: switch.<light>_switch
    "lights_view": "Lights",
    "heat_view": "Heating",
    "history_title": "Last 24 hours",
    "heat_note": None,               # optional markdown on the heating view
}

_TRANSLIT = {"þ": "th", "ð": "d", "æ": "ae", "ø": "o", "ß": "ss", "œ": "oe", "ł": "l", "đ": "d"}


def slugify(text):
    """Entity-id style slug, close to Home Assistant's: 'Þvottahús A' -> 'thvottahus_a'."""
    text = "".join(_TRANSLIT.get(c, c) for c in text.lower())
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


@dataclass
class Light:
    object: str           # OM object name, e.g. x320000001_DIMM_01_Kitchen
    label: str            # myGrenton widget label (= the HA entity's original name)
    area: str | None      # area key (see areas:)
    name: str             # Home Assistant name
    entity_id: str        # light.<...>
    onoff: bool = False   # a dimmer channel driving a load that can't be dimmed

    def kind(self, module_type):
        """dimmer | dali | onoff, given the module type from the project."""
        if self.onoff or module_type == "DOUT":
            return "onoff"
        return "dali" if module_type == "DALI_GEAR" else "dimmer"


@dataclass
class Page:
    label: str
    icon: str
    lights: list


@dataclass
class Thermostat:
    object: str           # OM object name, e.g. Thermo_Stofa
    label: str            # myGrenton label
    name: str             # HA name prefix
    slug: str             # entity ids sensor.<slug>_<temperature>, number.<slug>_<setpoint>
    area: str | None


@dataclass
class Group:
    entity_id: str
    name: str
    area: str | None
    members: list


@dataclass
class Site:
    root: Path
    name: str
    project_dir: Path
    secrets_file: Path
    workspace: Path | None
    default_clu: str | None
    interface: dict
    adopt: Path | None
    pages: list
    not_connected: dict
    thermostat_page: dict | None
    values_page: dict | None
    setpoint_range: tuple
    thermostats: list
    areas: dict
    remove_areas: list
    groups: list
    ha: dict
    strings: dict = field(default_factory=dict)

    @property
    def lights(self):
        return [lt for p in self.pages for lt in p.lights]

    def temp_label(self, t):
        return f"{t.label} {self.strings['temperature']}"

    def setpoint_label(self, t):
        return f"{t.label} {self.strings['setpoint']}"

    def temp_entity(self, t):
        return f"sensor.{t.slug}_{slugify(self.strings['temperature'])}"

    def setpoint_entity(self, t):
        return f"number.{t.slug}_{slugify(self.strings['setpoint'])}"

    def switch_entity(self, lt):
        return lt.entity_id.replace("light.", "switch.", 1) + "_" + slugify(self.strings["switch_suffix"])


class SiteError(SystemExit):
    pass


def find_site(path=None):
    """--site, else $GRENTON_SITE, else site.yaml in this folder or a parent."""
    if path:
        return Path(path)
    if os.environ.get("GRENTON_SITE"):
        return Path(os.environ["GRENTON_SITE"])
    for d in [Path.cwd(), *Path.cwd().parents]:
        if (d / "site.yaml").exists():
            return d / "site.yaml"
    raise SiteError("no site.yaml found (pass --site, set GRENTON_SITE, or run inside a site folder)")


def load(path=None):
    path = find_site(path).resolve()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    root = path.parent
    rel = lambda p: (root / p) if p else None  # noqa: E731
    errors = []

    proj = raw.get("project", {})
    mg = raw.get("mygrenton", {})
    areas = {}
    for key, a in (raw.get("areas") or {}).items():
        a = a if isinstance(a, dict) else {"name": a}
        areas[key] = (a["name"], a.get("icon"))

    def area_ok(a, where):
        if a is not None and a not in areas:
            errors.append(f"{where}: unknown area {a!r}")
        return a

    pages, seen = [], set()
    for p in mg.get("pages", []):
        lights = []
        for x in p.get("lights", []):
            if x["object"] in seen:
                errors.append(f"{x['object']}: on more than one page")
            seen.add(x["object"])
            label = x["label"]
            name = x.get("name", label)
            area = area_ok(x.get("area", p.get("area")), x["object"])
            lights.append(Light(object=x["object"], label=label, area=area, name=name,
                                entity_id=x.get("entity_id", "light." + slugify(name)),
                                onoff=bool(x.get("onoff", False))))
        pages.append(Page(label=p["label"], icon=p.get("icon", "default"), lights=lights))

    th = raw.get("thermostats") or {}
    thermostats = []
    for t in th.get("list", []):
        name = t.get("name", t["label"])
        thermostats.append(Thermostat(object=t["object"], label=t["label"], name=name,
                                      slug=t.get("slug", slugify(name)),
                                      area=area_ok(t.get("area"), t["object"])))

    groups = []
    for g in (raw.get("homeassistant") or {}).get("groups", []):
        groups.append(Group(entity_id=g["entity_id"], name=g["name"],
                            area=area_ok(g.get("area"), g["entity_id"]), members=g["members"]))

    ha = dict(raw.get("homeassistant") or {})
    ha.setdefault("dashboard", None)
    for k in ("token_file",):
        if ha.get(k):
            ha[k] = rel(ha[k])

    nc = raw.get("not_connected") or {}
    if isinstance(nc, list):
        nc = {o: None for o in nc}

    if errors:
        raise SiteError(f"{path}:\n  " + "\n  ".join(errors))
    if "id" not in mg:
        raise SiteError(f"{path}: mygrenton.id missing (any UUID; keep it once HA uses the interface)")

    return Site(
        root=root,
        name=raw.get("name", root.name),
        project_dir=rel(proj.get("dir", "project")),
        secrets_file=rel(proj.get("secrets", "secrets/grenton.env")),
        workspace=rel(proj.get("workspace")),
        default_clu=proj.get("default_clu"),
        interface={"id": mg["id"], "label": mg.get("label", raw.get("name", root.name)),
                   "icon": mg.get("icon", "home_1"), "theme": mg.get("theme", "blue"),
                   "first_widget_id": int(mg.get("first_widget_id", 1793740100000))},
        adopt=rel(mg.get("adopt")),
        pages=pages,
        not_connected=nc,
        thermostat_page=th.get("page"),
        values_page=th.get("values_page"),
        setpoint_range=tuple(float(v) for v in th.get("setpoint_range", (10, 28))),
        thermostats=thermostats,
        areas=areas,
        remove_areas=ha.get("remove_areas", []),
        groups=groups,
        ha=ha,
        strings={**DEFAULT_STRINGS, **(raw.get("strings") or {})},
    )
