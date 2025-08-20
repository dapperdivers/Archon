"""
PyPI Client for MCP Package Discovery

This module provides PyPI client functionality for discovering MCP packages.
"""

import re
from typing import Any

import httpx

import logging
mcp_logger = logging.getLogger(__name__)
from .models import PackageInfo


class PyPIClient:
    """Client for PyPI operations."""

    def __init__(self):
        self.api_url = "https://pypi.org/pypi"
        self.search_url = "https://pypi.org/search/"
        self.timeout = 30.0

    async def search_packages(self, query: str, limit: int = 20) -> list[PackageInfo]:
        """Search for UV-compatible MCP packages on PyPI."""
        # PyPI doesn't have a direct search API like NPM, so we'll use known MCP packages
        # In a real implementation, you might scrape the search results or use an API

        known_mcp_packages = [
            PackageInfo(
                name="mcp-server-fetch",
                version="1.0.0",
                description="MCP server for fetching web content",
                author="MCP Community",
                keywords=["mcp", "fetch", "web", "http"],
                mcp_version="1.0"
            ),
            PackageInfo(
                name="mcp-server-git",
                version="0.2.0",
                description="MCP server for Git operations",
                author="MCP Community",
                keywords=["mcp", "git", "version-control"],
                mcp_version="1.0"
            ),
            PackageInfo(
                name="mcp-server-database",
                version="0.1.5",
                description="MCP server for database operations",
                author="MCP Community",
                keywords=["mcp", "database", "sql"],
                mcp_version="1.0"
            ),
            PackageInfo(
                name="mcp-server-files",
                version="1.1.0",
                description="MCP server for file system operations",
                author="MCP Community",
                keywords=["mcp", "files", "filesystem"],
                mcp_version="1.0"
            )
        ]

        # Filter packages based on query
        filtered_packages = [
            pkg for pkg in known_mcp_packages
            if query.lower() in pkg.name.lower() or
               query.lower() in pkg.description.lower() or
               any(query.lower() in keyword.lower() for keyword in pkg.keywords)
        ]

        return filtered_packages[:limit]

    async def get_package_info(self, package_name: str) -> PackageInfo | None:
        """Get PyPI package information."""
        try:
            url = f"{self.api_url}/{package_name}/json"

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()

            info = data.get("info", {})

            return PackageInfo(
                name=info.get("name", ""),
                version=info.get("version", ""),
                description=info.get("summary", ""),
                author=info.get("author"),
                repository=info.get("home_page"),
                homepage=info.get("home_page"),
                license=info.get("license"),
                keywords=info.get("keywords", "").split(",") if info.get("keywords") else [],
                dependencies=self._extract_pypi_dependencies(data),
                mcp_version=self._extract_mcp_version_pypi(info)
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def get_package_versions(self, package_name: str) -> list[str]:
        """Get available versions for a PyPI package."""
        try:
            url = f"{self.api_url}/{package_name}/json"
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()

            releases = data.get("releases", {})
            versions = [v for v in releases.keys() if releases[v]]  # Only versions with files
            versions.sort(reverse=True, key=lambda v: [int(x) for x in v.split(".") if x.isdigit()])
            return versions

        except Exception as e:
            mcp_logger.error(f"Error getting versions for {package_name}: {e}")
            return []

    async def get_package_dependencies(self, package_name: str) -> dict[str, str]:
        """Get PyPI package dependencies."""
        try:
            package_info = await self.get_package_info(package_name)
            return package_info.dependencies if package_info else {}

        except Exception as e:
            mcp_logger.debug(f"Could not get dependencies for {package_name}: {e}")
            return {}

    def _extract_mcp_version_pypi(self, info: dict[str, Any]) -> str | None:
        """Extract MCP version from PyPI package metadata."""
        # Check classifier information
        classifiers = info.get("classifiers", [])
        for classifier in classifiers:
            if "mcp" in classifier.lower():
                version_match = re.search(r"(\\d+\\.\\d+)", classifier)
                if version_match:
                    return version_match.group(1)

        return None

    def _extract_pypi_dependencies(self, data: dict[str, Any]) -> dict[str, str]:
        """Extract dependencies from PyPI package data."""
        info = data.get("info", {})
        requires_dist = info.get("requires_dist", [])

        dependencies = {}
        if requires_dist:
            for req in requires_dist:
                # Parse requirement string like "requests>=2.25.1"
                match = re.match(r"([a-zA-Z0-9_-]+)\\s*([><=!]+.*)?", req)
                if match:
                    dep_name = match.group(1)
                    version_spec = match.group(2) or "*"
                    dependencies[dep_name] = version_spec

        return dependencies

    async def search_by_classifier(self, classifier: str, limit: int = 20) -> list[PackageInfo]:
        """Search packages by classifier (e.g., 'Development Status :: 4 - Beta')."""
        # This would require scraping PyPI search results or using a third-party service
        # For now, return empty list
        return []

    async def get_package_stats(self, package_name: str) -> dict[str, Any]:
        """Get package statistics."""
        try:
            # PyPI doesn't provide download stats in the main API
            # Would need to use pypistats or similar service
            return {"package": package_name, "stats_available": False}

        except Exception as e:
            mcp_logger.debug(f"Could not get stats for {package_name}: {e}")
            return {}

    def is_mcp_package(self, package_info: PackageInfo) -> bool:
        """Check if a package appears to be an MCP server."""
        name = package_info.name.lower()
        description = package_info.description.lower()
        keywords = [str(k).lower() for k in package_info.keywords]

        # Check for MCP indicators
        mcp_indicators = [
            "mcp" in name,
            "model-context-protocol" in name,
            "mcp" in description,
            "model context protocol" in description,
            any("mcp" in keyword for keyword in keywords),
            "server" in name and ("mcp" in description or any("mcp" in k for k in keywords)),
        ]

        return any(mcp_indicators)

    async def get_latest_mcp_packages(self, limit: int = 10) -> list[PackageInfo]:
        """Get the latest MCP packages from PyPI."""
        # This would require real-time PyPI data
        # For now, return the known packages
        return await self.search_packages("mcp", limit)

    async def verify_package_exists(self, package_name: str) -> bool:
        """Verify that a package exists on PyPI."""
        try:
            package_info = await self.get_package_info(package_name)
            return package_info is not None
        except Exception:
            return False

    async def get_package_metadata(self, package_name: str) -> dict[str, Any]:
        """Get complete package metadata."""
        try:
            url = f"{self.api_url}/{package_name}/json"

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.json()

        except Exception as e:
            mcp_logger.error(f"Error getting metadata for {package_name}: {e}")
            return {}
