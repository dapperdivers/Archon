"""
MCP Pod Manager

This module handles Kubernetes pod lifecycle management for MCP servers.
"""

import os
from typing import Any

from .config import PodResourceConfig, SecurityConfig, ServerConfig


class PodManager:
    """Manages Kubernetes pod creation and configuration for MCP servers."""

    def __init__(self, namespace: str = "archon", pod_name_prefix: str = "mcp"):
        self.namespace = namespace
        self.pod_name_prefix = pod_name_prefix

    def get_server_image_and_config(self, server_config: ServerConfig) -> tuple[str, list[dict], list[str], list[str]]:
        """Get Docker image, environment, command, and args based on server type."""
        server_type = server_config.server_type

        if server_type == "npx":
            image = "node:18-alpine"
            command = ["npx"]
            args = ["-y", server_config.package or ""]
            if server_config.transport == "stdio":
                args.append("stdio")
            env_vars = [
                {"name": "NODE_ENV", "value": "production"},
                {"name": "NPM_CONFIG_UPDATE_NOTIFIER", "value": "false"}
            ]
        elif server_type == "uv":
            image = "python:3.12-slim"
            command = ["sh", "-c"]
            install_cmd = f"pip install uv && uv run --with {server_config.package or ''}"
            if server_config.transport == "stdio":
                install_cmd += " stdio"
            args = [install_cmd]
            env_vars = [
                {"name": "PYTHONUNBUFFERED", "value": "1"},
                {"name": "UV_NO_CACHE", "value": "1"}
            ]
        elif server_type == "python":
            image = "python:3.12-slim"
            command = ["python"]
            args = server_config.args or ["-m", server_config.package or ""]
            if server_config.transport == "stdio":
                args.append("stdio")
            env_vars = [{"name": "PYTHONUNBUFFERED", "value": "1"}]
        elif server_type == "docker":
            image = server_config.image or "alpine:latest"
            command = [server_config.command] if server_config.command else []
            args = server_config.args
            env_vars = []
        else:  # archon (default)
            image = os.getenv("ARCHON_MCP_IMAGE", "archon-mcp:latest")
            command = ["python", "-m", "src.mcp.mcp_server"]
            args = []
            env_vars = [
                {"name": "ARCHON_MCP_HOST", "value": "0.0.0.0"},
                {"name": "ARCHON_MCP_PORT", "value": str(server_config.port or 8051)},
                {"name": "LOG_LEVEL", "value": os.getenv("LOG_LEVEL", "INFO")},
                {"name": "DEPLOYMENT_MODE", "value": "kubernetes"},
                {"name": "SERVICE_DISCOVERY_MODE", "value": "kubernetes"},
                {"name": "KUBERNETES_NAMESPACE", "value": self.namespace},
            ]

        # Add custom environment variables
        for key, value in server_config.env.items():
            env_vars.append({"name": key, "value": value})

        return image, env_vars, command, args

    def create_pod_manifest(
        self,
        pod_name: str,
        server_config: ServerConfig,
        resources: PodResourceConfig | None = None,
        security: SecurityConfig | None = None
    ) -> dict[str, Any]:
        """Generate pod manifest for MCP container with support for different server types."""

        # Use defaults if not provided
        if resources is None:
            resources = PodResourceConfig()
        if security is None:
            security = SecurityConfig()

        image, env_vars, command, args = self.get_server_image_and_config(server_config)

        # Generate unique pod name if not provided
        server_name = server_config.name or server_config.server_type
        if not pod_name:
            import time
            timestamp = int(time.time())
            pod_name = f"{self.pod_name_prefix}-{server_name}-{timestamp}"

        container_spec = {
            "name": f"mcp-{server_name}",
            "image": image,
            "env": env_vars,
            "resources": {
                "requests": {
                    "memory": resources.memory_request,
                    "cpu": resources.cpu_request
                },
                "limits": {
                    "memory": resources.memory_limit,
                    "cpu": resources.cpu_limit
                }
            },
            "securityContext": {
                "allowPrivilegeEscalation": security.allow_privilege_escalation,
                "capabilities": {
                    "drop": security.capabilities_drop
                },
                "readOnlyRootFilesystem": security.read_only_root_filesystem,
                "runAsNonRoot": security.run_as_non_root,
                "runAsUser": security.run_as_user,
                "runAsGroup": security.run_as_group
            }
        }

        # Add command and args if specified
        if command:
            container_spec["command"] = command
        if args:
            container_spec["args"] = args

        # Add ports for HTTP-based servers
        if server_config.transport in ["sse", "http"] and server_config.port:
            container_spec["ports"] = [{
                "containerPort": server_config.port,
                "protocol": "TCP"
            }]

            # Add health checks for HTTP servers
            if server_config.server_type == "archon":
                container_spec["livenessProbe"] = {
                    "httpGet": {"path": "/health", "port": server_config.port},
                    "initialDelaySeconds": 30,
                    "periodSeconds": 10
                }
                container_spec["readinessProbe"] = {
                    "httpGet": {"path": "/health", "port": server_config.port},
                    "initialDelaySeconds": 5,
                    "periodSeconds": 5
                }

        # For stdio servers, we need special handling
        if server_config.transport == "stdio":
            container_spec.update({
                "stdin": True,
                "stdinOnce": False,
                "tty": False
            })

        pod_spec = {
            "restartPolicy": "Never",
            "securityContext": {
                "runAsNonRoot": security.run_as_non_root,
                "runAsUser": security.run_as_user,
                "fsGroup": security.run_as_group
            },
            "containers": [container_spec]
        }

        return {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": pod_name,
                "namespace": self.namespace,
                "labels": {
                    "app": self.pod_name_prefix,
                    "component": "mcp-server",
                    "server-type": server_config.server_type,
                    "transport": server_config.transport,
                    "created-by": "archon-sidecar"
                },
                "annotations": {
                    "server-config": server_config.model_dump_json(),
                }
            },
            "spec": pod_spec
        }

    def get_pod_selector_labels(self) -> dict[str, str]:
        """Get label selector for MCP pods."""
        return {
            "app": self.pod_name_prefix,
            "component": "mcp-server"
        }

    def extract_server_config_from_pod(self, pod: dict[str, Any]) -> ServerConfig | None:
        """Extract server configuration from pod annotations."""
        try:
            annotations = pod.get("metadata", {}).get("annotations", {})
            config_json = annotations.get("server-config")
            if config_json:
                import json
                config_data = json.loads(config_json)
                return ServerConfig(**config_data)
        except Exception:
            pass
        return None

    def is_pod_ready(self, pod: dict[str, Any]) -> bool:
        """Check if a pod is ready."""
        status = pod.get("status", {})
        phase = status.get("phase")

        if phase != "Running":
            return False

        # Check readiness conditions
        conditions = status.get("conditions", [])
        for condition in conditions:
            if condition.get("type") == "Ready":
                return condition.get("status") == "True"

        return False

    def get_pod_status(self, pod: dict[str, Any]) -> str:
        """Get human-readable pod status."""
        status = pod.get("status", {})
        phase = status.get("phase", "Unknown")

        if phase == "Pending":
            # Check container statuses for more detail
            container_statuses = status.get("containerStatuses", [])
            for container_status in container_statuses:
                waiting = container_status.get("state", {}).get("waiting")
                if waiting:
                    return f"Pending ({waiting.get('reason', 'Unknown')})"
            return "Pending"
        elif phase == "Running":
            if self.is_pod_ready(pod):
                return "Running"
            else:
                return "Starting"
        elif phase == "Succeeded":
            return "Completed"
        elif phase == "Failed":
            return "Failed"
        else:
            return phase
