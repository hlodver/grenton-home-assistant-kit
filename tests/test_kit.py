import base64
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
    tree_id, added = mygrenton.ensure_tree_entry(house.project_dir, house.interface["label"])
    assert not added
    man = json.loads((house.project_dir / ".omp-manifest.json").read_text())
    names = [e["name"] for e in man["entries"]]
    assert names.count(f"nodes/{tree_id}/data.json") == 1
    assert (house.project_dir / "nodes" / str(tree_id) / "data.json").exists()


def test_pack_restores_key_and_unpack_redacts(house, tmp_path):
    out = tmp_path / "out.omp"
    omp.pack(house.project_dir, out, house.secrets_file)
    with zipfile.ZipFile(out) as z:
        assert KEY in z.read("properties.xml").decode()
    files = lambda: {str(p.relative_to(house.project_dir)): p.read_bytes()  # noqa: E731
                     for p in house.project_dir.rglob("*") if p.is_file()}
    before = files()
    omp.unpack(out, house.project_dir, house.secrets_file)
    after = files()
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


# --- edits (phase 5) -------------------------------------------------------------------

BUTTON, KITCHEN = "x270000001_PANEL_BUTTON_01", "x320000001_DIMM_01_Kitchen"


def _texts(house):
    return ((house.project_dir / "system.xml").read_text(), (house.project_dir / "system-gm.json").read_text())


def _gm(house):
    gm = json.loads((house.project_dir / "system-gm.json").read_text())
    return {m["name"]: m for c in gm["clus"] for m in c["modules"]}, gm


def _dirty(house, obj):
    import re
    xml = (house.project_dir / "system.xml").read_text()
    m = re.search(rf"<name>{obj}</name>\s*<parent .*?<isDirty>(\w+)</isDirty>", xml, re.S)
    return m.group(1) == "true"


def test_add_event_command_to_empty_and_full_events(house):
    d = house.project_dir
    omp.add_event_command(d, BUTTON, "OnHold", "CLU987654321->x320000001_DIMM_01_Kitchen->HoldValue(4500)")
    omp.add_event_command(d, BUTTON, "OnClick", "CLU123456789->hello()")
    mods, _ = _gm(house)
    ev = {e["name"]: e["command"] for e in mods[BUTTON]["events"]}
    assert ev["OnHold"] == ["CLU987654321->x320000001_DIMM_01_Kitchen->HoldValue(4500)"]
    assert ev["OnClick"] == ["CLU987654321->x320000001_DIMM_01_Kitchen->Switch(0)", "CLU123456789->hello()"]
    xml, _ = _texts(house)
    assert "<string>CLU123456789-&gt;hello()</string>" in xml
    assert "HoldValue(4500)</string>" in xml
    assert _dirty(house, BUTTON)


def test_remove_and_replace_event_command(house):
    d = house.project_dir
    before = _texts(house)
    omp.add_event_command(d, BUTTON, "OnHold", "CLU123456789->hello()")
    omp.remove_event_command(d, BUTTON, "CLU123456789->hello()")
    xml, js = _texts(house)
    # back to OM's own form for an empty event: <commands .../> and "command" : [ ]
    assert js == before[1]
    assert xml.replace("<isDirty>true</isDirty>", "<isDirty>false</isDirty>") == before[0]
    omp.replace_event_command(d, BUTTON, f"CLU987654321->{KITCHEN}->Switch(0)", f"CLU987654321->{KITCHEN}->SwitchOn(0)")
    mods, _ = _gm(house)
    assert {e["name"]: e["command"] for e in mods[BUTTON]["events"]}["OnClick"] == [f"CLU987654321->{KITCHEN}->SwitchOn(0)"]
    omp.clear_events(d, BUTTON)
    mods, _ = _gm(house)
    assert all(not e["command"] for e in mods[BUTTON]["events"])
    with pytest.raises(SystemExit):
        omp.remove_event_command(d, BUTTON, "CLU123456789->nothing()")


def test_set_feature_changes_both_files_only_there(house):
    d = house.project_dir
    xml0, js0 = _texts(house)
    assert omp.get_feature(d, BUTTON, "Label") == "Kitchen"
    omp.set_feature(d, BUTTON, "Label", 'Kitchen "main"')
    assert omp.get_feature(d, BUTTON, "Label") == 'Kitchen "main"'   # XML text; quotes need no escaping there
    mods, _ = _gm(house)
    assert {f["name"]: f["initValue"] for f in mods[BUTTON]["embeddedFeatures"]}["Label"] == 'Kitchen "main"'
    assert {f["name"]: f["initValue"] for f in mods[KITCHEN]["embeddedFeatures"]}["MinValue"] == "0"  # untouched
    xml, js = _texts(house)
    assert len(js.splitlines()) == len(js0.splitlines())
    assert _dirty(house, BUTTON) and not _dirty(house, KITCHEN)


def test_add_and_set_script(house):
    d = house.project_dir
    omp.add_script(d, "CLU123456789", "evening", "-- evening scene\nlocal x = 1", [("level", "NUMBER", "0.3")])
    _, gm = _gm(house)
    scripts = {s["name"]: s for s in gm["clus"][0]["scripts"]}
    assert set(scripts) == {"hello", "evening"}
    assert base64.b64decode(scripts["evening"]["content"]).decode() == "-- evening scene\nlocal x = 1"
    assert scripts["evening"]["scriptParams"][0]["name"] == "level"
    assert (d / "scripts" / "CLU123456789" / "evening.lua").read_text() == "-- evening scene\nlocal x = 1"
    assert (d / "scripts" / "CLU123456789" / "evening.lua.vd").exists()
    man = {e["name"] for e in json.loads((d / ".omp-manifest.json").read_text())["entries"]}
    assert {"scripts/CLU123456789/evening.lua", "scripts/CLU123456789/evening.lua.vd"} <= man
    xml, _ = _texts(house)
    assert "<name>evening</name>" in xml and "<paramType>NUMBER</paramType>" in xml
    with pytest.raises(SystemExit, match="already exists"):
        omp.add_script(d, "CLU123456789", "evening", "x")
    omp.set_script(d, "CLU123456789", "hello", "-- new text")
    _, gm = _gm(house)
    hello = next(s for s in gm["clus"][0]["scripts"] if s["name"] == "hello")
    assert base64.b64decode(hello["content"]).decode() == "-- new text"
    assert _dirty(house, "hello")
    # a script on a CLU with no scripts yet
    omp.add_script(d, "CLU987654321", "first", "local y = 2")
    _, gm = _gm(house)
    assert [s["name"] for s in gm["clus"][1]["scripts"]] == ["first"]


def test_edits_survive_pack_and_unpack(house, tmp_path):
    d = house.project_dir
    omp.add_event_command(d, BUTTON, "OnHold", "CLU123456789->hello()")
    omp.add_script(d, "CLU123456789", "evening", "local x = 1")
    out = tmp_path / "edited.omp"
    omp.pack(d, out, house.secrets_file)
    with zipfile.ZipFile(out) as z:
        assert "scripts/CLU123456789/evening.lua" in z.namelist()
        assert KEY in z.read("system-gm.json").decode()
    omp.pack(d, tmp_path / "again.omp", house.secrets_file)
    assert (tmp_path / "again.omp").read_bytes() == out.read_bytes()


def test_pack_refuses_files_missing_from_manifest(house, tmp_path):
    (house.project_dir / "stray.txt").write_text("x")
    with pytest.raises(SystemExit, match="not in manifest"):
        omp.pack(house.project_dir, tmp_path / "x.omp", house.secrets_file)


def test_import_workspace(house, tmp_path):
    d = house.project_dir
    ws = tmp_path / "workspace" / "Test House"
    shutil.copytree(d, ws, ignore=shutil.ignore_patterns(".omp-manifest.json"))
    for f in ("properties.xml", "system-gm.json"):  # OM's workspace holds the real key
        p = ws / f
        p.write_text(p.read_text().replace("${GRENTON_PROJECT_KEY}", KEY).replace("${GRENTON_PROJECT_IV}", IV))
    (ws / "scripts" / "CLU123456789" / "hello.lua").write_text("-- changed in OM\n")
    (ws / "nodes" / "9").mkdir(parents=True)
    (ws / "nodes" / "9" / "data.json").write_text("{}")
    omp.import_workspace(ws, d, house.secrets_file)
    assert (d / "scripts" / "CLU123456789" / "hello.lua").read_text() == "-- changed in OM\n"
    assert KEY not in (d / "properties.xml").read_text()                  # redacted again
    names = {e["name"] for e in json.loads((d / ".omp-manifest.json").read_text())["entries"]}
    assert {"nodes/", "nodes/9/", "nodes/9/data.json"} <= names
    omp.pack(d, tmp_path / "x.omp", house.secrets_file)                    # still packs
    # a file OM no longer has is kept unless --allow-delete
    (ws / "scripts" / "CLU123456789" / "hello.lua.vd").unlink()
    omp.import_workspace(ws, d, house.secrets_file)
    assert (d / "scripts" / "CLU123456789" / "hello.lua.vd").exists()
    omp.import_workspace(ws, d, house.secrets_file, allow_delete=True)
    assert not (d / "scripts" / "CLU123456789" / "hello.lua.vd").exists()


def test_import_workspace_needs_an_open_project(house, tmp_path):
    with pytest.raises(SystemExit, match="no project open"):
        omp.import_workspace(tmp_path, house.project_dir, house.secrets_file)


def test_redact_refuses_a_changed_key(house):
    p = house.project_dir / "properties.xml"
    p.write_text(p.read_text().replace("${GRENTON_PROJECT_KEY}", "c29tZS1vdGhlci1rZXk="))
    with pytest.raises(SystemExit, match="different GRENTON_PROJECT_KEY"):
        omp.redact(house.project_dir, house.secrets_file)


def test_cli_runs_against_a_site(house, capsys, monkeypatch):
    from grenton_kit.cli import main
    monkeypatch.chdir(house.root)
    main(["omp", "get-feature", BUTTON, "Label"])
    assert capsys.readouterr().out.strip() == "Kitchen"
    main(["mygrenton", "build"])
    assert "widgets" in capsys.readouterr().out
    main(["discover"])
    assert (house.root / "inventory.md").exists() and (house.root / "site.draft.yaml").exists()
