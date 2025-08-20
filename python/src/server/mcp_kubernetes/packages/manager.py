"""
MCP Package Manager

This module provides package management capabilities for MCP servers,
including NPX, UV, and other package managers. It handles package discovery,
installation verification, and dependency management.
"""

import asyncio
from typing import Any

from ...config.logfire_config import mcp_logger
from .models import PackageInfo, PackageSearchResult
from .npm_client import NPMClient
from .pypi_client import PyPIClient


class MCPPackageManager:
    """Manager for MCP package operations across different package managers."""

    def __init__(self):
        self.npm_client = NPMClient()
        self.pypi_client = PyPIClient()
        self.timeout = 30.0
        self.cache: dict[str, Any] = {}
        self.cache_ttl = 3600  # 1 hour

    async def search_npm_packages(self, query: str, limit: int = 20) -> PackageSearchResult:
        """Search for NPX-compatible MCP packages on NPM."""
        start_time = asyncio.get_event_loop().time()

        try:
            result = await self.npm_client.search_packages(query, limit)
            search_time = (asyncio.get_event_loop().time() - start_time) * 1000

            return PackageSearchResult(
                packages=result,
                total_count=len(result),
                search_time_ms=search_time,
                source="npm"
            )

        except Exception as e:
            mcp_logger.error(f"Error searching NPM packages: {e}")
            return PackageSearchResult(
                packages=[],
                total_count=0,
                search_time_ms=(asyncio.get_event_loop().time() - start_time) * 1000,
                source="npm"
            )

    async def search_pypi_packages(self, query: str, limit: int = 20) -> PackageSearchResult:
        """Search for UV-compatible MCP packages on PyPI."""
        start_time = asyncio.get_event_loop().time()

        try:
            result = await self.pypi_client.search_packages(query, limit)
            search_time = (asyncio.get_event_loop().time() - start_time) * 1000

            return PackageSearchResult(
                packages=result,
                total_count=len(result),
                search_time_ms=search_time,
                source="pypi"
            )

        except Exception as e:
            mcp_logger.error(f"Error searching PyPI packages: {e}")
            return PackageSearchResult(
                packages=[],
                total_count=0,
                search_time_ms=(asyncio.get_event_loop().time() - start_time) * 1000,
                source="pypi"
            )

    async def get_package_info(self, package_name: str, package_manager: str = "npm") -> PackageInfo | None:
        """Get detailed information about a specific package."""
        try:
            if package_manager == "npm":
                return await self.npm_client.get_package_info(package_name)
            elif package_manager == "pypi":
                return await self.pypi_client.get_package_info(package_name)
            else:
                mcp_logger.warning(f"Unsupported package manager: {package_manager}")
                return None

        except Exception as e:
            mcp_logger.error(f"Error getting package info for {package_name}: {e}")
            return None

    async def verify_package_exists(self, package_name: str, package_manager: str = "npm") -> bool:
        """Verify that a package exists in the registry."""
        package_info = await self.get_package_info(package_name, package_manager)
        return package_info is not None

    async def get_package_versions(self, package_name: str, package_manager: str = "npm") -> list[str]:
        """Get available versions for a package."""
        try:
            if package_manager == "npm":
                return await self.npm_client.get_package_versions(package_name)
            elif package_manager == "pypi":
                return await self.pypi_client.get_package_versions(package_name)
            else:
                mcp_logger.warning(f"Unsupported package manager: {package_manager}")
                return []

        except Exception as e:
            mcp_logger.error(f"Error getting versions for {package_name}: {e}")
            return []

    def get_install_command(self, package_name: str, package_manager: str = "npm", version: str = None) -> str:
        """Get the install command for a package."""
        if package_manager == "npm":
            if version:
                return f"npx -y {package_name}@{version}"
            else:
                return f"npx -y {package_name}"
        elif package_manager == "uv":
            if version:
                return f"uv run --with {package_name}=={version}"
            else:
                return f"uv run --with {package_name}"
        elif package_manager == "pip":
            if version:
                return f"pip install {package_name}=={version}"
            else:
                return f"pip install {package_name}"
        else:
            return f"# Unknown package manager: {package_manager}"

    async def search_all_packages(self, query: str, limit: int = 20) -> dict[str, PackageSearchResult]:
        """Search packages across all supported package managers."""
        results = {}

        # Search in parallel
        search_tasks = [
            self.search_npm_packages(query, limit),
            self.search_pypi_packages(query, limit)
        ]

        npm_result, pypi_result = await asyncio.gather(*search_tasks, return_exceptions=True)

        if isinstance(npm_result, PackageSearchResult):
            results["npm"] = npm_result
        else:
            mcp_logger.error(f"NPM search failed: {npm_result}")
            results["npm"] = PackageSearchResult([], 0, 0, "npm")

        if isinstance(pypi_result, PackageSearchResult):
            results["pypi"] = pypi_result
        else:
            mcp_logger.error(f"PyPI search failed: {pypi_result}")
            results["pypi"] = PackageSearchResult([], 0, 0, "pypi")

        return results

    async def get_mcp_packages(self, package_manager: str = "npm", limit: int = 50) -> PackageSearchResult:
        """Get packages specifically tagged as MCP servers."""
        return await self.search_packages("mcp server", package_manager, limit)

    async def search_packages(self, query: str, package_manager: str = "npm", limit: int = 20) -> PackageSearchResult:
        """Search packages in a specific package manager."""
        if package_manager == "npm":
            return await self.search_npm_packages(query, limit)
        elif package_manager == "pypi":
            return await self.search_pypi_packages(query, limit)
        else:
            raise ValueError(f"Unsupported package manager: {package_manager}")

    def get_supported_package_managers(self) -> list[str]:
        """Get list of supported package managers."""
        return ["npm", "pypi", "uv", "pip"]

    async def get_package_dependencies(self, package_name: str, package_manager: str = "npm") -> dict[str, str]:
        """Get dependencies for a package."""
        try:
            if package_manager == "npm":
                return await self.npm_client.get_package_dependencies(package_name)
            elif package_manager == "pypi":
                return await self.pypi_client.get_package_dependencies(package_name)
            else:
                return {}

        except Exception as e:
            mcp_logger.debug(f"Could not get dependencies for {package_name}: {e}")
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
            name.startswith("@modelcontextprotocol/"),
            "server" in name and "mcp" in description,
        ]

        return any(mcp_indicators)

    async def get_package_statistics(self) -> dict[str, Any]:
        """Get statistics about available MCP packages."""
        try:
            # Search for MCP packages across all managers
            results = await self.search_all_packages("mcp", limit=100)

            stats = {
                "total_npm_packages": len(results["npm"].packages),
                "total_pypi_packages": len(results["pypi"].packages),
                "npm_search_time": results["npm"].search_time_ms,
                "pypi_search_time": results["pypi"].search_time_ms,
                "popular_packages": [],
                "categories": {}
            }

            # Get popular packages (first 10 from each)
            popular_npm = results["npm"].packages[:5]
            popular_pypi = results["pypi"].packages[:5]

            stats["popular_packages"] = [
                {"name": p.name, "source": "npm", "description": p.description}
                for p in popular_npm
            ] + [
                {"name": p.name, "source": "pypi", "description": p.description}
                for p in popular_pypi
            ]

            return stats

        except Exception as e:
            mcp_logger.error(f"Error getting package statistics: {e}")
            return {"error": str(e)}


# Global package manager instance
_package_manager: MCPPackageManager | None = None


def get_package_manager() -> MCPPackageManager:
    """Get the global MCP package manager instance."""
    global _package_manager
    if _package_manager is None:
        _package_manager = MCPPackageManager()
    return _package_manager
