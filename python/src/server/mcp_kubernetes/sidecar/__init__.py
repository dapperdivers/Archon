"""
MCP Sidecar Module

Handles Kubernetes pod management and orchestration for MCP servers.

This module provides:
- MCPSidecarManager: Main orchestration class
- Pod lifecycle management
- Configuration handling for different server types
- Kubernetes API integration

Components:
- manager: Main sidecar manager class
- pod_manager: Pod creation and lifecycle management
- config: Configuration handling and validation
"""

from .config import ExternalMCPRequest, ServerConfig
from .manager import MCPSidecarManager

__all__ = [
    "MCPSidecarManager",
    "ServerConfig",
    "ExternalMCPRequest"
]
