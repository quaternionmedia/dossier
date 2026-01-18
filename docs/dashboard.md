# TUI Dashboard Guide

[← Back to Index](index.md) | [Quickstart](quickstart.md) | [Workflows →](workflows.md)

---

The Dossier TUI Dashboard is a full-featured terminal interface for browsing, managing, and exploring your project portfolio. This guide covers all features, keyboard shortcuts, and workflows.

## Quick Start

```bash
# Launch the dashboard
uv run dossier dashboard
```

**First time?** Sync some projects first:
```bash
# Sync your GitHub repos, then launch
uv run dossier github sync-user YOUR_USERNAME
uv run dossier dashboard
```

---

## Interface Overview

```
┌────────────────────────────────────────────────────────────────────────────┐
│ Dossier Dashboard                                            📊 5 projects │
├──────────────────────┬─────────────────────────────────────────────────────┤
│ 🏢 astral-sh (2)     │ Dossier │ Details │ Docs │ Lang │ ... │            │
│   🔄 ruff ⭐12000    │─────────────────────────────────────────────────────│
│     📚 Docs (5)      │                                                     │
│       📝 README.md   │  # astral-sh/ruff                                   │
│       📝 docs/...    │                                                     │
│   🔄 uv ⭐8000       │  Fast Python linter written in Rust                 │
│ 🏢 pallets (1)       │                                                     │
│   ○ flask            │  ⭐ 12,000 stars | 🍴 2,000 forks                   │
│ 👤 Users (2)         │  📝 MIT License | 🐍 Python, Rust                   │
│   github/user/...    │                                                     │
│ 💻 Languages (3)     │  Dependencies: pydantic, click, ...                 │
│   lang/python        │                                                     │
│ 📦 Packages (5)      │                                                     │
│   pkg/fastapi        │                                                     │
├──────────────────────┴─────────────────────────────────────────────────────┤
│ 🔍 Search... or :cmd (try :help)  [Sync] [Add] [Del] [?]                   │
├────────────────────────────────────────────────────────────────────────────┤
│ q Quit │ s Sync │ a Add │ d Delete │ o Open │ / Search │ f Filter │ ? Help │
└────────────────────────────────────────────────────────────────────────────┘
```

### Layout

| Panel | Description |
|-------|-------------|
| **Left: Project Tree** | Hierarchical browser organized by org/category |
| **Right: Tab Panels** | 11 tabs with project details |
| **Bottom: Command Bar** | Search, vim-style commands, action buttons |
| **Footer: Key Bindings** | Quick reference for keyboard shortcuts |

---

## Project Tree (Left Panel)

The project tree automatically organizes projects hierarchically:

### Organization Grouping

```
🏢 astral-sh (3)              # GitHub org/owner
  🔄 ruff ⭐12000             # Synced repo with star count
    📚 Docs (5)               # Documentation folder
      📝 README.md            # Click to open viewer
      📝 docs/guide.md
  🔄 uv ⭐8000
  ○ some-repo                 # Not yet synced
```

### Entity Categories

```
👤 Users (2)                  # GitHub user entities
  github/user/astral-sh
  github/user/charlie
💻 Languages (3)              # Global language entities
  lang/python
  lang/rust
  lang/typescript
📦 Packages (5)               # Global package entities
  pkg/fastapi
  pkg/click
  pkg/pydantic
📁 Other (1)                  # Uncategorized projects
  standalone-project
```

### Tree Icons

| Icon | Meaning |
|------|---------|
| 🏢 | Organization/owner group |
| 📂 | Subgroup (repo with entities) |
| 🔄 | Synced project |
| ○ | Not synced |
| ⭐ | Star count |
| 📚 | Documentation folder |
| 📝 | Markdown file |
| 📄 | Other doc file |
| 👤 | User entity |
| 💻 | Language entity |
| 📦 | Package entity |

### Navigating the Tree

| Key | Action |
|-----|--------|
| `↑` / `↓` or `j` / `k` | Move up/down |
| `Enter` | Expand/collapse or select |
| `→` | Expand node |
| `←` | Collapse node |
| `/` | Focus search |

---

## Tab Panels (Right Panel)

### Tab 1: Dossier

Formatted project overview showing:
- Project name and description
- GitHub stats (stars, forks, watchers)
- License and primary language
- Component tree (languages, dependencies, contributors)

### Tab 2: Details

Raw project metadata:
- Full name, description
- Repository URL (clickable)
- GitHub owner/repo
- Sync timestamps
- Creation/update dates

### Tab 3: Documentation

**Tree view** of docs grouped by source file:

```
📝 README.md (3)
  📖 Overview
  🔧 Installation
  💡 Usage
📝 docs/guide.md (2)
  📚 Getting Started
  📚 Advanced Usage
```

**Click any doc** to open the content viewer with prev/next navigation.

### Tab 4: Languages

Language breakdown table:
- Language name
- File extensions
- Encoding
- Bytes count
- Percentage

**Click a language row** to navigate to its entity project (`lang/python`).

### Tab 5: Branches

Repository branches:
- Branch name
- Default/protected status
- Latest commit SHA
- Commit message
- Author
- Date

**Click a branch row** to navigate to its entity (`owner/repo/branch/main`).

### Tab 6: Dependencies

Dependencies from manifest files:
- Package name
- Version spec
- Type (runtime, dev, optional)
- Source (pyproject.toml, package.json, etc.)

**Click a dependency row** to navigate to its entity (`pkg/fastapi`).

### Tab 7: Contributors

Top contributors by commit count:
- Username
- Contribution count
- Profile URL

Contributors are view-only (no click action).

### Tab 8: Issues

Open and closed issues:
- Issue number
- Title
- State (open/closed)
- Author
- Labels

**Click an issue row** to navigate to its entity (`owner/repo/issue/123`).

### Tab 9: Pull Requests

Pull requests with:
- PR number
- Title
- State (open/closed/merged)
- Author
- Additions/deletions

**Click a PR row** to navigate to its entity (`owner/repo/pr/456`).

### Tab 10: Releases

Version releases:
- Tag name
- Release name
- Date
- Prerelease flag

**Click a release row** to navigate to its entity (`owner/repo/ver/v1.0.0`).

### Tab 11: Components

Parent-child project relationships:
- Child project name
- Relationship type
- Description

**Click a component row** to navigate to that project.

---

## Content Viewer

Click on documentation in the tree or docs tab to open the **Content Viewer**:

```
┌─────────────────────────────────────────────────────────────────┐
│ 📄 docs/quickstart.md                                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  # Quick Start                                                  │
│                                                                 │
│  Get running in 5 minutes...                                    │
│                                                                 │
│  ## Installation                                                │
│  ```bash                                                        │
│  uv sync                                                        │
│  ```                                                            │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│ [Close] [🌐 Browser]        2/5        [◀ Prev] [Next ▶]        │
└─────────────────────────────────────────────────────────────────┘
```

### Viewer Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `q` or `Esc` | Close viewer |
| `n` or `j` | Next document |
| `p` or `k` | Previous document |
| `o` | Open in browser |

### Viewer Features

- **File path in title** - Shows the actual file path being viewed
- **Prev/Next navigation** - Browse through related documents
- **Counter display** - Shows current position (e.g., "2/5")
- **Open in browser** - Jump to GitHub for full context

---

## Keyboard Shortcuts

### Global Shortcuts

| Key | Action |
|-----|--------|
| `q` | Quit dashboard |
| `r` | Refresh project list |
| `s` | Sync selected project(s) |
| `a` | Add new project |
| `d` | Delete selected project(s) |
| `o` | Open GitHub in browser |
| `l` | Link selected tree item as project |
| `c` | Add component relationship |
| `/` | Focus search/command bar |
| `f` | Cycle filter (All → Synced → Unsynced → Starred) |
| `?` | Show help |
| `Tab` | Navigate between panels |

### Multi-Selection

| Key | Action |
|-----|--------|
| `Space` | Toggle select current project |
| `Ctrl+A` | Select all visible projects |
| `Escape` | Clear selection |
| `Ctrl+Click` | Toggle select clicked project |
| `Shift+Click` | Toggle select clicked project |

### Navigation

| Key | Action |
|-----|--------|
| `↑` / `↓` | Move up/down in tree |
| `j` / `k` | Move up/down (vim-style) |
| `←` / `→` | Collapse/expand tree node |
| `Enter` | Select/expand node |
| `Tab` | Next panel |
| `Shift+Tab` | Previous panel |

---

## Command Bar

The command bar at the bottom supports both search and vim-style commands.

### Search

Type to filter projects by name or description:

```
🔍 fastapi           # Filters to projects containing "fastapi"
```

### Vim-Style Commands

Prefix with `:` to run commands:

| Command | Action |
|---------|--------|
| `:q` | Quit |
| `:r` | Refresh |
| `:s` | Sync selected |
| `:sync owner/repo` | Sync specific repo |
| `:add owner/repo` | Add project |
| `:filter synced` | Filter to synced projects |
| `:filter unsynced` | Filter to unsynced projects |
| `:filter starred` | Filter to starred projects |
| `:filter all` | Clear filter |
| `:sort name` | Sort by name |
| `:sort stars` | Sort by star count |
| `:sort synced` | Sort by sync date |
| `:clear` | Clear search |
| `:help` | Show help |

### Examples

```bash
# Search for Python projects
python

# Sync a specific repo
:sync astral-sh/ruff

# Filter to only synced projects
:filter synced

# Sort by stars
:sort stars

# Add a new project
:add pallets/flask
```

---

## Workflows

### Browse Your Projects

```bash
# Launch and explore
uv run dossier dashboard

# In the dashboard:
# 1. Use ↑/↓ to navigate the project tree
# 2. Press Enter to expand org folders
# 3. Tab to switch to detail panels
# 4. Use number keys or Tab to switch tabs
```

### Read Documentation

```bash
# 1. Select a project in the tree
# 2. Expand the 📚 Docs folder
# 3. Click any doc to open viewer
# 4. Use n/p to navigate between docs
# 5. Press q to close
```

### Sync Multiple Projects

```bash
# 1. Navigate to projects you want to sync
# 2. Press Space to select each one
#    OR press Ctrl+A to select all
# 3. Press 's' to sync all selected
```

### Search and Filter

```bash
# 1. Press '/' to focus search
# 2. Type search term (e.g., "api")
# 3. Press Enter to filter
# 4. Press 'f' to cycle through filters
# 5. Type ':clear' to reset
```

### Navigate Entities

```bash
# 1. Select a project
# 2. Go to Dependencies tab
# 3. Click a dependency (e.g., "fastapi")
# 4. Dashboard navigates to pkg/fastapi entity
# 5. Use browser back or select different project
```

---

## Tips & Tricks

### Speed Navigation

- **Learn the tabs**: Dossier, Details, Docs, Lang, Branch, Deps, People, Issues, PRs, Releases, Links
- **Use Tab key**: Quickly cycle through panels
- **Vim keys work**: `j`/`k` for up/down, `/` for search

### Efficient Syncing

- **Batch sync**: Select multiple with `Space`, then `s`
- **Force refresh**: Use `:sync owner/repo` to re-sync
- **Filter first**: `:filter unsynced` then `Ctrl+A`, `s`

### Quick Access

- **Search by name**: Just start typing in command bar
- **Open in browser**: Press `o` on any project
- **View docs**: Expand tree → click doc → browse with `n`/`p`

### Keyboard-Only Workflow

```
/search → Enter → ↓↓↓ → Enter → Tab → (browse tabs) → o → q
```

---

## Troubleshooting

### "No projects found"

```bash
# Sync some projects first
uv run dossier github sync-user YOUR_USERNAME

# Then relaunch
uv run dossier dashboard
```

### Tree not updating

Press `r` to refresh, or use `:r` in command bar.

### Can't see all tabs

Use `Tab` key to navigate, or resize terminal window wider.

### Viewer not opening

Make sure you're clicking on a doc node (📝), not a folder (📚).

---

## Related Documentation

- [Quickstart](quickstart.md) — Installation and first steps
- [Workflows](workflows.md) — Copy-paste command examples
- [Architecture](architecture.md) — How the TUI is built
- [Keyboard Reference](#keyboard-shortcuts) — Full shortcut list

