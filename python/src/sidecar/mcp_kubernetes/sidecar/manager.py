"""
MCP Sidecar Manager

This module provides the main sidecar manager class for orchestrating MCP servers in Kubernetes.
"""

import os
import time
from collections import deque
from datetime import datetime
from typing import Any

import httpx

from ...config import mcp_logger
from .config import MCPResponse, ServerConfig, SidecarConfig
from .pod_manager import PodManager


class MCPSidecarManager:
    """Enhanced Kubernetes pod manager supporting multiple MCP server types."""

    def __init__(self, namespace: str = None, config: SidecarConfig = None):
        # Use provided config or create default
        if config is None:
            config = SidecarConfig()
        if namespace:
            config.namespace = namespace

        self.config = config
        self.namespace = config.namespace
        self.pod_name_prefix = config.pod_name_prefix
        self.status: str = "stopped"
        self.start_time: float | None = None
        self.logs: deque = deque(maxlen=1000)
        self.running_servers: dict[str, dict] = {}  # Track multiple servers

        # Initialize pod manager
        self.pod_manager = PodManager(self.namespace, self.pod_name_prefix)

        # Kubernetes API configuration
        self.k8s_host = os.getenv("KUBERNETES_SERVICE_HOST", "kubernetes.default.svc")
        self.k8s_port = os.getenv("KUBERNETES_SERVICE_PORT", "443")
        self.api_base = f"https://{self.k8s_host}:{self.k8s_port}"

        # Service account token
        token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
        if os.path.exists(token_path):
            with open(token_path) as f:
                self.token = f.read().strip()
        else:
            self.token = None
            mcp_logger.warning("Kubernetes service account token not found")

        # CA certificate for TLS verification
        ca_cert_path = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
        self.ca_cert = ca_cert_path if os.path.exists(ca_cert_path) else None

    @property
    def headers(self) -> dict[str, str]:
        """Get headers for Kubernetes API requests."""
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _add_log(self, level: str, message: str):
        """Add a log entry."""
        timestamp = datetime.utcnow().isoformat()
        log_entry = {"timestamp": timestamp, "level": level, "message": message}
        self.logs.append(log_entry)

        # Also log to standard logger
        if level == "ERROR":
            mcp_logger.error(message)
        elif level == "WARNING":
            mcp_logger.warning(message)
        else:
            mcp_logger.info(message)

    async def _api_request(self, method: str, path: str, json_data: dict | None = None) -> dict[str, Any]:
        """Make authenticated request to Kubernetes API."""
        url = f"{self.api_base}{path}"

        async with httpx.AsyncClient(verify=self.ca_cert, timeout=30.0) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=self.headers,
                json=json_data
            )
            response.raise_for_status()
            return response.json()

    async def _get_pods(self) -> list[dict[str, Any]]:
        """Get all MCP pods in the namespace."""
        try:
            selector_labels = self.pod_manager.get_pod_selector_labels()
            label_selector = ",".join([f"{k}={v}" for k, v in selector_labels.items()])

            path = f"/api/v1/namespaces/{self.namespace}/pods"
            params = f"?labelSelector={label_selector}"
            result = await self._api_request("GET", path + params)
            return result.get("items", [])
        except Exception as e:
            mcp_logger.error(f"Error getting pods: {e}")
            return []

    async def start_server(self, server_config: ServerConfig | None = None) -> MCPResponse:
        """Start a new MCP pod with optional external server configuration."""
        try:
            # Use default Archon config if none provided
            if server_config is None:
                server_config = ServerConfig()

            # Validate configuration
            try:
                server_config = ServerConfig(**server_config.model_dump())
            except Exception as e:
                return MCPResponse(
                    success=False,
                    status="error",
                    message=f"Invalid server configuration: {e}"
                )

            # Generate unique server ID
            server_id = f"{server_config.server_type}-{server_config.name or 'default'}-{int(time.time())}"

            # Check if we're at the concurrent server limit
            if len(self.running_servers) >= self.config.max_concurrent_servers:
                return MCPResponse(
                    success=False,
                    status="error",
                    message=f"Maximum concurrent servers ({self.config.max_concurrent_servers}) reached"
                )

            # Check if server with same type and name is already running
            if server_config.name:
                existing_servers = [
                    s for s in self.running_servers.values()
                    if s.get("server_type") == server_config.server_type and s.get("name") == server_config.name
                ]
                if existing_servers:
                    return MCPResponse(
                        success=False,
                        status="running",
                        message=f"Server {server_config.server_type}:{server_config.name} is already running",
                        server_id=existing_servers[0]["server_id"]
                    )

            # Generate pod name
            timestamp = int(time.time())
            server_name = server_config.name or server_config.server_type
            pod_name = f"{self.pod_name_prefix}-{server_name}-{timestamp}"

            # Create new pod
            manifest = self.pod_manager.create_pod_manifest(
                pod_name=pod_name,
                server_config=server_config,
                resources=self.config.resources,
                security=self.config.security
            )

            path = f"/api/v1/namespaces/{self.namespace}/pods"
            result = await self._api_request("POST", path, manifest)

            pod_name = result["metadata"]["name"]

            # Track the running server
            self.running_servers[server_id] = {
                "server_id": server_id,
                "pod_name": pod_name,
                "server_type": server_config.server_type,
                "name": server_config.name,
                "transport": server_config.transport,
                "status": "starting",
                "start_time": time.time(),
                "config": server_config.model_dump()
            }

            # Update global status if this is the main Archon server
            if server_config.server_type == "archon":
                self.status = "starting"
                self.start_time = time.time()

            self._add_log("INFO", f"Created {server_config.server_type} MCP pod: {pod_name}")

            return MCPResponse(
                success=True,
                status="starting",
                message=f"{server_config.server_type} MCP pod {pod_name} created successfully",
                server_id=server_id,
                data={
                    "pod_name": pod_name,
                    "server_type": server_config.server_type,
                    "transport": server_config.transport
                }
            )

        except httpx.HTTPStatusError as e:
            error_msg = f"Kubernetes API error: {e.response.status_code}"
            self._add_log("ERROR", error_msg)
            return MCPResponse(success=False, status="error", message=error_msg)
        except Exception as e:
            error_msg = f"Failed to start MCP pod: {str(e)}"
            self._add_log("ERROR", error_msg)
            return MCPResponse(success=False, status="error", message=error_msg)

    async def stop_server(self, server_id: str | None = None) -> MCPResponse:
        """Stop MCP pods. If server_id is provided, stop only that server, otherwise stop all."""
        try:
            if server_id:
                # Stop specific server
                if server_id not in self.running_servers:
                    return MCPResponse(
                        success=False,
                        status="not_found",
                        message=f"Server {server_id} not found"
                    )

                server_info = self.running_servers[server_id]
                pod_name = server_info["pod_name"]

                path = f"/api/v1/namespaces/{self.namespace}/pods/{pod_name}"
                await self._api_request("DELETE", path)

                # Remove from tracking
                del self.running_servers[server_id]

                # Update global status if this was the main Archon server
                if server_info["server_type"] == "archon":
                    self.status = "stopped"
                    self.start_time = None

                self._add_log("INFO", f"Deleted {server_info['server_type']} pod: {pod_name}")

                return MCPResponse(
                    success=True,
                    status="stopped",
                    message=f"Server {server_id} stopped successfully",
                    server_id=server_id
                )
            else:
                # Stop all servers
                stopped_count = 0
                errors = []

                for sid, server_info in list(self.running_servers.items()):
                    try:
                        pod_name = server_info["pod_name"]
                        path = f"/api/v1/namespaces/{self.namespace}/pods/{pod_name}"
                        await self._api_request("DELETE", path)
                        stopped_count += 1
                        self._add_log("INFO", f"Deleted {server_info['server_type']} pod: {pod_name}")
                    except Exception as e:
                        errors.append(f"Failed to stop {sid}: {e}")

                # Clear all servers
                self.running_servers.clear()
                self.status = "stopped"
                self.start_time = None

                if errors:
                    return MCPResponse(
                        success=stopped_count > 0,
                        status="partial",
                        message=f"Stopped {stopped_count} servers with {len(errors)} errors: {'; '.join(errors)}"
                    )
                else:
                    return MCPResponse(
                        success=True,
                        status="stopped",
                        message=f"All {stopped_count} servers stopped successfully"
                    )

        except Exception as e:
            error_msg = f"Failed to stop servers: {str(e)}"
            self._add_log("ERROR", error_msg)
            return MCPResponse(success=False, status="error", message=error_msg)

    async def get_status(self) -> MCPResponse:
        """Get sidecar and server status."""
        try:
            # Refresh server statuses from Kubernetes
            await self._refresh_server_statuses()

            # Count servers by status
            status_counts = {}
            for server in self.running_servers.values():
                status = server.get("status", "unknown")
                status_counts[status] = status_counts.get(status, 0) + 1

            return MCPResponse(
                success=True,
                status=self.status,
                message=f"Sidecar status: {self.status}",
                data={
                    "sidecar_status": self.status,
                    "start_time": self.start_time,
                    "namespace": self.namespace,
                    "running_servers": len(self.running_servers),
                    "server_statuses": status_counts,
                    "servers": list(self.running_servers.values())
                }
            )

        except Exception as e:
            error_msg = f"Failed to get status: {str(e)}"
            self._add_log("ERROR", error_msg)
            return MCPResponse(success=False, status="error", message=error_msg)

    async def _refresh_server_statuses(self):
        """Refresh server statuses from Kubernetes API."""
        try:
            pods = await self._get_pods()

            # Update status of tracked servers
            for _server_id, server_info in self.running_servers.items():
                pod_name = server_info["pod_name"]

                # Find corresponding pod
                pod = next((p for p in pods if p["metadata"]["name"] == pod_name), None)
                if pod:
                    server_info["status"] = self.pod_manager.get_pod_status(pod)
                    server_info["ready"] = self.pod_manager.is_pod_ready(pod)
                else:
                    # Pod not found, mark as failed
                    server_info["status"] = "not_found"
                    server_info["ready"] = False

        except Exception as e:
            mcp_logger.error(f"Error refreshing server statuses: {e}")

    async def start_external_server(self, config: dict[str, Any]) -> MCPResponse:
        """Start an external MCP server with the given configuration."""
        try:
            server_config = ServerConfig(**config)
            return await self.start_server(server_config)
        except Exception as e:
            return MCPResponse(
                success=False,
                status="error",
                message=f"Invalid configuration: {e}"
            )

    async def stop_external_server(self, server_id: str) -> MCPResponse:
        """Stop a specific external MCP server."""
        return await self.stop_server(server_id)

    async def list_external_servers(self) -> MCPResponse:
        """List all running external MCP servers."""
        try:
            await self._refresh_server_statuses()

            # Filter out Archon core servers if desired
            external_servers = [
                server for server in self.running_servers.values()
                if server.get("server_type") != "archon"
            ]

            return MCPResponse(
                success=True,
                status="ok",
                message=f"Found {len(external_servers)} external servers",
                data={
                    "servers": external_servers,
                    "total_count": len(external_servers)
                }
            )

        except Exception as e:
            return MCPResponse(
                success=False,
                status="error",
                message=f"Failed to list servers: {e}"
            )

    async def health_check(self) -> MCPResponse:
        """Perform health check of the sidecar."""
        try:
            # Test Kubernetes API connectivity
            try:
                await self._api_request("GET", f"/api/v1/namespaces/{self.namespace}")
                k8s_healthy = True
            except Exception:
                k8s_healthy = False

            # Check running servers
            healthy_servers = 0
            total_servers = len(self.running_servers)

            if total_servers > 0:
                await self._refresh_server_statuses()
                for server in self.running_servers.values():
                    if server.get("ready", False):
                        healthy_servers += 1

            overall_healthy = k8s_healthy and (total_servers == 0 or healthy_servers > 0)

            return MCPResponse(
                success=overall_healthy,
                status="healthy" if overall_healthy else "unhealthy",
                message=f"Sidecar health check: {'passed' if overall_healthy else 'failed'}",
                data={
                    "kubernetes_api": k8s_healthy,
                    "total_servers": total_servers,
                    "healthy_servers": healthy_servers,
                    "namespace": self.namespace,
                    "token_present": bool(self.token),
                    "ca_cert_present": bool(self.ca_cert)
                }
            )

        except Exception as e:
            return MCPResponse(
                success=False,
                status="error",
                message=f"Health check failed: {e}"
            )

    def get_logs(self, limit: int = 100) -> list[dict]:
        """Get recent log entries."""
        return list(self.logs)[-limit:]
