# Settings Overlay

[← Back to Index](index.md) | [Dashboard Guide](dashboard.md) | [Architecture →](architecture.md)

---

Press `` ` `` (backtick) anywhere in the dashboard to open the settings overlay.

## Quick Access

```bash
# In the dashboard, press backtick to open settings
`
```

---

## Interface Overview

```
┌─────────────────────────────────────────────────────────────────┐
│ ⚙️  App Info                                                    │
├─────────────────────────────────────────────────────────────────┤
│ Version:      0.1.0                                             │
│ Python:       3.13.3                                            │
│ Platform:     Windows 10                                        │
│ Database:     C:\Users\you\.dossier\dossier.db                  │
│ DB Size:      2.4 MB                                            │
│ Projects:     42                                                │
│ Config:       C:\Users\you\.dossier\config.json                 │
├─────────────────────────────────────────────────────────────────┤
│ 🎨 Theme                                                        │
│ ○ Textual Dark  ○ Textual Light  ○ Nord  ...                    │
├─────────────────────────────────────────────────────────────────┤
│ 📋 Default Tab                                                  │
│ ● Dossier  ○ Details  ○ Documentation  ...                      │
├─────────────────────────────────────────────────────────────────┤
│ 🔄 Sync Preferences                                             │
│ Batch size: [10]     Delay (seconds): [1.0]                     │
├─────────────────────────────────────────────────────────────────┤
│ 📁 Export Format                                                │
│ ● YAML (.dossier)  ○ JSON (.json)                               │
├─────────────────────────────────────────────────────────────────┤
│              [Reset Defaults]  [Close]                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## App Info Section

The settings overlay displays useful debugging and system information:

| Field | Description |
|-------|-------------|
| **Version** | Current Dossier version |
| **Python** | Python interpreter version |
| **Platform** | Operating system and release |
| **Database** | Full path to SQLite database file |
| **DB Size** | Size of database on disk (B, KB, or MB) |
| **Projects** | Total number of projects in database |
| **Config** | Path to configuration file |

This information is useful for:
- Debugging issues
- Reporting bugs
- Verifying installation
- Checking database and config locations

---

## Theme Selection

Dossier supports 9 built-in themes. Select a theme by clicking or using arrow keys:

### Dark Themes

| Theme | Description |
|-------|-------------|
| **Textual Dark** | Default dark theme (Textual's built-in) |
| **Nord** | Arctic, bluish color palette |
| **Gruvbox** | Retro groove with warm colors |
| **Catppuccin Mocha** | Soothing pastel dark theme |
| **Dracula** | Dark theme with vibrant colors |
| **Tokyo Night** | Dark theme inspired by Tokyo lights |
| **Monokai** | Classic Sublime Text inspired |

### Light Themes

| Theme | Description |
|-------|-------------|
| **Textual Light** | Default light theme |
| **Solarized Light** | Precision colors for light backgrounds |

### Changing Themes

1. Press `` ` `` to open settings
2. Use `↑`/`↓` or click to select a theme
3. Theme applies immediately and **auto-saves**
4. Press **Close** or `Escape` to dismiss

**All settings auto-save** — changes are persisted to `~/.dossier/config.json` immediately when you make them.

---

## Default Tab

Choose which tab opens when you select a project:

| Tab | Description |
|-----|-------------|
| **Dossier (Main)** | Formatted overview with component tree (default) |
| **Projects > Details** | Raw project metadata |
| **Projects > Documentation** | Parsed doc sections |
| **Projects > Languages** | Language breakdown |
| **Projects > Branches** | Repository branches |
| **Projects > Dependencies** | Package dependencies |
| **Projects > Contributors** | Top contributors |
| **Projects > Issues** | GitHub issues |
| **Projects > Pull Requests** | PRs with diff stats |
| **Projects > Releases** | Version releases |
| **Projects > Components** | Project relationships |
| **Deltas (Main)** | Delta list with phases, notes, and links |


---

## Sync Preferences

Configure batch operations for GitHub sync:

| Setting | Default | Description |
|---------|---------|-------------|
| **Batch size** | 10 | Number of repos to sync per batch |
| **Delay** | 1.0 | Seconds between batches (rate limiting) |

Adjust these if you're hitting rate limits or want faster syncing.

---

## Export Format

Choose the default format for project exports:

| Format | Extension | Description |
|--------|-----------|-------------|
| **YAML** | `.dossier` | Human-readable, standard Dossier format |
| **JSON** | `.json` | Machine-readable, compact |

---

## Auto-Save Behavior

All settings **auto-save immediately** when changed. There's no need to manually save.

Settings are persisted to `~/.dossier/config.json`.

| Button | Action |
|--------|--------|
| **Reset Defaults** | Reset all settings to factory defaults |
| **Close** | Close the settings overlay |

**Note:** Clicking **Reset Defaults** will immediately revert all settings and save the defaults.

---

## Configuration File

Settings are stored in JSON format at `~/.dossier/config.json`:

```json
{
  "theme": "catppuccin-mocha",
  "default_tab": "tab-dossier",
  "tree_density": "comfortable",
  "sync_batch_size": 10,
  "sync_delay": 1.0,
  "export_format": "yaml",
  "sidebar_width": null
}
```

You can edit this file directly, but changes only take effect when you restart the dashboard.

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `` ` `` | Open settings overlay |
| `↑` / `↓` | Navigate options |
| `Enter` / `Space` | Select option |
| `Tab` | Move between sections |
| `Escape` | Close settings |
| `q` | Close settings |

---

## Related Documentation

- [Dashboard Guide](dashboard.md) — Full TUI documentation including frogmouth integration
- [Quickstart](quickstart.md) — Installation and first steps
- [Architecture](architecture.md) — System design details

---

## Optional Dependencies

### Frogmouth Viewer

Install frogmouth for enhanced markdown viewing:

```bash
# Install separately (has older textual/httpx constraints)
pip install frogmouth
```

Once installed, the Content Viewer gains a "🐸 Frogmouth" button that opens documents in the frogmouth terminal markdown viewer.

See the [Dashboard Guide](dashboard.md) for more details.
