import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")
WORKSPACES_DIR = BASE_DIR / "terraform" / "workspaces"
TEMPLATES_DIR = Path(__file__).parent / "templates"

_KEYVAULT_URL = os.getenv("AZURE_KEYVAULT_URL", "")


def _load_secrets() -> dict:
    """Load secrets from Azure Key Vault if AZURE_KEYVAULT_URL is set, else fall back to env vars."""
    if not _KEYVAULT_URL:
        return {}
    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient

        client = SecretClient(vault_url=_KEYVAULT_URL, credential=DefaultAzureCredential())
        secret_map = {
            "AZURE_CLIENT_ID": "azure-client-id",
            "AZURE_CLIENT_SECRET": "azure-client-secret",
            "AZURE_SUBSCRIPTION_ID": "azure-subscription-id",
            "AZURE_TENANT_ID": "azure-tenant-id",
        }
        result = {}
        for env_key, secret_name in secret_map.items():
            try:
                result[env_key] = client.get_secret(secret_name).value
            except Exception:
                pass  # Fall back to env var for this specific secret
        return result
    except Exception:
        return {}


_kv_secrets = _load_secrets()


def _get(key: str, default: str = "") -> str:
    return _kv_secrets.get(key) or os.getenv(key, default)


AZURE_SUBSCRIPTION_ID = _get("AZURE_SUBSCRIPTION_ID")
AZURE_TENANT_ID = _get("AZURE_TENANT_ID")
AZURE_CLIENT_ID = _get("AZURE_CLIENT_ID")
AZURE_CLIENT_SECRET = _get("AZURE_CLIENT_SECRET")

TFSTATE_RESOURCE_GROUP = os.getenv("TFSTATE_RESOURCE_GROUP", "tfstate-rg")
TFSTATE_STORAGE_ACCOUNT = os.getenv("TFSTATE_STORAGE_ACCOUNT", "tfstateaccount")
TFSTATE_CONTAINER = os.getenv("TFSTATE_CONTAINER", "tfstate")
