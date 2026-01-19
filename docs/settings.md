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
│           [Save]  [Reset]  [Close]                              │
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
3. Theme applies immediately (preview)
4. Click **Save** to persist the theme
5. Press **Close** or `Escape` to dismiss

---

## Default Tab

Choose which tab opens when you select a project:

| Tab | Description |
|-----|-------------|
| **Dossier** | Formatted overview with component tree (default) |
| **Details** | Raw project metadata |
| **Documentation** | Parsed doc sections |
| **Languages** | Language breakdown |
| **Branches** | Repository branches |
| **Dependencies** | Package dependencies |
| **Contributors** | Top contributors |
| **Issues** | GitHub issues |
| **Pull Requests** | PRs with diff stats |
| **Releases** | Version releases |
| **Components** | Project relationships |

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

## Saving Settings

Settings are saved to `~/.dossier/config.json`.

| Button | Action |
|--------|--------|
| **Save** | Persist all settings to config file |
| **Reset** | Reset all settings to defaults |
| **Close** | Close without saving (changes are lost) |

**Note:** Theme changes preview immediately but are only saved when you click **Save**.

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

- [Dashboard Guide](dashboard.md) — Full TUI documentation
- [Quickstart](quickstart.md) — Installation and first steps
- [Architecture](architecture.md) — System design details
