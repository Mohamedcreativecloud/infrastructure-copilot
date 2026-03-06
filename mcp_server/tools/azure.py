import functools
from mcp_server.config import (
    AZURE_CLIENT_ID,
    AZURE_CLIENT_SECRET,
    AZURE_SUBSCRIPTION_ID,
    AZURE_TENANT_ID,
)
from azure.identity import ClientSecretCredential
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.containerservice import ContainerServiceClient
from azure.mgmt.storage import StorageManagementClient
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.subscription import SubscriptionClient


# All clients are cached — one auth token + one connection pool per session.
# This replaces shelling out to `az` CLI (which spawned a new Python process per call).

@functools.lru_cache(maxsize=1)
def _credential() -> ClientSecretCredential:
    return ClientSecretCredential(
        tenant_id=AZURE_TENANT_ID,
        client_id=AZURE_CLIENT_ID,
        client_secret=AZURE_CLIENT_SECRET,
    )


@functools.lru_cache(maxsize=1)
def _resource_client() -> ResourceManagementClient:
    return ResourceManagementClient(_credential(), AZURE_SUBSCRIPTION_ID)


@functools.lru_cache(maxsize=1)
def _subscription_client() -> SubscriptionClient:
    return SubscriptionClient(_credential())


@functools.lru_cache(maxsize=1)
def _aks_client() -> ContainerServiceClient:
    return ContainerServiceClient(_credential(), AZURE_SUBSCRIPTION_ID)


@functools.lru_cache(maxsize=1)
def _storage_client() -> StorageManagementClient:
    return StorageManagementClient(_credential(), AZURE_SUBSCRIPTION_ID)


@functools.lru_cache(maxsize=1)
def _compute_client() -> ComputeManagementClient:
    return ComputeManagementClient(_credential(), AZURE_SUBSCRIPTION_ID)


def get_subscription_info() -> dict:
    try:
        sub = _subscription_client().subscriptions.get(AZURE_SUBSCRIPTION_ID)
        return {
            "success": True,
            "data": {
                "id": sub.subscription_id,
                "name": sub.display_name,
                "tenant_id": getattr(sub, "tenant_id", AZURE_TENANT_ID),
                "state": str(sub.state),
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_resource_groups() -> dict:
    try:
        groups = list(_resource_client().resource_groups.list())
        return {
            "success": True,
            "data": [
                {"name": g.name, "location": g.location, "tags": g.tags}
                for g in groups
            ],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_resource_group(name: str) -> dict:
    try:
        g = _resource_client().resource_groups.get(name)
        return {"success": True, "data": {"name": g.name, "location": g.location, "tags": g.tags}}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_resources(resource_group: str | None = None) -> dict:
    try:
        client = _resource_client()
        if resource_group:
            items = list(client.resources.list_by_resource_group(resource_group))
        else:
            items = list(client.resources.list())
        return {
            "success": True,
            "data": [
                {"name": r.name, "type": r.type, "location": r.location, "tags": r.tags}
                for r in items
            ],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_aks_clusters(resource_group: str | None = None) -> dict:
    try:
        client = _aks_client()
        if resource_group:
            clusters = list(client.managed_clusters.list_by_resource_group(resource_group))
        else:
            clusters = list(client.managed_clusters.list())
        return {
            "success": True,
            "data": [
                {
                    "name": c.name,
                    "location": c.location,
                    "kubernetes_version": c.kubernetes_version,
                    "provisioning_state": c.provisioning_state,
                }
                for c in clusters
            ],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_storage_accounts(resource_group: str | None = None) -> dict:
    try:
        client = _storage_client()
        if resource_group:
            accounts = list(client.storage_accounts.list_by_resource_group(resource_group))
        else:
            accounts = list(client.storage_accounts.list())
        return {
            "success": True,
            "data": [
                {
                    "name": a.name,
                    "location": a.location,
                    "sku": a.sku.name if a.sku else None,
                    "kind": a.kind,
                }
                for a in accounts
            ],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_vms(resource_group: str | None = None) -> dict:
    try:
        client = _compute_client()
        if resource_group:
            vms = list(client.virtual_machines.list(resource_group))
        else:
            vms = list(client.virtual_machines.list_all())
        return {
            "success": True,
            "data": [
                {
                    "name": v.name,
                    "location": v.location,
                    "vm_size": v.hardware_profile.vm_size if v.hardware_profile else None,
                }
                for v in vms
            ],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
