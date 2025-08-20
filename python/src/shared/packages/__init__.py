"""
MCP Package Management Module

Provides package discovery and management for MCP servers across different package managers.

This module supports:
- NPM package discovery and information
- PyPI package discovery and information
- Package verification and validation
- Version management
- Dependency resolution

Components:
- manager: Main package management class
- npm_client: NPM registry client
- pypi_client: PyPI registry client
"""

from .manager import MCPPackageManager, get_package_manager
from .models import PackageInfo, PackageSearchResult

__all__ = [
    "MCPPackageManager",
    "PackageInfo",
    "PackageSearchResult",
    "get_package_manager"
]
