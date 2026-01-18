# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Pull Requests Tab** - View PRs with merge status, branch info, and diff statistics (+/-)
- **Releases Tab** - View version releases with tags, prerelease/draft indicators
- **Filter Bar** - Filter projects by sync status (All/Synced/Unsynced), sort by stars
- **Keyboard Filter** - Press `f` to cycle through filter states
- **Enhanced Search** - Search now includes project descriptions
- **Dossier File Format** - New `.dossier` YAML format for standardized project overviews:
  - `dossier export dossier <project>` - Export project to .dossier file
  - `dossier export show <project>` - Display dossier to stdout
  - `dossier export all` - Export all projects
  - `dossier init` - Create template .dossier file
  - `GET /dossier/{project_name}` - API endpoint for dossier data
- **Alembic Migrations** - Database schema migration support:
  - `dossier db upgrade` - Apply pending migrations
  - `dossier db downgrade` - Rollback migrations
  - `dossier db current` - Show current revision
  - `dossier db history` - Show migration history
  - `dossier db revision "msg"` - Create new migration
  - `dossier db stamp` - Mark database revision
- **TUI Dossier Tab** - New default tab showing formatted project overview:
  - Auto-opens when selecting a project
  - Shows tech stack with visual percentage bars
  - Activity metrics (issues, PRs, contributors)
  - Dependencies grouped by type
  - Quick links to repository resources
- **Component API Endpoints** - Manage project relationships via REST API:
  - `GET /projects/{name}/components` - List subprojects
  - `POST /projects/{name}/components` - Add component relationship
  - `PUT /projects/{name}/components/{child}` - Update relationship
  - `DELETE /projects/{name}/components/{child}` - Remove relationship
  - `GET /components` - List all component relationships
- **TUI Component Management** - Interactive component/subproject management:
  - ➕ Add Component button - Link a subproject to current project
  - 🔗 Link as Parent button - Link current project to a parent
  - ❌ Remove button - Remove selected relationship
  - `c` keyboard shortcut - Add component
  - Shows both child and parent relationships in Components tab
  - Relationship types: 🧩 component, 📦 dependency, 🔗 related

### Changed

- TUI now has 11 tabs (added Dossier, Pull Requests, Releases)
- Dossier tab is now the default view when selecting a project
- Database now has 11 tables (added project_pull_request, project_release)
- GitHub sync now fetches PRs (up to 50) and releases (up to 20) per repo

### Fixed

- Fixed `published_at` attribute error in TUI (field names corrected to `release_published_at`)

## [0.1.0] - 2026-01-17

### Added

- Initial release of Dossier documentation tool
- **TUI Dashboard** - Full-featured Textual terminal UI with 8 tabs:
  - Details, Documentation, Languages, Branches, Dependencies, Contributors, Issues, Components
- **GitHub Integration**:
  - Single repo sync (`dossier github sync`)
  - User sync (`dossier github sync-user`)
  - Organization sync (`dossier github sync-org`)
  - Intelligent batching with rate limit handling
  - Extended data: languages, branches, dependencies, contributors, issues
- **CLI Interface** - Comprehensive Click commands with Trogon command explorer
- **REST API** - FastAPI server for programmatic access
- **Documentation Levels** - Query at summary, overview, detailed, or technical levels
- **Project Components** - Model parent-child relationships between projects
- **Data Models**:
  - Project with GitHub metadata
  - DocumentSection for parsed docs
  - ProjectLanguage with file extensions and encoding
  - ProjectBranch with commit info
  - ProjectDependency from manifest files
  - ProjectContributor with commit counts
  - ProjectIssue with state and labels
- **Development Commands**:
  - `dev status` - Database statistics
  - `dev reset` - Reset database
  - `dev clear` - Selective data clearing
  - `dev seed` - Create example data
  - `dev vacuum` - Optimize database
  - `dev dump` - Export data
  - `dev test` - Run test suite
  - `dev purge` - Remove test projects

### Technical

- Python 3.13+ required
- SQLModel ORM with SQLite backend
- httpx HTTP client with retry handling
- Textual 0.89+ for TUI
- Click 8+ with Trogon integration
- FastAPI with lifespan pattern
- pytest test suite with respx mocking

[Unreleased]: https://github.com/quaternionmedia/dossier/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/quaternionmedia/dossier/releases/tag/v0.1.0
