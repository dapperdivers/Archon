"""
MCP Server Template Management

This module provides utilities for managing MCP server templates.
"""


from .models import MCPServerCapability, MCPServerTemplate


def create_template_from_config(config: dict) -> MCPServerTemplate:
    """Create a server template from a configuration dictionary."""

    # Convert capabilities
    capabilities = []
    for cap_data in config.get("capabilities", []):
        capability = MCPServerCapability(
            name=cap_data["name"],
            description=cap_data["description"],
            category=cap_data.get("category", "general"),
            parameters=cap_data.get("parameters", []),
            examples=cap_data.get("examples", [])
        )
        capabilities.append(capability)

    return MCPServerTemplate(
        server_id=config["server_id"],
        name=config["name"],
        description=config["description"],
        server_type=config["server_type"],
        package=config.get("package"),
        command=config.get("command"),
        default_args=config.get("default_args", []),
        required_env=config.get("required_env", []),
        optional_env=config.get("optional_env", {}),
        transport=config.get("transport", "stdio"),
        default_port=config.get("default_port"),
        capabilities=capabilities,
        tags=config.get("tags", []),
        documentation_url=config.get("documentation_url"),
        repository_url=config.get("repository_url"),
        version=config.get("version"),
        author=config.get("author"),
        license=config.get("license")
    )


def validate_template_config(config: dict) -> list[str]:
    """Validate a template configuration and return any errors."""
    errors = []

    required_fields = ["server_id", "name", "description", "server_type"]
    for field in required_fields:
        if not config.get(field):
            errors.append(f"Missing required field: {field}")

    server_type = config.get("server_type")
    if server_type in ["npx", "uv"] and not config.get("package"):
        errors.append(f"package is required for {server_type} servers")

    if server_type == "docker" and not config.get("command"):
        errors.append("command is required for docker servers")

    transport = config.get("transport", "stdio")
    if transport not in ["stdio", "sse", "http", "websocket"]:
        errors.append("transport must be one of: stdio, sse, http, websocket")

    return errors


def merge_templates(base_template: MCPServerTemplate, override_template: MCPServerTemplate) -> MCPServerTemplate:
    """Merge two templates, with override_template taking precedence."""

    # Merge capabilities
    merged_capabilities = list(base_template.capabilities)
    for override_cap in override_template.capabilities:
        # Replace capability with same name, or add if new
        for i, base_cap in enumerate(merged_capabilities):
            if base_cap.name == override_cap.name:
                merged_capabilities[i] = override_cap
                break
        else:
            merged_capabilities.append(override_cap)

    # Merge environment variables
    merged_env = dict(base_template.optional_env)
    merged_env.update(override_template.optional_env)

    # Merge tags
    merged_tags = list(set(base_template.tags + override_template.tags))

    # Merge args
    merged_args = list(base_template.default_args)
    if override_template.default_args:
        merged_args = override_template.default_args

    # Merge required env
    merged_required_env = list(set(base_template.required_env + override_template.required_env))

    return MCPServerTemplate(
        server_id=override_template.server_id or base_template.server_id,
        name=override_template.name or base_template.name,
        description=override_template.description or base_template.description,
        server_type=override_template.server_type or base_template.server_type,
        package=override_template.package or base_template.package,
        command=override_template.command or base_template.command,
        default_args=merged_args,
        required_env=merged_required_env,
        optional_env=merged_env,
        transport=override_template.transport or base_template.transport,
        default_port=override_template.default_port or base_template.default_port,
        capabilities=merged_capabilities,
        tags=merged_tags,
        documentation_url=override_template.documentation_url or base_template.documentation_url,
        repository_url=override_template.repository_url or base_template.repository_url,
        version=override_template.version or base_template.version,
        author=override_template.author or base_template.author,
        license=override_template.license or base_template.license
    )


def create_custom_template(
    server_id: str,
    name: str,
    description: str,
    server_type: str,
    package: str | None = None,
    command: str | None = None,
    **kwargs
) -> MCPServerTemplate:
    """Create a custom server template with minimal required fields."""

    return MCPServerTemplate(
        server_id=server_id,
        name=name,
        description=description,
        server_type=server_type,
        package=package,
        command=command,
        default_args=kwargs.get("default_args", []),
        required_env=kwargs.get("required_env", []),
        optional_env=kwargs.get("optional_env", {}),
        transport=kwargs.get("transport", "stdio"),
        default_port=kwargs.get("default_port"),
        capabilities=kwargs.get("capabilities", []),
        tags=kwargs.get("tags", []),
        documentation_url=kwargs.get("documentation_url"),
        repository_url=kwargs.get("repository_url"),
        version=kwargs.get("version"),
        author=kwargs.get("author"),
        license=kwargs.get("license")
    )


def get_builtin_templates() -> list[dict]:
    """Get the built-in template configurations."""
    return [
        # These are the raw configurations that will be converted to templates
        # The actual templates are created in builtin_servers.py
        {
            "server_id": "archon-core",
            "name": "Archon Core",
            "description": "Core Archon MCP server with RAG, projects, and knowledge management",
            "server_type": "archon",
            "transport": "sse",
            "default_port": 8051,
            "tags": ["archon", "rag", "knowledge", "projects", "core"],
            "author": "Anthropic",
            "license": "MIT"
        }
    ]


def template_to_dict(template: MCPServerTemplate) -> dict:
    """Convert a template to a dictionary representation."""
    return {
        "server_id": template.server_id,
        "name": template.name,
        "description": template.description,
        "server_type": template.server_type,
        "package": template.package,
        "command": template.command,
        "default_args": template.default_args,
        "required_env": template.required_env,
        "optional_env": template.optional_env,
        "transport": template.transport,
        "default_port": template.default_port,
        "capabilities": [
            {
                "name": cap.name,
                "description": cap.description,
                "category": cap.category,
                "parameters": cap.parameters,
                "examples": cap.examples
            }
            for cap in template.capabilities
        ],
        "tags": template.tags,
        "documentation_url": template.documentation_url,
        "repository_url": template.repository_url,
        "version": template.version,
        "author": template.author,
        "license": template.license
    }
