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
]

TREE_DENSITY_OPTIONS = [
    ("comfortable", "Comfortable"),
    ("compact", "Compact"),
]

EXPORT_FORMAT_OPTIONS = [
    ("yaml", "YAML (.dossier)"),
    ("json", "JSON (.json)"),
]
