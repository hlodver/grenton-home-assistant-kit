"""Grenton Object Manager project (.omp) <-> git-friendly folder.

An .omp is a zip holding system.xml (XStream object tree, OM's source of truth),
system-gm.json (an export of the same objects), properties.xml, scripts and
diagnostics. Unpacked into a folder, every change is a readable git diff, and packing
gives back an .omp that is byte-identical when nothing changed.

Feature and event edits are narrow text replacements in system.xml and the matching
entries in system-gm.json; nothing else in the files changes.
"""
import base64
import json
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

MANIFEST = ".omp-manifest.json"

# The project cipher key lets anyone on the LAN talk to the CLUs. It stays out of git:
# project/ holds placeholders, the real values live in a secrets file (default
# secrets/grenton.env, gitignored), and pack() puts them back only in the .omp handed to
# Object Manager.
SECRET_FILES = ("properties.xml", "system-gm.json")
PLACEHOLDERS = {"GRENTON_PROJECT_KEY": "${GRENTON_PROJECT_KEY}", "GRENTON_PROJECT_IV": "${GRENTON_PROJECT_IV}"}


def load_secrets(secrets_file):
    secrets_file = Path(secrets_file)
    if not secrets_file.exists():
        raise SystemExit(f"{secrets_file} missing: it holds GRENTON_PROJECT_KEY / GRENTON_PROJECT_IV "
                         "(see README, 'Secrets')")
    env = {}
    for line in secrets_file.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    missing = [k for k in PLACEHOLDERS if not env.get(k)]
    if missing:
        raise SystemExit(f"{secrets_file}: missing {', '.join(missing)}")
    return env


def redact(d, secrets_file):
    """Replace the real key/iv in project files with placeholders (after unpack/import)."""
    env = load_secrets(secrets_file)
    d = Path(d)
    props = (d / "properties.xml").read_text(encoding="utf-8")
    key = re.search(r"<keyBytes[^>]*>([^<]*)</keyBytes>", props)
    iv = re.search(r"<ivBytes[^>]*>([^<]*)</ivBytes>", props)
    for found, name in ((key, "GRENTON_PROJECT_KEY"), (iv, "GRENTON_PROJECT_IV")):
        if found and found.group(1) not in (env[name], PLACEHOLDERS[name]):
            raise SystemExit(f"properties.xml has a different {name} than {secrets_file}; "
                             "update the secrets file deliberately if the project key changed")
    for fname in SECRET_FILES:
        p = d / fname
        text = p.read_text(encoding="utf-8")
        for name, ph in PLACEHOLDERS.items():
            text = text.replace(env[name], ph)
        p.write_text(text, encoding="utf-8")


def unredact(data, fname, env):
    if fname not in SECRET_FILES:
        return data
    text = data.decode("utf-8")
    for name, ph in PLACEHOLDERS.items():
        text = text.replace(ph, env[name])
    return text.encode("utf-8")


def unpack(omp, d, secrets_file):
    d = Path(d)
    if d.exists():
        for p in d.iterdir():  # replace contents but keep the folder (and git history) in place
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    d.mkdir(parents=True, exist_ok=True)
    entries = []
    with zipfile.ZipFile(omp) as z:
        for i in z.infolist():
            entries.append({"name": i.filename, "date_time": list(i.date_time),
                            "compress_type": i.compress_type, "create_system": i.create_system,
                            "create_version": i.create_version, "extract_version": i.extract_version,
                            "external_attr": i.external_attr})
            target = d / i.filename
            if i.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(i))
        manifest = {"source": Path(omp).name,
                    "comment_b64": base64.b64encode(z.comment).decode(), "entries": entries}
    (d / MANIFEST).write_text(json.dumps(manifest, indent=1) + "\n")
    redact(d, secrets_file)
    print(f"unpacked {omp} -> {d} ({len(entries)} entries, key redacted)")


def pack(d, out, secrets_file):
    d = Path(d)
    manifest = json.loads((d / MANIFEST).read_text())
    listed = {e["name"].rstrip("/") for e in manifest["entries"]}
    extra = [str(p.relative_to(d)) for p in d.rglob("*")
             if p.is_file() and p.name != MANIFEST and str(p.relative_to(d)) not in listed]
    if extra:
        raise SystemExit(f"files not in manifest (OM would not know them): {extra}")
    env = load_secrets(secrets_file)
    with zipfile.ZipFile(out, "w") as z:
        z.comment = base64.b64decode(manifest["comment_b64"])
        for e in manifest["entries"]:
            info = zipfile.ZipInfo(e["name"], tuple(e["date_time"]))
            info.compress_type = e["compress_type"]
            info.create_system = e["create_system"]
            info.external_attr = e["external_attr"]
            info.create_version = e["create_version"]
            info.extract_version = e["extract_version"]
            data = b"" if e["name"].endswith("/") else unredact((d / e["name"]).read_bytes(), e["name"], env)
            z.writestr(info, data, compress_type=e["compress_type"])
    print(f"packed {d} -> {out}")


def import_workspace(ws, d, secrets_file, allow_delete=False):
    """Copy Object Manager's live workspace folder into DIR and extend the manifest.

    New files get zip metadata modelled on existing entries. Files missing from the
    workspace are only deleted with allow_delete, because OM sometimes holds content
    (e.g. scripts) in memory without writing it to disk.
    """
    ws, d = Path(ws), Path(d)
    if not (ws / "system.xml").exists():
        raise SystemExit(f"no project open in {ws} (OM removes it when it closes); "
                         "import while the project is open in Object Manager")
    manifest = json.loads((d / MANIFEST).read_text())
    known = {e["name"] for e in manifest["entries"]}
    proto = next(e for e in manifest["entries"] if not e["name"].endswith("/"))
    changed, added = [], []
    for p in sorted(ws.rglob("*")):
        rel = p.relative_to(ws).as_posix()
        if p.is_dir():
            name = rel + "/"
            if name not in known and any(q.is_file() for q in p.rglob("*")):
                manifest["entries"].append(dict(proto, name=name, compress_type=0))
                known.add(name)
            continue
        target = d / rel
        if not target.exists() or target.read_bytes() != p.read_bytes():
            target.parent.mkdir(parents=True, exist_ok=True)
            (changed if target.exists() else added).append(rel)
            shutil.copy2(p, target)
        if rel not in known:
            mt = datetime.fromtimestamp(p.stat().st_mtime)
            manifest["entries"].append(dict(proto, name=rel, date_time=list(mt.timetuple()[:6])))
            known.add(rel)
    missing = [e["name"] for e in manifest["entries"]
               if not e["name"].endswith("/") and not (ws / e["name"]).exists()]
    if missing and allow_delete:
        for name in missing:
            (d / name).unlink(missing_ok=True)
        manifest["entries"] = [e for e in manifest["entries"] if e["name"] not in missing]
    manifest["source"] = f"workspace {ws}"
    (d / MANIFEST).write_text(json.dumps(manifest, indent=1) + "\n")
    redact(d, secrets_file)
    print(f"changed: {len(changed)}  added: {len(added)}")
    for rel in changed:
        print("  M", rel)
    for rel in added:
        print("  A", rel)
    for name in missing:
        print("  D" if allow_delete else "  ! missing in workspace, kept:", name)


def _xml_feature(xml, obj, feature):
    # the object definition carries <nameOnCLU>; tree nodes with the same <name> do not
    m = re.search(rf"<name>{re.escape(obj)}</name>\s*<nameOnCLU>", xml)
    if not m:
        raise SystemExit(f"system.xml: object {obj!r} not found")
    end = xml.find("</features>", m.end())
    fm = re.search(rf"<name>{re.escape(feature)}</name>.*?</EmbeddedFeature>", xml[m.start():end], re.S)
    if not fm:
        raise SystemExit(f"system.xml: feature {feature!r} not found on {obj!r}")
    fs = m.start() + fm.start()
    vm = re.search(r"<initValue>(.*?)</initValue>", fm.group(0), re.S)
    if not vm:
        raise SystemExit(f"system.xml: {obj}.{feature} has no initValue")
    return fs + vm.start(1), fs + vm.end(1)


def _gm_feature(js, obj, feature):
    m = re.search(rf'"name" : "{re.escape(obj)}",\s*"nameOnCLU"', js)
    if not m:
        raise SystemExit(f"system-gm.json: object {obj!r} not found")
    block = js[m.end():js.find('"methods"', m.end())]
    for fm in re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", block):
        if re.search(rf'"name" : "{re.escape(feature)}"', fm.group(0)):
            vm = re.search(r'"initValue" : "((?:[^"\\]|\\.)*)"', fm.group(0))
            if vm:
                base = m.end() + fm.start()
                return base + vm.start(1), base + vm.end(1)
    raise SystemExit(f"system-gm.json: {obj}.{feature} initValue not found")


def mark_dirty(d, obj):
    """Set isDirty on OBJ's tree node so OM sees the change and sends it.

    Tree nodes are <TreeObject> elements whose <name> is followed by <parent>;
    the object definitions (with <nameOnCLU>) carry no isDirty flag.
    """
    p = Path(d) / "system.xml"
    xml = p.read_text(encoding="utf-8")
    m = re.search(rf"<name>{re.escape(obj)}</name>\s*<parent ", xml)
    if not m:
        raise SystemExit(f"system.xml: tree node for {obj!r} not found")
    end = xml.find("</TreeObject>", m.end())
    dm = re.search(r"<isDirty>(true|false)</isDirty>", xml[m.end():end])
    if not dm:
        raise SystemExit(f"system.xml: {obj!r} tree node has no isDirty")
    s = m.end() + dm.start(1)
    p.write_text(xml[:s] + "true" + xml[s + len(dm.group(1)):], encoding="utf-8")


def add_event_command(d, obj, event, command):
    """Append COMMAND (e.g. 'CLU123456789->Thermo_Living->Start()') to OBJ's EVENT."""
    d = Path(d)
    p = d / "system.xml"
    xml = p.read_text(encoding="utf-8")
    m = re.search(rf"<name>{re.escape(obj)}</name>\s*(?:<ipAddress>[^<]*</ipAddress>\s*)?<nameOnCLU>", xml)
    if not m:
        raise SystemExit(f"system.xml: object {obj!r} not found")
    em = re.search(rf"<name>{re.escape(event)}</name>\s*<argList[^>]*/>\s*(<commands class=\"linked-list\" id=\"\d+\")(/>|>)",
                   xml[m.end():])
    if not em or "<nameOnCLU>" in xml[m.end():m.end() + em.start()]:
        raise SystemExit(f"system.xml: event {event!r} not found on {obj!r}")
    indent = " " * 30
    item = f"{indent}<string>{escape(command)}</string>\n"
    if em.group(2) == "/>":
        s, e = m.end() + em.start(1), m.end() + em.end(2)
        xml = xml[:s] + em.group(1) + ">\n" + item + indent[:-2] + "</commands>" + xml[e:]
    else:
        close = xml.find("</commands>", m.end() + em.end())
        line_start = xml.rfind("\n", 0, close) + 1
        xml = xml[:line_start] + item + xml[line_start:]
    p.write_text(xml, encoding="utf-8")

    p = d / "system-gm.json"
    js = p.read_text(encoding="utf-8")
    m = re.search(rf'"name" : "{re.escape(obj)}",', js)
    em = re.search(rf'"name" : "{re.escape(event)}",\s*"index" : \d+,\s*"command" : \[(.*?)\]', js[m.end():], re.S)
    if not em:
        raise SystemExit(f"system-gm.json: event {event!r} not found on {obj!r}")
    s, e = m.end() + em.start(1), m.end() + em.end(1)
    existing = em.group(1).strip()
    quoted = json.dumps(command)
    new = f" {quoted} " if not existing else f" {existing}, {quoted} "
    p.write_text(js[:s] + new + js[e:], encoding="utf-8")
    mark_dirty(d, obj)
    print(f"{obj}.{event} += {command}")


def _object_span(text, obj, json_mode=False):
    """Start/end of OBJ's own definition, so edits never touch another object's identical command."""
    if json_mode:
        m = re.search(rf'"name" : "{re.escape(obj)}",\s*"nameOnCLU"', text)
        nxt = re.search(r'"nameOnCLU"', text[m.end():]) if m else None
    else:
        m = re.search(rf"<name>{re.escape(obj)}</name>\s*(?:<ipAddress>[^<]*</ipAddress>\s*)?<nameOnCLU>", text)
        nxt = re.search(r"<nameOnCLU>", text[m.end():]) if m else None
    if not m:
        raise SystemExit(f"object {obj!r} not found")
    return m.start(), (m.end() + nxt.start()) if nxt else len(text)


def remove_event_command(d, obj, command):
    """Remove COMMAND from OBJ's events (system.xml and system-gm.json), scoped to that object."""
    d = Path(d)
    p = d / "system.xml"
    xml = p.read_text(encoding="utf-8")
    s, e = _object_span(xml, obj)
    block = xml[s:e]
    line = re.search(rf"\n[ ]*<string>{re.escape(escape(command))}</string>", block)
    if not line:
        raise SystemExit(f"system.xml: {obj} has no command {command}")
    block = block[:line.start()] + block[line.end():]
    # an event left with no commands goes back to the self-closing form OM writes
    block = re.sub(r'(<commands class="linked-list" id="\d+")>\s*</commands>', r"\1/>", block)
    p.write_text(xml[:s] + block + xml[e:], encoding="utf-8")
    p = d / "system-gm.json"
    js = p.read_text(encoding="utf-8")
    s, e = _object_span(js, obj, json_mode=True)
    block = js[s:e]
    q = re.escape(json.dumps(command))
    block, n = re.subn(rf'"command" : \[ {q} \]', '"command" : [ ]', block, count=1)
    if not n:
        block, n = re.subn(rf'(, {q}(?= ))|({q}, )', "", block, count=1)
    if not n:
        raise SystemExit(f"system-gm.json: {obj} has no command {command}")
    p.write_text(js[:s] + block + js[e:], encoding="utf-8")
    mark_dirty(d, obj)
    print(f"{obj}: removed {command}")


def clear_events(d, obj):
    """Remove every command from every event of OBJ (scoped to that object)."""
    d = Path(d)
    p = d / "system.xml"
    xml = p.read_text(encoding="utf-8")
    s, e = _object_span(xml, obj)
    block = re.sub(r'(<commands class="linked-list" id="\d+")>.*?</commands>', r"\1/>", xml[s:e], flags=re.S)
    p.write_text(xml[:s] + block + xml[e:], encoding="utf-8")
    p = d / "system-gm.json"
    js = p.read_text(encoding="utf-8")
    s, e = _object_span(js, obj, json_mode=True)
    block = re.sub(r'"command" : \[[^\]]*\]', '"command" : [ ]', js[s:e])
    p.write_text(js[:s] + block + js[e:], encoding="utf-8")
    mark_dirty(d, obj)


def replace_event_command(d, obj, old, new):
    """Replace one event command string of OBJ in place (system.xml and system-gm.json)."""
    d = Path(d)
    p = d / "system.xml"
    xml = p.read_text(encoding="utf-8")
    o, n = f"<string>{escape(old)}</string>", f"<string>{escape(new)}</string>"
    if xml.count(o) != 1:
        raise SystemExit(f"system.xml: expected exactly one '{old}', found {xml.count(o)}")
    p.write_text(xml.replace(o, n), encoding="utf-8")
    p = d / "system-gm.json"
    js = p.read_text(encoding="utf-8")
    o, n = json.dumps(old), json.dumps(new)
    if js.count(o) != 1:
        raise SystemExit(f"system-gm.json: expected exactly one {o}, found {js.count(o)}")
    p.write_text(js.replace(o, n), encoding="utf-8")
    mark_dirty(d, obj)
    print(f"{obj}: {old} -> {new}")


def _scripts_container(xml, clu):
    """(xstream id, insert position) of CLU's Scripts container children block."""
    clu_node = re.search(rf"<TreeObject id=\"(\d+)\">\s*<name>{re.escape(clu)}</name>\s*<parent ", xml)
    if not clu_node:
        raise SystemExit(f"system.xml: tree node for {clu!r} not found")
    m = re.search(rf"<TreeObject id=\"(\d+)\">\s*<name>Scripts</name>\s*<parent reference=\"{clu_node.group(1)}\"/>\s*"
                  r"\n([ ]*)<children id=\"\d+\"(/?)>", xml)
    if not m:
        raise SystemExit(f"system.xml: Scripts container of {clu!r} not found")
    return m


def _gm_script_list(js, clu):
    m = re.search(rf'"name" : "{re.escape(clu)}",', js)
    sm = re.search(r'"scripts" : \[', js[m.end():])
    return m.end() + sm.end()


def _write_script_files(d, clu, name, content):
    """OM loads script text from scripts/<CLU>/<name>.lua (plus a .lua.vd diagram file).

    Its own Save doesn't always write these, so we write them and list them in the manifest.
    The .vd is a serialized empty visual diagram; any existing one serves as template.
    """
    d = Path(d)
    folder = d / "scripts" / clu
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.lua").write_text(content, encoding="utf-8")
    vd = folder / f"{name}.lua.vd"
    if not vd.exists():
        template = next((d / "scripts").rglob("*.lua.vd"), None)
        if template is None:
            raise SystemExit("no .lua.vd template found under scripts/")
        shutil.copyfile(template, vd)
    manifest = json.loads((d / MANIFEST).read_text())
    known = {e["name"] for e in manifest["entries"]}
    proto = next(e for e in manifest["entries"] if e["name"].endswith(".lua.vd"))
    now = list(datetime.now().timetuple()[:6])
    for rel in (f"scripts/{clu}/", f"scripts/{clu}/{name}.lua", f"scripts/{clu}/{name}.lua.vd"):
        if rel not in known:
            manifest["entries"].append(dict(proto, name=rel, date_time=now,
                                            compress_type=0 if rel.endswith("/") else proto["compress_type"]))
    (d / MANIFEST).write_text(json.dumps(manifest, indent=1) + "\n")


def set_script(d, clu, name, content):
    """Replace a script's source (OM syntax, e.g. CLU->obj->Method()) in system-gm.json."""
    d = Path(d)
    p = d / "system-gm.json"
    js = p.read_text(encoding="utf-8")
    m = re.search(rf'"name" : "{re.escape(name)}",\s*"manualEdit" : true,\s*"content" : "([^"]*)"', js)
    if not m:
        raise SystemExit(f"system-gm.json: script {name!r} not found")
    b64 = base64.b64encode(content.encode("utf-8")).decode()
    p.write_text(js[:m.start(1)] + b64 + js[m.end(1):], encoding="utf-8")
    _write_script_files(d, clu, name, content)
    mark_dirty(d, name)
    print(f"script {name}: content replaced ({len(content)} chars)")


def add_script(d, clu, name, content, params=()):
    """Create a manual-edit script on CLU. params: [(name, 'NUMBER'|'STRING', default)]."""
    d = Path(d)
    p = d / "system.xml"
    xml = p.read_text(encoding="utf-8")
    if re.search(rf"<name>{re.escape(name)}</name>\s*<parent ", xml):
        raise SystemExit(f"script {name!r} already exists")
    m = _scripts_container(xml, clu)
    next_xid = max(int(i) for i in re.findall(r' id="(\d+)"', xml)) + 1
    next_tid = max(int(i) for i in re.findall(r"<id>(\d+)</id>", xml)) + 1

    def xid():
        nonlocal next_xid
        next_xid += 1
        return next_xid - 1

    ind = m.group(2) + "  "
    i2, i3, i4 = ind + "  ", ind + "    ", ind + "      "
    plines = []
    for pname, ptype, pdefault in params:
        plines += [f"{i4}<ScriptParameter id=\"{xid()}\">",
                   f"{i4}  <name>{escape(pname)}</name>",
                   f"{i4}  <value>{escape(str(pdefault))}</value>",
                   f"{i4}  <defaultValue>{escape(str(pdefault))}</defaultValue>",
                   f"{i4}  <extendParamType id=\"{xid()}\">",
                   f"{i4}    <paramType>{ptype}</paramType>",
                   f"{i4}  </extendParamType>",
                   f"{i4}  <unit></unit>",
                   f"{i4}  <divisor>1.0</divisor>",
                   f"{i4}  <optional>false</optional>",
                   f"{i4}</ScriptParameter>"]
    tree_id, children_id, spec_id, params_id = xid(), xid(), xid(), xid()
    params_xml = (f"{i3}<parameters id=\"{params_id}\">\n" + "\n".join(plines) + f"\n{i3}</parameters>"
                  if plines else f"{i3}<parameters id=\"{params_id}\"/>")
    # ids inside parameters were allocated before params_id; harmless, only uniqueness matters
    node = "\n".join([
        f"{ind}<TreeObject id=\"{tree_id}\">",
        f"{i2}<name>{escape(name)}</name>",
        f"{i2}<parent reference=\"{m.group(1)}\"/>",
        f"{i2}<children id=\"{children_id}\"/>",
        f"{i2}<type>SCRIPT</type>",
        f"{i2}<id>{next_tid}</id>",
        f"{i2}<specificObject class=\"Script\" id=\"{spec_id}\">",
        f"{i3}<name>{escape(name)}</name>",
        params_xml,
        f"{i3}<isManualEdit>true</isManualEdit>",
        f"{i3}<isRemoved>false</isRemoved>",
        f"{i3}<visible>true</visible>",
        f"{i2}</specificObject>",
        f"{i2}<selected>false</selected>",
        f"{i2}<link>false</link>",
        f"{i2}<removedLink>false</removedLink>",
        f"{i2}<isDirty>true</isDirty>",
        f"{ind}</TreeObject>"]) + "\n"
    if m.group(3) == "/":  # empty container: <children id=".."/>
        open_tag = m.group(0)[m.group(0).rfind("<children"):]
        xml = xml[:m.end() - len(open_tag)] + open_tag[:-2] + ">\n" + node + m.group(2) + "</children>" + xml[m.end():]
    else:
        close = xml.find(f"\n{m.group(2)}</children>", m.end())
        xml = xml[:close + 1] + node + xml[close + 1:]
    p.write_text(xml, encoding="utf-8")

    p = d / "system-gm.json"
    js = p.read_text(encoding="utf-8")
    pos = _gm_script_list(js, clu)
    sp = ", ".join(
        "{\n        " + ",\n        ".join([
            f'"name" : {json.dumps(n)}', f'"value" : {json.dumps(str(v))}', f'"defaultValue" : {json.dumps(str(v))}',
            '"extendParamType" : {\n          "restrictionValues" : [ ],\n          "restrictionValuesNames" : [ ],\n'
            f'          "paramType" : "{t}"\n        }}', '"unit" : ""', '"divisor" : 1.0']) + "\n      }"
        for n, t, v in params)
    entry = ("{\n      " + ",\n      ".join([
        f'"name" : {json.dumps(name)}', '"manualEdit" : true',
        f'"content" : "{base64.b64encode(content.encode("utf-8")).decode()}"',
        f'"scriptParams" : [ {sp} ]' if params else '"scriptParams" : [ ]']) + "\n    }")
    rest = js[pos:].lstrip()
    if rest.startswith("]"):  # "scripts" : [ ]
        js = js[:pos] + " " + entry + " " + rest
    else:  # "scripts" : [ {...}, ... ]  -> new entry first
        js = js[:pos] + " " + entry + ", " + rest
    p.write_text(js, encoding="utf-8")
    _write_script_files(d, clu, name, content)
    print(f"script {name} added on {clu} (tree id {next_tid})")


def get_feature(d, obj, feature):
    xml = (Path(d) / "system.xml").read_text(encoding="utf-8")
    s, e = _xml_feature(xml, obj, feature)
    return xml[s:e]


def set_feature(d, obj, feature, value):
    d = Path(d)
    old = get_feature(d, obj, feature)
    p = d / "system.xml"
    xml = p.read_text(encoding="utf-8")
    s, e = _xml_feature(xml, obj, feature)
    p.write_text(xml[:s] + escape(value) + xml[e:], encoding="utf-8")
    p = d / "system-gm.json"
    js = p.read_text(encoding="utf-8")
    s, e = _gm_feature(js, obj, feature)
    p.write_text(js[:s] + value.replace("\\", "\\\\").replace('"', '\\"') + js[e:], encoding="utf-8")
    if old != value:
        mark_dirty(d, obj)
    print(f"{obj}.{feature}: {old!r} -> {value!r}")
