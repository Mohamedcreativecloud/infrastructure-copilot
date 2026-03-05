import subprocess
import json
import shutil


def _az(*args: str) -> dict:
    if not shutil.which("az"):
        return {"success": False, "error": "Azure CLI not found in PATH"}
    result = subprocess.run(
        ["az", *args, "--output", "json"],
        capture_output=True,
        text=True,
    )
    try:
        data = json.loads(result.stdout) if result.stdout.strip() else {}
    except json.JSONDecodeError:
        data = result.stdout.strip()
    return {
        "success": result.returncode == 0,
        "data": data,
        "error": result.stderr.strip() if result.returncode != 0 else None,
    }


def list_resource_groups() -> dict:
    return _az("group", "list")


def list_resources(resource_group: str | None = None) -> dict:
    if resource_group:
        return _az("resource", "list", "--resource-group", resource_group)
    return _az("resource", "list")


def get_resource_group(name: str) -> dict:
    return _az("group", "show", "--name", name)


def list_aks_clusters(resource_group: str | None = None) -> dict:
    args = ["aks", "list"]
    if resource_group:
        args += ["--resource-group", resource_group]
    return _az(*args)


def list_storage_accounts(resource_group: str | None = None) -> dict:
    args = ["storage", "account", "list"]
    if resource_group:
        args += ["--resource-group", resource_group]
    return _az(*args)


def list_vms(resource_group: str | None = None) -> dict:
    args = ["vm", "list"]
    if resource_group:
        args += ["--resource-group", resource_group]
    return _az(*args)


def get_subscription_info() -> dict:
    return _az("account", "show")
