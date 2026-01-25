# Workflows & Examples

[← Back to Index](index.md) | [Quickstart](quickstart.md) | [Extending →](extending.md)

---

Copy-paste ready workflows for common use cases. All commands assume you've installed Dossier and set up your GitHub token.

## Prerequisites

```bash
# One-time setup (copy-paste this block)
git clone https://github.com/quaternionmedia/dossier.git
cd dossier
uv sync

# Set GitHub token (get one at https://github.com/settings/tokens)
# Linux/macOS:
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
# Windows PowerShell:
$env:GITHUB_TOKEN = "ghp_xxxxxxxxxxxxxxxxxxxx"
```

**Verify it works:**
```bash
uv run dossier github sync-user YOUR_USERNAME --limit 1
# Should show: 📊 Rate limit: 4999/5000 remaining
```

---

## Workflow 1: Personal Portfolio Tracking

**Goal**: Track all your GitHub repositories in one place.

```bash
# Step 1: Sync all your repos (replace YOUR_GITHUB_USERNAME)
uv run dossier github sync-user YOUR_GITHUB_USERNAME

# Step 2: Launch dashboard to browse
uv run dossier dashboard
# → Use arrow keys to navigate the project tree
# → Tab to switch between panels
# → Click docs in the tree to preview

# Step 3: List projects sorted by stars (CLI)
uv run dossier projects list -v

# Step 4: Export portfolio overview
mkdir -p ./my-portfolio
uv run dossier export all -d ./my-portfolio
```

**Verify it worked:**
```bash
uv run dossier dev status
# Should show: Projects: N | Synced: N | ...
```

---

## Workflow 2: Documentation Browsing

**Goal**: Browse project documentation without leaving the terminal.

```bash
# Step 1: Sync a project
uv run dossier github sync pallets/flask

# Step 2: Launch dashboard
uv run dossier dashboard

# Step 3: Navigate the documentation tree
# → Expand the project in the left tree
# → Click 📚 Docs folder to expand
# → Click any doc file to open the viewer
# → Use n/p or j/k to navigate between docs
# → Press q to close the viewer
```

**Keyboard navigation in the viewer:**
| Key | Action |
|-----|--------|
| `n` or `j` | Next document |
| `p` or `k` | Previous document |
| `o` | Open in browser |
| `q` or `Esc` | Close viewer |

---

## Workflow 3: Multi-Org Team Visibility

**Goal**: Unified view across multiple GitHub organizations.

```bash
# Step 1: Sync each org (run these in sequence)
uv run dossier github sync-org acme-frontend --limit 50
uv run dossier github sync-org acme-backend --limit 50
uv run dossier github sync-org acme-infra --limit 50

# Step 2: View all in one dashboard
uv run dossier dashboard

# Step 3: Filter to synced projects only (press 'f' in TUI, or use CLI)
uv run dossier projects list --synced

# Step 4: Search across all projects
uv run dossier projects list | grep "api"
```

**Create a parent "workspace" project**:
```bash
# Create umbrella project
uv run dossier projects add acme-platform -d "All Acme Platform Projects"

# Link child projects
uv run dossier components add acme-platform acme-frontend/web-app
uv run dossier components add acme-platform acme-backend/api-service
uv run dossier components add acme-platform acme-infra/k8s-configs

# View hierarchy
uv run dossier components list acme-platform
```

---

## Workflow 4: Offline-First Development

**Goal**: Work without network, sync when connected.

```bash
# Step 1: Initial sync while online
uv run dossier github sync-user myusername
uv run dossier github sync-org mycompany --limit 20

# Step 2: Disconnect from network (airplane mode, VPN off, etc.)

# Step 3: All reads work offline
uv run dossier dashboard                    # Browse projects
uv run dossier projects list -v             # List with details
uv run dossier query mycompany/api          # Query docs
uv run dossier export show mycompany/api    # Preview dossier

# Step 4: Reconnect and sync changes
uv run dossier github sync-user myusername --force
```

---

## Workflow 5: Daily Standup Prep

**Goal**: Quick overview of project activity for standup.

```bash
# Check open issues across all synced projects
uv run dossier dashboard
# Switch to Projects > Issues

# Export status report
uv run dossier export all -d ./standup-$(date +%Y-%m-%d)

# Quick project status
uv run dossier projects show myorg/current-sprint-project
```

---

## Workflow 6: Dependency Audit

**Goal**: See what dependencies your projects use.

```bash
# Sync a project with dependencies
uv run dossier github sync astral-sh/uv

# View in dashboard (Projects > Dependencies)
uv run dossier dashboard

# Or query via CLI
uv run dossier projects show astral-sh/uv
```

**Check dependency across multiple projects**:
```bash
# Sync multiple projects
uv run dossier github sync pallets/flask
uv run dossier github sync pallets/click
uv run dossier github sync pallets/werkzeug

# View each project's dependencies in dashboard
uv run dossier dashboard
```

---

## Workflow 7: Onboarding New Team Member

**Goal**: Get a new developer up to speed on team projects.

```bash
# Step 1: Clone and install Dossier
git clone https://github.com/quaternionmedia/dossier.git
cd dossier
uv sync

# Step 2: Set token
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx

# Step 3: Sync team's repos
uv run dossier github sync-org your-team-org

# Step 4: Launch dashboard and explore
uv run dossier dashboard
```

**Navigation tips:**
```
Arrows / j,k   = Navigate project tree
Tab            = Switch between panels
Enter          = Expand/select tree node
/              = Search projects
s              = Sync selected project
o              = Open in GitHub browser
n / p          = Next/prev doc in viewer
?              = Help
```

---

## Workflow 8: Release Tracking

**Goal**: Track versions and releases across projects.

```bash
# Sync projects you want to track
uv run dossier github sync fastapi/fastapi
uv run dossier github sync pydantic/pydantic
uv run dossier github sync encode/starlette

# View releases in dashboard (Projects > Releases)
uv run dossier dashboard

# Export dossier files with version info
uv run dossier export dossier fastapi/fastapi
cat fastapi_fastapi.dossier
```

---

## Workflow 9: Entity Graph Building

**Goal**: Build navigable entity graphs with proper disambiguation.

```bash
# Step 1: Sync some projects
uv run dossier github sync-org your-org --limit 20

# Step 2: Build entity graph for one project
uv run dossier graph build your-org/main-repo

# Step 3: View what was created
uv run dossier graph stats
```

**Understanding Entity Scoping**:
```bash
# After building a graph, entities get unique names:

# Repo-scoped (unique per repository):
#   your-org/main-repo/branch/main
#   your-org/main-repo/issue/123
#   your-org/main-repo/pr/456
#   your-org/main-repo/ver/v1.0.0
#   your-org/main-repo/doc/readme

# App-scoped (same user across all repos):
#   github/user/contributor-name

# Global (shared everywhere):
#   lang/python
#   pkg/fastapi

# View a linked entity as a project
uv run dossier projects show github/user/contributor-name
uv run dossier projects show lang/python
```

**Build graphs for all projects**:
```bash
# Build graphs for everything
uv run dossier graph build-all

# Skip certain entity types
uv run dossier graph build-all --no-issues --no-prs

# Limit entities per project
uv run dossier graph build-all --max-contributors 5 --max-issues 20
```

---

## Workflow 10: CI/CD Integration

**Goal**: Use Dossier in automated pipelines.

```bash
# In CI script (GitHub Actions, etc.)

# Install
pip install uv
uv sync

# Sync specific repos
uv run dossier github sync ${{ github.repository }}

# Export dossier as artifact
uv run dossier export dossier ${{ github.repository }} -o ./artifacts/

# Or use API for integrations
uv run dossier serve &
curl http://localhost:8000/projects
curl http://localhost:8000/dossier/${{ github.repository }}
```

**GitHub Actions example**:
```yaml
# .github/workflows/dossier.yml
name: Generate Dossier
on: [push]
jobs:
  dossier:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync
      - run: uv run dossier github sync ${{ github.repository }}
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      - run: uv run dossier export dossier ${{ github.repository }}
      - uses: actions/upload-artifact@v4
        with:
          name: dossier
          path: "*.dossier"
```

---

## Workflow 11: Backup & Migration

**Goal**: Export data for backup or migration to another machine.

```bash
# Full database backup
cp ~/.dossier/dossier.db ~/backups/dossier-$(date +%Y%m%d).db

# Export all projects as dossier files
uv run dossier export all -d ~/backups/dossier-exports/

# Export as JSON (for processing)
uv run dossier dev dump -o ~/backups/dossier-dump.json

# On new machine: copy database back
mkdir -p ~/.dossier
cp ~/backups/dossier-*.db ~/.dossier/dossier.db

# Verify
uv run dossier dev status
uv run dossier projects list
```

---

## Workflow 12: API-Driven Integration

**Goal**: Build integrations using the REST API.

```bash
# Terminal 1: Start API server
uv run dossier serve --reload

# Terminal 2: Use the API
# List projects
curl http://localhost:8000/projects | jq

# Get specific project
curl http://localhost:8000/projects/astral-sh/uv | jq

# Get project dossier
curl http://localhost:8000/dossier/astral-sh/uv | jq

# Sync a repo via API
curl -X POST "http://localhost:8000/github/sync?repo=owner/repo"

# Search GitHub
curl "http://localhost:8000/github/search?q=python+cli" | jq
```

**Python client example**:
```python
import httpx

client = httpx.Client(base_url="http://localhost:8000")

# List all projects
projects = client.get("/projects").json()
for p in projects:
    print(f"{p['name']}: ⭐ {p.get('github_stars', 0)}")

# Get dossier for specific project
dossier = client.get("/dossier/astral-sh/uv").json()
print(dossier)
```

---

## Workflow 13: Delta Management (Local Change Tracking)

**Goal**: Track features, bugfixes, and changes through their lifecycle using deltas.

Deltas are your local, structured way to track work across phases - like personal Jira tickets stored in your Dossier database.

### The Delta Lifecycle

```
BRAINSTORM → PLANNING → IMPLEMENTATION → REVIEW → DOCUMENTATION → COMPLETE
                                                                      ↓
                                                               (ABANDONED)
```

### Creating and Managing Deltas

```bash
# Step 1: Launch dashboard and navigate to Deltas tab
uv run dossier dashboard

# Step 2: Create a new delta
# Click "+ New Delta" button or press 'n'
# Fill in:
#   Name: add-dark-mode (slug format)
#   Title: Add Dark Mode Toggle
#   Type: feature
#   Priority: medium

# Step 3: Add notes during brainstorming
# Select delta → Click "+ Add Note"
# Document initial ideas, questions to resolve

# Step 4: Advance through phases
# Click ">> Advance Phase" button or press 'a'
# Add transition notes at each phase

# Step 5: Link related entities
# Click "Link Entity" or press 'l'
# Link to: Issues, PRs, Branches, other Deltas
```

### Example: Feature Development Flow

```bash
# 1. Create delta in BRAINSTORM phase
#    → Add notes with initial ideas

# 2. Advance to PLANNING
#    → Document technical design
#    → Link to GitHub issue if one exists

# 3. Advance to IMPLEMENTATION
#    → started_at timestamp is set
#    → Link your feature branch
#    → Add progress notes as you code

# 4. Advance to REVIEW
#    → Link the PR
#    → Add notes about review feedback

# 5. Advance to DOCUMENTATION
#    → Track docs updates

# 6. Advance to COMPLETE
#    → completed_at timestamp is set
#    → Full history preserved
```

### Keyboard Shortcuts in Deltas Tab

| Key | Action |
|-----|--------|
| `n` | New delta |
| `a` | Advance phase |
| `l` | Add link |
| `Enter` | View delta details |

### Best Practices

- **Use descriptive names**: `fix-auth-timeout`, `refactor-api-client`
- **Add notes at every phase**: Creates audit trail of decisions and blockers
- **Link related entities**: Issues, branches, PRs, other deltas
- **Don't skip phases**: Each serves a purpose (prevents premature coding, captures feedback)
- **Use priority wisely**: critical (production bugs), high (blocking), medium (normal), low (nice-to-have)

---

## Quick Reference: Common Commands

### Sync
```bash
uv run dossier github sync owner/repo              # Single repo
uv run dossier github sync-user username           # All user repos
uv run dossier github sync-org orgname             # All org repos
uv run dossier github sync-org orgname --limit 20  # Limit count
uv run dossier github sync-user me --force         # Force re-sync
```

### Browse
```bash
uv run dossier dashboard                           # TUI dashboard
uv run dossier tui                                 # Command explorer
uv run dossier projects list                       # List all
uv run dossier projects list -v                    # Verbose
uv run dossier projects list --synced              # Only synced
uv run dossier projects show owner/repo            # Show details
```

### Export
```bash
uv run dossier export dossier owner/repo           # Export .dossier
uv run dossier export show owner/repo              # Preview only
uv run dossier export all -d ./exports             # Export all
```

### Graph
```bash
uv run dossier graph build owner/repo              # Build for one project
uv run dossier graph build-all                     # Build for all projects
uv run dossier graph stats                         # Show statistics
uv run dossier graph build owner/repo --no-issues  # Skip issues
uv run dossier graph build-all --max-contributors 5 # Limit entities
```

### Manage
```bash
uv run dossier projects add name -d "description"  # Add manual
uv run dossier projects remove name -y             # Remove
uv run dossier projects rename old new             # Rename
uv run dossier components add parent child         # Link projects
```

### Database
```bash
uv run dossier dev status                          # Stats
uv run dossier dev reset -y                        # Reset all
uv run dossier dev vacuum                          # Optimize
uv run dossier db upgrade                          # Run migrations
```

### Deltas (coming in Phase 2)
```bash
uv run dossier deltas list owner/repo              # List deltas
uv run dossier deltas create owner/repo name       # Create delta
uv run dossier deltas advance owner/repo name      # Advance phase
uv run dossier deltas link owner/repo name --issue 42  # Link entity
uv run dossier deltas show owner/repo name         # Show details
```

---

## Troubleshooting

### "Rate limit exceeded"
```bash
# Check your token is set
echo $GITHUB_TOKEN

# Verify rate limit
uv run dossier github sync-user yourname --limit 1
# Should show: 📊 Rate limit: 4999/5000 remaining
```

### "Project not found"
```bash
# List all projects to verify name
uv run dossier projects list | grep -i "partial-name"

# Project names include owner: "owner/repo", not just "repo"
uv run dossier projects show owner/repo  # ✅ Correct
uv run dossier projects show repo        # ❌ Won't work
```

### Database issues
```bash
# Check database location and status
uv run dossier dev status

# Reset if corrupted
uv run dossier dev reset -y

# Run pending migrations
uv run dossier db upgrade
```

---

Next: [Extending Dossier →](extending.md)
