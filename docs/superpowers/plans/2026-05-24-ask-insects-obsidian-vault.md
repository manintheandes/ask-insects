# Ask Insects Obsidian Vault Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an Ask Insects Obsidian vault that mirrors the Ask Monarch and Ask Just public wiki setup.

**Architecture:** The Ask Insects repo owns the vault content in `wiki/`. `/Users/josh/Documents/Ask Insects Wiki` points to that folder for local Obsidian access. The vault has its own `.obsidian` config and does not borrow another site's Publish identity.

**Tech Stack:** Markdown, Obsidian vault config JSON, Obsidian Publish CSS, Ask Insects hosted source plane.

---

### Task 1: Create Vault Surface

**Files:**
- Create: `wiki/`
- Create: `/Users/josh/Documents/Ask Insects Wiki` symlink

- [x] **Step 1: Create wiki directories**

Run:

```bash
mkdir -p wiki/.obsidian wiki/Guides wiki/Sources
```

Expected: directories exist.

- [x] **Step 2: Create local Documents vault pointer**

Run:

```bash
ln -sfn /Users/josh/Documents/New\ project\ 12/wiki /Users/josh/Documents/Ask\ Insects\ Wiki
```

Expected: `/Users/josh/Documents/Ask Insects Wiki` points to the Ask Insects repo `wiki/` folder.

### Task 2: Add Publish-Ready Pages

**Files:**
- Create: `wiki/Ask Insects.md`
- Create: `wiki/Source Map.md`
- Create: `wiki/Ask Insects Updates.md`
- Create: `wiki/Guides/Team Setup.md`
- Create: `wiki/Guides/Question Cookbook.md`
- Create: `wiki/Guides/Insects Deep Research.md`
- Create: `wiki/Guides/Insects Skills.md`
- Create: `wiki/Sources/*.md`

- [x] **Step 1: Add the Ask Monarch-shaped page family**

Expected: the vault has the same visible page family as Ask Monarch and Ask Just, with Ask Insects source content.

### Task 3: Add Vault Configuration

**Files:**
- Create: `wiki/.obsidian/app.json`
- Create: `wiki/.obsidian/appearance.json`
- Create: `wiki/.obsidian/core-plugins.json`
- Create: `wiki/.obsidian/graph.json`
- Create: `wiki/.obsidian/templates.json`
- Create: `wiki/.obsidian/publish.json`
- Create: `wiki/.obsidian/workspace.json`
- Create: `wiki/publish.css`

- [x] **Step 1: Add Obsidian config**

Expected: Publish is enabled, the workspace opens on `Ask Insects.md`, and `publish.json` has no borrowed site ID.

### Task 4: Verify

**Files:**
- Read: `wiki/`
- Read: `/Users/josh/Documents/Ask Insects Wiki`

- [x] **Step 1: Check file structure**

Run:

```bash
find -L /Users/josh/Documents/Ask\ Insects\ Wiki -maxdepth 3 -type f | sort
```

Expected: home page, source map, update page, guides, source pages, `.obsidian` config, and `publish.css` are present.

- [x] **Step 2: Check source links**

Run:

```bash
python3 - <<'PY'
from pathlib import Path
root = Path('wiki')
pages = {p.relative_to(root).with_suffix('').as_posix() for p in root.rglob('*.md')}
pages |= {p.stem for p in root.rglob('*.md')}
missing = []
for path in root.rglob('*.md'):
    text = path.read_text()
    for part in text.split('[[')[1:]:
        target = part.split(']]', 1)[0].split('|', 1)[0]
        if target not in pages:
            missing.append((path.as_posix(), target))
if missing:
    raise SystemExit(missing)
print('wiki links ok')
PY
```

Expected: `wiki links ok`.
