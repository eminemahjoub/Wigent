from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ProjectInfo:
    type: str = "unknown"
    framework: str | None = None
    language: str = "unknown"
    root_path: Path | None = None
    has_git: bool = False
    has_tests: bool = False
    has_docker: bool = False
    package_manager: str | None = None
    entry_point: Path | None = None
    important_files: list[Path] = field(default_factory=list)
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


GIT_MARKERS = [".git", ".gitconfig"]
MONOREPO_MARKERS = ["pnpm-workspace.yaml", "lerna.json", "nx.json", "turbo.json"]

TEST_DIRS = ["tests", "test", "__tests__", "spec", "e2e"]
TEST_FILES = ["pytest.ini", "setup.cfg", "jest.config.js", "vitest.config.ts"]

IGNORE_DIRS = {
    ".git", "__pycache__", "node_modules", "venv", ".venv",
    ".env", "dist", "build", ".next", ".nuxt", ".turbo",
    "target", ".gradle", ".mvn", ".idea", ".vscode",
}


def _has_file(root: Path, *names: str) -> bool:
    for name in names:
        if (root / name).is_file():
            return True
    return False


def _has_dir(root: Path, name: str) -> bool:
    return (root / name).is_dir()


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


class WorkspaceDetector:
    def find_project_root(self, path: str | Path) -> Path:
        start = Path(path).resolve()
        if start.is_file():
            start = start.parent

        for ancestor in [start] + list(start.parents):
            if (ancestor / ".git").exists() or (ancestor / ".git").is_dir():
                return ancestor
            for marker in MONOREPO_MARKERS:
                if (ancestor / marker).is_file():
                    return ancestor
            if _has_file(ancestor, "pyproject.toml", "setup.py", "setup.cfg",
                         "package.json", "Cargo.toml", "go.mod",
                         "Gemfile", "composer.json"):
                return ancestor

        return start

    def detect_project_type(self, path: str | Path) -> ProjectInfo:
        root = self.find_project_root(path)
        path_str = str(root)

        has_git = (root / ".git").exists() or (root / ".git").is_dir()
        has_docker = (root / "Dockerfile").is_file() or (root / "docker-compose.yml").is_file()
        has_tests = any((root / d).is_dir() for d in TEST_DIRS) or any((root / f).is_file() for f in TEST_FILES)

        pkg_json = _read_json(root / "package.json") if (root / "package.json").is_file() else None
        pyproject = None
        pyproject_path = root / "pyproject.toml"
        if pyproject_path.is_file():
            try:
                import tomllib
                pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
            except (ImportError, OSError, Exception):
                try:
                    import tomli
                    pyproject = tomli.loads(pyproject_path.read_text(encoding="utf-8"))
                except (ImportError, OSError, Exception):
                    pyproject = {"raw": True}

        important: list[Path] = []
        entry_point: Path | None = None

        if (root / "next.config.js").is_file() and pkg_json:
            deps = {**pkg_json.get("dependencies", {}), **pkg_json.get("devDependencies", {})}
            if "next" in deps:
                important = [root / "next.config.js", root / "package.json"]
                if (root / "pages").is_dir():
                    important.append(root / "pages")
                if (root / "app").is_dir():
                    important.append(root / "app")
                return ProjectInfo(
                    type="nextjs", framework="next.js",
                    language="typescript", root_path=root,
                    has_git=has_git, has_tests=has_tests, has_docker=has_docker,
                    package_manager=_detect_pm(root, pkg_json),
                    entry_point=root / "next.config.js",
                    important_files=important,
                )

        if pkg_json:
            deps = {**pkg_json.get("dependencies", {}), **pkg_json.get("devDependencies", {})}
            if "react" in deps:
                important = [root / "package.json"]
                for src in ("src", "app", "lib"):
                    if (root / src).is_dir():
                        important.append(root / src)
                return ProjectInfo(
                    type="react", framework="react",
                    language="typescript" if _has_file(root, "tsconfig.json") else "javascript",
                    root_path=root, has_git=has_git, has_tests=has_tests, has_docker=has_docker,
                    package_manager=_detect_pm(root, pkg_json),
                    entry_point=root / "package.json",
                    important_files=important,
                )
            if "vue" in deps:
                return ProjectInfo(
                    type="vue", framework="vue",
                    language="typescript" if _has_file(root, "tsconfig.json") else "javascript",
                    root_path=root, has_git=has_git, has_tests=has_tests, has_docker=has_docker,
                    package_manager=_detect_pm(root, pkg_json),
                    important_files=[root / "package.json"],
                )
            if (root / "angular.json").is_file():
                return ProjectInfo(
                    type="angular", framework="angular",
                    language="typescript", root_path=root,
                    has_git=has_git, has_tests=has_tests, has_docker=has_docker,
                    package_manager=_detect_pm(root, pkg_json),
                    important_files=[root / "angular.json", root / "package.json"],
                )
            return ProjectInfo(
                type="node", framework="node.js",
                language="typescript" if _has_file(root, "tsconfig.json") else "javascript",
                root_path=root, has_git=has_git, has_tests=has_tests, has_docker=has_docker,
                package_manager=_detect_pm(root, pkg_json),
                entry_point=root / "package.json",
                important_files=[root / "package.json"],
            )

        if (root / "manage.py").is_file():
            entry_point = root / "manage.py"
            important = [entry_point]
            if (root / "requirements.txt").is_file():
                important.append(root / "requirements.txt")
            return ProjectInfo(
                type="django", framework="django",
                language="python", root_path=root,
                has_git=has_git, has_tests=has_tests, has_docker=has_docker,
                package_manager="pip",
                entry_point=entry_point, important_files=important,
            )

        if pyproject and not pyproject.get("raw"):
            project_data = pyproject.get("project", {}) or {}
            deps_str = " ".join(project_data.get("dependencies", [])) if isinstance(project_data.get("dependencies"), list) else ""
            has_fastapi = "fastapi" in deps_str or "uvicorn" in deps_str
            has_flask = "flask" in deps_str.lower()
            build_system = pyproject.get("build-system", {})
            backend = (build_system.get("build-backend") or "").lower() if build_system else ""

            if has_fastapi:
                framework = "fastapi"
                entry_point = root / "main.py" if (root / "main.py").is_file() else None
            elif has_flask:
                framework = "flask"
                entry_point = root / "app.py" if (root / "app.py").is_file() else root / "main.py" if (root / "main.py").is_file() else None
            else:
                framework = None

            important = [pyproject_path]
            if (root / "README.md").is_file():
                important.append(root / "README.md")

            return ProjectInfo(
                type="python", framework=framework,
                language="python", root_path=root,
                has_git=has_git, has_tests=has_tests, has_docker=has_docker,
                package_manager="pip" if not backend else "poetry" if "poetry" in backend else "pdm" if "pdm" in backend else "pip",
                entry_point=entry_point, important_files=important,
            )

        if (root / "setup.py").is_file() or (root / "setup.cfg").is_file() or (root / "requirements.txt").is_file():
            entry_point = root / "setup.py" if (root / "setup.py").is_file() else None
            return ProjectInfo(
                type="python", framework=None,
                language="python", root_path=root,
                has_git=has_git, has_tests=has_tests, has_docker=has_docker,
                package_manager="pip",
                entry_point=entry_point,
                important_files=[root / "setup.py"] if (root / "setup.py").is_file() else [],
            )

        if (root / "Cargo.toml").is_file():
            return ProjectInfo(
                type="rust", framework=None,
                language="rust", root_path=root,
                has_git=has_git, has_tests=has_tests, has_docker=has_docker,
                package_manager="cargo",
                entry_point=root / "Cargo.toml",
                important_files=[root / "Cargo.toml"],
            )

        if (root / "go.mod").is_file():
            return ProjectInfo(
                type="go", framework=None,
                language="go", root_path=root,
                has_git=has_git, has_tests=has_tests, has_docker=has_docker,
                package_manager="go",
                entry_point=root / "go.mod",
                important_files=[root / "go.mod"],
            )

        if (root / "pom.xml").is_file() or (root / "build.gradle").is_file() or (root / "build.gradle.kts").is_file():
            return ProjectInfo(
                type="java", framework=None,
                language="java", root_path=root,
                has_git=has_git, has_tests=has_tests, has_docker=has_docker,
                package_manager="maven" if (root / "pom.xml").is_file() else "gradle",
                entry_point=root / "pom.xml" if (root / "pom.xml").is_file() else None,
                important_files=[root / "pom.xml"] if (root / "pom.xml").is_file() else [],
            )

        if (root / "Gemfile").is_file():
            return ProjectInfo(
                type="ruby", framework=None,
                language="ruby", root_path=root,
                has_git=has_git, has_tests=has_tests, has_docker=has_docker,
                package_manager="bundler",
                important_files=[root / "Gemfile"],
            )

        if (root / "composer.json").is_file():
            return ProjectInfo(
                type="php", framework=None,
                language="php", root_path=root,
                has_git=has_git, has_tests=has_tests, has_docker=has_docker,
                package_manager="composer",
                important_files=[root / "composer.json"],
            )

        if (root / "Dockerfile").is_file():
            return ProjectInfo(
                type="docker", framework=None,
                language="dockerfile", root_path=root,
                has_git=has_git, has_tests=has_tests, has_docker=True,
                package_manager=None,
                important_files=[root / "Dockerfile"],
            )

        if (root / "index.html").is_file():
            return ProjectInfo(
                type="html", framework=None,
                language="html", root_path=root,
                has_git=has_git, has_tests=has_tests, has_docker=has_docker,
                package_manager=None,
                entry_point=root / "index.html",
                important_files=[root / "index.html"],
            )

        return ProjectInfo(
            type="unknown", framework=None,
            language="unknown", root_path=root,
            has_git=has_git, has_tests=has_tests, has_docker=has_docker,
            package_manager=None,
            important_files=important,
        )

    def get_project_metadata(self, path: str | Path) -> dict[str, Any]:
        root = self.find_project_root(path)
        info = self.detect_project_type(path)
        return {
            "name": root.name,
            "type": info.type,
            "framework": info.framework,
            "language": info.language,
            "root": str(root),
            "has_git": info.has_git,
            "has_tests": info.has_tests,
            "has_docker": info.has_docker,
            "package_manager": info.package_manager,
        }

    def list_important_files(self, path: str | Path) -> list[Path]:
        info = self.detect_project_type(path)
        return info.important_files

    def get_tech_stack(self, path: str | Path) -> dict[str, str | None]:
        info = self.detect_project_type(path)
        return {
            "type": info.type,
            "framework": info.framework,
            "language": info.language,
            "package_manager": info.package_manager,
        }

    def is_git_repo(self, path: str | Path) -> bool:
        root = self.find_project_root(path)
        return (root / ".git").exists() or (root / ".git").is_dir()


def _detect_pm(root: Path, pkg_json: dict[str, Any] | None) -> str | None:
    if (root / "pnpm-lock.yaml").is_file():
        return "pnpm"
    if (root / "yarn.lock").is_file():
        return "yarn"
    if (root / "package-lock.json").is_file():
        return "npm"
    if (root / "bun.lockb").is_file() or (root / "bun.lock").is_file():
        return "bun"
    if pkg_json:
        mgr = pkg_json.get("packageManager", "")
        if mgr:
            return mgr.split("@")[0]
    return "npm"


__all__ = [
    "ProjectInfo",
    "WorkspaceDetector",
]
