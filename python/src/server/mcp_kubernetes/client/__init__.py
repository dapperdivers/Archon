"""
MCP Sidecar Client Module

Provides high-level client interface for interacting with the MCP sidecar.

This module handles:
- HTTP client for sidecar communication
- Request/response handling
- Error handling and retries
- Session management

Components:
- sidecar_client: Main client class for sidecar operations
"""

from .sidecar_client import MCPSidecarClient

__all__ = [
    "MCPSidecarClient"
]
