"""grenton init: create a site repo for one house, optionally from an OM project file."""
import glob
import shutil
import subprocess
from datetime import date
from importlib import resources
from pathlib import Path

from . import discover, omp
from .site import slugify

TEMPLATES = resources.files("grenton_kit") / "templates"


def find_workspace(label):
    """OM's live workspace for a project, where OM keeps it on this machine (macOS: in the app)."""
    pats = ["/Applications/Object Manager*.app/Contents/MacOS/workspace/*",
            str(Path.home() / "Applications/Object Manager*.app/Contents/MacOS/workspace/*")]
    for pat in pats:
        for p in sorted(glob.glob(pat), reverse=True):  # newest OM version first
            if Path(p).name == label:
                return Path(p)
    return None


def write_discovery(project_dir, site_dir, workspace=None):
    """inventory.md, plus site.yaml if there is none yet (else site.draft.yaml). Returns the files written."""
    inv = discover.inventory(project_dir)
    site_dir = Path(site_dir)
    (site_dir / "inventory.md").write_text(discover.report(inv), encoding="utf-8")
    draft = discover.draft_site(inv, project_dir)
    if workspace:
        draft = draft.replace("  secrets: secrets/grenton.env\n",
                              f"  secrets: secrets/grenton.env\n  workspace: {workspace}\n", 1)
    target = site_dir / ("site.draft.yaml" if (site_dir / "site.yaml").exists() else "site.yaml")
    target.write_text(draft, encoding="utf-8")
    return inv, ["inventory.md", target.name]


def init(folder, omp_file=None, git=True):
    folder = Path(folder).expanduser().resolve()
    if folder.exists() and any(p.name != ".git" for p in folder.iterdir()):
        raise SystemExit(f"{folder} is not empty")
    (folder / "docs").mkdir(parents=True, exist_ok=True)
    (folder / ".claude" / "skills" / "onboard").mkdir(parents=True, exist_ok=True)
    (folder / "secrets").mkdir(mode=0o700, exist_ok=True)

    inv, written = None, []
    if omp_file:
        sec = folder / "secrets" / "grenton.env"
        omp.secrets_from_omp(omp_file, sec)
        omp.unpack(omp_file, folder / "project", sec)
        label = discover.inventory(folder / "project")["label"]
        inv, written = write_discovery(folder / "project", folder, find_workspace(label))

    name = (inv or {}).get("label") or folder.name
    fmt = {"date": date.today().isoformat(), "name": name, "slug": slugify(name) or "site",
           "source": f" from `{Path(omp_file).name}`" if omp_file else "",
           "imported": "x" if omp_file else " "}
    (folder / ".gitignore").write_text((TEMPLATES / "gitignore").read_text())
    (folder / "README.md").write_text((TEMPLATES / "README.md").read_text().format(**fmt))
    (folder / "CLAUDE.md").write_text((TEMPLATES / "CLAUDE.md").read_text())
    for doc in ("STATUS.md", "LOG.md"):
        (folder / "docs" / doc).write_text((TEMPLATES / "docs" / doc).read_text().format(**fmt))
    (folder / "docs" / "LESSONS.md").write_text((TEMPLATES / "docs" / "LESSONS.md").read_text())
    (folder / ".claude" / "skills" / "onboard" / "SKILL.md").write_text(
        (TEMPLATES / "skills" / "onboard" / "SKILL.md").read_text())

    if git and shutil.which("git"):
        run = lambda *a: subprocess.run(["git", *a], cwd=folder, check=True, capture_output=True, text=True)  # noqa: E731
        if not (folder / ".git").exists():
            run("init", "-q", "-b", "main")
        run("add", "-A")
        staged = run("diff", "--cached", "--name-only").stdout.split()
        leaked = [f for f in staged if f.startswith("secrets/") or f.endswith(".omp")]
        if leaked:
            raise SystemExit(f"refusing to commit secrets: {leaked}")
        message = f"grenton init{fmt['source'].replace('`', '')}"
        has_identity = subprocess.run(["git", "var", "GIT_COMMITTER_IDENT"], cwd=folder,
                                      capture_output=True).returncode == 0
        if has_identity:
            run("commit", "-q", "-m", message)
        else:  # a fresh machine: git has no user.name / user.email yet
            print("  git has no user name/email yet, so the files are staged but not committed. Run:\n"
                  '    git config --global user.name "Your Name"\n'
                  '    git config --global user.email you@example.com\n'
                  f'    git -C "{folder}" commit -m "{message}"')

    print(f"site repo: {folder}")
    if inv:
        print(f"  project: {len(inv['lights'])} lights, {len(inv['relays'])} relays, "
              f"{len(inv['thermostats'])} thermostats, {len(inv['clus'])} CLUs; wrote {', '.join(written)}")
    print("  next: cd there and run /onboard in Claude Code, or edit site.yaml and run grenton mygrenton build")
    return folder
