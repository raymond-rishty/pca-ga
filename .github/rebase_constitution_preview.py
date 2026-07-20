from pathlib import Path
import subprocess

BACKUP = "agent/preserve-constitution-preview-formatting-backup"

subprocess.run(["git", "fetch", "origin", BACKUP], check=True)
old_script = subprocess.run(
    ["git", "show", f"origin/{BACKUP}:scripts/44_link_constitution_refs.py"],
    check=True,
    capture_output=True,
    text=True,
).stdout
if "def render_section_body(" not in old_script:
    raise SystemExit("Backup branch does not contain structured BCO rendering")
Path("scripts/44_link_constitution_refs.py").write_text(old_script, encoding="utf-8")

css_path = Path("assets/constitution-links.css")
css = css_path.read_text(encoding="utf-8").rstrip()
structured = (
    ".constitution-sheet__body .lead{margin:0 0 .75em}"
    ".constitution-sheet__body .bpara{margin:.75em 0}"
    ".constitution-sheet__body .li{margin:.48em 0;padding-left:1.55em;text-indent:-1.55em}"
    ".constitution-sheet__body .mk{font-weight:600;color:var(--ink);margin-right:.15em}"
    ".constitution-sheet__body .d1{margin-left:1.35em}"
    ".constitution-sheet__body .d2{margin-left:2.7em}"
    ".constitution-sheet__body .d3{margin-left:4.05em}"
    ".constitution-sheet__body .d4{margin-left:5.4em}"
)
if ".constitution-sheet__body .lead{" not in css:
    css += "\n" + structured
css_path.write_text(css + "\n", encoding="utf-8")

sw_path = Path("sw.js")
sw = sw_path.read_text(encoding="utf-8")
if "const CACHE = 'pca-ga-v10';" not in sw:
    raise SystemExit("Expected current main cache version pca-ga-v10")
sw_path.write_text(
    sw.replace("const CACHE = 'pca-ga-v10';", "const CACHE = 'pca-ga-v11';", 1),
    encoding="utf-8",
)
