import asyncio
import json
import logging
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from mcp_server.tools import terraform, azure, generator

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("infrastructure-copilot")

server = Server("infrastructure-copilot")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="generate_terraform",
            description=(
                "Generate a Terraform .tf file for an Azure resource using a template. "
                "Use get_resource_schema first to know which params are required."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace": {
                        "type": "string",
                        "description": "Workspace name (folder under terraform/workspaces/)",
                    },
                    "resource_type": {
                        "type": "string",
                        "enum": ["resource_group", "aks", "vm", "storage", "vnet"],
                        "description": "The Azure resource type to generate",
                    },
                    "params": {
                        "type": "object",
                        "description": "Template parameters for the resource (use get_resource_schema to see required fields)",
                    },
                },
                "required": ["workspace", "resource_type", "params"],
            },
        ),
        Tool(
            name="get_resource_schema",
            description="Get the required and optional parameters for a given Azure resource type before generating Terraform.",
            inputSchema={
                "type": "object",
                "properties": {
                    "resource_type": {
                        "type": "string",
                        "enum": ["resource_group", "aks", "vm", "storage", "vnet"],
                    }
                },
                "required": ["resource_type"],
            },
        ),
        Tool(
            name="terraform_init",
            description="Run 'terraform init' in a workspace. Always run this before plan/apply on a new workspace.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace": {"type": "string", "description": "Workspace name"}
                },
                "required": ["workspace"],
            },
        ),
        Tool(
            name="terraform_plan",
            description="Run 'terraform plan' in a workspace. Shows what will be created/changed/destroyed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace": {"type": "string", "description": "Workspace name"}
                },
                "required": ["workspace"],
            },
        ),
        Tool(
            name="terraform_apply",
            description="Run 'terraform apply' to deploy infrastructure to Azure. Requires init and plan to have run first.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace": {"type": "string", "description": "Workspace name"}
                },
                "required": ["workspace"],
            },
        ),
        Tool(
            name="terraform_destroy",
            description="Run 'terraform destroy' to tear down all resources in a workspace.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace": {"type": "string", "description": "Workspace name"}
                },
                "required": ["workspace"],
            },
        ),
        Tool(
            name="terraform_output",
            description="Get the Terraform output values (e.g. IP addresses, cluster names) after apply.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace": {"type": "string", "description": "Workspace name"}
                },
                "required": ["workspace"],
            },
        ),
        Tool(
            name="list_workspaces",
            description="List all existing Terraform workspaces.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_workspace_files",
            description="Read the Terraform .tf files inside a workspace.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace": {"type": "string", "description": "Workspace name"}
                },
                "required": ["workspace"],
            },
        ),
        Tool(
            name="list_azure_resources",
            description="List Azure resources. Optionally filter by resource group.",
            inputSchema={
                "type": "object",
                "properties": {
                    "resource_group": {
                        "type": "string",
                        "description": "Optional: filter by resource group name",
                    }
                },
            },
        ),
        Tool(
            name="list_resource_groups",
            description="List all Azure Resource Groups in the subscription.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_subscription_info",
            description="Get current Azure subscription details (ID, name, tenant).",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="list_aks_clusters",
            description="List AKS clusters in the subscription or a specific resource group.",
            inputSchema={
                "type": "object",
                "properties": {
                    "resource_group": {"type": "string", "description": "Optional resource group filter"}
                },
            },
        ),
        Tool(
            name="list_vms",
            description="List Virtual Machines in the subscription or a specific resource group.",
            inputSchema={
                "type": "object",
                "properties": {
                    "resource_group": {"type": "string", "description": "Optional resource group filter"}
                },
            },
        ),
        Tool(
            name="list_storage_accounts",
            description="List Storage Accounts in the subscription or a specific resource group.",
            inputSchema={
                "type": "object",
                "properties": {
                    "resource_group": {"type": "string", "description": "Optional resource group filter"}
                },
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None, _dispatch, name, arguments
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    except Exception as e:
        log.exception("Tool error: %s", name)
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]


def _dispatch(name: str, args: dict):
    match name:
        case "generate_terraform":
            return generator.generate_terraform(
                workspace=args["workspace"],
                resource_type=args["resource_type"],
                params=args["params"],
            )
        case "get_resource_schema":
            return generator.get_resource_schema(args["resource_type"])
        case "terraform_init":
            return terraform.terraform_init(args["workspace"])
        case "terraform_plan":
            return terraform.terraform_plan(args["workspace"])
        case "terraform_apply":
            return terraform.terraform_apply(args["workspace"])
        case "terraform_destroy":
            return terraform.terraform_destroy(args["workspace"])
        case "terraform_output":
            return terraform.terraform_output(args["workspace"])
        case "list_workspaces":
            return terraform.list_workspaces()
        case "get_workspace_files":
            return terraform.get_workspace_files(args["workspace"])
        case "list_azure_resources":
            return azure.list_resources(args.get("resource_group"))
        case "list_resource_groups":
            return azure.list_resource_groups()
        case "get_subscription_info":
            return azure.get_subscription_info()
        case "list_aks_clusters":
            return azure.list_aks_clusters(args.get("resource_group"))
        case "list_vms":
            return azure.list_vms(args.get("resource_group"))
        case "list_storage_accounts":
            return azure.list_storage_accounts(args.get("resource_group"))
        case _:
            return {"success": False, "error": f"Unknown tool: {name}"}


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
