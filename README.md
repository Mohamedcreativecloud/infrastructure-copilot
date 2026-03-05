# Infrastructure Copilot

An MCP (Model Context Protocol) server that lets you design and deploy Azure infrastructure using natural language. Describe what you need, and the server generates and applies Terraform code against your Azure subscription.

## Features

- Generate Terraform HCL from structured parameters using Jinja2 templates
- Run `terraform init`, `plan`, `apply`, and `destroy` from within your MCP client
- Query live Azure resources (resource groups, AKS clusters, VMs, storage accounts)
- Workspace-based isolation — each project gets its own folder under `terraform/workspaces/`
- Supports: **Resource Groups**, **AKS**, **Virtual Machines**, **Storage Accounts**, **Virtual Networks**

## Prerequisites

| Tool | Version |
|------|---------|
| Python | >= 3.11 |
| Terraform | >= 1.6 |
| Azure CLI | >= 2.50 |

## Setup

### 1. Clone and install

```bash
git clone https://github.com/Mohamedcreativecloud/infrastructure-copilot.git
cd infrastructure-copilot
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Create an Azure Service Principal

```bash
az login
az ad sp create-for-rbac \
  --name "infrastructure-copilot-sp" \
  --role Contributor \
  --scopes /subscriptions/<SUBSCRIPTION_ID>
```

Copy the output values into your `.env` file:

```bash
cp .env.example .env
# edit .env with your values
```

### 3. Configure Claude Desktop

Open your Claude Desktop config file:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

Add the server block from `claude_desktop_config.json` in this repo, updating the `cwd` and `env` values.

Restart Claude Desktop — the tools will appear automatically.

## Usage Examples

Once connected, talk to Claude naturally:

> "Create a resource group called `prod-rg` in Norway East"

> "Deploy an AKS cluster with 3 nodes using Standard_D2s_v3, autoscaling up to 10, in the prod-rg resource group"

> "Show me all resource groups in my subscription"

> "Destroy the dev workspace"

## Project Structure

```
infrastructure-copilot/
├── mcp_server/
│   ├── server.py          # MCP server — registers all tools
│   ├── config.py          # Environment config
│   └── tools/
│       ├── terraform.py   # terraform init/plan/apply/destroy/output
│       ├── azure.py       # Azure CLI queries
│       └── generator.py   # Jinja2 template rendering
│   └── templates/
│       ├── providers.tf.j2
│       ├── resource_group.tf.j2
│       ├── aks.tf.j2
│       ├── vm.tf.j2
│       ├── storage.tf.j2
│       └── vnet.tf.j2
├── terraform/
│   └── workspaces/        # Generated .tf files per workspace
├── .env.example
├── requirements.txt
└── claude_desktop_config.json
```

## Supported Resources

| Resource Type | Required Params |
|---------------|----------------|
| `resource_group` | `name`, `location` |
| `aks` | `name`, `location`, `resource_group_name`, `node_count`, `vm_size` |
| `vm` | `name`, `location`, `resource_group_name`, `vm_size`, `admin_username` |
| `storage` | `name`, `location`, `resource_group_name` |
| `vnet` | `name`, `location`, `resource_group_name`, `address_space` |

## Available MCP Tools

| Tool | Description |
|------|-------------|
| `get_resource_schema` | Get required/optional params for a resource type |
| `generate_terraform` | Render a `.tf` file from a template |
| `terraform_init` | Initialize a workspace |
| `terraform_plan` | Preview changes |
| `terraform_apply` | Deploy to Azure |
| `terraform_destroy` | Tear down resources |
| `terraform_output` | Read output values |
| `list_workspaces` | List all workspaces |
| `get_workspace_files` | Read `.tf` files in a workspace |
| `list_resource_groups` | List Azure resource groups |
| `list_azure_resources` | List all Azure resources |
| `list_aks_clusters` | List AKS clusters |
| `list_vms` | List Virtual Machines |
| `list_storage_accounts` | List Storage Accounts |
| `get_subscription_info` | Current subscription details |

## Security Notes

- Never commit `.env` — it is in `.gitignore`
- Use a dedicated Service Principal with minimum required permissions
- Terraform state files (`.tfstate`) are excluded from git
- For production, configure remote state in Azure Blob Storage using `TFSTATE_*` env vars

## License

MIT
