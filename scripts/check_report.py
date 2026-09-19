"""Run the TEMPLATE-lab-report.md pre-publication checklist against a report.

Mechanical checks only -- the voice rules need reading, but 'no sequence
narration' and 'no retraction tally' have recognisable surface forms, and
link/asset resolution is purely mechanical. Catching those here leaves human
attention for the claims.
"""
import os
import re
import subprocess
import sys

SRC = "/home/user/code/regular-labs"
SLUG = "2026-09-19-h3-reference-video-consistency"
MD = f"{SRC}/src/{SLUG}.md"
HTML = f"{SRC}/site/{SLUG}.html"

text = open(MD).read()
fails, warns = [], []

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

# --- required sections ----------------------------------------------------
for heading in ["## The question", "## Method", "## Results", "## Cost",
                "## What this does not settle"]:
    if heading not in text:
        fails.append(f"missing section: {heading}")

# --- cost must include calendar time -------------------------------------
cost = text.split("## Cost", 1)[-1].split("##", 1)[0]
if not re.search(r"calendar", cost, re.I):
    fails.append("Cost section does not mention calendar time")

# --- limitations must say what is NOT supported --------------------------
lim = text.split("## What this does not settle", 1)[-1].split("##", 1)[0]
if len(lim.strip()) < 200:
    warns.append("limitations section is very short")

# --- build, then resolve every asset and internal link -------------------
subprocess.run(["pnpm", "run", "build"], cwd=SRC, capture_output=True, check=True)
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
index = open(f"{SRC}/src/index.md").read()
reports = index.split("## Reports", 1)[-1].split("## Journal", 1)[0]
if SLUG not in reports:
    fails.append("not listed under ## Reports in index.md")
feed = open(f"{SRC}/site/feed.xml").read()
if SLUG not in feed:
    fails.append("not present in feed.xml")

# --- numbers in prose must appear in the committed data ------------------
data = ""
for f in os.listdir(f"{SRC}/src/files/{SLUG}"):
    if f.endswith(".json"):
        data += open(f"{SRC}/src/files/{SLUG}/{f}").read()
for n in ["33.02","6.01","0.50","2.32","26.53","8.91","4.91","81.8","364",
          "3.81","7.27","21.41","42.68","0.34","0.66","1.45","3.79",
          "23.9","30.4","14.2","19.4","7.16","82041",
          "3.85","3.99","17.81","12.58","24.58","7.91","67.8","29.4","3.6",
          "1.81","2.56","2.61","22.44","22.82","23.22","56.7","79.0","79.3",
          "14.95","21.67","23.5","23.7","4.15","4.80","14.10","18.20","0.2"]:
    if n not in data:
        fails.append(f"prose number {n} not found in committed data files")

for w in warns:
    print("WARN ", w)
for f in fails:
    print("FAIL ", f)
print()
if fails:
    print(f"CHECKLIST FAILED: {len(fails)} problem(s)")
    sys.exit(1)
print(f"CHECKLIST PASSED ({len(warns)} warning(s))")
