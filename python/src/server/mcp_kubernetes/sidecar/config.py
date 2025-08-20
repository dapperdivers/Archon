"""
MCP Sidecar Configuration

This module handles configuration models and validation for the MCP sidecar.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, validator


class ServerConfig(BaseModel):
    """Configuration for an MCP server."""

    server_type: str = Field(default="archon", description="Type of server: archon, npx, uv, python, docker")
    name: str | None = Field(default=None, description="Human-readable name for the server")
    package: str | None = Field(default=None, description="Package name for npx/uv servers")
    command: str | None = Field(default=None, description="Custom command to run")
    args: list[str] = Field(default_factory=list, description="Command arguments")
    env: dict[str, str] = Field(default_factory=dict, description="Environment variables")
    transport: str = Field(default="sse", description="Communication transport: stdio, sse, http")
    image: str | None = Field(default=None, description="Custom Docker image")
    port: int | None = Field(default=None, description="Port for HTTP/SSE servers")
    timeout: int = Field(default=300, description="Pod startup timeout in seconds")

    @validator('server_type')
    def validate_server_type(cls, v):
        valid_types = {"archon", "npx", "uv", "python", "docker"}
        if v not in valid_types:
            raise ValueError(f"server_type must be one of: {valid_types}")
        return v

    @validator('transport')
    def validate_transport(cls, v):
        valid_transports = {"stdio", "sse", "http", "websocket"}
        if v not in valid_transports:
            raise ValueError(f"transport must be one of: {valid_transports}")
        return v

    @validator('package')
    def validate_package_required(cls, v, values):
        server_type = values.get('server_type')
        if server_type in {'npx', 'uv'} and not v:
            raise ValueError(f"package is required for {server_type} servers")
        return v

    @validator('command')
    def validate_command_required(cls, v, values):
        server_type = values.get('server_type')
        if server_type == 'docker' and not v:
            raise ValueError("command is required for docker servers")
        return v

    @validator('port')
    def validate_port_for_transport(cls, v, values):
        transport = values.get('transport')
        if transport in {'sse', 'http'} and not v:
            # Set default ports based on server type
            server_type = values.get('server_type', 'archon')
            if server_type == 'archon':
                return 8051
            else:
                return 8080
        return v


class MCPRequest(BaseModel):
    """Basic MCP sidecar request."""

    action: str = Field(description="Action to perform: start, stop, status")

    @validator('action')
    def validate_action(cls, v):
        valid_actions = {"start", "stop", "status", "health"}
        if v not in valid_actions:
            raise ValueError(f"action must be one of: {valid_actions}")
        return v


class ExternalMCPRequest(BaseModel):
    """Request for external MCP server operations."""

    action: str = Field(description="Action to perform: start, stop, status, list")
    server_config: dict[str, Any] | None = Field(default=None, description="Server configuration")
    server_id: str | None = Field(default=None, description="Server ID for stop/status actions")

    @validator('action')
    def validate_action(cls, v):
        valid_actions = {"start", "stop", "status", "list"}
        if v not in valid_actions:
            raise ValueError(f"action must be one of: {valid_actions}")
        return v

    @validator('server_config')
    def validate_server_config_for_start(cls, v, values):
        action = values.get('action')
        if action == 'start' and not v:
            raise ValueError("server_config is required for start action")
        return v

    @validator('server_id')
    def validate_server_id_for_actions(cls, v, values):
        action = values.get('action')
        if action in {'stop', 'status'} and not v:
            raise ValueError(f"server_id is required for {action} action")
        return v


class MCPResponse(BaseModel):
    """Response from MCP sidecar operations."""

    success: bool = Field(description="Whether the operation succeeded")
    message: str = Field(description="Human-readable message")
    status: str | None = Field(default=None, description="Current status")
    data: dict[str, Any] | None = Field(default=None, description="Additional response data")
    server_id: str | None = Field(default=None, description="Server ID for tracking")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat(), description="Response timestamp")


class PodResourceConfig(BaseModel):
    """Resource configuration for MCP pods."""

    cpu_request: str = Field(default="250m", description="CPU request")
    cpu_limit: str = Field(default="500m", description="CPU limit")
    memory_request: str = Field(default="256Mi", description="Memory request")
    memory_limit: str = Field(default="512Mi", description="Memory limit")


class SecurityConfig(BaseModel):
    """Security configuration for MCP pods."""

    run_as_non_root: bool = Field(default=True, description="Run containers as non-root")
    run_as_user: int = Field(default=1001, description="User ID to run as")
    run_as_group: int = Field(default=1001, description="Group ID to run as")
    read_only_root_filesystem: bool = Field(default=False, description="Use read-only root filesystem")
    allow_privilege_escalation: bool = Field(default=False, description="Allow privilege escalation")
    capabilities_drop: list[str] = Field(default_factory=lambda: ["ALL"], description="Capabilities to drop")


class SidecarConfig(BaseModel):
    """Configuration for the MCP sidecar."""

    namespace: str = Field(default="archon", description="Kubernetes namespace")
    pod_name_prefix: str = Field(default="mcp", description="Prefix for pod names")
    max_concurrent_servers: int = Field(default=10, description="Maximum concurrent external servers")
    resources: PodResourceConfig = Field(default_factory=PodResourceConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    cleanup_timeout: int = Field(default=30, description="Pod cleanup timeout in seconds")
    health_check_interval: int = Field(default=30, description="Health check interval in seconds")
