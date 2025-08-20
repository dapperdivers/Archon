"""
MCP Server Registry Module

Provides server discovery, template management, and capability tracking.

This module handles:
- Built-in server definitions (Archon, Brave Search, GitHub, etc.)
- Server template management and validation
- Capability discovery and categorization
- Server configuration generation

Components:
- server_registry: Main registry class
- templates: Template management utilities
- builtin_servers: Definitions for popular MCP servers
"""

from .models import MCPServerCapability, MCPServerTemplate
from .server_registry import MCPServerRegistry, get_mcp_registry

__all__ = [
    "MCPServerRegistry",
    "MCPServerTemplate",
    "MCPServerCapability",
    "get_mcp_registry"
]
