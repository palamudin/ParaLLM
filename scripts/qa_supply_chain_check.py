from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path


class SupplyChainError(RuntimeError):
    pass


REMOTE_ACTION_RE = re.compile(r"uses:\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@([^\s#]+)")
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REMOTE_SCRIPT_RE = re.compile(r"<script[^>]+src=[\"']https?://", re.I)
REMOTE_STYLESHEET_RE = re.compile(r"<link[^>]+href=[\"']https?://", re.I)


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def info(message: str) -> None:
    print(f"[supply-chain] {message}")


def require_pinned_requirements(path: Path) -> None:
    if not path.is_file():
        raise SupplyChainError(f"Missing dependency manifest: {path.relative_to(project_root())}")
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-r "):
            continue
        if "==" not in line:
            raise SupplyChainError(f"{path.name}:{line_number} is not exactly pinned: {line}")


def require_local_browser_assets(index_path: Path) -> None:
    html = index_path.read_text(encoding="utf-8")
    if REMOTE_SCRIPT_RE.search(html):
        raise SupplyChainError("index.html still loads a remote script at runtime.")
    if REMOTE_STYLESHEET_RE.search(html):
        raise SupplyChainError("index.html still loads a remote stylesheet at runtime.")


def require_sha_pinned_actions(workflows_dir: Path) -> None:
    for workflow in sorted(workflows_dir.glob("*.yml")):
        content = workflow.read_text(encoding="utf-8")
        if "permissions:" not in content:
            raise SupplyChainError(f"{workflow.name} is missing an explicit permissions block.")
        for match in REMOTE_ACTION_RE.finditer(content):
            action, ref = match.groups()
            if action.startswith("./"):
                continue
            if not FULL_SHA_RE.fullmatch(ref):
                raise SupplyChainError(
                    f"{workflow.name} uses mutable action ref {action}@{ref}. Pin a full commit SHA."
                )


def run_pip_audit(root: Path) -> None:
    pip_audit_bin = shutil.which("pip-audit")
    if not pip_audit_bin:
        raise SupplyChainError("pip-audit is not installed. Install requirements-dev.txt first.")
    result = subprocess.run(
        [pip_audit_bin, "-r", str(root / "requirements-ci.txt")],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    if stdout:
        print(stdout)
    if stderr:
        print(stderr, file=sys.stderr)
    if result.returncode != 0:
        raise SupplyChainError(f"pip-audit failed with exit code {result.returncode}.")


def main() -> int:
    root = project_root()
    try:
        info("Checking pinned Python dependency manifests")
        require_pinned_requirements(root / "requirements-ci.txt")
        require_pinned_requirements(root / "requirements-dev.txt")

        info("Checking runtime browser assets are local")
        require_local_browser_assets(root / "index.html")

        info("Checking GitHub Actions workflow pinning")
        require_sha_pinned_actions(root / ".github" / "workflows")

        info("Running pip-audit against requirements-ci.txt")
        run_pip_audit(root)

        info("PASS")
        return 0
    except SupplyChainError as exc:
        info(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
