"""Regenerate tests/fixtures/house/project/ (a synthetic house in Object Manager's file format).

  uv run python tests/fixtures/make_house.py

system.xml follows Object Manager's XStream layout and system-gm.json its Jackson layout
('"key" : value', '[ {'), because the edit tools match that formatting. Every name and
number here is made up.
"""
import base64
import json
from pathlib import Path

OUT = Path(__file__).parent / "house" / "project"
KEY, IV = "${GRENTON_PROJECT_KEY}", "${GRENTON_PROJECT_IV}"
SCRIPT = "-- greet the house\nlocal a = 1\n"


def jdump(v, ind=0):
    """Jackson's default pretty printer, as Object Manager writes system-gm.json."""
    sp = "  " * ind
    if isinstance(v, dict):
        if not v:
            return "{ }"
        return "{\n" + ",\n".join(f'{sp}  {json.dumps(k)} : {jdump(x, ind + 1)}' for k, x in v.items()) + f"\n{sp}}}"
    if isinstance(v, list):
        if not v:
            return "[ ]"
        if all(isinstance(x, dict) for x in v):
            return "[ " + ", ".join(jdump(x, ind) for x in v) + " ]"
        return "[ " + ", ".join(json.dumps(x, ensure_ascii=False) for x in v) + " ]"
    return json.dumps(v, ensure_ascii=False)


def feature(name, value, index):
    return {"initValue": value, "unit": "", "divisor": 1.0, "index": index, "accessType": "ALL",
            "type": {"restrictionValues": [], "restrictionValuesNames": [], "paramType": "NUMBER"},
            "value": "", "name": name, "hit": name.lower()}


def event(name, index, commands=()):
    return {"name": name, "index": index, "command": list(commands), "customSchemeCommands": [], "paramType": []}


def module(name, on_clu, typ, features=(), events=()):
    return {"name": name, "nameOnCLU": on_clu, "type": typ, "description": "", "labels": [],
            "classTypeId": 0, "tfBusOrder": 0, "embeddedFeatures": list(features), "events": list(events),
            "moduleDevice": {"moduleID": int(name[1:10]), "hwType": 1}, "methods": []}


BUTTON = "x270000001_PANEL_BUTTON_01"
KITCHEN = "x320000001_DIMM_01_Kitchen"
GM = {
    "label": "Test House",
    "projectKey": {"keyBytes": KEY, "ivBytes": IV},
    "clus": [{
        "cipherKeyType": "PROJECT_KEY", "name": "CLU123456789", "ipAddress": "10.0.0.2",
        "nameOnCLU": "CLU123456789",
        "peripheries": [{
            "name": "Thermo_Living", "nameOnCLU": "THE0001", "typeName": "Thermostat", "typeId": "18",
            "typeVersion": "2",
            "embeddedFeatures": [
                {"initValue": "CLU123456789->x270000001_PANELSENSTEMP_01->Value", "index": 0, "name": "Source"},
                {"initValue": "CLU123456789->x330000001_DOUT_01->Value", "index": 1, "name": "Target"}],
            "events": [event("OnChange", 0)], "methods": []}],
        "embeddedFeatures": [], "definedFeatures": [], "events": [event("OnInit", 0, ["CLU123456789->Thermo_Living->Start()"])],
        "modules": [
            module("x201000001_DOUT_01", "DOU0001", "DOUT"),
            module("x201000001_DOUT_02", "DOU0004", "DOUT"),
            module("x490000000001_DALI_GEAR_01", "DAL0001", "DALI_GEAR"),
            module("x270000001_PANEL_01_Living_room_L", "PAN0001", "PANEL"),
            module("x270000001_PANELSENSTEMP_01", "PST0001", "PANELSENSTEMP"),
            module(BUTTON, "PBU0001", "PANEL_BUTTON",
                   [feature("Mode", "0", 1), feature("Label", "Kitchen", 2)],
                   [event("OnHold", 5), event("OnClick", 6, [f"CLU987654321->{KITCHEN}->Switch(0)"])]),
            module("x330000001_DOUT_01", "DOU0002", "DOUT"),
            module("x330000001_DOUT_02", "DOU0003", "DOUT")],
        "methods": [],
        "scripts": [{"name": "hello", "manualEdit": True,
                     "content": base64.b64encode(SCRIPT.encode()).decode(), "scriptParams": []}]}, {
        "cipherKeyType": "PROJECT_KEY", "name": "CLU987654321", "ipAddress": "10.0.0.3",
        "nameOnCLU": "CLU555555", "peripheries": [], "embeddedFeatures": [], "definedFeatures": [], "events": [],
        "modules": [
            module(KITCHEN, "DIM0001", "DIMM", [feature("MinValue", "0", 3)]),
            module("x320000002_DIMM_01_Cabinet", "DIM0002", "DIMM"),
            module("x320000003_DIMM_01_Spare", "DIM0003", "DIMM")],
        "methods": [], "scripts": []}],
}


def tree(xid, name, parent, children, typ, tid, extra="", dirty="false", ind=10, children_xml=None):
    p = " " * ind
    kids = (f'{p}  <children id="{children}">\n{children_xml}{p}  </children>' if children_xml
            else f'{p}  <children id="{children}"/>')
    return (f'{p}<TreeObject id="{xid}">\n{p}  <name>{name}</name>\n{p}  <parent reference="{parent}"/>\n'
            f'{kids}\n{p}  <type>{typ}</type>\n{p}  <id>{tid}</id>\n{extra}'
            f'{p}  <selected>false</selected>\n{p}  <link>false</link>\n{p}  <removedLink>false</removedLink>\n'
            f'{p}  <isDirty>{dirty}</isDirty>\n{p}</TreeObject>\n')


def xml_feature(xid, name, value):
    p = " " * 10
    return (f'{p}<EmbeddedFeature id="{xid}">\n{p}  <name>{name}</name>\n{p}  <accessType>ALL</accessType>\n'
            f'{p}  <initValue>{value}</initValue>\n{p}  <index>0</index>\n{p}</EmbeddedFeature>\n')


def xml_event(xid, name, commands=()):
    p = " " * 10
    if commands:
        body = "".join(f"{p}    <string>{c.replace('>', '&gt;')}</string>\n" for c in commands)
        cmds = f'{p}  <commands class="linked-list" id="{xid + 2}">\n{body}{p}  </commands>\n'
    else:
        cmds = f'{p}  <commands class="linked-list" id="{xid + 2}"/>\n'
    return (f'{p}<Event id="{xid}">\n{p}  <name>{name}</name>\n{p}  <argList class="linked-list" id="{xid + 1}"/>\n'
            f'{cmds}{p}</Event>\n')


def xml_object(xid, cls, name, on_clu, typ, features="", events=""):
    p = " " * 6
    return (f'{p}<{cls} id="{xid}">\n{p}  <name>{name}</name>\n{p}  <nameOnCLU>{on_clu}</nameOnCLU>\n'
            f'{p}  <type>{typ}</type>\n{p}  <features id="{xid + 1}">\n{features}{p}  </features>\n'
            f'{p}  <events id="{xid + 2}">\n{events}{p}  </events>\n{p}</{cls}>\n')


def system_xml():
    script = tree(13, "hello", 11, 14, "SCRIPT", 5, ind=14, dirty="false",
                  extra='                <specificObject class="Script" id="15">\n'
                        '                  <name>hello</name>\n                  <parameters id="16"/>\n'
                        '                  <isManualEdit>true</isManualEdit>\n'
                        '                </specificObject>\n')
    scripts = tree(11, "Scripts", 3, 12, "SCRIPTS", 4, ind=12, children_xml=script)
    clu1_kids = scripts + tree(17, BUTTON, 3, 18, "INPUT", 6, ind=12,
                               extra='              <specificObject class="Input" reference="100"/>\n')
    clu2_scripts = tree(31, "Scripts", 9, 32, "SCRIPTS", 8, ind=12)
    clu2_kids = clu2_scripts + tree(19, KITCHEN, 9, 20, "OUTPUT", 7, ind=12,
                                    extra='              <specificObject class="Output" reference="200"/>\n')
    clus = (tree(3, "CLU123456789", 1, 4, "CLU", 1, ind=8, children_xml=clu1_kids)
            + tree(9, "CLU987654321", 1, 10, "CLU", 2, ind=8, children_xml=clu2_kids)
            + tree(21, "myGrenton", 1, 22, "MYGRENTON_INTERFACES", 3, ind=8))
    defs = (xml_object(100, "Input", BUTTON, "PBU0001", "PANEL_BUTTON",
                       xml_feature(103, "Mode", "0") + xml_feature(104, "Label", "Kitchen"),
                       xml_event(110, "OnHold") + xml_event(120, "OnClick", [f"CLU987654321->{KITCHEN}->Switch(0)"]))
            + xml_object(200, "Output", KITCHEN, "DIM0001", "DIMM", xml_feature(203, "MinValue", "0")))
    return (f'<object-stream>\n  <TreeObject id="1">\n    <name>System</name>\n    <children id="2">\n'
            f'{clus}    </children>\n  </TreeObject>\n  <definitions id="99">\n{defs}  </definitions>\n</object-stream>\n')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "system.xml").write_text(system_xml())
    (OUT / "system-gm.json").write_text(jdump(GM))
    (OUT / "properties.xml").write_text(f"<properties>\n  <keyBytes>{KEY}</keyBytes>\n  <ivBytes>{IV}</ivBytes>\n</properties>\n")
    sd = OUT / "scripts" / "CLU123456789"
    sd.mkdir(parents=True, exist_ok=True)
    (sd / "hello.lua").write_text(SCRIPT)
    (sd / "hello.lua.vd").write_bytes(b"\xac\xed\x00\x05visual-diagram-placeholder")
    e = lambda n, c=8: {"name": n, "date_time": [2026, 1, 1, 12, 0, 0], "compress_type": c, "create_system": 3,  # noqa: E731
                        "create_version": 20, "extract_version": 20, "external_attr": 2175008768}
    entries = [e("system.xml"), e("system-gm.json"), e("properties.xml"), e("scripts/", 0),
               e("scripts/CLU123456789/", 0), e("scripts/CLU123456789/hello.lua"), e("scripts/CLU123456789/hello.lua.vd")]
    man = {"source": "synthetic", "comment_b64": base64.b64encode(b"backup_Test House").decode(), "entries": entries}
    (OUT / ".omp-manifest.json").write_text(json.dumps(man, indent=1) + "\n")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
