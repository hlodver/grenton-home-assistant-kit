"""grenton: command line for a Grenton site folder (one house, described by site.yaml).

  grenton omp unpack PROJECT.omp            import an OM save or backup into project/
  grenton omp pack --out NEW.omp            build an .omp for Object Manager
  grenton omp import-workspace [WS]         import OM's live workspace (project open in OM)
  grenton omp add-event-command OBJ EVENT CMD | remove-event-command OBJ CMD
  grenton omp replace-event-command OBJ OLD NEW
  grenton omp add-script NAME FILE [--param name:NUMBER:default] [--clu CLU] | set-script NAME FILE
  grenton omp get-feature OBJ FEATURE | set-feature OBJ FEATURE VALUE
  grenton mygrenton build                   generate the myGrenton interface into project/
  grenton ha call '<ws message>' ...        raw Home Assistant websocket calls
  grenton ha sync [--apply]                 line HA up with site.yaml (dry run by default)

Options before the command: --site PATH (default: site.yaml here or in a parent folder).
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from . import omp
from . import site as site_mod


def main(argv=None):
    ap = argparse.ArgumentParser(prog="grenton", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", help="path to site.yaml")
    top = ap.add_subparsers(dest="group", required=True)

    o = top.add_parser("omp", help="Object Manager project files").add_subparsers(dest="cmd", required=True)
    u = o.add_parser("unpack"); u.add_argument("omp")
    p = o.add_parser("pack"); p.add_argument("--out", required=True)
    w = o.add_parser("import-workspace"); w.add_argument("ws", nargs="?")
    w.add_argument("--allow-delete", action="store_true")
    c = o.add_parser("add-event-command"); c.add_argument("obj"); c.add_argument("event"); c.add_argument("command")
    rc = o.add_parser("remove-event-command"); rc.add_argument("obj"); rc.add_argument("command")
    xc = o.add_parser("replace-event-command"); xc.add_argument("obj"); xc.add_argument("old"); xc.add_argument("new")
    for cmd in ("add-script", "set-script"):
        sc = o.add_parser(cmd); sc.add_argument("name"); sc.add_argument("file"); sc.add_argument("--clu")
        if cmd == "add-script":
            sc.add_argument("--param", action="append", default=[], help="name:NUMBER|STRING:default")
    g = o.add_parser("get-feature"); g.add_argument("obj"); g.add_argument("feature")
    s = o.add_parser("set-feature"); s.add_argument("obj"); s.add_argument("feature"); s.add_argument("value")

    m = top.add_parser("mygrenton", help="myGrenton interface").add_subparsers(dest="cmd", required=True)
    m.add_parser("build")

    h = top.add_parser("ha", help="Home Assistant").add_subparsers(dest="cmd", required=True)
    hc = h.add_parser("call"); hc.add_argument("messages", nargs="*"); hc.add_argument("-f", dest="file")
    hs = h.add_parser("sync"); hs.add_argument("--apply", action="store_true")

    a = ap.parse_args(argv)
    st = site_mod.load(a.site)
    d, sec = st.project_dir, st.secrets_file

    if a.group == "omp":
        clu = getattr(a, "clu", None) or st.default_clu
        if a.cmd == "unpack":
            omp.unpack(a.omp, d, sec)
        elif a.cmd == "pack":
            omp.pack(d, a.out, sec)
        elif a.cmd == "import-workspace":
            ws = a.ws or st.workspace
            if not ws:
                raise SystemExit("no workspace given and project.workspace not set in site.yaml")
            omp.import_workspace(ws, d, sec, a.allow_delete)
        elif a.cmd == "add-event-command":
            omp.add_event_command(d, a.obj, a.event, a.command)
        elif a.cmd == "remove-event-command":
            omp.remove_event_command(d, a.obj, a.command)
        elif a.cmd == "replace-event-command":
            omp.replace_event_command(d, a.obj, a.old, a.new)
        elif a.cmd in ("add-script", "set-script"):
            if not clu:
                raise SystemExit("--clu missing and project.default_clu not set in site.yaml")
            content = Path(a.file).read_text(encoding="utf-8").rstrip("\n")
            if a.cmd == "add-script":
                omp.add_script(d, clu, a.name, content, [tuple(x.split(":", 2)) for x in a.param])
            else:
                omp.set_script(d, clu, a.name, content)
        elif a.cmd == "get-feature":
            print(omp.get_feature(d, a.obj, a.feature))
        else:
            omp.set_feature(d, a.obj, a.feature, a.value)

    elif a.group == "mygrenton":
        from . import mygrenton
        mygrenton.write(st)

    else:
        if a.cmd == "sync":
            from .ha.sync import sync
            asyncio.run(sync(st, apply=a.apply))
        else:
            from .ha.client import HA
            msgs = json.load(open(a.file)) if a.file else [json.loads(x) for x in a.messages]

            async def run():
                ok = True
                async with HA(st.ha) as ha:
                    for msg in msgs:
                        r = await ha.raw(msg)
                        ok &= r.get("success", False)
                        print(json.dumps(r["result"] if r.get("success") else {"error": r.get("error"), "msg": msg},
                                         ensure_ascii=False))
                return ok
            sys.exit(0 if asyncio.run(run()) else 1)


if __name__ == "__main__":
    main()
