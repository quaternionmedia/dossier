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
│ �️  App Info                                                    │
├─────────────────────────────────────────────────────────────────┤
│ Version:      0.1.0                                             │
│ Python:       3.13.3                                            │
│ Platform:     Windows 10                                        │
│ Database:     C:\Users\you\.dossier\dossier.db                  │
│ DB Size:      2.4 MB                                            │
│ Projects:     42                                                │
├─────────────────────────────────────────────────────────────────┤
│ 🎨 Theme                                                        │
├─────────────────────────────────────────────────────────────────┤
│ ○ Textual Dark                                                  │
│ ○ Textual Light                                                 │
│ ○ Nord                                                          │
│ ○ Gruvbox                                                       │
│ ● Catppuccin Mocha                                              │
│ ○ Dracula                                                       │
│ ○ Tokyo Night                                                   │
│ ○ Monokai                                                       │
│ ○ Solarized Light                                               │
├─────────────────────────────────────────────────────────────────┤
│                         [Close]                                 │
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

This information is useful for:
- Debugging issues
- Reporting bugs
- Verifying installation
- Checking database location

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
3. Theme applies immediately
4. Press `Escape` or click **Close** to dismiss

**Note:** Theme selection is not persisted between sessions. The dashboard always starts with the default theme (Textual Dark).

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `` ` `` | Open settings overlay |
| `↑` / `↓` | Navigate theme options |
| `Enter` / `Space` | Select theme |
| `Escape` | Close settings |
| `q` | Close settings |

---

## Future Settings

Planned settings for future releases:

- [ ] **Persist theme** — Save theme preference to config file
- [ ] **Default tab** — Choose which tab opens on project select
- [ ] **Tree density** — Compact vs comfortable spacing
- [ ] **Sync preferences** — Default batch size, rate limit behavior
- [ ] **Keyboard shortcuts** — Customize key bindings
- [ ] **Export format** — Default export format preferences

---

## Related Documentation

- [Dashboard Guide](dashboard.md) — Full TUI documentation
- [Quickstart](quickstart.md) — Installation and first steps
- [Architecture](architecture.md) — System design details
