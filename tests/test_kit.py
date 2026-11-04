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
