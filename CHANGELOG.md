# Changelog

All notable changes to the Wigent project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial project scaffolding with autonomous AI coding agent (`agent.py`)
- Tool implementations: `write_file`, `read_file`, `run_command`, `list_files`, `search_codebase`, `get_file_summary`
- OpenAI GPT-4o function-calling integration with think-act-observe loop
- Workspace sandbox with path-escape guards for all file operations
- Professional `.gitignore` covering Python, venv, IDE, OS, and AI artifacts
- `CHANGELOG.md` following Keep a Changelog format
- `CONTRIBUTING.md` with development workflow and guidelines
- GitHub issue templates for bug reports and feature requests
- Branch strategy: `main` (production), `develop` (active), `refactor/modular-architecture` (current work)

### Security
- Path-traversal protection on `write_file` and `read_file`
- Workspace sandbox restricts all file I/O to `agent_workspace/` directory
