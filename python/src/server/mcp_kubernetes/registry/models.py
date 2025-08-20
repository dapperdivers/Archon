"""
MCP Registry Models

This module defines the data models used by the MCP server registry.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MCPServerCapability:
    """Represents a capability provided by an MCP server."""
    name: str
    description: str
    parameters: list[dict[str, Any]] = field(default_factory=list)
    category: str = "general"
    examples: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class MCPServerTemplate:
    """Template for configuring an MCP server."""
    server_id: str
    name: str
    description: str
    server_type: str  # "archon", "npx", "uv", "python", "docker"
    package: str | None = None
    command: str | None = None
    default_args: list[str] = field(default_factory=list)
    required_env: list[str] = field(default_factory=list)
    optional_env: dict[str, str] = field(default_factory=dict)
    transport: str = "stdio"
    default_port: int | None = None
    capabilities: list[MCPServerCapability] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    documentation_url: str | None = None
    repository_url: str | None = None
    version: str | None = None
    author: str | None = None
    license: str | None = None

    def to_config(self, env_overrides: dict[str, str] = None) -> dict[str, Any]:
        """Convert template to server configuration."""
        config = {
            "name": self.name,
            "server_type": self.server_type,
            "package": self.package,
            "command": self.command,
            "args": self.default_args.copy(),
            "transport": self.transport,
            "port": self.default_port,
            "env": self.optional_env.copy()
        }

        # Add environment overrides
        if env_overrides:
            config["env"].update(env_overrides)

        # Remove None values
        return {k: v for k, v in config.items() if v is not None}

    def get_install_command(self) -> str | None:
        """Get the installation command for this server."""
        if self.server_type == "npx" and self.package:
            return f"npx -y {self.package}"
        elif self.server_type == "uv" and self.package:
            return f"uv run --with {self.package}"
        elif self.server_type == "python" and self.package:
            return f"pip install {self.package}"
        elif self.server_type == "docker" and self.command:
            return f"docker run {self.command}"
        return None

    def validate(self) -> list[str]:
        """Validate the template and return any errors."""
        errors = []

        if not self.server_id:
            errors.append("server_id is required")
        if not self.name:
            errors.append("name is required")
        if not self.description:
            errors.append("description is required")
        if not self.server_type:
            errors.append("server_type is required")

        if self.server_type in ["npx", "uv", "python"] and not self.package:
            errors.append(f"package is required for {self.server_type} servers")

        if self.server_type == "docker" and not self.command:
            errors.append("command is required for docker servers")

        if self.transport not in ["stdio", "sse", "http", "websocket"]:
            errors.append("transport must be one of: stdio, sse, http, websocket")

        return errors

    def is_valid(self) -> bool:
        """Check if the template is valid."""
        return len(self.validate()) == 0
