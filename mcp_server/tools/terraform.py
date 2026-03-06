import asyncio
import functools
import re
import subprocess
import shutil
import os
import threading
import uuid
from pathlib import Path
from mcp_server.config import WORKSPACES_DIR

# Background job tracking for long-running terraform commands
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()

# Approved plans: workspace -> job_id
_approved_plans: dict[str, str] = {}
_approved_plans_lock = threading.Lock()

# Cache terraform binary path once at startup — avoids repeated PATH scans
_TERRAFORM_PATH: str | None = shutil.which("terraform")

_TERRAFORM_TIMEOUT = 600  # 10 minutes for init/plan/apply/destroy
_OUTPUT_TIMEOUT = 30

_SAFE_WORKSPACE = re.compile(r"^[a-zA-Z0-9_\-]+$")


def _workspace_path(workspace: str) -> Path:
    if not _SAFE_WORKSPACE.match(workspace):
        raise ValueError(f"Invalid workspace name: '{workspace}'. Only letters, numbers, - and _ are allowed.")
    path = WORKSPACES_DIR / workspace
    path.mkdir(parents=True, exist_ok=True)
    return path


_PLUGIN_CACHE_DIR = Path.home() / ".terraform.d" / "plugin-cache"
_PLUGIN_CACHE_DIR.mkdir(parents=True, exist_ok=True)


@functools.lru_cache(maxsize=1)
def _build_env() -> dict:
    """Build subprocess env once and cache — avoids copying os.environ on every command."""
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
            "TF_PLUGIN_CACHE_DIR": str(_PLUGIN_CACHE_DIR),
        }
    )
    return env


def _run(cmd: list[str], cwd: Path, timeout: int = _OUTPUT_TIMEOUT) -> dict:
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            env=_build_env(),
            timeout=timeout,
        )
        return {
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
            "success": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Command timed out after {timeout}s"}


_MAX_OUTPUT_LINES = 150  # Prevent flooding Claude's context window


async def _run_streaming(cmd: list[str], cwd: Path, log_callback=None, timeout: int = _TERRAFORM_TIMEOUT, max_lines: int = _MAX_OUTPUT_LINES) -> dict:
    """Run a command with real-time output streaming via MCP log notifications."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_build_env(),
    )

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    async def _read_stream(stream, lines, prefix=""):
        while True:
            line = await stream.readline()
            if not line:
                break
            decoded = line.decode().rstrip()
            lines.append(decoded)
            if log_callback and decoded:
                await log_callback(f"{prefix}{decoded}")

    try:
        await asyncio.wait_for(
            asyncio.gather(
                _read_stream(proc.stdout, stdout_lines),
                _read_stream(proc.stderr, stderr_lines),
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        proc.terminate()
        await proc.wait()
        return {"success": False, "error": f"Command timed out after {timeout}s"}

    returncode = await proc.wait()

    # Truncate to avoid overflowing Claude's context — keep tail (summary is at the end)
    total = len(stdout_lines)
    truncated = total > max_lines
    visible = stdout_lines[-max_lines:] if truncated else stdout_lines

    return {
        "stdout": "\n".join(visible),
        "stderr": "\n".join(stderr_lines[-50:]),
        "returncode": returncode,
        "success": returncode == 0,
        **({"truncated": f"Output truncated: showing last {max_lines} of {total} lines"} if truncated else {}),
    }


def _target_args(target: str | None) -> list[str]:
    return ["-target", target] if target else []


# ── Workspace validation ──

def _validate_workspace(path: Path) -> dict | None:
    """Validate that a workspace has the required files. Returns error dict or None."""
    if not path.exists():
        return {"success": False, "error": f"Workspace directory does not exist: {path}"}
    tf_files = list(path.glob("*.tf"))
    if not tf_files:
        return {"success": False, "error": f"No .tf files found in workspace '{path.name}'. Run generate_terraform first."}
    if not (path / "providers.tf").exists():
        return {"success": False, "error": f"Missing providers.tf in workspace '{path.name}'. Run generate_terraform first."}
    return None


# ── Sync functions ──

def _is_initialized(path: Path) -> bool:
    """Check if workspace already has providers installed (and backend configured if backend.tf exists)."""
    providers_dir = path / ".terraform" / "providers"
    lock_file = path / ".terraform.lock.hcl"
    if not (providers_dir.exists() and lock_file.exists()):
        return False
    # If backend.tf exists, verify that backend config is present in .terraform
    backend_tf = path / "backend.tf"
    if backend_tf.exists():
        terraform_dir = path / ".terraform"
        backend_config = terraform_dir / "terraform.tfstate"
        # Check for remote backend marker
        tf_state = terraform_dir / "terraform.tfstate"
        if tf_state.exists():
            import json
            try:
                data = json.loads(tf_state.read_text())
                if data.get("backend", {}).get("type") == "azurerm":
                    return True
            except Exception:
                pass
        return False
    return True


def terraform_init(workspace: str) -> dict:
    if not _TERRAFORM_PATH:
        return {"success": False, "error": "terraform not found in PATH"}
    path = _workspace_path(workspace)
    if _is_initialized(path):
        return {"success": True, "stdout": "Workspace already initialized (skipped).", "stderr": "", "returncode": 0}
    return _run([_TERRAFORM_PATH, "init", "-no-color"], path, timeout=300)


def terraform_plan(workspace: str) -> dict:
    if not _TERRAFORM_PATH:
        return {"success": False, "error": "terraform not found in PATH"}
    return _run([_TERRAFORM_PATH, "plan", "-no-color", "-out=tfplan"], _workspace_path(workspace), timeout=_TERRAFORM_TIMEOUT)


def terraform_apply(workspace: str) -> dict:
    if not _TERRAFORM_PATH:
        return {"success": False, "error": "terraform not found in PATH"}
    path = _workspace_path(workspace)
    plan_file = path / "tfplan"
    cmd = [_TERRAFORM_PATH, "apply", "-no-color", "-auto-approve"]
    if plan_file.exists():
        cmd.append("tfplan")
    return _run(cmd, path, timeout=_TERRAFORM_TIMEOUT)


def terraform_destroy(workspace: str) -> dict:
    if not _TERRAFORM_PATH:
        return {"success": False, "error": "terraform not found in PATH"}
    return _run([_TERRAFORM_PATH, "destroy", "-no-color", "-auto-approve"], _workspace_path(workspace), timeout=_TERRAFORM_TIMEOUT)


def terraform_output(workspace: str) -> dict:
    if not _TERRAFORM_PATH:
        return {"success": False, "error": "terraform not found in PATH"}
    return _run([_TERRAFORM_PATH, "output", "-no-color", "-json"], _workspace_path(workspace))


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


# ── Plan approval ──

def approve_plan(workspace: str, job_id: str) -> dict:
    """Approve a completed terraform plan so that apply can proceed."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        return {"success": False, "error": f"Unknown job_id: '{job_id}'."}
    if job.get("status") != "done":
        return {"success": False, "error": f"Job '{job_id}' is not finished yet (status: {job.get('status')})."}
    if not job.get("success"):
        return {"success": False, "error": f"Cannot approve a failed plan (job '{job_id}')."}

    path = _workspace_path(workspace)
    plan_file = path / "tfplan"
    if not plan_file.exists():
        return {"success": False, "error": f"No tfplan file found in workspace '{workspace}'. Run terraform_plan first."}

    with _approved_plans_lock:
        _approved_plans[workspace] = job_id

    return {"success": True, "message": f"Plan approved for workspace '{workspace}'. You may now run terraform_apply."}


# ── Async streaming functions ──

async def terraform_init_async(workspace: str, log_callback=None) -> dict:
    if not _TERRAFORM_PATH:
        return {"success": False, "error": "terraform not found in PATH"}
    path = _workspace_path(workspace)
    if _is_initialized(path):
        return {"success": True, "stdout": "Workspace already initialized (skipped).", "stderr": "", "returncode": 0}
    backend_tf = path / "backend.tf"
    flags = ["-no-color"]
    if backend_tf.exists():
        flags.append("-reconfigure")
    return _start_job(lambda: _run([_TERRAFORM_PATH, "init"] + flags, path, timeout=300))


def _start_job(fn) -> dict:
    """Run fn in a background thread, return job_id immediately."""
    job_id = uuid.uuid4().hex[:8]
    with _jobs_lock:
        _jobs[job_id] = {"status": "running"}

    def run():
        result = fn()
        with _jobs_lock:
            _jobs[job_id].update({"status": "done", **result})

    threading.Thread(target=run, daemon=True).start()
    return {"job_id": job_id, "status": "running", "message": "Started in background — use get_job_result to check progress."}


def get_job_result(job_id: str) -> dict:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        return {"success": False, "error": f"Unknown job_id: {job_id}"}
    return job


async def terraform_plan_async(workspace: str, log_callback=None) -> dict:
    if not _TERRAFORM_PATH:
        return {"success": False, "error": "terraform not found in PATH"}
    path = _workspace_path(workspace)

    validation_error = _validate_workspace(path)
    if validation_error:
        return validation_error

    has_state = (path / "terraform.tfstate").exists() or (path / ".terraform" / "terraform.tfstate").exists()
    cmd = [_TERRAFORM_PATH, "plan", "-no-color", "-out=tfplan"]
    if not has_state:
        cmd.append("-refresh=false")
    return _start_job(lambda: _run(cmd, path, timeout=_TERRAFORM_TIMEOUT))


async def terraform_apply_async(workspace: str, log_callback=None) -> dict:
    if not _TERRAFORM_PATH:
        return {"success": False, "error": "terraform not found in PATH"}
    path = _workspace_path(workspace)

    validation_error = _validate_workspace(path)
    if validation_error:
        return validation_error

    with _approved_plans_lock:
        approved_job_id = _approved_plans.get(workspace)

    if not approved_job_id:
        return {
            "success": False,
            "error": f"Plan must be approved first. Run terraform_plan, then approve_plan for workspace '{workspace}'.",
        }

    plan_file = path / "tfplan"
    cmd = [_TERRAFORM_PATH, "apply", "-no-color", "-auto-approve"]
    if plan_file.exists():
        cmd.append("tfplan")

    def run_and_clear():
        result = _run(cmd, path, timeout=_TERRAFORM_TIMEOUT)
        if result.get("success"):
            with _approved_plans_lock:
                _approved_plans.pop(workspace, None)
        return result

    return _start_job(run_and_clear)


async def terraform_destroy_async(workspace: str, confirm: bool = False, log_callback=None) -> dict:
    if not confirm:
        return {
            "success": False,
            "error": f"Set confirm=true to destroy all resources in workspace '{workspace}'. THIS IS IRREVERSIBLE.",
        }
    if not _TERRAFORM_PATH:
        return {"success": False, "error": "terraform not found in PATH"}
    path = _workspace_path(workspace)
    return _start_job(lambda: _run([_TERRAFORM_PATH, "destroy", "-no-color", "-auto-approve"], path, timeout=_TERRAFORM_TIMEOUT))


async def terraform_output_async(workspace: str, log_callback=None) -> dict:
    if not _TERRAFORM_PATH:
        return {"success": False, "error": "terraform not found in PATH"}
    return _run([_TERRAFORM_PATH, "output", "-no-color", "-json"], _workspace_path(workspace), timeout=_OUTPUT_TIMEOUT)
