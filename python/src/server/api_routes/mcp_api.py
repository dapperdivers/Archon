"""
MCP API endpoints for Archon

Handles:
- MCP server lifecycle (start/stop/status)
- MCP server configuration management
- WebSocket log streaming
- Tool discovery and testing

Supports both Docker and Kubernetes deployment modes.
"""

import asyncio
import os
import time
from collections import deque
from datetime import datetime
from typing import Any, Protocol

import docker
from docker.errors import APIError, NotFound
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ...shared.packages import get_package_manager

# Import shared registry and package management components
from ...shared.registry import get_mcp_registry

# Import unified logging
from ..config.logfire_config import api_logger, mcp_logger, safe_set_attribute, safe_span
from ..services.kubernetes_mcp_manager import KubernetesMCPManager
from ..services.mcp_sidecar_client import MCPSidecarClient
from ..utils import get_supabase_client

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


class ServerConfig(BaseModel):
    transport: str = "sse"
    host: str = "localhost"
    port: int = 8051


class ServerResponse(BaseModel):
    success: bool
    message: str
    status: str | None = None
    pid: int | None = None


class LogEntry(BaseModel):
    timestamp: str
    level: str
    message: str


class ExternalServerConfig(BaseModel):
    server_type: str = "npx"  # "npx", "uv", "python", "docker"
    name: str | None = None
    package: str | None = None  # For npx/uv servers
    command: str | None = None  # Custom command
    args: list[str] = []
    env: dict[str, str] = {}
    transport: str = "stdio"  # "stdio", "sse", "http"
    image: str | None = None  # Custom Docker image
    port: int | None = None
    timeout: int = 300  # Pod startup timeout


class ContainerManager(Protocol):
    """Protocol for container managers (Docker or Kubernetes)."""

    async def start_server(self) -> dict[str, Any]:
        """Start the MCP server."""
        ...

    async def stop_server(self) -> dict[str, Any]:
        """Stop the MCP server."""
        ...

    def get_status(self) -> dict[str, Any]:
        """Get server status."""
        ...


class DockerManager:
    """Manages the MCP Docker container lifecycle."""

    def __init__(self):
        self.container_name = None  # Will be resolved dynamically
        self.docker_client = None
        self.container = None
        self.status: str = "stopped"
        self.start_time: float | None = None
        self.logs: deque = deque(maxlen=1000)  # Keep last 1000 log entries
        self.log_websockets: list[WebSocket] = []
        self.log_reader_task: asyncio.Task | None = None
        self._operation_lock = asyncio.Lock()  # Prevent concurrent start/stop operations
        self._last_operation_time = 0
        self._min_operation_interval = 2.0  # Minimum 2 seconds between operations
        self._docker_initialized = False
        # Don't initialize Docker here - do it lazily

    def _resolve_container(self):
        """Simple container resolution - just use fixed name."""
        if not self.docker_client:
            return None
        
        try:
            # Simple: Just look for the fixed container name
            container = self.docker_client.containers.get("archon-mcp")
            self.container_name = "archon-mcp"
            mcp_logger.info("Found MCP container")
            return container
        except NotFound:
            mcp_logger.warning("MCP container not found - is it running?")
            self.container_name = "archon-mcp"
            return None

    def _initialize_docker_client(self):
        """Initialize Docker client and get container reference."""
        if self._docker_initialized:
            return self.docker_client is not None

        # Check deployment mode first
        deployment_mode = os.getenv("DEPLOYMENT_MODE", "").lower()
        if deployment_mode == "kubernetes":
            mcp_logger.debug("Skipping Docker initialization in Kubernetes mode")
            self._docker_initialized = True
            return False

        try:
            self.docker_client = docker.from_env()
            self.container = self._resolve_container()
            if not self.container:
                mcp_logger.warning("MCP container not found during initialization")
            self._docker_initialized = True
            return True
        except Exception as e:
            # Only log error if not in Kubernetes mode
            if deployment_mode != "kubernetes":
                mcp_logger.error(f"Failed to initialize Docker client: {str(e)}")
            self.docker_client = None
            self._docker_initialized = True
            return False

    def _get_container_status(self) -> str:
        """Get the current status of the MCP container."""
        # Ensure Docker is initialized
        if not self._initialize_docker_client():
            return "docker_unavailable"

        if not self.docker_client:
            return "docker_unavailable"

        try:
            if self.container:
                self.container.reload()  # Refresh container info
            else:
                # Try to resolve container again if we don't have it
                self.container = self._resolve_container()
                if not self.container:
                    return "not_found"

            return self.container.status
        except NotFound:
            # Try to resolve again in case container was recreated
            self.container = self._resolve_container()
            if self.container:
                return self.container.status
            return "not_found"
        except Exception as e:
            mcp_logger.error(f"Error getting container status: {str(e)}")
            return "error"

    def _is_log_reader_active(self) -> bool:
        """Check if the log reader task is active."""
        return self.log_reader_task is not None and not self.log_reader_task.done()

    async def _ensure_log_reader_running(self):
        """Ensure the log reader task is running if container is active."""
        if not self.container:
            return

        # Cancel existing task if any
        if self.log_reader_task:
            self.log_reader_task.cancel()
            try:
                await self.log_reader_task
            except asyncio.CancelledError:
                pass

        # Start new log reader task
        self.log_reader_task = asyncio.create_task(self._read_container_logs())
        self._add_log("INFO", "Connected to MCP container logs")
        mcp_logger.info(f"Started log reader for already-running container: {self.container_name}")

    async def start_server(self) -> dict[str, Any]:
        """Start the MCP Docker container."""
        async with self._operation_lock:
            # Check throttling
            current_time = time.time()
            if current_time - self._last_operation_time < self._min_operation_interval:
                wait_time = self._min_operation_interval - (
                    current_time - self._last_operation_time
                )
                mcp_logger.warning(f"Start operation throttled, please wait {wait_time:.1f}s")
                return {
                    "success": False,
                    "status": self.status,
                    "message": f"Please wait {wait_time:.1f}s before starting server again",
                }

        with safe_span("mcp_server_start") as span:
            safe_set_attribute(span, "action", "start_server")

            # Ensure Docker is initialized
            if not self._initialize_docker_client():
                deployment_mode = os.getenv("DEPLOYMENT_MODE", "").lower()
                if deployment_mode == "kubernetes":
                    mcp_logger.info("Docker not available in Kubernetes mode - use sidecar instead")
                    return {
                        "success": False,
                        "status": "kubernetes_mode",
                        "message": "In Kubernetes mode - MCP management handled by sidecar",
                    }
                else:
                    mcp_logger.error("Docker client not available")
                    return {
                        "success": False,
                        "status": "docker_unavailable",
                        "message": "Docker is not available. Is Docker socket mounted?",
                    }

            if not self.docker_client:
                mcp_logger.error("Docker client not available")
                return {
                    "success": False,
                    "status": "docker_unavailable",
                    "message": "Docker is not available. Is Docker socket mounted?",
                }

            # Check current container status
            container_status = self._get_container_status()

            if container_status == "not_found":
                mcp_logger.error(f"Container {self.container_name} not found")
                return {
                    "success": False,
                    "status": "not_found",
                    "message": f"MCP container {self.container_name} not found. Run docker-compose up -d archon-mcp",
                }

            if container_status == "running":
                mcp_logger.warning("MCP server start attempted while already running")
                return {
                    "success": False,
                    "status": "running",
                    "message": "MCP server is already running",
                }

            try:
                # Start the container
                self.container.start()
                self.status = "starting"
                self.start_time = time.time()
                self._last_operation_time = time.time()
                self._add_log("INFO", "MCP container starting...")
                mcp_logger.info(f"Starting MCP container: {self.container_name}")
                safe_set_attribute(span, "container_id", self.container.id)

                # Start reading logs from the container
                if self.log_reader_task:
                    self.log_reader_task.cancel()
                self.log_reader_task = asyncio.create_task(self._read_container_logs())

                # Give it a moment to start
                await asyncio.sleep(2)

                # Check if container is running
                self.container.reload()
                if self.container.status == "running":
                    self.status = "running"
                    self._add_log("INFO", "MCP container started successfully")
                    mcp_logger.info(
                        f"MCP container started successfully - container_id={self.container.id}"
                    )
                    safe_set_attribute(span, "success", True)
                    safe_set_attribute(span, "status", "running")
                    return {
                        "success": True,
                        "status": self.status,
                        "message": "MCP server started successfully",
                        "container_id": self.container.id[:12],
                    }
                else:
                    self.status = "failed"
                    self._add_log(
                        "ERROR", f"MCP container failed to start. Status: {self.container.status}"
                    )
                    mcp_logger.error(
                        f"MCP container failed to start - status: {self.container.status}"
                    )
                    safe_set_attribute(span, "success", False)
                    safe_set_attribute(span, "status", self.container.status)
                    return {
                        "success": False,
                        "status": self.status,
                        "message": f"MCP container failed to start. Status: {self.container.status}",
                    }

            except APIError as e:
                self.status = "failed"
                self._add_log("ERROR", f"Docker API error: {str(e)}")
                mcp_logger.error(f"Docker API error during MCP startup - error={str(e)}")
                safe_set_attribute(span, "success", False)
                safe_set_attribute(span, "error", str(e))
                return {
                    "success": False,
                    "status": self.status,
                    "message": f"Docker API error: {str(e)}",
                }
            except Exception as e:
                self.status = "failed"
                self._add_log("ERROR", f"Failed to start MCP server: {str(e)}")
                mcp_logger.error(
                    f"Exception during MCP server startup - error={str(e)}, error_type={type(e).__name__}"
                )
                safe_set_attribute(span, "success", False)
                safe_set_attribute(span, "error", str(e))
                return {
                    "success": False,
                    "status": self.status,
                    "message": f"Failed to start MCP server: {str(e)}",
                }

    async def stop_server(self) -> dict[str, Any]:
        """Stop the MCP Docker container."""
        async with self._operation_lock:
            # Check throttling
            current_time = time.time()
            if current_time - self._last_operation_time < self._min_operation_interval:
                wait_time = self._min_operation_interval - (
                    current_time - self._last_operation_time
                )
                mcp_logger.warning(f"Stop operation throttled, please wait {wait_time:.1f}s")
                return {
                    "success": False,
                    "status": self.status,
                    "message": f"Please wait {wait_time:.1f}s before stopping server again",
                }

        with safe_span("mcp_server_stop") as span:
            safe_set_attribute(span, "action", "stop_server")

            # Ensure Docker is initialized
            if not self._initialize_docker_client():
                deployment_mode = os.getenv("DEPLOYMENT_MODE", "").lower()
                if deployment_mode == "kubernetes":
                    mcp_logger.info("Docker not available in Kubernetes mode - use sidecar instead")
                    return {
                        "success": False,
                        "status": "kubernetes_mode",
                        "message": "In Kubernetes mode - MCP management handled by sidecar",
                    }
                else:
                    mcp_logger.error("Docker client not available")
                    return {
                        "success": False,
                        "status": "docker_unavailable",
                        "message": "Docker is not available",
                    }

            if not self.docker_client:
                mcp_logger.error("Docker client not available")
                return {
                    "success": False,
                    "status": "docker_unavailable",
                    "message": "Docker is not available",
                }

            # Check current container status
            container_status = self._get_container_status()

            if container_status not in ["running", "restarting"]:
                mcp_logger.warning(
                    f"MCP server stop attempted when not running. Status: {container_status}"
                )
                return {
                    "success": False,
                    "status": container_status,
                    "message": f"MCP server is not running (status: {container_status})",
                }

            try:
                self.status = "stopping"
                self._add_log("INFO", "Stopping MCP container...")
                mcp_logger.info(f"Stopping MCP container: {self.container_name}")
                safe_set_attribute(span, "container_id", self.container.id)

                # Cancel log reading task
                if self.log_reader_task:
                    self.log_reader_task.cancel()
                    try:
                        await self.log_reader_task
                    except asyncio.CancelledError:
                        pass

                # Stop the container with timeout
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.container.stop(timeout=10),  # 10 second timeout
                )

                self.status = "stopped"
                self.start_time = None
                self._last_operation_time = time.time()
                self._add_log("INFO", "MCP container stopped")
                mcp_logger.info("MCP container stopped successfully")
                safe_set_attribute(span, "success", True)
                safe_set_attribute(span, "status", "stopped")

                return {
                    "success": True,
                    "status": self.status,
                    "message": "MCP server stopped successfully",
                }

            except APIError as e:
                self._add_log("ERROR", f"Docker API error: {str(e)}")
                mcp_logger.error(f"Docker API error during MCP stop - error={str(e)}")
                safe_set_attribute(span, "success", False)
                safe_set_attribute(span, "error", str(e))
                return {
                    "success": False,
                    "status": self.status,
                    "message": f"Docker API error: {str(e)}",
                }
            except Exception as e:
                self._add_log("ERROR", f"Error stopping MCP server: {str(e)}")
                mcp_logger.error(
                    f"Exception during MCP server stop - error={str(e)}, error_type={type(e).__name__}"
                )
                safe_set_attribute(span, "success", False)
                safe_set_attribute(span, "error", str(e))
                return {
                    "success": False,
                    "status": self.status,
                    "message": f"Error stopping MCP server: {str(e)}",
                }

    def get_status(self) -> dict[str, Any]:
        """Get the current server status."""
        # Ensure Docker is initialized
        if not self._initialize_docker_client():
            deployment_mode = os.getenv("DEPLOYMENT_MODE", "").lower()
            if deployment_mode == "kubernetes":
                return {
                    "status": "kubernetes_mode",
                    "message": "In Kubernetes mode - MCP management handled by sidecar",
                    "uptime": None,
                    "logs_available": False
                }
            else:
                return {
                    "status": "docker_unavailable",
                    "message": "Docker is not available",
                    "uptime": None,
                    "logs_available": False
                }

        # Update status based on actual container state
        container_status = self._get_container_status()

        # Map Docker statuses to our statuses
        status_map = {
            "running": "running",
            "restarting": "restarting",
            "paused": "paused",
            "exited": "stopped",
            "dead": "stopped",
            "created": "stopped",
            "removing": "stopping",
            "not_found": "not_found",
            "docker_unavailable": "docker_unavailable",
            "error": "error",
        }

        self.status = status_map.get(container_status, "unknown")

        # If container is running but log reader isn't active, start it
        if self.status == "running" and not self._is_log_reader_active():
            asyncio.create_task(self._ensure_log_reader_running())

        uptime = None
        if self.status == "running" and self.start_time:
            uptime = int(time.time() - self.start_time)
        elif self.status == "running" and self.container:
            # Try to get uptime from container info
            try:
                self.container.reload()
                started_at = self.container.attrs["State"]["StartedAt"]
                # Parse ISO format datetime
                from datetime import datetime

                started_time = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                uptime = int((datetime.now(started_time.tzinfo) - started_time).total_seconds())
            except Exception:
                pass

        # Convert log entries to strings for backward compatibility
        recent_logs = []
        for log in list(self.logs)[-10:]:
            if isinstance(log, dict):
                recent_logs.append(f"[{log['level']}] {log['message']}")
            else:
                recent_logs.append(str(log))

        return {
            "status": self.status,
            "uptime": uptime,
            "logs": recent_logs,
            "container_status": container_status,  # Include raw Docker status
        }

    def _add_log(self, level: str, message: str):
        """Add a log entry and broadcast to connected WebSockets."""
        log_entry = {
            "timestamp": datetime.now(datetime.timezone.utc).isoformat(),
            "level": level,
            "message": message,
        }
        self.logs.append(log_entry)

        # Broadcast to all connected WebSockets
        asyncio.create_task(self._broadcast_log(log_entry))

    async def _broadcast_log(self, log_entry: dict[str, Any]):
        """Broadcast log entry to all connected WebSockets."""
        disconnected = []
        for ws in self.log_websockets:
            try:
                await ws.send_json(log_entry)
            except Exception:
                disconnected.append(ws)

        # Remove disconnected WebSockets
        for ws in disconnected:
            self.log_websockets.remove(ws)

    async def _read_container_logs(self):
        """Read logs from Docker container."""
        if not self.container:
            return

        try:
            # Stream logs from container
            log_generator = self.container.logs(stream=True, follow=True, tail=100)

            while True:
                try:
                    log_line = await asyncio.get_event_loop().run_in_executor(
                        None, next, log_generator, None
                    )

                    if log_line is None:
                        break

                    # Decode bytes to string
                    if isinstance(log_line, bytes):
                        log_line = log_line.decode("utf-8").strip()

                    if log_line:
                        level, message = self._parse_log_line(log_line)
                        self._add_log(level, message)

                except StopIteration:
                    break
                except Exception as e:
                    self._add_log("ERROR", f"Log reading error: {str(e)}")
                    break

        except asyncio.CancelledError:
            pass
        except APIError as e:
            if "container not found" not in str(e).lower():
                self._add_log("ERROR", f"Docker API error reading logs: {str(e)}")
        except Exception as e:
            self._add_log("ERROR", f"Error reading container logs: {str(e)}")
        finally:
            # Check if container stopped
            try:
                self.container.reload()
                if self.container.status not in ["running", "restarting"]:
                    self._add_log(
                        "INFO", f"MCP container stopped with status: {self.container.status}"
                    )
            except Exception:
                pass

    def _parse_log_line(self, line: str) -> tuple[str, str]:
        """Parse a log line to extract level and message."""
        line = line.strip()
        if not line:
            return "INFO", ""

        # Try to extract log level from common formats
        if line.startswith("[") and "]" in line:
            end_bracket = line.find("]")
            potential_level = line[1:end_bracket].upper()
            if potential_level in ["INFO", "DEBUG", "WARNING", "ERROR", "CRITICAL"]:
                return potential_level, line[end_bracket + 1 :].strip()

        # Check for common log level indicators
        line_lower = line.lower()
        if any(word in line_lower for word in ["error", "exception", "failed", "critical"]):
            return "ERROR", line
        elif any(word in line_lower for word in ["warning", "warn"]):
            return "WARNING", line
        elif any(word in line_lower for word in ["debug"]):
            return "DEBUG", line
        else:
            return "INFO", line

    def get_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get historical logs."""
        logs = list(self.logs)
        if limit > 0:
            logs = logs[-limit:]
        return logs

    def clear_logs(self):
        """Clear the log buffer."""
        self.logs.clear()
        self._add_log("INFO", "Logs cleared")

    async def add_websocket(self, websocket: WebSocket):
        """Add a WebSocket connection for log streaming."""
        await websocket.accept()
        self.log_websockets.append(websocket)

        # Send connection info but NOT historical logs
        # The frontend already fetches historical logs via the /logs endpoint
        await websocket.send_json({
            "type": "connection",
            "message": "WebSocket connected for log streaming",
        })

    def remove_websocket(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        if websocket in self.log_websockets:
            self.log_websockets.remove(websocket)


class MCPServerManager:
    """Factory class that manages MCP server using appropriate backend (Docker or sidecar)."""

    def __init__(self):
        self.log_websockets: list[WebSocket] = []
        self.sidecar_client = MCPSidecarClient()
        self.manager: ContainerManager | None = None
        self._manager_type = "unknown"

        # Initialize manager asynchronously on first use
        self._initialization_lock = asyncio.Lock()
        self._initialized = False

    async def _ensure_initialized(self):
        """Ensure the manager is initialized, preferring sidecar over Docker."""
        if self._initialized:
            return

        async with self._initialization_lock:
            if self._initialized:
                return

            # Try sidecar first (for Kubernetes environments)
            if await self.sidecar_client.is_available():
                self.manager = self.sidecar_client
                self._manager_type = "sidecar"
                mcp_logger.info("Using MCP sidecar for Kubernetes pod management")
            else:
                # Check deployment mode before trying Docker
                deployment_mode = os.getenv("DEPLOYMENT_MODE", "").lower()
                if deployment_mode == "kubernetes":
                    # In Kubernetes without sidecar, use Kubernetes-native MCP management
                    mcp_logger.info("Using Kubernetes-native MCP management (main MCP server)")
                    self.manager = KubernetesMCPManager()
                    self._manager_type = "kubernetes"
                else:
                    # Fall back to Docker for non-Kubernetes environments
                    self.manager = DockerManager()
                    self._manager_type = "docker"
                    mcp_logger.info("Using Docker backend for MCP management")

            self._initialized = True

    async def start_server(self) -> dict[str, Any]:
        """Start the MCP server using the configured backend."""
        await self._ensure_initialized()
        if self.manager is None:
            return {
                "success": False,
                "status": "unavailable",
                "message": "MCP management not available in current deployment mode"
            }
        return await self.manager.start_server()

    async def stop_server(self) -> dict[str, Any]:
        """Stop the MCP server using the configured backend."""
        await self._ensure_initialized()
        if self.manager is None:
            return {
                "success": False,
                "status": "unavailable",
                "message": "MCP management not available in current deployment mode"
            }
        return await self.manager.stop_server()

    def get_status(self) -> dict[str, Any]:
        """Get server status from the configured backend."""
        # Assume initialization is handled by async callers
        if not self._initialized:
            return {
                "status": "initializing",
                "message": "Manager not yet initialized",
                "deployment_mode": self._manager_type
            }

        if self.manager is None:
            return {
                "status": "unavailable",
                "message": "MCP management not available in current deployment mode",
                "deployment_mode": self._manager_type,
                "uptime": None,
                "logs_available": False
            }

        status = self.manager.get_status()
        # Add deployment mode to status
        status["deployment_mode"] = self._manager_type
        return status

    def get_logs(self, limit: int = 100, server_id: str | None = None) -> list[dict[str, Any]]:
        """Get historical logs."""
        if not self._initialized:
            return []

        if self.manager is None:
            return []

        if hasattr(self.manager, 'get_logs'):
            # Check if the manager supports server_id parameter (Kubernetes manager does)
            import inspect
            sig = inspect.signature(self.manager.get_logs)
            if 'server_id' in sig.parameters:
                return self.manager.get_logs(limit, server_id)
            else:
                # Fallback for managers that don't support server_id (Docker manager)
                if server_id is not None:
                    # External servers not supported in non-Kubernetes environments
                    return []
                return self.manager.get_logs(limit)
        # Fallback for managers without get_logs method
        if hasattr(self.manager, 'logs'):
            if server_id is not None:
                return []  # External servers not supported
            logs = list(self.manager.logs)
            if limit > 0:
                logs = logs[-limit:]
            return logs
        return []

    def clear_logs(self):
        """Clear the log buffer."""
        if not self._initialized:
            return

        if self.manager is None:
            return

        if hasattr(self.manager, 'clear_logs'):
            self.manager.clear_logs()

    async def add_websocket(self, websocket: WebSocket):
        """Add a WebSocket connection for log streaming."""
        await self._ensure_initialized()
        await websocket.accept()
        self.log_websockets.append(websocket)

        if self.manager is None:
            # Send unavailable message
            await websocket.send_json({
                "type": "error",
                "message": "MCP management not available in current deployment mode",
            })
            return

        # Try to delegate to manager's websocket handling
        if hasattr(self.manager, 'add_websocket'):
            await self.manager.add_websocket(websocket)
        else:
            # Fallback: send connection message
            await websocket.send_json({
                "type": "connection",
                "message": f"WebSocket connected for log streaming (using {self._manager_type})",
            })

    def remove_websocket(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        if websocket in self.log_websockets:
            self.log_websockets.remove(websocket)

        # Try to delegate to manager's websocket handling
        if self._initialized and hasattr(self.manager, 'remove_websocket'):
            self.manager.remove_websocket(websocket)


# Global MCP manager instance
mcp_manager = MCPServerManager()


# FastAPI dependency to ensure MCP manager is initialized
async def ensure_mcp_initialized():
    """Dependency that ensures MCP manager is initialized before endpoint execution."""
    await mcp_manager._ensure_initialized()


# FastAPI dependency for status endpoints that should show initialization progress
async def try_mcp_initialization():
    """Dependency that attempts initialization but doesn't block if in progress."""
    # For status endpoints, we want to show "initializing" if not ready yet
    # So we don't await here, just trigger initialization if needed
    if not mcp_manager._initialized:
        # Start initialization as a background task without waiting
        import asyncio
        asyncio.create_task(mcp_manager._ensure_initialized())
    # Always return, letting the endpoint decide what to show
    return


@router.post("/start", response_model=ServerResponse)
async def start_server(_: None = Depends(ensure_mcp_initialized)):
    """Start the MCP server."""
    with safe_span("api_mcp_start") as span:
        safe_set_attribute(span, "endpoint", "/mcp/start")
        safe_set_attribute(span, "method", "POST")

        try:
            result = await mcp_manager.start_server()
            api_logger.info(
                "MCP server start API called - success=%s", result.get("success", False)
            )
            safe_set_attribute(span, "success", result.get("success", False))
            return result
        except Exception as e:
            api_logger.error("MCP server start API failed - error=%s", str(e))
            safe_set_attribute(span, "success", False)
            safe_set_attribute(span, "error", str(e))
            raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/stop", response_model=ServerResponse)
async def stop_server(_: None = Depends(ensure_mcp_initialized)):
    """Stop the MCP server."""
    with safe_span("api_mcp_stop") as span:
        safe_set_attribute(span, "endpoint", "/mcp/stop")
        safe_set_attribute(span, "method", "POST")

        try:
            result = await mcp_manager.stop_server()
            api_logger.info(f"MCP server stop API called - success={result.get('success', False)}")
            safe_set_attribute(span, "success", result.get("success", False))
            return result
        except Exception as e:
            api_logger.error(f"MCP server stop API failed - error={str(e)}")
            safe_set_attribute(span, "success", False)
            safe_set_attribute(span, "error", str(e))
            raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/status")
async def get_status(_: None = Depends(try_mcp_initialization)):
    """Get MCP server status."""
    with safe_span("api_mcp_status") as span:
        safe_set_attribute(span, "endpoint", "/mcp/status")
        safe_set_attribute(span, "method", "GET")

        try:
            status = mcp_manager.get_status()
            api_logger.debug(f"MCP server status checked - status={status.get('status')}")
            safe_set_attribute(span, "status", status.get("status"))
            safe_set_attribute(span, "uptime", status.get("uptime"))
            return status
        except Exception as e:
            api_logger.error(f"MCP server status API failed - error={str(e)}")
            safe_set_attribute(span, "error", str(e))
            raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/logs")
async def get_logs(limit: int = 100, _: None = Depends(ensure_mcp_initialized)):
    """Get MCP server logs (main Archon MCP server)."""
    with safe_span("api_mcp_logs") as span:
        safe_set_attribute(span, "endpoint", "/mcp/logs")
        safe_set_attribute(span, "method", "GET")
        safe_set_attribute(span, "limit", limit)

        try:
            logs = mcp_manager.get_logs(limit)
            api_logger.debug("MCP server logs retrieved", count=len(logs))
            safe_set_attribute(span, "log_count", len(logs))
            return {"logs": logs}
        except Exception as e:
            api_logger.error("MCP server logs API failed", error=str(e))
            safe_set_attribute(span, "error", str(e))
            raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/servers/external/{server_id}/logs")
async def get_external_server_logs(server_id: str, limit: int = 100, _: None = Depends(ensure_mcp_initialized)):
    """Get logs from a specific external MCP server."""
    with safe_span("api_external_mcp_logs") as span:
        safe_set_attribute(span, "endpoint", f"/mcp/servers/external/{server_id}/logs")
        safe_set_attribute(span, "method", "GET")
        safe_set_attribute(span, "server_id", server_id)
        safe_set_attribute(span, "limit", limit)

        try:
            # Only available in Kubernetes environments
            if mcp_manager._manager_type != "kubernetes":
                raise HTTPException(
                    status_code=503,
                    detail="External server logs only available in Kubernetes deployments"
                )
            
            logs = mcp_manager.get_logs(limit, server_id)
            api_logger.debug(f"External server logs retrieved - server_id={server_id}, count={len(logs)}")
            safe_set_attribute(span, "log_count", len(logs))
            return {"logs": logs, "server_id": server_id}
        except HTTPException:
            raise
        except Exception as e:
            api_logger.error(f"External server logs API failed - server_id={server_id}, error={str(e)}")
            safe_set_attribute(span, "error", str(e))
            raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/logs")
async def clear_logs(_: None = Depends(ensure_mcp_initialized)):
    """Clear MCP server logs."""
    with safe_span("api_mcp_clear_logs") as span:
        safe_set_attribute(span, "endpoint", "/mcp/logs")
        safe_set_attribute(span, "method", "DELETE")

        try:
            mcp_manager.clear_logs()
            api_logger.info("MCP server logs cleared")
            safe_set_attribute(span, "success", True)
            return {"success": True, "message": "Logs cleared successfully"}
        except Exception as e:
            api_logger.error("MCP server clear logs API failed", error=str(e))
            safe_set_attribute(span, "success", False)
            safe_set_attribute(span, "error", str(e))
            raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/config")
async def get_mcp_config():
    """Get MCP server configuration."""
    with safe_span("api_get_mcp_config") as span:
        safe_set_attribute(span, "endpoint", "/api/mcp/config")
        safe_set_attribute(span, "method", "GET")

        try:
            api_logger.info("Getting MCP server configuration")

            # Get actual MCP port from environment or use default
            import os

            mcp_port = int(os.getenv("ARCHON_MCP_PORT", "8051"))

            # Configuration for SSE-only mode with actual port
            config = {
                "host": "localhost",
                "port": mcp_port,
                "transport": "sse",
            }

            # Get only model choice from database
            try:
                from ..services.credential_service import credential_service

                model_choice = await credential_service.get_credential(
                    "MODEL_CHOICE", "gpt-4o-mini"
                )
                config["model_choice"] = model_choice
                config["use_contextual_embeddings"] = (
                    await credential_service.get_credential("USE_CONTEXTUAL_EMBEDDINGS", "false")
                ).lower() == "true"
                config["use_hybrid_search"] = (
                    await credential_service.get_credential("USE_HYBRID_SEARCH", "false")
                ).lower() == "true"
                config["use_agentic_rag"] = (
                    await credential_service.get_credential("USE_AGENTIC_RAG", "false")
                ).lower() == "true"
                config["use_reranking"] = (
                    await credential_service.get_credential("USE_RERANKING", "false")
                ).lower() == "true"
            except Exception:
                # Fallback to default model
                config["model_choice"] = "gpt-4o-mini"
                config["use_contextual_embeddings"] = False
                config["use_hybrid_search"] = False
                config["use_agentic_rag"] = False
                config["use_reranking"] = False

            api_logger.info("MCP configuration (SSE-only mode)")
            safe_set_attribute(span, "host", config["host"])
            safe_set_attribute(span, "port", config["port"])
            safe_set_attribute(span, "transport", "sse")
            safe_set_attribute(span, "model_choice", config.get("model_choice", "gpt-4o-mini"))

            return config
        except Exception as e:
            api_logger.error("Failed to get MCP configuration", error=str(e))
            safe_set_attribute(span, "error", str(e))
            raise HTTPException(status_code=500, detail={"error": str(e)}) from e


@router.post("/config")
async def save_configuration(config: ServerConfig):
    """Save MCP server configuration."""
    with safe_span("api_save_mcp_config") as span:
        safe_set_attribute(span, "endpoint", "/api/mcp/config")
        safe_set_attribute(span, "method", "POST")
        safe_set_attribute(span, "transport", config.transport)
        safe_set_attribute(span, "host", config.host)
        safe_set_attribute(span, "port", config.port)

        try:
            api_logger.info(
                f"Saving MCP server configuration | transport={config.transport} | host={config.host} | port={config.port}"
            )
            supabase_client = get_supabase_client()  # Verify we can connect to Supabase
            if not supabase_client:
                raise Exception("Failed to connect to Supabase")

            config_json = config.model_dump_json()

            # Save MCP config using credential service
            from ..services.credential_service import credential_service

            success = await credential_service.set_credential(
                "mcp_config",
                config_json,
                category="mcp",
                description="MCP server configuration settings",
            )

            if success:
                api_logger.info("MCP configuration saved successfully")
                safe_set_attribute(span, "operation", "save")
            else:
                raise Exception("Failed to save MCP configuration")

            safe_set_attribute(span, "success", True)
            return {"success": True, "message": "Configuration saved"}

        except Exception as e:
            api_logger.error(f"Failed to save MCP configuration | error={str(e)}")
            safe_set_attribute(span, "error", str(e))
            raise HTTPException(status_code=500, detail={"error": str(e)}) from e


@router.websocket("/logs/stream")
async def websocket_log_stream(websocket: WebSocket):
    """WebSocket endpoint for streaming MCP server logs."""
    await mcp_manager.add_websocket(websocket)
    try:
        while True:
            # Keep connection alive
            await asyncio.sleep(1)
            # Check if WebSocket is still connected
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        mcp_manager.remove_websocket(websocket)
    except Exception:
        mcp_manager.remove_websocket(websocket)
        try:
            await websocket.close()
        except Exception:
            pass


# External Server Management Endpoints

@router.post("/servers/external/start")
async def start_external_server(config: ExternalServerConfig, _: None = Depends(ensure_mcp_initialized)):
    """Start an external MCP server (npx, uv, etc.)."""
    with safe_span("api_start_external_mcp_server") as span:
        safe_set_attribute(span, "endpoint", "/mcp/servers/external/start")
        safe_set_attribute(span, "method", "POST")
        safe_set_attribute(span, "server_type", config.server_type)
        safe_set_attribute(span, "transport", config.transport)

        try:
            # Manager is already initialized via dependency

            if mcp_manager._manager_type != "sidecar":
                raise HTTPException(
                    status_code=503,
                    detail="External servers require Kubernetes sidecar deployment"
                )

            # Convert to sidecar format
            server_config_dict = {
                "server_type": config.server_type,
                "name": config.name,
                "package": config.package,
                "command": config.command,
                "args": config.args,
                "env": config.env,
                "transport": config.transport,
                "image": config.image,
                "port": config.port,
                "timeout": config.timeout
            }

            result = await mcp_manager.sidecar_client.start_external_server(server_config_dict)

            api_logger.info(
                f"External MCP server start API called - server_type={config.server_type}, success={result.get('success', False)}"
            )
            safe_set_attribute(span, "success", result.get("success", False))
            safe_set_attribute(span, "server_id", result.get("server_id"))

            return result

        except HTTPException:
            raise
        except Exception as e:
            api_logger.error(f"External MCP server start API failed - error={str(e)}")
            safe_set_attribute(span, "success", False)
            safe_set_attribute(span, "error", str(e))
            raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/servers/external/stop/{server_id}")
async def stop_external_server(server_id: str, _: None = Depends(ensure_mcp_initialized)):
    """Stop a specific external MCP server."""
    with safe_span("api_stop_external_mcp_server") as span:
        safe_set_attribute(span, "endpoint", "/mcp/servers/external/stop")
        safe_set_attribute(span, "method", "POST")
        safe_set_attribute(span, "server_id", server_id)

        try:
            # Manager is already initialized via dependency

            if mcp_manager._manager_type != "sidecar":
                raise HTTPException(
                    status_code=503,
                    detail="External servers require Kubernetes sidecar deployment"
                )

            result = await mcp_manager.sidecar_client.stop_external_server(server_id)

            api_logger.info(
                f"External MCP server stop API called - server_id={server_id}, success={result.get('success', False)}"
            )
            safe_set_attribute(span, "success", result.get("success", False))

            return result

        except HTTPException:
            raise
        except Exception as e:
            api_logger.error(f"External MCP server stop API failed - error={str(e)}")
            safe_set_attribute(span, "success", False)
            safe_set_attribute(span, "error", str(e))
            raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/servers/external")
async def list_external_servers(_: None = Depends(ensure_mcp_initialized)):
    """List all running external MCP servers."""
    with safe_span("api_list_external_mcp_servers") as span:
        safe_set_attribute(span, "endpoint", "/mcp/servers/external")
        safe_set_attribute(span, "method", "GET")

        try:
            # Manager is already initialized via dependency

            if mcp_manager._manager_type != "sidecar":
                return {
                    "servers": [],
                    "count": 0,
                    "deployment_mode": mcp_manager._manager_type,
                    "message": "External servers require Kubernetes sidecar deployment"
                }

            result = await mcp_manager.sidecar_client.list_external_servers()

            api_logger.debug(f"Listed external MCP servers - count={result.get('count', 0)}")
            safe_set_attribute(span, "server_count", result.get("count", 0))

            return result

        except Exception as e:
            api_logger.error(f"External MCP server list API failed - error={str(e)}")
            safe_set_attribute(span, "error", str(e))
            raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/servers/external/{server_id}")
async def get_external_server_info(server_id: str, _: None = Depends(ensure_mcp_initialized)):
    """Get information about a specific external MCP server."""
    with safe_span("api_get_external_mcp_server_info") as span:
        safe_set_attribute(span, "endpoint", "/mcp/servers/external/{server_id}")
        safe_set_attribute(span, "method", "GET")
        safe_set_attribute(span, "server_id", server_id)

        try:
            # Manager is already initialized via dependency

            if mcp_manager._manager_type != "sidecar":
                raise HTTPException(
                    status_code=503,
                    detail="External servers require Kubernetes sidecar deployment"
                )

            result = await mcp_manager.sidecar_client.get_external_server_info(server_id)

            if result is None:
                raise HTTPException(status_code=404, detail=f"Server {server_id} not found")

            api_logger.debug(f"Retrieved external MCP server info - server_id={server_id}")

            return result

        except HTTPException:
            raise
        except Exception as e:
            api_logger.error(f"External MCP server info API failed - error={str(e)}")
            safe_set_attribute(span, "error", str(e))
            raise HTTPException(status_code=500, detail=str(e)) from e


# Server-specific streaming endpoints

@router.websocket("/servers/external/{server_id}/stream")
async def websocket_external_server_stream(websocket: WebSocket, server_id: str):
    """WebSocket endpoint for streaming from a specific external MCP server."""
    await websocket.accept()

    try:
        # Ensure manager is initialized (WebSockets can't use Depends())
        await mcp_manager._ensure_initialized()

        if mcp_manager._manager_type != "sidecar":
            await websocket.send_json({
                "type": "error",
                "message": "External servers require Kubernetes sidecar deployment"
            })
            return

        # Get server info
        server_info = await mcp_manager.sidecar_client.get_external_server_info(server_id)
        if not server_info:
            await websocket.send_json({
                "type": "error",
                "message": f"Server {server_id} not found"
            })
            return

        # Send connection info
        await websocket.send_json({
            "type": "connection",
            "message": f"Connected to {server_info.get('server_type', 'unknown')} server {server_id}",
            "server_info": server_info
        })

        # Keep connection alive and handle any incoming messages
        while True:
            try:
                await asyncio.sleep(1)
                # Send periodic ping
                await websocket.send_json({"type": "ping", "timestamp": datetime.now(datetime.timezone.utc).isoformat()})

                # In a real implementation, you would:
                # 1. Connect to the server's stdio/sse stream
                # 2. Forward messages bidirectionally
                # 3. Handle protocol conversion (stdio <-> websocket)

            except Exception as e:
                mcp_logger.error(f"Error in server stream {server_id}: {e}")
                break

    except WebSocketDisconnect:
        mcp_logger.info(f"WebSocket disconnected for server {server_id}")
    except Exception as e:
        mcp_logger.error(f"Error in external server stream endpoint: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@router.post("/servers/external/{server_id}/execute")
async def execute_tool_on_external_server(server_id: str, tool_request: dict, _: None = Depends(ensure_mcp_initialized)):
    """Execute a tool on a specific external MCP server."""
    with safe_span("api_execute_external_server_tool") as span:
        safe_set_attribute(span, "endpoint", "/mcp/servers/external/{server_id}/execute")
        safe_set_attribute(span, "method", "POST")
        safe_set_attribute(span, "server_id", server_id)
        safe_set_attribute(span, "tool_name", tool_request.get("tool_name"))

        try:
            # Manager is already initialized via dependency

            if mcp_manager._manager_type != "sidecar":
                raise HTTPException(
                    status_code=503,
                    detail="External servers require Kubernetes sidecar deployment"
                )

            # Validate server exists
            server_info = await mcp_manager.sidecar_client.get_external_server_info(server_id)
            if not server_info:
                raise HTTPException(status_code=404, detail=f"Server {server_id} not found")

            # For now, return a placeholder response
            # In a real implementation, you would:
            # 1. Connect to the server's communication channel
            # 2. Send the tool execution request
            # 3. Wait for and return the response

            result = {
                "success": True,
                "server_id": server_id,
                "tool_name": tool_request.get("tool_name"),
                "result": "Tool execution not yet implemented in sidecar",
                "message": "This is a placeholder response. Full tool execution will be implemented in the next phase."
            }

            api_logger.info(
                f"Tool execution request for server {server_id} - tool={tool_request.get('tool_name')}"
            )
            safe_set_attribute(span, "success", True)

            return result

        except HTTPException:
            raise
        except Exception as e:
            api_logger.error(f"External server tool execution failed - error={str(e)}")
            safe_set_attribute(span, "success", False)
            safe_set_attribute(span, "error", str(e))
            raise HTTPException(status_code=500, detail=str(e)) from e


# Registry and Package Management Endpoints

@router.get("/registry/templates")
async def get_mcp_server_templates(
    category: str = None,
    server_type: str = None,
    tags: list[str] = None
):
    """Get available MCP server templates."""
    with safe_span("api_get_mcp_templates") as span:
        safe_set_attribute(span, "endpoint", "/mcp/registry/templates")
        safe_set_attribute(span, "method", "GET")
        if category:
            safe_set_attribute(span, "category", category)
        if server_type:
            safe_set_attribute(span, "server_type", server_type)

        try:
            # Registry is already imported at the top

            registry = get_mcp_registry()
            templates = registry.list_templates(
                category=category,
                server_type=server_type,
                tags=tags
            )

            # Convert to JSON-serializable format
            template_data = []
            for template in templates:
                template_dict = {
                    "server_id": template.server_id,
                    "name": template.name,
                    "description": template.description,
                    "server_type": template.server_type,
                    "package": template.package,
                    "transport": template.transport,
                    "capabilities": [
                        {
                            "name": cap.name,
                            "description": cap.description,
                            "category": cap.category,
                            "parameters": cap.parameters
                        }
                        for cap in template.capabilities
                    ],
                    "tags": template.tags,
                    "documentation_url": template.documentation_url,
                    "author": template.author,
                    "license": template.license
                }
                template_data.append(template_dict)

            api_logger.debug(f"Retrieved {len(template_data)} MCP server templates")
            safe_set_attribute(span, "template_count", len(template_data))

            return {
                "templates": template_data,
                "count": len(template_data),
                "categories": registry.get_categories()
            }

        except Exception as e:
            api_logger.error(f"Failed to get MCP server templates - error={str(e)}")
            safe_set_attribute(span, "error", str(e))
            raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/registry/search")
async def search_mcp_packages(query: str, package_manager: str = "all", limit: int = 20):
    """Search for MCP packages across package managers."""
    with safe_span("api_search_mcp_packages") as span:
        safe_set_attribute(span, "endpoint", "/mcp/registry/search")
        safe_set_attribute(span, "method", "GET")
        safe_set_attribute(span, "query", query)
        safe_set_attribute(span, "package_manager", package_manager)
        safe_set_attribute(span, "limit", limit)

        try:
            # Package manager is already imported at the top

            package_mgr = get_package_manager()

            if package_manager == "all":
                results = await package_mgr.search_all_packages(query, limit)
            elif package_manager == "npm":
                npm_result = await package_mgr.search_npm_packages(query, limit)
                results = {"npm": npm_result}
            elif package_manager == "pypi":
                pypi_result = await package_mgr.search_pypi_packages(query, limit)
                results = {"pypi": pypi_result}
            else:
                raise HTTPException(status_code=400, detail="Invalid package manager")

            # Convert to JSON-serializable format
            search_results = {}
            total_packages = 0

            for pm_name, result in results.items():
                packages_data = []
                for pkg in result.packages:
                    pkg_dict = {
                        "name": pkg.name,
                        "version": pkg.version,
                        "description": pkg.description,
                        "author": pkg.author,
                        "repository": pkg.repository,
                        "license": pkg.license,
                        "keywords": pkg.keywords,
                        "mcp_version": pkg.mcp_version
                    }
                    packages_data.append(pkg_dict)

                search_results[pm_name] = {
                    "packages": packages_data,
                    "count": result.total_count,
                    "search_time_ms": result.search_time_ms,
                    "source": result.source
                }
                total_packages += result.total_count

            api_logger.debug(f"Package search completed - query={query}, total_packages={total_packages}")
            safe_set_attribute(span, "total_packages", total_packages)

            return {
                "query": query,
                "results": search_results,
                "total_packages": total_packages
            }

        except HTTPException:
            raise
        except Exception as e:
            api_logger.error(f"Package search failed - error={str(e)}")
            safe_set_attribute(span, "error", str(e))
            raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/tools")
async def get_mcp_tools():
    """Get available MCP tools by querying the running MCP server's registered tools."""
    with safe_span("api_get_mcp_tools") as span:
        safe_set_attribute(span, "endpoint", "/api/mcp/tools")
        safe_set_attribute(span, "method", "GET")

        try:
            api_logger.info("Getting MCP tools from registered server instance")

            # Check if server is running
            server_status = mcp_manager.get_status()
            is_running = server_status.get("status") == "running"
            safe_set_attribute(span, "server_running", is_running)

            if not is_running:
                api_logger.warning("MCP server not running when requesting tools")
                return {
                    "tools": [],
                    "count": 0,
                    "server_running": False,
                    "source": "server_not_running",
                    "message": "MCP server is not running. Start the server to see available tools.",
                }

            # SIMPLE DEBUG: Just check if we can see any tools at all
            try:
                # Try to inspect the process to see what tools exist
                api_logger.info("Debugging: Attempting to check MCP server tools")

                # For now, just return the known modules info since server is registering them
                # This will at least show the UI that tools exist while we debug the real issue
                if is_running:
                    return {
                        "tools": [
                            {
                                "name": "debug_placeholder",
                                "description": "MCP server is running and modules are registered, but tool introspection is not working yet",
                                "module": "debug",
                                "parameters": [],
                            }
                        ],
                        "count": 1,
                        "server_running": True,
                        "source": "debug_placeholder",
                        "message": "MCP server is running with 3 modules registered. Tool introspection needs to be fixed.",
                    }
                else:
                    return {
                        "tools": [],
                        "count": 0,
                        "server_running": False,
                        "source": "server_not_running",
                        "message": "MCP server is not running. Start the server to see available tools.",
                    }

            except Exception as e:
                api_logger.error("Failed to debug MCP server tools", error=str(e))

                return {
                    "tools": [],
                    "count": 0,
                    "server_running": is_running,
                    "source": "debug_error",
                    "message": f"Debug failed: {str(e)}",
                }

        except Exception as e:
            api_logger.error("Failed to get MCP tools", error=str(e))
            safe_set_attribute(span, "error", str(e))
            safe_set_attribute(span, "source", "general_error")

            return {
                "tools": [],
                "count": 0,
                "server_running": False,
                "source": "general_error",
                "message": f"Error retrieving MCP tools: {str(e)}",
            }


@router.get("/health")
async def mcp_health():
    """Health check for MCP API."""
    with safe_span("api_mcp_health") as span:
        safe_set_attribute(span, "endpoint", "/api/mcp/health")
        safe_set_attribute(span, "method", "GET")

        # Removed health check logging to reduce console noise
        result = {"status": "healthy", "service": "mcp"}
        safe_set_attribute(span, "status", "healthy")

        return result


