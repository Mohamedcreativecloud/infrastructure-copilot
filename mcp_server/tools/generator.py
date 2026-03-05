from pathlib import Path
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from mcp_server.config import TEMPLATES_DIR, WORKSPACES_DIR


SUPPORTED_RESOURCES = [
    "resource_group",
    "aks",
    "vm",
    "storage",
    "vnet",
]

_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)


def generate_terraform(
    workspace: str,
    resource_type: str,
    params: dict,
) -> dict:
    if resource_type not in SUPPORTED_RESOURCES:
        return {
            "success": False,
            "error": f"Unsupported resource type '{resource_type}'. Supported: {SUPPORTED_RESOURCES}",
        }

    template_file = f"{resource_type}.tf.j2"
    try:
        template = _jinja_env.get_template(template_file)
    except Exception as e:
        return {"success": False, "error": f"Template not found: {e}"}

    try:
        rendered = template.render(**params)
    except Exception as e:
        return {"success": False, "error": f"Template render error: {e}"}

    workspace_path = WORKSPACES_DIR / workspace
    workspace_path.mkdir(parents=True, exist_ok=True)

    output_file = workspace_path / f"{resource_type}.tf"
    output_file.write_text(rendered)

    providers_result = _ensure_providers(workspace, params)

    return {
        "success": True,
        "file": str(output_file),
        "content": rendered,
        "providers_written": providers_result,
    }


def _ensure_providers(workspace: str, params: dict) -> bool:
    providers_file = WORKSPACES_DIR / workspace / "providers.tf"
    if providers_file.exists():
        return False
    try:
        template = _jinja_env.get_template("providers.tf.j2")
        rendered = template.render(**params)
        providers_file.write_text(rendered)
        return True
    except Exception:
        return False


def list_supported_resources() -> list[str]:
    return SUPPORTED_RESOURCES


def get_resource_schema(resource_type: str) -> dict:
    schemas = {
        "resource_group": {
            "required": ["name", "location"],
            "optional": ["tags"],
            "description": "Azure Resource Group",
        },
        "aks": {
            "required": ["name", "location", "resource_group_name", "node_count", "vm_size"],
            "optional": ["kubernetes_version", "min_node_count", "max_node_count", "enable_autoscaling", "tags"],
            "description": "Azure Kubernetes Service cluster",
        },
        "vm": {
            "required": ["name", "location", "resource_group_name", "vm_size", "admin_username"],
            "optional": ["os_disk_size_gb", "source_image_publisher", "source_image_offer", "source_image_sku", "tags"],
            "description": "Azure Virtual Machine",
        },
        "storage": {
            "required": ["name", "location", "resource_group_name"],
            "optional": ["account_tier", "account_replication_type", "enable_https", "tags"],
            "description": "Azure Storage Account",
        },
        "vnet": {
            "required": ["name", "location", "resource_group_name", "address_space"],
            "optional": ["subnets", "tags"],
            "description": "Azure Virtual Network",
        },
    }
    return schemas.get(resource_type, {})
