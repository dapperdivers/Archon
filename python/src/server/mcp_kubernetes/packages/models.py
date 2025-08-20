"""
MCP Package Models

This module defines the data models used by the package management system.
"""

from dataclasses import dataclass


@dataclass
class PackageInfo:
    """Information about an MCP package."""
    name: str
    version: str
    description: str
    author: str | None = None
    repository: str | None = None
    homepage: str | None = None
    license: str | None = None
    keywords: list[str] = None
    dependencies: dict[str, str] = None
    mcp_version: str | None = None

    def __post_init__(self):
        if self.keywords is None:
            self.keywords = []
        if self.dependencies is None:
            self.dependencies = {}


@dataclass
class PackageSearchResult:
    """Result from package search operation."""
    packages: list[PackageInfo]
    total_count: int
    search_time_ms: float
    source: str  # "npm", "pypi", "cache"
