import asyncio
import json
import logging
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from mcp_server.tools import terraform, azure, generator
from mcp_server import audit

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
            description=(
                "Run 'terraform apply' to deploy infrastructure to Azure. "
                "Requires terraform_plan to have run AND approve_plan to have been called first."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace": {"type": "string", "description": "Workspace name"}
                },
                "required": ["workspace"],
            },
        ),
        Tool(
            name="approve_plan",
            description="Approve a completed terraform plan before apply can run. Call after terraform_plan job is done.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace": {"type": "string", "description": "Workspace name"},
                    "job_id": {"type": "string", "description": "Job ID returned by terraform_plan"},
                },
                "required": ["workspace", "job_id"],
            },
        ),
        Tool(
            name="terraform_destroy",
            description=(
                "DANGER: Destroys ALL resources in a workspace. THIS IS IRREVERSIBLE. "
                "You must set confirm=true explicitly to proceed."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace": {"type": "string", "description": "Workspace name"},
                    "confirm": {
                        "type": "boolean",
                        "description": "Must be set to true to confirm destruction of all resources. THIS IS IRREVERSIBLE.",
                    },
                },
                "required": ["workspace", "confirm"],
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
            name="get_job_result",
            description="Check the result of a background terraform job (plan/apply/destroy). Poll until status is 'done'.",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "Job ID returned by terraform_plan, terraform_apply, or terraform_destroy"}
                },
                "required": ["job_id"],
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
            name="get_audit_log",
            description="Return the most recent audit log entries (tool calls and their outcomes).",
            inputSchema={
                "type": "object",
                "properties": {
                    "n": {
                        "type": "integer",
                        "description": "Number of recent entries to return (default 50)",
                        "default": 50,
                    }
                },
            },
        ),
        Tool(
            name="list_azure_resources",
            description="List Azure resources. Always prefer filtering by resource_group — listing all resources in a subscription can be very slow and return thousands of results.",
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
        streaming_tools = {"terraform_init", "terraform_plan", "terraform_apply", "terraform_destroy", "terraform_output"}

        if name in streaming_tools:
            async def log_callback(message: str):
                ctx = server.request_context
                await ctx.session.send_log_message(level="info", data=message, logger="terraform")

            result = await _dispatch_async(name, arguments, log_callback)
        else:
            result = await asyncio.get_running_loop().run_in_executor(
                None, _dispatch, name, arguments
            )

        success = result.get("success", True) if isinstance(result, dict) else True
        audit.log_event(name, arguments, result if isinstance(result, dict) else {}, success)

        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    except Exception as e:
        log.exception("Tool error: %s", name)
        err = {"success": False, "error": str(e)}
        audit.log_event(name, arguments, err, False)
        return [TextContent(type="text", text=json.dumps(err))]


async def _dispatch_async(name: str, args: dict, log_callback):
    match name:
        case "terraform_init":
            return await terraform.terraform_init_async(args["workspace"], log_callback)
        case "terraform_plan":
            return await terraform.terraform_plan_async(args["workspace"], log_callback)
        case "terraform_apply":
            return await terraform.terraform_apply_async(args["workspace"], log_callback)
        case "terraform_destroy":
            return await terraform.terraform_destroy_async(
                args["workspace"],
                confirm=args.get("confirm", False),
                log_callback=log_callback,
            )
        case "terraform_output":
            return await terraform.terraform_output_async(args["workspace"], log_callback)


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
        case "approve_plan":
            return terraform.approve_plan(args["workspace"], args["job_id"])
        case "terraform_output":
            return terraform.terraform_output(args["workspace"])
        case "get_job_result":
            return terraform.get_job_result(args["job_id"])
        case "list_workspaces":
            return terraform.list_workspaces()
        case "get_workspace_files":
            return terraform.get_workspace_files(args["workspace"])
        case "get_audit_log":
            return audit.get_recent_events(args.get("n", 50))
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
