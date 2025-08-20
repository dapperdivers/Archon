"""
MCP Kubernetes Module

This module provides comprehensive support for running MCP (Model Context Protocol) servers
in Kubernetes environments. It includes support for:

- Dynamic pod creation and management for external MCP servers
- Multiple communication protocols (stdio, SSE, WebSocket, HTTP)
- Package discovery and management (NPM, PyPI)
- Server registry with built-in templates
- Protocol adapters for different MCP transports

Main Components:
- sidecar: Kubernetes pod management and orchestration
- stdio: STDIO communication bridge via Kubernetes exec API
- protocols: Protocol adapters for different MCP transports
- registry: MCP server discovery and template management
- packages: Package management for NPM and PyPI servers
- client: High-level client interface for sidecar operations

Example Usage:
    from src.server.mcp_kubernetes import MCPKubernetesManager

    manager = MCPKubernetesManager()

    # Start external MCP server
    config = {
        "server_type": "npx",
        "package": "@modelcontextprotocol/server-brave-search",
        "transport": "stdio"
    }
    result = await manager.start_external_server(config)
"""

from .client.sidecar_client import MCPSidecarClient
from .packages.manager import MCPPackageManager, get_package_manager
from .protocols.adapters import ProtocolType, create_adapter
from .registry.server_registry import MCPServerRegistry, get_mcp_registry
from .sidecar.manager import MCPSidecarManager
from .stdio.bridge import MCPStdioBridge


# Main manager class for easy access
class MCPKubernetesManager:
    """
    High-level manager for MCP Kubernetes operations.

    Provides a unified interface for managing MCP servers in Kubernetes.
    """

    def __init__(self, namespace: str = "archon"):
        self.sidecar = MCPSidecarManager(namespace=namespace)
        self.client = MCPSidecarClient()
        self.registry = get_mcp_registry()
        self.package_manager = get_package_manager()

    async def start_external_server(self, config: dict):
        """Start an external MCP server."""
        return await self.sidecar.start_external_server(config)

    async def stop_external_server(self, server_id: str):
        """Stop an external MCP server."""
        return await self.sidecar.stop_external_server(server_id)

    async def list_external_servers(self):
        """List running external MCP servers."""
        return await self.sidecar.list_external_servers()

    def get_server_templates(self, category: str = None):
        """Get available MCP server templates."""
        return self.registry.list_templates(category=category)

    async def search_packages(self, query: str, limit: int = 20):
        """Search for MCP packages across NPM and PyPI."""
        return await self.package_manager.search_all_packages(query, limit)

# Export main components
__all__ = [
    "MCPKubernetesManager",
    "MCPSidecarManager",
    "MCPSidecarClient",
    "MCPServerRegistry",
    "MCPPackageManager",
    "MCPStdioBridge",
    "get_mcp_registry",
    "get_package_manager",
    "create_adapter",
    "ProtocolType"
]
