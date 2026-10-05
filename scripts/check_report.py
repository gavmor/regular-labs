"""Run the TEMPLATE-lab-report.md pre-publication checklist against ONE report.

Mechanical checks only -- the voice rules need reading, but 'no sequence
narration' and 'no retraction tally' have recognisable surface forms, and
link/asset resolution is purely mechanical. Catching those here leaves human
attention for the claims.

Scope is deliberately one report (the slug argument). The deploy workflow runs
this only against reports *changed in the push*, so the historical corpus is
grandfathered and the template is enforced going forward.

Usage:
    python scripts/check_report.py <slug>
    python scripts/check_report.py src/<slug>.md   # a path is also accepted

Repo root is resolved from this file's location, or $REGULAR_LABS_ROOT, so the
check runs identically on a dev box and on a CI runner.
"""
import os
import re
import subprocess
import sys

ROOT = os.environ.get("REGULAR_LABS_ROOT") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

raw = sys.argv[1] if len(sys.argv) > 1 else "2026-09-19-h3-reference-video-consistency"
# Accept a bare slug, a src/<slug>.md path, or any path ending in the file.
SLUG = re.sub(r"^src/", "", raw)
SLUG = re.sub(r"\.md$", "", os.path.basename(SLUG)) if raw.endswith(".md") else SLUG
MD = f"{ROOT}/src/{SLUG}.md"
HTML = f"{ROOT}/site/{SLUG}.html"

if not os.path.exists(MD):
    print(f"FAIL  report not found: {MD}")
    sys.exit(1)

text = open(MD).read()
fails, warns = [], []

# A copy with fenced code blocks removed, so a heading quoted in prose or shown
# inside a ``` block does not count as the section itself existing. Section
# detection runs against this; voice/link checks run against the original.
scan = re.sub(r"^```.*?^```\s*$", "", text, flags=re.S | re.M)


def hpos(heading):
    """Byte offset of a heading that stands alone on its own line, else -1."""
    m = re.search(rf"^{re.escape(heading)}\s*$", scan, re.M)
    return m.start() if m else -1


def body(heading):
    """Text from a heading to the next '## ' heading (empty if absent)."""
    i = hpos(heading)
    if i == -1:
        return ""
    rest = scan[i + len(heading):]
    nxt = re.search(r"^## ", rest, re.M)
    return rest[:nxt.start()] if nxt else rest


# --- voice: sequence narration and retraction tallies ---------------------
BANNED = [
    r"\bI originally\b", r"\bI first published\b", r"\bwhere I got it wrong\b",
    r"\bI initially\b", r"\bit took .{0,40}before I\b", r"\bI had been\b",
    r"\bCorrections?\b\s*$", r"\bretracted?\b", r"\bearlier I\b",
    r"\bturned out to be wrong\b", r"\bmy mistake\b", r"\bI was wrong\b",
]
for pat in BANNED:
    for m in re.finditer(pat, text, re.I | re.M):
        line = text[:m.start()].count("\n") + 1
        fails.append(f"voice: {pat!r} at line {line}: {m.group(0)!r}")

# --- status line: a line starting with *Status: near the top --------------
if not re.search(r"^\*Status:", text, re.M):
    fails.append("missing status line (expected a line starting with '*Status:')")

# --- required sections, IN ORDER ------------------------------------------
# These six headings are fixed: exact text, canonical order. The one free slot
# is the interpretation section (any title) between Results and 'What this does
# not settle' -- intentionally not checked here.
REQUIRED = [
    "## The question",
    "## Method",
    "## Results",
    "## What this does not settle",
    "## Cost",
    "## Files",
]
positions = {}
for heading in REQUIRED:
    idx = hpos(heading)
    if idx == -1:
        fails.append(f"missing section: {heading}")
    else:
        positions[heading] = idx
present = [h for h in REQUIRED if h in positions]
if any(positions[h] < positions[a] for a, h in zip(present, present[1:])):
    fails.append(
        "sections out of canonical order: expected "
        + " -> ".join(h.replace("## ", "") for h in REQUIRED)
    )

# --- cost must include calendar time -------------------------------------
if not re.search(r"calendar", body("## Cost"), re.I):
    fails.append("Cost section does not mention calendar time")

# --- limitations must say what is NOT supported --------------------------
if len(body("## What this does not settle").strip()) < 200:
    warns.append("limitations section is very short")

# --- generative/pipeline reports must link to a downloadable workflow -----
if re.search(r"\b(?:comfyui|diffusion|t2i|turnaround)\b", text, re.I) and "## Files" in positions:
    if not re.search(rf"files/{SLUG}/[^\s)]+\.(?:json|api\.json|py)", body("## Files")):
        fails.append("generative report missing downloadable workflow/script link in ## Files")

# --- build, then resolve every asset and internal link -------------------
env = dict(os.environ, PATH=f"/home/user/.local/share/pnpm:/home/user/.local/share/mise/shims:{os.environ.get('PATH', '')}")
subprocess.run(["pnpm", "run", "build"], cwd=ROOT, capture_output=True, check=True, env=env)
if not os.path.exists(HTML):
    fails.append(f"built page missing: {HTML}")
else:
    html = open(HTML).read()
    for ref in re.findall(r'(?:href|src)="([^"#:]+?)"', html):
        if ref.startswith(("http", "//", "mailto")) or ref.rstrip("/").endswith("changelog"):
            continue
        target = os.path.normpath(os.path.join(os.path.dirname(HTML), ref))
        if not os.path.exists(target):
            fails.append(f"dead ref: {ref}")

    # every figure must carry alt text
    for img in re.findall(r"<img[^>]*>", html):
        if 'alt=""' in img or "alt=" not in img:
            fails.append(f"image without alt text: {img[:80]}")

# --- indexed under Reports, and present in the feed ----------------------
index = open(f"{ROOT}/src/index.md").read()
reports = index.split("## Reports", 1)[-1].split("## Journal", 1)[0]
if SLUG not in reports:
    fails.append("not listed under ## Reports in index.md")
feed = open(f"{ROOT}/site/feed.xml").read()
if SLUG not in feed:
    fails.append("not present in feed.xml")

for w in warns:
    print("WARN ", w)
for f in fails:
    print("FAIL ", f)
print()
if fails:
    print(f"CHECKLIST FAILED: {len(fails)} problem(s)")
    sys.exit(1)
print(f"CHECKLIST PASSED ({len(warns)} warning(s))")
