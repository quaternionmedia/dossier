# Contributing Guide

[← Back to Index](index.md) | [Extending](extending.md) | [Architecture](architecture.md)

---

Thank you for your interest in contributing to Dossier! This guide covers the development workflow. For adding custom parsers, data models, or extending Dossier for your needs, see [Extending Dossier](extending.md).

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Code Standards](#code-standards)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Release Process](#release-process)

## Code of Conduct

We are committed to providing a welcoming and inclusive experience for everyone. Please:

- Be respectful and inclusive
- Welcome newcomers and help them learn
- Focus on constructive feedback
- Assume good intentions

## Getting Started

### Prerequisites

- Python 3.13 or higher
- [uv](https://github.com/astral-sh/uv) package manager
- Git

### Fork and Clone

```bash
# Fork the repository on GitHub, then:
git clone https://github.com/YOUR-USERNAME/dossier.git
cd dossier

# Add upstream remote
git remote add upstream https://github.com/quaternionmedia/dossier.git
```

## Development Setup

### Install Dependencies

```bash
# Install all dependencies including dev dependencies
uv sync

# Verify installation
uv run dossier --version
```

### IDE Setup

#### VS Code (Recommended)

Install recommended extensions:
- Python (Microsoft)
- Pylance
- Ruff

Settings are pre-configured in `.vscode/settings.json`.

#### PyCharm

1. Open project directory
2. Configure Python interpreter to use `.venv/bin/python`
3. Enable pytest as test runner

### Verify Setup

```bash
# Run tests
uv run pytest

# Run linting
uv run ruff check .

# Format code
uv run ruff format .
```

## Making Changes

### Branch Naming

Use descriptive branch names:

| Type | Pattern | Example |
|------|---------|---------|
| Feature | `feature/<description>` | `feature/add-rst-parser` |
| Bug Fix | `fix/<description>` | `fix/query-level-filter` |
| Documentation | `docs/<description>` | `docs/api-examples` |
| Refactor | `refactor/<description>` | `refactor/parser-registry` |

### Workflow

```bash
# 1. Create a feature branch
git checkout -b feature/my-feature

# 2. Make changes and commit
git add .
git commit -m "feat: add new feature"

# 3. Keep branch updated
git fetch upstream
git rebase upstream/main

# 4. Push changes
git push origin feature/my-feature

# 5. Open Pull Request on GitHub
```

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

#### Types

| Type | Description |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation changes |
| `style` | Code style (formatting, semicolons) |
| `refactor` | Code refactoring |
| `test` | Adding or updating tests |
| `chore` | Maintenance tasks |

#### Examples

```
feat(parser): add ReStructuredText parser support

fix(api): correct documentation level filtering

docs(readme): update installation instructions

test(cli): add tests for register command edge cases
```

## Code Standards

### Python Style

We follow [PEP 8](https://pep8.org/) with these specifics:

- **Line length**: 88 characters (Black default)
- **Quotes**: Double quotes for strings
- **Imports**: Sorted with isort

### Type Hints

All code must include type hints:

```python
# ✅ Good
def parse_file(file_path: Path) -> list[DocumentSection]:
    ...

# ❌ Bad
def parse_file(file_path):
    ...
```

### Docstrings

Use Google-style docstrings:

```python
def parse(self, file_path: Path) -> list[DocumentSection]:
    """Parse a documentation file into sections.
    
    Args:
        file_path: Path to the file to parse.
        
    Returns:
        List of DocumentSection objects extracted from the file.
        
    Raises:
        FileNotFoundError: If the file doesn't exist.
        ParseError: If the file cannot be parsed.
    """
```

### Code Organization

```python
# 1. Standard library imports
import os
from pathlib import Path

# 2. Third-party imports
from fastapi import FastAPI
from sqlmodel import Session

# 3. Local imports
from dossier.models import Project
```

## Testing

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run specific test file
uv run pytest tests/test_api.py

# Run specific test
uv run pytest tests/test_api.py::test_list_projects

# Run with coverage
uv run pytest --cov=dossier --cov-report=html

# Generate documentation screenshots
uv run pytest tests/test_tui.py --screenshots
```

### Test Naming Conventions

**Important**: All test projects must include "test" in their name so they can be automatically purged after test runs.

```python
# ✅ Good - will be purged by `dossier dev purge -p test`
Project(name="test/my-project")
Project(name="test-org/some-repo")
Project(name="test-minimal")

# ❌ Bad - won't be cleaned up automatically  
Project(name="fastapi/fastapi")
Project(name="my-project")
```

The test suite automatically runs `uv run dossier dev purge -p "test" -y` before and after test runs to clean up test data.

### Screenshot Generation

The TUI tests include parameterized screenshot generation for documentation:

```bash
# Generate all screenshots to docs/screenshots/
uv run pytest tests/test_tui.py::TestTUIScreenshotsParameterized --screenshots -v

# Or via the CLI test command
uv run dossier test --screenshots
```

Screenshots are generated at multiple resolutions:
- **Desktop** (120x40) - Standard terminal size
- **Wide** (160x50) - Wide terminal 
- **Compact** (80x30) - Minimal terminal

**Note:** Screenshots require test projects to be seeded first. The test suite handles this automatically.

### Writing Tests

#### Test File Naming

- Test files: `test_<module>.py`
- Test functions: `test_<description>`

#### Test Structure

```python
def test_should_do_something_when_condition():
    """Test description explaining the scenario."""
    # Arrange
    input_data = create_test_data()
    
    # Act
    result = function_under_test(input_data)
    
    # Assert
    assert result.status == expected_status
```

#### Test Categories

| Category | Location | Description |
|----------|----------|-------------|
| Unit | `tests/test_*.py` | Test individual functions |
| Integration | `tests/test_api.py` | Test API endpoints |
| CLI | `tests/test_cli.py` | Test CLI commands |

### Test Coverage

Aim for:
- **Minimum**: 80% coverage
- **Target**: 90% coverage
- **Critical paths**: 100% coverage

## Pull Request Process

### Before Submitting

- [ ] All tests pass (`uv run pytest`)
- [ ] Code is formatted (`uv run ruff format .`)
- [ ] Linting passes (`uv run ruff check .`)
- [ ] Documentation updated if needed
- [ ] Commit messages follow conventions

### PR Template

```markdown
## Description
Brief description of changes.

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
Describe how you tested the changes.

## Checklistgit add -A && git commit -m "feat(tui): add entity tree expansion, clickable dossier links, and dashboard docs"
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] Changelog updated
```

### Review Process

1. **Automated checks** run on PR creation
2. **Code review** by at least one maintainer
3. **Address feedback** and update PR
4. **Approval** from maintainer
5. **Merge** using squash and merge

## Adding New Features

### Adding a New Parser

1. Create parser file:

```python
# src/dossier/parsers/rst.py
from dossier.parsers.base import BaseParser

class ReStructuredTextParser(BaseParser):
    file_extensions = [".rst"]
    
    def parse(self, file_path: Path) -> list[DocumentSection]:
        # Implementation
        pass
```

2. Register in `__init__.py`:

```python
from .rst import ReStructuredTextParser
```

3. Add tests:

```python
# tests/test_parsers.py
def test_rst_parser():
    parser = ReStructuredTextParser()
    # Test implementation
```

### Adding a New API Endpoint

1. Add route in `api/main.py`:

```python
@app.get("/new-endpoint")
def new_endpoint(session: Session = Depends(get_session)):
    # Implementation
    pass
```

2. Add tests in `tests/test_api.py`:

```python
def test_new_endpoint(client):
    response = client.get("/new-endpoint")
    assert response.status_code == 200
```

3. Update API documentation

### Adding a New CLI Command

1. Add command in `cli.py`:

```python
@main.command()
@click.argument("arg")
def new_command(arg: str):
    """Command description."""
    # Implementation
    pass
```

2. Add tests in `tests/test_cli.py`:

```python
def test_new_command():
    runner = CliRunner()
    result = runner.invoke(main, ["new-command", "arg"])
    assert result.exit_code == 0
```

## Release Process

### Version Numbering

We use [Semantic Versioning](https://semver.org/):

- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

### Release Checklist

1. Update version in `src/dossier/__init__.py`
2. Update CHANGELOG.md
3. Create release PR
4. After merge, tag release: `git tag v0.2.0`
5. Push tag: `git push --tags`

## Getting Help

- **Questions**: Open a GitHub Discussion
- **Bugs**: Open a GitHub Issue
- **Security**: Email security@your-org.com

## Recognition

Contributors are recognized in:
- CONTRIBUTORS.md file
- Release notes
- Project README

Thank you for contributing to Dossier! 🎉
