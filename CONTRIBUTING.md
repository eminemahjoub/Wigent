# Contributing to Wigent

We're excited that you want to contribute! This document outlines the workflow, standards, and conventions used in this project.

---

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Getting Started](#getting-started)
3. [Development Workflow](#development-workflow)
4. [Branch Strategy](#branch-strategy)
5. [Coding Standards](#coding-standards)
6. [Commit Guidelines](#commit-guidelines)
7. [Pull Request Process](#pull-request-process)
8. [Issue Reporting](#issue-reporting)

---

## Code of Conduct

This project follows a **no-tolerance for harassment** policy. Be respectful, constructive, and inclusive. Disagreements are expected, but personal attacks are not.

---

## Getting Started

1. **Clone the repository:**
   ```bash
   git clone git@github.com:your-org/wigent.git
   cd wigent
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set environment variables:**
   ```bash
   export OPENAI_API_KEY="your-api-key-here"
   ```

5. **Run the agent:**
   ```bash
   python agent.py
   ```

---

## Development Workflow

1. **Pick an issue** from the tracker or create one describing what you want to work on.
2. **Create a branch** from `develop` following our naming convention (see below).
3. **Make changes** — keep them small, focused, and well-tested.
4. **Run linting and type checks** before committing:
   ```bash
   ruff check .
   mypy .
   ```
5. **Write or update tests** in `tests/`.
6. **Run tests** to verify nothing is broken:
   ```bash
   pytest
   ```
7. **Commit** using conventional commit messages.
8. **Push** and open a Pull Request targeting `develop`.

---

## Branch Strategy

| Branch | Purpose | Protected |
|---|---|---|
| `main` | Production-ready code | Yes |
| `develop` | Active development integration | Yes |
| `refactor/*` | Code refactoring efforts | No |
| `feature/*` | New features | No |
| `fix/*` | Bug fixes | No |
| `docs/*` | Documentation-only changes | No |

**Rules:**
- `main` is **always** deployable.
- All PRs target `develop` unless it's an urgent hotfix (then target `main`).
- Branch names use lowercase with hyphens (e.g., `feature/multi-model-support`).

---

## Coding Standards

### Python

- **Style:** Follow [PEP 8](https://peps.python.org/pep-0008/).
- **Formatting:** Use `ruff format` (line length = 100).
- **Linting:** Run `ruff check` — no warnings allowed on commits.
- **Types:** All function signatures must have type annotations. Use `mypy` in strict mode.
- **Docstrings:** Use Google-style docstrings for all public functions and classes.
- **Imports:** Organize in three blocks separated by a blank line:
  1. Standard library
  2. Third-party
  3. Local

### Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]
```

**Types:** `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `style`, `ci`, `perf`, `security`

**Examples:**
```
feat(tools): add search_codebase with ripgrep fallback
fix(agent): handle API timeout with exponential backoff
refactor(loop): extract tool dispatcher into separate module
docs(readme): add quickstart section
```

---

## Pull Request Process

1. Ensure your branch is rebased onto the latest `develop`.
2. Run the full test suite and lint/type checks — CI must pass.
3. Update `CHANGELOG.md` under `[Unreleased]` with your changes.
4. Request review from at least one maintainer.
5. Address all review feedback.
6. A maintainer will squash-merge into `develop`.

**PR title format:** `type(scope): brief description` (same as commit messages).

---

## Issue Reporting

Use the provided GitHub issue templates:

- **Bug report:** `.github/ISSUE_TEMPLATE/bug.md`
- **Feature request:** `.github/ISSUE_TEMPLATE/feature.md`

Include as much context as possible: OS version, Python version, relevant logs, steps to reproduce, and expected vs actual behavior.

---

## Questions?

Open a [Discussion](https://github.com/your-org/wigent/discussions) or ping a maintainer.
