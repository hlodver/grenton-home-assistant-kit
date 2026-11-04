# The Object Manager project file (.omp)

Observed with Object Manager 1.13.1. Other versions may differ, so check before you
rely on a detail.

## What's inside

An `.omp` is an ordinary zip archive. The entries are:

| Entry | What it is |
|---|---|
| `system.xml` | The whole project as a Java XStream object tree: CLUs, modules, objects, features, events, scripts, interfaces. **Object Manager's source of truth.** Several MB. |
| `system-gm.json` | A JSON export of the same objects (`label`, `projectKey`, `clus[]`). Easier to read than the XML. Object Manager regenerates it, but edits must keep it in step with `system.xml`. |
| `properties.xml` | Project settings, including the **project cipher key and IV** that the CLUs accept. Treat it as a secret. |
| `scripts/<CLU>/<name>.lua` (+ `.lua.vd`) | Script sources. The `.vd` is a serialized visual-script diagram. |
| `nodes/<id>/data.json` | myGrenton interfaces (see [mygrenton-format.md](mygrenton-format.md)). |
| `diagnostics/<CLU serial>/om.lua/*` | Every `om.lua` Object Manager has read from or written to each CLU, timestamped (`*_W_om.lua` = written). |

`om.lua` is the compiled configuration that runs on a CLU. It's readable Lua: objects,
settings (`:set(index, value)`) and event handlers. Diffing the newest `*_W_om.lua`
against the previous one shows exactly what a send changed. That makes it the best way
to verify a send.

## Keeping it in git

`grenton omp unpack` extracts the zip into `project/` and records what's needed to
rebuild it byte for byte in `project/.omp-manifest.json`: entry order, timestamps,
compression, attributes and the zip comment. `grenton omp pack` rebuilds the archive.
With no changes, the result is byte-identical to the original, so every real change
shows up as a readable diff.

The project key never goes into git. On the way in, the key and IV in `properties.xml`
and `system-gm.json` are replaced with `${GRENTON_PROJECT_KEY}` and
`${GRENTON_PROJECT_IV}`. The real values live in `secrets/grenton.env`, and `pack` puts
them back only in the `.omp` it writes. `.omp` files contain the key, so never commit them.

## Object Manager's workspace

While a project is open, Object Manager works on an unpacked copy in its workspace folder.
On macOS that's inside the app bundle:
`/Applications/Object Manager <version>.app/Contents/MacOS/workspace/<project>/`. The
layout is the same as `project/`.

- **Object Manager deletes the workspace when the project is closed.**
  `grenton omp import-workspace` only works while the project is open.
- Import after every send and every change made in Object Manager, so git records what
  Object Manager did.
- An import brings back whatever version Object Manager has open. If an older file was
  opened, the import overwrites newer content. Check `git diff` after every import.

## Editing safely

- **XStream ids:** elements carry `id="n"` and refer to each other with
  `reference="n"`. New elements need ids above the current maximum, and tree nodes need
  a numeric `<id>` above the current maximum as well.
- **Object Manager renumbers every XStream id when it saves.** Never text-merge an
  Object Manager save with your own edits. Import Object Manager's version, then
  re-apply your edits with the tools; that's why they are scripts and not patches.
- **What gets sent:** Object Manager decides what to send from the `<isDirty>` flags on
  tree nodes. `grenton omp` sets the flag on what it changes. If Object Manager still
  says "configuration up-to-date", answer Yes to resend; it rebuilds everything from
  the project.
- **Scripts:** Object Manager loads script text from `scripts/<CLU>/<name>.lua`. The
  base64 copy in `system-gm.json` alone opens as an empty script, and the script is
  removed from the CLU. `add-script` and `set-script` write both.
- **Features** (initial values) live in `system.xml` as `<initValue>` and in
  `system-gm.json` as `"initValue"`. `set-feature` changes both and nothing else.
- To learn the XML for something new, make the change once in Object Manager, import,
  and diff.
