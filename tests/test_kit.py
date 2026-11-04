import json
import shutil
import zipfile
from pathlib import Path

import pytest

from grenton_kit import mygrenton, omp, site
from grenton_kit.ha.client import rest_url, ws_url
from grenton_kit.ha.sync import dashboard_config, split_lights

FIXTURE = Path(__file__).parent / "fixtures" / "house"
KEY, IV = "c2VjcmV0LWtleS0xMjM0NQ==", "aXYtNjc4OQ=="


@pytest.fixture
def house(tmp_path):
    d = tmp_path / "house"
    shutil.copytree(FIXTURE, d)
    (d / "secrets").mkdir()
    (d / "secrets" / "grenton.env").write_text(f"GRENTON_PROJECT_KEY={KEY}\nGRENTON_PROJECT_IV={IV}\n")
    return site.load(d / "site.yaml")


@pytest.mark.parametrize("text,slug", [
    ("Eldhús A", "eldhus_a"), ("Þvottahús", "thvottahus"), ("Baðherbergi skápur", "badherbergi_skapur"),
    ("Óþekkt dimmer 3", "othekkt_dimmer_3"), ("Łazienka", "lazienka"),
    ("Herb. 1 (skrifstofa)", "herb_1_skrifstofa")])
def test_slugify(text, slug):
    assert site.slugify(text) == slug


def test_site_defaults(house):
    lights = {lt.label: lt for lt in house.lights}
    assert lights["Kitchen ceiling"].entity_id == "light.kitchen_ceiling"
    assert lights["Kitchen ceiling"].area == "kitchen"         # from the page
    assert lights["Garage"].area == "garage"                   # light overrides page
    assert lights["LED strip"].entity_id == "light.living_led"
    assert house.areas["living"] == ("Living room", None)      # short form
    t = house.thermostats[0]
    assert (house.temp_entity(t), house.setpoint_entity(t)) == (
        "sensor.living_room_temperature", "number.living_room_setpoint")
    assert house.switch_entity(lights["Cabinet"]) == "switch.cabinet_switch"


def test_unknown_area_is_an_error(tmp_path):
    (tmp_path / "site.yaml").write_text(
        "mygrenton:\n  id: x\n  pages:\n    - {label: P, lights: [{object: o, label: L, area: nowhere}]}\n")
    with pytest.raises(SystemExit, match="unknown area 'nowhere'"):
        site.load(tmp_path / "site.yaml")


def test_dto_id_is_stable():
    assert mygrenton.dto_id("x320000001_DIMM_01_Kitchen") == mygrenton.dto_id("x320000001_DIMM_01_Kitchen")
    assert len(mygrenton.dto_id("a")) == 8 and mygrenton.dto_id("a") != mygrenton.dto_id("b")


def test_build_uses_name_on_clu_and_kinds(house):
    data, n = mygrenton.build(house)
    assert [p["label"] for p in data["pages"]] == ["Heating", "Temperatures", "Kitchen", "Living"]
    assert n == 1 + 2 + 2 + 2
    kitchen = data["pages"][2]["widgets"]
    assert kitchen[0]["type"] == "DIMMER_V2"
    # renamed CLU: widgets must use nameOnCLU, not the display name
    assert kitchen[0]["object"]["value"]["cluId"] == "CLU555555"
    assert kitchen[0]["object"]["value"]["objectName"] == "DIM0001"
    assert kitchen[1]["type"] == "ON_OFF"                       # onoff: true on a dimmer
    living = data["pages"][3]["widgets"]
    assert living[0]["max"] == 254.0 and living[0]["object"]["value"]["index"] == "2"  # DALI
    assert living[1]["type"] == "ON_OFF"                        # DOUT
    th = data["pages"][0]["widgets"][0]
    assert th["type"] == "THERMOSTAT_V2" and th["object"]["currentTemperature"]["index"] == "14"
    temps = data["pages"][1]["widgets"]
    assert [w["label"] for w in temps] == ["Living room temperature", "Living room setpoint"]
    assert data["pages"][1]["widgets"][1]["object"]["setValueAction"]["index"] == "3"


def test_build_is_deterministic(house):
    assert mygrenton.build(house) == mygrenton.build(house)


def test_unplaced_light_fails(house):
    house.not_connected.clear()
    with pytest.raises(SystemExit, match="x320000003_DIMM_01_Spare"):
        mygrenton.build(house)


def test_write_adds_tree_entry_once(house):
    mygrenton.write(house)
    xml = (house.project_dir / "system.xml").read_text()
    assert xml.count("<type>MYGRENTON_INTERFACE</type>") == 1
    mygrenton.write(house)
    assert (house.project_dir / "system.xml").read_text() == xml
    man = json.loads((house.project_dir / ".omp-manifest.json").read_text())
    names = [e["name"] for e in man["entries"]]
    assert "nodes/3/data.json" in names and names.count("nodes/3/data.json") == 1


def test_pack_restores_key_and_unpack_redacts(house, tmp_path):
    out = tmp_path / "out.omp"
    omp.pack(house.project_dir, out, house.secrets_file)
    with zipfile.ZipFile(out) as z:
        assert KEY in z.read("properties.xml").decode()
    before = {p.name: p.read_bytes() for p in house.project_dir.iterdir()}
    omp.unpack(out, house.project_dir, house.secrets_file)
    after = {p.name: p.read_bytes() for p in house.project_dir.iterdir()}
    assert {k: v for k, v in after.items() if k != ".omp-manifest.json"} == \
           {k: v for k, v in before.items() if k != ".omp-manifest.json"}
    omp.pack(house.project_dir, tmp_path / "again.omp", house.secrets_file)
    assert (tmp_path / "again.omp").read_bytes() == out.read_bytes()


def test_dashboard(house):
    dimmers, onoff = split_lights(house)
    assert [lt.label for lt in dimmers] == ["Kitchen ceiling", "LED strip"]
    assert [lt.label for lt in onoff] == ["Cabinet", "Garage"]
    cfg = dashboard_config(house)
    assert [v["path"] for v in cfg["views"]] == ["lights", "heating"]
    kitchen = cfg["views"][0]["sections"][0]["cards"]
    assert kitchen[1]["features"] == [{"type": "light-brightness"}]
    assert "features" not in kitchen[2]                          # on/off: no brightness slider


def test_urls():
    assert ws_url({"url": "http://ha.local:8123"}) == "ws://ha.local:8123/api/websocket"
    assert ws_url({"url": "https://ha.example.com/"}) == "wss://ha.example.com/api/websocket"
    assert rest_url({"url": "http://192.168.1.10"}) == "http://192.168.1.10"


# --- discover / init -------------------------------------------------------------------

from grenton_kit import discover  # noqa: E402
from grenton_kit.init import init  # noqa: E402


def test_inventory(house):
    inv = discover.inventory(house.project_dir)
    clus = {c["name"]: c for c in inv["clus"]}
    assert clus["CLU987654321"]["renamed"] and clus["CLU987654321"]["nameOnCLU"] == "CLU555555"
    assert inv["panels"] == {"x270000001": "Living room"}           # trailing "L" dropped
    relays = {r["object"]: r["use"] for r in inv["relays"]}
    assert relays["x330000001_DOUT_01"] == "heating (Thermo_Living)"
    assert relays["x330000001_DOUT_02"].startswith("probably heating")
    assert relays["x201000001_DOUT_02"] == "unused"
    t = inv["thermostats"][0]
    assert (t["sensor"], t["output"]) == ("x270000001_PANELSENSTEMP_01", "x330000001_DOUT_01")
    lights = {lt["object"]: lt for lt in inv["lights"]}
    assert lights["x320000001_DIMM_01_Kitchen"]["refs"] == ["panel Living room"]
    room, why = discover.guess_room(lights["x320000001_DIMM_01_Kitchen"], inv["panels"].values())
    assert (room, why) == ("Living room", "panel Living room")       # a direct panel button wins
    assert discover.guess_room(lights["x320000002_DIMM_01_Cabinet"])[0] == "Cabinet"
    assert "| CLU987654321 | CLU555555 ⚠ renamed" in discover.report(inv)


def test_draft_site_builds(house, tmp_path):
    inv = discover.inventory(house.project_dir)
    (house.root / "site.yaml").write_text(discover.draft_site(inv, house.project_dir))
    draft = site.load(house.root / "site.yaml")
    assert {lt.object for lt in draft.lights} == {
        "x320000001_DIMM_01_Kitchen", "x320000002_DIMM_01_Cabinet", "x320000003_DIMM_01_Spare",
        "x490000000001_DALI_GEAR_01"}
    assert [t.object for t in draft.thermostats] == ["Thermo_Living"]
    mygrenton.build(draft)


def test_init_from_omp(house, tmp_path):
    out = tmp_path / "house.omp"
    omp.pack(house.project_dir, out, house.secrets_file)
    new = init(tmp_path / "new", out, git=True)
    assert (new / "secrets" / "grenton.env").read_text() == house.secrets_file.read_text()
    assert oct((new / "secrets" / "grenton.env").stat().st_mode & 0o777) == "0o600"
    for f in ("site.yaml", "inventory.md", "CLAUDE.md", "README.md", "docs/STATUS.md",
              ".claude/skills/onboard/SKILL.md", ".gitignore"):
        assert (new / f).exists(), f
    assert "${GRENTON_PROJECT_KEY}" in (new / "project" / "properties.xml").read_text()
    import subprocess
    tracked = subprocess.run(["git", "ls-files"], cwd=new, capture_output=True, text=True).stdout.split()
    assert not [f for f in tracked if f.startswith("secrets/") or f.endswith(".omp")]
    assert "[x] 1. Project imported" in (new / "docs" / "STATUS.md").read_text()
    mygrenton.build(site.load(new / "site.yaml"))
    with pytest.raises(SystemExit, match="not empty"):
        init(new, out)


def test_secrets_from_omp_refuses_a_different_key(house, tmp_path):
    out = tmp_path / "house.omp"
    omp.pack(house.project_dir, out, house.secrets_file)
    other = tmp_path / "s" / "grenton.env"
    other.parent.mkdir()
    other.write_text("GRENTON_PROJECT_KEY=other\nGRENTON_PROJECT_IV=other\n")
    with pytest.raises(SystemExit, match="different key"):
        omp.secrets_from_omp(out, other)
