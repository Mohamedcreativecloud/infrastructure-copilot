import subprocess
import shutil
from pathlib import Path
from mcp_server.config import WORKSPACES_DIR


def _workspace_path(workspace: str) -> Path:
    path = WORKSPACES_DIR / workspace
    path.mkdir(parents=True, exist_ok=True)
    return path


def _run(cmd: list[str], cwd: Path) -> dict:
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=_build_env(),
    )
    return {
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "returncode": result.returncode,
        "success": result.returncode == 0,
    }


def _build_env() -> dict:
    import os
    from mcp_server.config import (
        AZURE_CLIENT_ID,
        AZURE_CLIENT_SECRET,
        AZURE_SUBSCRIPTION_ID,
        AZURE_TENANT_ID,
    )

    env = os.environ.copy()
    env.update(
        {
            "ARM_CLIENT_ID": AZURE_CLIENT_ID,
            "ARM_CLIENT_SECRET": AZURE_CLIENT_SECRET,
            "ARM_SUBSCRIPTION_ID": AZURE_SUBSCRIPTION_ID,
            "ARM_TENANT_ID": AZURE_TENANT_ID,
            "TF_IN_AUTOMATION": "true",
        }
    )
    return env


def terraform_init(workspace: str) -> dict:
    if not shutil.which("terraform"):
        return {"success": False, "error": "terraform not found in PATH"}
    path = _workspace_path(workspace)
    return _run(["terraform", "init", "-no-color"], path)


def terraform_plan(workspace: str) -> dict:
    if not shutil.which("terraform"):
        return {"success": False, "error": "terraform not found in PATH"}
    path = _workspace_path(workspace)
    return _run(["terraform", "plan", "-no-color", "-out=tfplan"], path)


def terraform_apply(workspace: str) -> dict:
    if not shutil.which("terraform"):
        return {"success": False, "error": "terraform not found in PATH"}
    path = _workspace_path(workspace)
    plan_file = path / "tfplan"
    if plan_file.exists():
        return _run(["terraform", "apply", "-no-color", "-auto-approve", "tfplan"], path)
    return _run(["terraform", "apply", "-no-color", "-auto-approve"], path)


def terraform_destroy(workspace: str) -> dict:
    if not shutil.which("terraform"):
        return {"success": False, "error": "terraform not found in PATH"}
    path = _workspace_path(workspace)
    return _run(["terraform", "destroy", "-no-color", "-auto-approve"], path)


def terraform_output(workspace: str) -> dict:
    if not shutil.which("terraform"):
        return {"success": False, "error": "terraform not found in PATH"}
    path = _workspace_path(workspace)
    return _run(["terraform", "output", "-no-color", "-json"], path)


def list_workspaces() -> list[str]:
    if not WORKSPACES_DIR.exists():
        return []
    return [d.name for d in WORKSPACES_DIR.iterdir() if d.is_dir()]


def get_workspace_files(workspace: str) -> dict:
    path = _workspace_path(workspace)
    files = {}
    for f in path.glob("*.tf"):
        files[f.name] = f.read_text()
    return files
