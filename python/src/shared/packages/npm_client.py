"""
NPM Client for MCP Package Discovery

This module provides NPM registry client functionality for discovering MCP packages.
"""

import re
from typing import Any

import httpx

import logging
mcp_logger = logging.getLogger(__name__)
from .models import PackageInfo


class NPMClient:
    """Client for NPM registry operations."""

    def __init__(self):
        self.registry_url = "https://registry.npmjs.org"
        self.search_url = "https://registry.npmjs.org/-/v1/search"
        self.timeout = 30.0

    async def search_packages(self, query: str, limit: int = 20) -> list[PackageInfo]:
        """Search for MCP packages on NPM."""
        try:
            params = {
                "text": f"{query} mcp server",
                "size": limit,
                "quality": 0.65,
                "popularity": 0.98,
                "maintenance": 0.5
            }

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.search_url, params=params)
                response.raise_for_status()
                data = response.json()

            packages = []
            for item in data.get("objects", []):
                package_data = item.get("package", {})

                # Filter for MCP-related packages
                if self._is_mcp_package(package_data):
                    package_info = PackageInfo(
                        name=package_data.get("name", ""),
                        version=package_data.get("version", ""),
                        description=package_data.get("description", ""),
                        author=self._extract_author(package_data.get("author")),
                        repository=self._extract_repository(package_data.get("links", {})),
                        homepage=package_data.get("links", {}).get("homepage"),
                        license=package_data.get("license"),
                        keywords=package_data.get("keywords", []),
                        dependencies=await self._get_npm_dependencies(package_data.get("name", ""))
                    )
                    packages.append(package_info)

            return packages

        except Exception as e:
            mcp_logger.error(f"Error searching NPM packages: {e}")
            return []

    async def get_package_info(self, package_name: str) -> PackageInfo | None:
        """Get NPM package information."""
        try:
            url = f"{self.registry_url}/{package_name}"

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()

            latest_version = data.get("dist-tags", {}).get("latest", "")
            version_data = data.get("versions", {}).get(latest_version, {})

            return PackageInfo(
                name=data.get("name", ""),
                version=latest_version,
                description=data.get("description", ""),
                author=self._extract_author(data.get("author")),
                repository=self._extract_repository(data.get("repository")),
                homepage=data.get("homepage"),
                license=data.get("license"),
                keywords=data.get("keywords", []),
                dependencies=version_data.get("dependencies", {}),
                mcp_version=self._extract_mcp_version(version_data)
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def get_package_versions(self, package_name: str) -> list[str]:
        """Get available versions for an NPM package."""
        try:
            url = f"{self.registry_url}/{package_name}"
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()

            versions = list(data.get("versions", {}).keys())
            # Sort versions in descending order (newest first)
            versions.sort(reverse=True, key=lambda v: [int(x) for x in v.split(".") if x.isdigit()])
            return versions

        except Exception as e:
            mcp_logger.error(f"Error getting versions for {package_name}: {e}")
            return []

    async def get_package_dependencies(self, package_name: str) -> dict[str, str]:
        """Get NPM package dependencies."""
        try:
            package_info = await self.get_package_info(package_name)
            return package_info.dependencies if package_info else {}

        except Exception as e:
            mcp_logger.debug(f"Could not get dependencies for {package_name}: {e}")
            return {}

    async def _get_npm_dependencies(self, package_name: str) -> dict[str, str]:
        """Get NPM package dependencies (internal method)."""
        try:
            package_info = await self.get_package_info(package_name)
            return package_info.dependencies if package_info else {}

        except Exception as e:
            mcp_logger.debug(f"Could not get dependencies for {package_name}: {e}")
            return {}

    def _is_mcp_package(self, package_data: dict[str, Any]) -> bool:
        """Check if a package is an MCP server package."""
        name = package_data.get("name", "").lower()
        description = package_data.get("description", "").lower()
        keywords = package_data.get("keywords", [])

        # Check for MCP indicators
        mcp_indicators = [
            "mcp" in name,
            "model-context-protocol" in name,
            "mcp" in description,
            "model context protocol" in description,
            any("mcp" in str(keyword).lower() for keyword in keywords),
            name.startswith("@modelcontextprotocol/"),
        ]

        return any(mcp_indicators)

    def _extract_author(self, author_data: Any) -> str | None:
        """Extract author name from various author data formats."""
        if isinstance(author_data, str):
            return author_data
        elif isinstance(author_data, dict):
            return author_data.get("name")
        return None

    def _extract_repository(self, repo_data: Any) -> str | None:
        """Extract repository URL from various repository data formats."""
        if isinstance(repo_data, str):
            return repo_data
        elif isinstance(repo_data, dict):
            url = repo_data.get("url", repo_data.get("repository"))
            if url and isinstance(url, str):
                # Clean up git+https URLs
                return re.sub(r"^git\\+", "", url)
        return None

    def _extract_mcp_version(self, version_data: dict[str, Any]) -> str | None:
        """Extract MCP version from package metadata."""
        # Look for MCP-related dependencies or metadata
        dependencies = version_data.get("dependencies", {})

        # Check for MCP SDK dependencies
        for dep_name in dependencies:
            if "mcp" in dep_name.lower() or "model-context-protocol" in dep_name.lower():
                return dependencies[dep_name]

        # Check package description or keywords for version info
        description = version_data.get("description", "")
        mcp_version_match = re.search(r"mcp[:\\s]+v?(\\d+\\.\\d+)", description, re.IGNORECASE)
        if mcp_version_match:
            return mcp_version_match.group(1)

        return None

    async def get_package_download_stats(self, package_name: str) -> dict[str, Any]:
        """Get download statistics for a package."""
        try:
            # NPM provides download statistics via their API
            stats_url = f"https://api.npmjs.org/downloads/range/last-month/{package_name}"

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(stats_url)
                response.raise_for_status()
                data = response.json()

            return {
                "package": data.get("package"),
                "downloads": data.get("downloads", []),
                "total_downloads": sum(day.get("downloads", 0) for day in data.get("downloads", []))
            }

        except Exception as e:
            mcp_logger.debug(f"Could not get download stats for {package_name}: {e}")
            return {}

    async def search_by_maintainer(self, maintainer: str, limit: int = 20) -> list[PackageInfo]:
        """Search for packages by maintainer."""
        try:
            params = {
                "text": f"maintainer:{maintainer}",
                "size": limit
            }

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.search_url, params=params)
                response.raise_for_status()
                data = response.json()

            packages = []
            for item in data.get("objects", []):
                package_data = item.get("package", {})

                package_info = PackageInfo(
                    name=package_data.get("name", ""),
                    version=package_data.get("version", ""),
                    description=package_data.get("description", ""),
                    author=self._extract_author(package_data.get("author")),
                    repository=self._extract_repository(package_data.get("links", {})),
                    homepage=package_data.get("links", {}).get("homepage"),
                    license=package_data.get("license"),
                    keywords=package_data.get("keywords", [])
                )
                packages.append(package_info)

            return packages

        except Exception as e:
            mcp_logger.error(f"Error searching packages by maintainer {maintainer}: {e}")
            return []
