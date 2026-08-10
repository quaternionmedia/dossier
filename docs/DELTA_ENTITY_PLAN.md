# Delta Entity Type Implementation Plan

## Overview

This document outlines the plan for adding a new **Delta** entity type to Dossier. A Delta tracks changes to a specific project/component through various phases: brainstorm, planning, implementation, review, and documentation.

A Delta is conceptually a **specific type of Project** - it represents a discrete unit of change (like a feature, bugfix, or refactor) that has its own lifecycle and can link to related entities.

---

## 1. Data Model Design

### 1.1 Delta Status Enum

```python
class DeltaPhase(str, Enum):
    """Phases of a delta's lifecycle."""

    BRAINSTORM = "brainstorm"      # Initial ideation phase
    PLANNING = "planning"          # Design and planning phase
    IMPLEMENTATION = "implementation"  # Active development
    REVIEW = "review"              # Code review / QA phase
    DOCUMENTATION = "documentation"  # Documentation phase
    COMPLETE = "complete"          # Delta is finished
    ABANDONED = "abandoned"        # Delta was abandoned
```

### 1.2 ProjectDelta Model

**File**: `src/dossier/models/schemas.py`

```python
class ProjectDelta(SQLModel, table=True):
    """A delta (change) tracked for a project.

    Deltas represent discrete units of work (features, bugfixes, refactors)
    that progress through phases: brainstorm -> planning -> implementation ->
    review -> documentation -> complete.
    """

    __tablename__ = "project_delta"

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)

    # Core fields
    name: str  # Short identifier (e.g., "add-dark-mode", "fix-auth-bug")
    title: str  # Human-readable title
    description: Optional[str] = None

    # Phase tracking
    phase: DeltaPhase = Field(default=DeltaPhase.BRAINSTORM)
    phase_changed_at: datetime = Field(default_factory=utcnow)

    # Priority and categorization
    priority: str = "medium"  # low, medium, high, critical
    delta_type: str = "feature"  # feature, bugfix, refactor, docs, chore

    # Timestamps
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    # Optional linking
    issue_number: Optional[int] = None  # Link to related GitHub issue
    pr_number: Optional[int] = None     # Link to related PR
    branch_name: Optional[str] = None   # Associated branch
```

### 1.3 DeltaNote Model (for phase notes/updates)

```python
class DeltaNote(SQLModel, table=True):
    """A note or update for a delta during a specific phase."""

    __tablename__ = "delta_note"

    id: Optional[int] = Field(default=None, primary_key=True)
    delta_id: int = Field(foreign_key="project_delta.id", index=True)

    phase: DeltaPhase  # Phase this note was created during
    content: str       # Markdown content

    created_at: datetime = Field(default_factory=utcnow)
```

### 1.4 DeltaLink Model (for linking deltas to other entities)

```python
class DeltaLink(SQLModel, table=True):
    """Links a delta to related entities (issues, PRs, branches, other deltas)."""

    __tablename__ = "delta_link"

    id: Optional[int] = Field(default=None, primary_key=True)
    delta_id: int = Field(foreign_key="project_delta.id", index=True)

    # What this delta links to
    link_type: str  # "issue", "pr", "branch", "delta", "doc"
    target_id: Optional[int] = None     # ID for issues, PRs, deltas
    target_name: Optional[str] = None   # Name for branches, etc.

    created_at: datetime = Field(default_factory=utcnow)
```

---

## 2. Database Migration

**File**: `alembic/versions/2026_01_19_0000_005_add_delta_tables.py`

Creates three tables:
- `project_delta` - Main delta tracking
- `delta_note` - Phase notes
- `delta_link` - Entity linking

Includes indexes on:
- `project_delta.project_id`
- `project_delta.phase`
- `delta_note.delta_id`
- `delta_link.delta_id`

---

## 3. TUI Tab Implementation

### 3.1 Tab Configuration

**File**: `src/dossier/config.py`

Add to `AVAILABLE_TABS`:
```python
("tab-deltas", "Deltas"),
```

### 3.2 Tab UI Structure

**File**: `src/dossier/tui/app.py`

Add TabPane in `compose()`:
```python
with TabPane("Deltas", id="tab-deltas"):
    with Vertical():
        yield DataTable(id="deltas-table")
        with Horizontal(id="delta-buttons"):
            yield Button("+ New Delta", id="btn-new-delta", variant="primary")
            yield Button(">> Advance Phase", id="btn-advance-phase", variant="default")
            yield Button("+ Add Note", id="btn-add-note", variant="default")
```

### 3.3 Table Columns

```python
deltas_table.add_column("Name", width=20)
deltas_table.add_column("Title", width=35)
deltas_table.add_column("Phase", width=15)
deltas_table.add_column("Type", width=12)
deltas_table.add_column("Priority", width=10)
deltas_table.add_column("Links", width=15)
deltas_table.cursor_type = "row"
```

### 3.4 Tab Loader Method

```python
def _load_deltas_tab(self, project: Project) -> None:
    """Load deltas tab."""
    deltas_table = self.query_one("#deltas-table", DataTable)
    deltas_table.clear()

    with self.session_factory() as session:
        deltas = session.exec(
            select(ProjectDelta)
            .where(ProjectDelta.project_id == project.id)
            .order_by(
                # Sort by phase (active phases first), then by priority
                case(
                    (ProjectDelta.phase == DeltaPhase.IMPLEMENTATION, 0),
                    (ProjectDelta.phase == DeltaPhase.REVIEW, 1),
                    (ProjectDelta.phase == DeltaPhase.PLANNING, 2),
                    (ProjectDelta.phase == DeltaPhase.BRAINSTORM, 3),
                    (ProjectDelta.phase == DeltaPhase.DOCUMENTATION, 4),
                    else_=5
                ),
                ProjectDelta.updated_at.desc()
            )
        ).all()

        if not deltas:
            deltas_table.add_row(
                "(No deltas)", "-", "-", "-", "-", "-",
                key="empty"
            )
        else:
            for delta in deltas:
                phase_icons = {
                    DeltaPhase.BRAINSTORM: "💡",
                    DeltaPhase.PLANNING: "📋",
                    DeltaPhase.IMPLEMENTATION: "⚙️",
                    DeltaPhase.REVIEW: "🔍",
                    DeltaPhase.DOCUMENTATION: "📝",
                    DeltaPhase.COMPLETE: "✅",
                    DeltaPhase.ABANDONED: "❌",
                }
                priority_icons = {
                    "critical": "🔴",
                    "high": "🟠",
                    "medium": "🟡",
                    "low": "🟢",
                }
                type_icons = {
                    "feature": "✨",
                    "bugfix": "🐛",
                    "refactor": "♻️",
                    "docs": "📚",
                    "chore": "🔧",
                }

                # Count links
                link_count = session.exec(
                    select(func.count(DeltaLink.id))
                    .where(DeltaLink.delta_id == delta.id)
                ).one()

                deltas_table.add_row(
                    delta.name,
                    delta.title[:30] + ("..." if len(delta.title) > 30 else ""),
                    f"{phase_icons.get(delta.phase, '❓')} {delta.phase.value}",
                    f"{type_icons.get(delta.delta_type, '❓')} {delta.delta_type}",
                    f"{priority_icons.get(delta.priority, '⚪')} {delta.priority}",
                    f"🔗 {link_count}" if link_count else "-",
                    key=f"delta-{delta.id}",
                )
```

---

## 4. Entity Type Recognition

### 4.1 Name Pattern

Deltas follow the pattern: `{owner}/{repo}/delta/{name}`

Example: `astral-sh/ruff/delta/add-dark-mode`

### 4.2 Entity Type Detection

**File**: `src/dossier/tui/app.py`

Add to `_get_entity_type_from_name()`:
```python
if "/delta/" in name:
    return "delta"
```

### 4.3 Entity Type Filter

Add to the Select options in `compose()`:
```python
("🔺 Deltas", "delta"),
```

### 4.4 Display Name Shortening

Add to `_shorten_project_name()`:
```python
# Handle delta pattern: astral-sh/ruff/delta/add-dark-mode -> ruff△add-dark-mode
if "/delta/" in name:
    parts = name.split("/delta/")
    if len(parts) == 2:
        repo_part = parts[0].split("/")[-1]  # Get repo name
        return f"{repo_part}△{parts[1]}"
```

---

## 5. Delta as Project Type

Since a Delta is conceptually a type of Project, we support creating Delta entries as first-class projects with special handling:

### 5.1 Project Name Convention

When a Delta is created, it can optionally be registered as a Project with name:
`{owner}/{repo}/delta/{delta-name}`

This allows:
- Viewing the delta in the project tree
- Linking other entities to the delta
- Using existing project infrastructure for the delta

### 5.2 Project-Delta Synchronization

When a ProjectDelta is created, optionally create a corresponding Project:
```python
def create_delta_project(delta: ProjectDelta, parent_project: Project) -> Project:
    """Create a project entry for a delta."""
    return Project(
        name=f"{parent_project.get_full_name()}/delta/{delta.name}",
        full_name=f"{parent_project.get_full_name()}/delta/{delta.name}",
        description=delta.description or f"Delta: {delta.title}",
    )
```

---

## 6. UI Interactions

### 6.1 Create New Delta Dialog

Modal with fields:
- Name (slug, e.g., "add-dark-mode")
- Title (human-readable)
- Description (optional)
- Type (feature/bugfix/refactor/docs/chore)
- Priority (low/medium/high/critical)
- Link to Issue # (optional)
- Create as Project? (checkbox)

### 6.2 Advance Phase Action

When clicking "Advance Phase":
1. Move to next phase in sequence
2. Prompt for optional note about the phase transition
3. Update `phase_changed_at` timestamp
4. If moving to IMPLEMENTATION, set `started_at`
5. If moving to COMPLETE, set `completed_at`

Phase sequence: BRAINSTORM → PLANNING → IMPLEMENTATION → REVIEW → DOCUMENTATION → COMPLETE

### 6.3 Delta Detail View

When selecting a delta row, show expanded details:
- Full description
- Phase history with timestamps
- All notes grouped by phase
- Linked entities (issues, PRs, branches)
- Quick actions (link issue, link PR, add note)

### 6.4 Row Selection Handler

```python
def on_deltas_table_row_selected(self, event: DataTable.RowSelected) -> None:
    """Handle delta row selection."""
    table = self.query_one("#deltas-table", DataTable)
    row_key = event.row_key
    if row_key and str(row_key.value).startswith("delta-"):
        delta_id = int(str(row_key.value).split("-")[1])
        # Show delta detail modal or navigate to delta project
        self._show_delta_detail(delta_id)
```

---

## 7. Implementation Steps

### Step 1: Schema Changes
- [x] Add `DeltaPhase` enum to `schemas.py`
- [x] Add `ProjectDelta` model to `schemas.py`
- [x] Add `DeltaNote` model to `schemas.py`
- [x] Add `DeltaLink` model to `schemas.py`
- [x] Export new models in `models/__init__.py`

### Step 2: Database Migration
- [x] Create migration file `005_add_delta_tables.py`
- [x] Test migration up/down

### Step 3: Configuration
- [x] Add `("tab-deltas", "Deltas")` to `AVAILABLE_TABS` in `config.py`

### Step 4: TUI Tab Implementation
- [x] Add TabPane for Deltas in `compose()`
- [x] Add table column setup in `on_mount()`
- [x] Add `_load_deltas_tab()` loader method
- [x] Register loader in `loaders` dict

### Step 5: Entity Type Integration
- [x] Add delta detection to `_get_entity_type_from_name()`
- [x] Add delta filter option to entity type Select
- [x] Add delta shortening to `_shorten_project_name()`

### Step 6: UI Actions
- [x] Implement "New Delta" button handler and modal
- [x] Implement "Advance Phase" button handler
- [x] Implement "Add Note" button handler
- [x] Implement delta row selection handler

### Step 7: Testing
- [x] Unit tests for ProjectDelta model
- [x] Unit tests for phase transitions
- [x] Integration tests for delta API endpoints
- [x] Integration tests for delta CLI commands

---

## 8. File Changes Summary

| File | Changes |
|------|---------|
| `src/dossier/models/schemas.py` | Add DeltaPhase, ProjectDelta, DeltaNote, DeltaLink models |
| `src/dossier/models/__init__.py` | Export new models |
| `alembic/versions/005_*.py` | New migration for delta tables |
| `src/dossier/config.py` | Add tab-deltas to AVAILABLE_TABS |
| `src/dossier/tui/app.py` | Add tab, loader, handlers, entity type support |
| `src/dossier/api/main.py` | Add 5 REST API endpoints for delta management |
| `src/dossier/cli.py` | Add 6 CLI commands for delta management |
| `src/dossier/database.py` | Register delta models in init_db() |
| `src/dossier/parsers/autolinker.py` | Add delta auto-linking as project nodes |
| `tests/test_models.py` | Add delta model unit tests |
| `tests/test_api.py` | Add delta API integration tests |
| `tests/test_cli.py` | Add delta CLI integration tests |

---

## 9. Future Enhancements

- **Delta Templates**: Pre-defined templates for common delta types
- **Phase Automation**: Auto-advance phase based on linked PR status
- **Delta Reports**: Generate summary reports of delta progress
- **Delta Notifications**: Notify when deltas are stale in a phase
- **Cross-Project Deltas**: Deltas that span multiple projects
