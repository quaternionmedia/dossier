"""Dossier configuration management.

Handles persistent settings stored in ~/.dossier/config.json
"""

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


# Default configuration values
DEFAULT_THEME = "textual-dark"
DEFAULT_TAB = "tab-dossier"
DEFAULT_TREE_DENSITY = "comfortable"  # comfortable, compact
DEFAULT_SYNC_BATCH_SIZE = 10
DEFAULT_SYNC_DELAY = 1.0
DEFAULT_EXPORT_FORMAT = "yaml"  # yaml, json


@dataclass
class ViewState:
    """Persistent view state for the TUI dashboard."""
    
    # Last selected project (by full_name e.g., "owner/repo")
    last_project: Optional[str] = None
    
    # Active tab when closed
    active_tab: Optional[str] = None
    
    # Filter states
    filter_synced: Optional[bool] = None  # None=all, True=synced, False=unsynced
    filter_language: Optional[str] = None
    filter_entity: Optional[str] = None  # None=all, or "repo", "branch", etc.
    filter_starred: Optional[bool] = None
    
    # Sort mode
    sort_by: str = "stars"  # name, stars, synced


@dataclass
class DossierConfig:
    """Dossier application configuration."""
    
    # Appearance
    theme: str = DEFAULT_THEME
    default_tab: str = DEFAULT_TAB
    tree_density: str = DEFAULT_TREE_DENSITY
    
    # Sync preferences
    sync_batch_size: int = DEFAULT_SYNC_BATCH_SIZE
    sync_delay: float = DEFAULT_SYNC_DELAY
    
    # Export preferences
    export_format: str = DEFAULT_EXPORT_FORMAT
    
    # Window state (optional persistence)
    sidebar_width: Optional[int] = None
    
    # View state - stores last dashboard state for restoration
    view_state: Optional[ViewState] = None
    
    @classmethod
    def get_config_path(cls) -> Path:
        """Get the path to the config file."""
        return Path.home() / ".dossier" / "config.json"
    
    @classmethod
    def load(cls) -> "DossierConfig":
        """Load configuration from file, or return defaults if not found."""
        config_path = cls.get_config_path()
        
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Only use known fields to avoid issues with old config versions
                known_fields = {f.name for f in cls.__dataclass_fields__.values()}
                filtered_data = {k: v for k, v in data.items() if k in known_fields}
                
                # Handle nested ViewState
                if "view_state" in filtered_data and filtered_data["view_state"] is not None:
                    view_state_data = filtered_data["view_state"]
                    if isinstance(view_state_data, dict):
                        view_state_fields = {f.name for f in ViewState.__dataclass_fields__.values()}
                        filtered_view_state = {k: v for k, v in view_state_data.items() if k in view_state_fields}
                        filtered_data["view_state"] = ViewState(**filtered_view_state)
                
                return cls(**filtered_data)
            except (json.JSONDecodeError, TypeError, ValueError):
                # Invalid config, return defaults
                pass
        
        return cls()
    
    def save(self) -> None:
        """Save configuration to file."""
        config_path = self.get_config_path()
        
        # Ensure directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)
    
    def reset(self) -> None:
        """Reset configuration to defaults."""
        self.theme = DEFAULT_THEME
        self.default_tab = DEFAULT_TAB
        self.tree_density = DEFAULT_TREE_DENSITY
        self.sync_batch_size = DEFAULT_SYNC_BATCH_SIZE
        self.sync_delay = DEFAULT_SYNC_DELAY
        self.export_format = DEFAULT_EXPORT_FORMAT
        self.sidebar_width = None
        self.view_state = None
    
    def save_view_state(
        self,
        last_project: Optional[str] = None,
        active_tab: Optional[str] = None,
        filter_synced: Optional[bool] = None,
        filter_language: Optional[str] = None,
        filter_entity: Optional[str] = None,
        filter_starred: Optional[bool] = None,
        sort_by: str = "stars",
    ) -> None:
        """Save the current view state for restoration on next launch."""
        self.view_state = ViewState(
            last_project=last_project,
            active_tab=active_tab,
            filter_synced=filter_synced,
            filter_language=filter_language,
            filter_entity=filter_entity,
            filter_starred=filter_starred,
            sort_by=sort_by,
        )
        self.save()


# Available options for settings
AVAILABLE_THEMES = [
    ("textual-dark", "Textual Dark"),
    ("textual-light", "Textual Light"),
    ("nord", "Nord"),
    ("gruvbox", "Gruvbox"),
    ("catppuccin-mocha", "Catppuccin Mocha"),
    ("dracula", "Dracula"),
    ("tokyo-night", "Tokyo Night"),
    ("monokai", "Monokai"),
    ("solarized-light", "Solarized Light"),
]

AVAILABLE_TABS = [
    ("tab-dossier", "Dossier"),
    ("tab-details", "Details"),
    ("tab-docs", "Documentation"),
    ("tab-languages", "Languages"),
    ("tab-branches", "Branches"),
    ("tab-dependencies", "Dependencies"),
    ("tab-contributors", "Contributors"),
    ("tab-issues", "Issues"),
    ("tab-prs", "Pull Requests"),
    ("tab-releases", "Releases"),
    ("tab-components", "Components"),
    ("tab-deltas", "Deltas"),
]

TREE_DENSITY_OPTIONS = [
    ("comfortable", "Comfortable"),
    ("compact", "Compact"),
]

EXPORT_FORMAT_OPTIONS = [
    ("yaml", "YAML (.dossier)"),
    ("json", "JSON (.json)"),
]
