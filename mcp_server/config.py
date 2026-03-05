import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
WORKSPACES_DIR = BASE_DIR / "terraform" / "workspaces"
TEMPLATES_DIR = Path(__file__).parent / "templates"

AZURE_SUBSCRIPTION_ID = os.getenv("AZURE_SUBSCRIPTION_ID", "")
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID", "")
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "")
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "")

TFSTATE_RESOURCE_GROUP = os.getenv("TFSTATE_RESOURCE_GROUP", "tfstate-rg")
TFSTATE_STORAGE_ACCOUNT = os.getenv("TFSTATE_STORAGE_ACCOUNT", "tfstateaccount")
TFSTATE_CONTAINER = os.getenv("TFSTATE_CONTAINER", "tfstate")
