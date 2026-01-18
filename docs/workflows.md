# Workflows & Examples

[← Back to Index](index.md) | [Quickstart](quickstart.md) | [Extending →](extending.md)

---

Copy-paste ready workflows for common use cases. All commands assume you've installed Dossier and set up your GitHub token.

## Prerequisites

```bash
# One-time setup
git clone https://github.com/quaternionmedia/dossier.git
cd dossier
uv sync

# Set GitHub token (get one at https://github.com/settings/tokens)
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
```

---

## Workflow 1: Personal Portfolio Tracking

**Goal**: Track all your GitHub repositories in one place.

```bash
# Step 1: Sync all your repos
uv run dossier github sync-user YOUR_GITHUB_USERNAME

# Step 2: Launch dashboard to browse
uv run dossier dashboard

# Step 3: List projects sorted by stars
uv run dossier projects list -v

# Step 4: Export portfolio overview
uv run dossier export all -d ./my-portfolio
```

**Verify it worked**:
```bash
# Check project count
uv run dossier dev status

# Should show: Projects: N | Synced: N | ...
```

---

## Workflow 2: Multi-Org Team Visibility

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

## Workflow 3: Offline-First Development

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

## Workflow 4: Daily Standup Prep

**Goal**: Quick overview of project activity for standup.

```bash
# Check open issues across all synced projects
uv run dossier dashboard
# Press Tab until you reach Issues tab, or use keyboard: 8

# Export status report
uv run dossier export all -d ./standup-$(date +%Y-%m-%d)

# Quick project status
uv run dossier projects show myorg/current-sprint-project
```

---

## Workflow 5: Dependency Audit

**Goal**: See what dependencies your projects use.

```bash
# Sync a project with dependencies
uv run dossier github sync astral-sh/uv

# View in dashboard (Dependencies tab = Tab 6)
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

## Workflow 6: Onboarding New Team Member

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

# Navigation tips:
#   j/k or arrows = navigate project list
#   Tab = switch detail tabs
#   / = search projects
#   s = sync selected project
#   o = open in GitHub browser
#   ? = help
```

---

## Workflow 7: Release Tracking

**Goal**: Track versions and releases across projects.

```bash
# Sync projects you want to track
uv run dossier github sync fastapi/fastapi
uv run dossier github sync pydantic/pydantic
uv run dossier github sync encode/starlette

# View releases in dashboard (Releases tab = Tab 10)
uv run dossier dashboard

# Export dossier files with version info
uv run dossier export dossier fastapi/fastapi
cat fastapi_fastapi.dossier
```

---

## Workflow 8: CI/CD Integration

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

## Workflow 9: Backup & Migration

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

## Workflow 10: API-Driven Integration

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
