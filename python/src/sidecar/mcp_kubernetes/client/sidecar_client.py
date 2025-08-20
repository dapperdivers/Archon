"""
MCP Sidecar Client

This module provides a high-level client for communicating with the MCP sidecar service.
"""

import os
from typing import Any

import httpx

from ...config import mcp_logger


class MCPSidecarClient:
    """Client for communicating with the MCP sidecar service."""

    def __init__(self, sidecar_url: str = None, timeout: float = 30.0):
        """
        Initialize the sidecar client.

        Args:
            sidecar_url: URL of the sidecar service (auto-detected if not provided)
            timeout: Request timeout in seconds
        """
        self.timeout = timeout

        if sidecar_url:
            self.sidecar_url = sidecar_url.rstrip('/')
        else:
            self.sidecar_url = self._detect_sidecar_url()

        self.session: httpx.AsyncClient | None = None

    def _detect_sidecar_url(self) -> str:
        """Auto-detect the sidecar URL based on environment."""
        # Check for explicit environment variable
        sidecar_url = os.getenv("MCP_SIDECAR_URL")
        if sidecar_url:
            return sidecar_url.rstrip('/')

        # Check deployment mode
        deployment_mode = os.getenv("DEPLOYMENT_MODE", "").lower()
        service_discovery_mode = os.getenv("SERVICE_DISCOVERY_MODE", "").lower()

        if deployment_mode == "kubernetes" or service_discovery_mode == "kubernetes":
            # Kubernetes mode - look for sidecar on localhost
            return "http://localhost:8053"
        elif deployment_mode == "docker" or service_discovery_mode == "docker_compose":
            # Docker Compose mode - sidecar not typically used
            return "http://archon-sidecar:8053"
        else:
            # Local development - assume localhost
            return "http://localhost:8053"

    async def _get_session(self) -> httpx.AsyncClient:
        """Get or create HTTP session."""
        if self.session is None:
            self.session = httpx.AsyncClient(timeout=self.timeout)
        return self.session

    async def close(self):
        """Close the HTTP session."""
        if self.session:
            await self.session.aclose()
            self.session = None

    async def health_check(self) -> dict[str, Any]:
        """Check if the sidecar is healthy."""
        try:
            session = await self._get_session()
            response = await session.get(f"{self.sidecar_url}/health")
            response.raise_for_status()
            return response.json()

        except httpx.ConnectError:
            return {
                "success": False,
                "status": "unreachable",
                "message": f"Cannot connect to sidecar at {self.sidecar_url}"
            }
        except Exception as e:
            mcp_logger.error(f"Error checking sidecar health: {e}")
            return {
                "success": False,
                "status": "error",
                "message": str(e)
            }

    async def start_server(self, server_config: dict[str, Any] = None) -> dict[str, Any]:
        """Start the main MCP server."""
        try:
            session = await self._get_session()
            payload = {"action": "start"}

            response = await session.post(f"{self.sidecar_url}/mcp", json=payload)
            response.raise_for_status()
            return response.json()

        except Exception as e:
            mcp_logger.error(f"Error starting MCP server: {e}")
            return {
                "success": False,
                "status": "error",
                "message": str(e)
            }

    async def stop_server(self) -> dict[str, Any]:
        """Stop the main MCP server."""
        try:
            session = await self._get_session()
            payload = {"action": "stop"}

            response = await session.post(f"{self.sidecar_url}/mcp", json=payload)
            response.raise_for_status()
            return response.json()

        except Exception as e:
            mcp_logger.error(f"Error stopping MCP server: {e}")
            return {
                "success": False,
                "status": "error",
                "message": str(e)
            }

    async def get_server_status(self) -> dict[str, Any]:
        """Get the status of the main MCP server."""
        try:
            session = await self._get_session()
            payload = {"action": "status"}

            response = await session.post(f"{self.sidecar_url}/mcp", json=payload)
            response.raise_for_status()
            return response.json()

        except Exception as e:
            mcp_logger.error(f"Error getting MCP server status: {e}")
            return {
                "success": False,
                "status": "error",
                "message": str(e)
            }

    async def start_external_server(self, server_config: dict[str, Any]) -> dict[str, Any]:
        """Start an external MCP server."""
        try:
            session = await self._get_session()
            payload = {
                "action": "start",
                "server_config": server_config
            }

            response = await session.post(f"{self.sidecar_url}/external", json=payload)
            response.raise_for_status()
            return response.json()

        except Exception as e:
            mcp_logger.error(f"Error starting external MCP server: {e}")
            return {
                "success": False,
                "status": "error",
                "message": str(e)
            }

    async def stop_external_server(self, server_id: str) -> dict[str, Any]:
        """Stop an external MCP server."""
        try:
            session = await self._get_session()
            payload = {
                "action": "stop",
                "server_id": server_id
            }

            response = await session.post(f"{self.sidecar_url}/external", json=payload)
            response.raise_for_status()
            return response.json()

        except Exception as e:
            mcp_logger.error(f"Error stopping external MCP server {server_id}: {e}")
            return {
                "success": False,
                "status": "error",
                "message": str(e)
            }

    async def list_external_servers(self) -> dict[str, Any]:
        """List all external MCP servers."""
        try:
            session = await self._get_session()
            payload = {"action": "list"}

            response = await session.post(f"{self.sidecar_url}/external", json=payload)
            response.raise_for_status()
            return response.json()

        except Exception as e:
            mcp_logger.error(f"Error listing external MCP servers: {e}")
            return {
                "success": False,
                "status": "error",
                "message": str(e)
            }

    async def get_external_server_status(self, server_id: str) -> dict[str, Any]:
        """Get the status of a specific external MCP server."""
        try:
            session = await self._get_session()
            payload = {
                "action": "status",
                "server_id": server_id
            }

            response = await session.post(f"{self.sidecar_url}/external", json=payload)
            response.raise_for_status()
            return response.json()

        except Exception as e:
            mcp_logger.error(f"Error getting external server status for {server_id}: {e}")
            return {
                "success": False,
                "status": "error",
                "message": str(e)
            }

    async def get_sidecar_logs(self, limit: int = 100) -> dict[str, Any]:
        """Get recent sidecar logs."""
        try:
            session = await self._get_session()
            params = {"limit": limit}

            response = await session.get(f"{self.sidecar_url}/logs", params=params)
            response.raise_for_status()
            return response.json()

        except Exception as e:
            mcp_logger.error(f"Error getting sidecar logs: {e}")
            return {
                "success": False,
                "status": "error",
                "message": str(e)
            }

    async def is_available(self) -> bool:
        """Check if the sidecar is available."""
        try:
            health = await self.health_check()
            return health.get("success", False)
        except Exception:
            return False

    async def wait_for_availability(self, max_attempts: int = 30, delay: float = 1.0) -> bool:
        """Wait for the sidecar to become available."""
        import asyncio

        for attempt in range(max_attempts):
            if await self.is_available():
                return True

            if attempt < max_attempts - 1:
                await asyncio.sleep(delay)

        return False

    def get_sidecar_url(self) -> str:
        """Get the configured sidecar URL."""
        return self.sidecar_url

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


# Global client instance
_sidecar_client: MCPSidecarClient | None = None


def get_sidecar_client() -> MCPSidecarClient:
    """Get the global sidecar client instance."""
    global _sidecar_client
    if _sidecar_client is None:
        _sidecar_client = MCPSidecarClient()
    return _sidecar_client


async def close_sidecar_client():
    """Close the global sidecar client."""
    global _sidecar_client
    if _sidecar_client:
        await _sidecar_client.close()
        _sidecar_client = None
