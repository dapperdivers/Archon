"""
Kubernetes MCP Manager

Manages the main MCP server in Kubernetes environments where the MCP service
runs as a separate container in the same pod.
"""

import asyncio
import os
import time
from collections import deque
from datetime import datetime
from typing import Any

import httpx
from fastapi import WebSocket
from kubernetes import client, config
from kubernetes.client.rest import ApiException

from ..config.logfire_config import mcp_logger


class KubernetesMCPManager:
    """Manages the main MCP server in Kubernetes environments."""
    
    def __init__(self):
        self.mcp_url = self._get_mcp_url()
        self.status: str = "unknown"
        self.start_time: float | None = None
        self.logs: deque = deque(maxlen=1000)
        self.log_websockets: list[WebSocket] = []
        
        # Get pod info from environment
        self.pod_name = os.getenv("HOSTNAME", "unknown-pod")
        self.namespace = os.getenv("KUBERNETES_NAMESPACE", "default")
        self.mcp_container_name = "archon-mcp"  # Default MCP container name
        
        # Initialize Kubernetes client
        self.k8s_client = None
        self._initialize_k8s_client()
        
    def _initialize_k8s_client(self):
        """Initialize Kubernetes client for log access."""
        try:
            # Try to load in-cluster config first (for pods running in K8s)
            config.load_incluster_config()
            mcp_logger.info("Loaded in-cluster Kubernetes configuration")
        except Exception:
            try:
                # Fall back to local kubeconfig (for local development)
                config.load_kube_config()
                mcp_logger.info("Loaded local Kubernetes configuration")
            except Exception as e:
                mcp_logger.warning(f"Failed to initialize Kubernetes client: {e}")
                return
        
        self.k8s_client = client.CoreV1Api()
        mcp_logger.info("Kubernetes client initialized successfully")
    
    def _get_mcp_url(self) -> str:
        """Get the MCP service URL based on environment."""
        host = os.getenv("ARCHON_MCP_HOST", "localhost")
        port = os.getenv("ARCHON_MCP_PORT", "8051")
        return f"http://{host}:{port}"
    
    async def start_server(self) -> dict[str, Any]:
        """Start operation for MCP server (no-op in Kubernetes)."""
        mcp_logger.info("MCP start requested in Kubernetes mode")
        
        # In Kubernetes, containers start with the pod - we can't start them individually
        # Instead, check if the service is already running
        current_status = await self._check_mcp_health()
        
        if current_status.get("healthy", False):
            self._add_log("INFO", "MCP service is already running")
            self.status = "running"
            return {
                "success": True,
                "status": "running", 
                "message": "MCP service is already running in Kubernetes pod",
                "pod_name": self.pod_name,
                "namespace": self.namespace
            }
        else:
            self._add_log("WARNING", "MCP service appears to be unhealthy")
            self.status = "unhealthy"
            return {
                "success": False,
                "status": "unhealthy",
                "message": "MCP service is not responding - check pod logs",
                "pod_name": self.pod_name,
                "namespace": self.namespace
            }
    
    async def stop_server(self) -> dict[str, Any]:
        """Stop operation for MCP server (no-op in Kubernetes)."""
        mcp_logger.info("MCP stop requested in Kubernetes mode")
        
        self._add_log("INFO", "Stop requested - containers managed by Kubernetes")
        
        return {
            "success": True,
            "status": "kubernetes_managed",
            "message": "MCP server lifecycle is managed by Kubernetes. To stop, scale down the deployment.",
            "pod_name": self.pod_name,
            "namespace": self.namespace
        }
    
    def get_status(self) -> dict[str, Any]:
        """Get MCP server status in Kubernetes."""
        try:
            # Handle running async health check from sync method
            try:
                # Try to get the current event loop
                loop = asyncio.get_running_loop()
                # If we're in an event loop, create a task instead
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self._check_mcp_health())
                    health_result = future.result(timeout=10)
            except RuntimeError:
                # No event loop running, safe to use asyncio.run
                health_result = asyncio.run(self._check_mcp_health())
            
            if health_result.get("healthy", False):
                self.status = "running"
                uptime = health_result.get("uptime")
            else:
                self.status = "unhealthy" 
                uptime = None
                
            # Calculate pod uptime if available
            if not uptime and self.start_time:
                uptime = int(time.time() - self.start_time)
            
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
                "deployment_mode": "kubernetes",
                "pod_name": self.pod_name,
                "namespace": self.namespace,
                "mcp_url": self.mcp_url,
                "health_check": health_result
            }
            
        except Exception as e:
            mcp_logger.error(f"Error getting Kubernetes MCP status: {e}")
            return {
                "status": "error",
                "uptime": None,
                "logs": [f"Error getting status: {str(e)}"],
                "deployment_mode": "kubernetes",
                "pod_name": self.pod_name,
                "namespace": self.namespace,
                "error": str(e)
            }
    
    async def _check_mcp_health(self) -> dict[str, Any]:
        """Check MCP service health via direct HTTP call."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Try to connect to the MCP service endpoint
                # Since it's MCP protocol, we can try a simple GET to see if it responds
                response = await client.get(f"{self.mcp_url}/", timeout=5.0)
                
                if response.status_code in [200, 404, 405]:
                    # 200 = OK, 404/405 = Server is running but endpoint doesn't exist (which is fine for MCP)
                    return {
                        "healthy": True,
                        "status_code": response.status_code,
                        "response_time_ms": response.elapsed.total_seconds() * 1000 if response.elapsed else None,
                        "method": "http_check"
                    }
                else:
                    return {
                        "healthy": False,
                        "status_code": response.status_code,
                        "error": f"HTTP {response.status_code}",
                        "method": "http_check"
                    }
                    
        except httpx.ConnectError:
            # Try TCP connection as fallback
            return await self._check_tcp_connection()
            
        except httpx.TimeoutException:
            return {
                "healthy": False,
                "error": "Timeout connecting to MCP service",
                "method": "http_check"
            }
            
        except Exception as e:
            mcp_logger.error(f"Health check error: {e}")
            return {
                "healthy": False,
                "error": str(e),
                "method": "http_check"
            }
    
    async def _check_tcp_connection(self) -> dict[str, Any]:
        """Fallback TCP connection check."""
        try:
            # Extract host and port from URL
            host = "localhost"  # In same pod
            port = int(os.getenv("ARCHON_MCP_PORT", "8051"))
            
            # Try TCP connection
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=5.0
            )
            writer.close()
            await writer.wait_closed()
            
            return {
                "healthy": True,
                "method": "tcp_check",
                "host": host,
                "port": port
            }
            
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e),
                "method": "tcp_check",
                "host": host,
                "port": port
            }
    
    def _add_log(self, level: str, message: str):
        """Add a log entry and broadcast to WebSockets."""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "message": message,
        }
        self.logs.append(log_entry)
        
        # Broadcast to WebSockets
        asyncio.create_task(self._broadcast_log(log_entry))
    
    async def _broadcast_log(self, log_entry: dict[str, Any]):
        """Broadcast log entry to connected WebSockets."""
        disconnected = []
        for ws in self.log_websockets:
            try:
                await ws.send_json(log_entry)
            except Exception:
                disconnected.append(ws)
        
        # Remove disconnected WebSockets  
        for ws in disconnected:
            self.log_websockets.remove(ws)
    
    async def _fetch_mcp_container_logs(self, lines: int = 100, server_id: str | None = None) -> list[dict[str, Any]]:
        """Fetch logs from the MCP container or a specific external server pod."""
        if not self.k8s_client:
            mcp_logger.warning("Kubernetes client not available for log fetching")
            return []
        
        try:
            if server_id is None:
                # Get logs from the main MCP container in the same pod
                log_response = self.k8s_client.read_namespaced_pod_log(
                    name=self.pod_name,
                    namespace=self.namespace,
                    container=self.mcp_container_name,
                    tail_lines=lines,
                    timestamps=True
                )
            else:
                # Get logs from external server pod
                # External servers are typically deployed as separate pods with predictable names
                external_pod_name = f"mcp-{server_id}"
                try:
                    log_response = self.k8s_client.read_namespaced_pod_log(
                        name=external_pod_name,
                        namespace=self.namespace,
                        tail_lines=lines,
                        timestamps=True
                    )
                except ApiException as e:
                    if e.status == 404:
                        # Try alternative naming convention
                        external_pod_name = f"archon-mcp-{server_id}"
                        log_response = self.k8s_client.read_namespaced_pod_log(
                            name=external_pod_name,
                            namespace=self.namespace,
                            tail_lines=lines,
                            timestamps=True
                        )
                    else:
                        raise
            
            # Parse log lines into structured format
            log_entries = []
            for line in log_response.strip().split('\n'):
                if not line:
                    continue
                    
                # Parse Kubernetes log format: timestamp container_log_content
                try:
                    # Split on first space to separate timestamp from log content
                    parts = line.split(' ', 1)
                    if len(parts) >= 2:
                        timestamp_str = parts[0]
                        message = parts[1]
                        
                        # Determine log level from message content
                        level = self._parse_log_level(message)
                        
                        log_entries.append({
                            "timestamp": timestamp_str,
                            "level": level,
                            "message": message
                        })
                    else:
                        # If we can't parse timestamp, use current time
                        log_entries.append({
                            "timestamp": datetime.utcnow().isoformat() + "Z",
                            "level": "INFO",
                            "message": line
                        })
                except Exception as e:
                    mcp_logger.debug(f"Failed to parse log line '{line}': {e}")
                    # Add the raw line as a fallback
                    log_entries.append({
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "level": "INFO", 
                        "message": line
                    })
            
            return log_entries
            
        except ApiException as e:
            if e.status == 404:
                mcp_logger.info(f"MCP container '{self.mcp_container_name}' not found in pod '{self.pod_name}'")
            else:
                mcp_logger.error(f"Failed to fetch MCP container logs: {e}")
            return []
        except Exception as e:
            mcp_logger.error(f"Error fetching MCP container logs: {e}")
            return []
    
    def _parse_log_level(self, message: str) -> str:
        """Parse log level from message content."""
        message_lower = message.lower()
        if any(word in message_lower for word in ["error", "exception", "failed", "critical"]):
            return "ERROR"
        elif any(word in message_lower for word in ["warning", "warn"]):
            return "WARNING"
        elif any(word in message_lower for word in ["debug"]):
            return "DEBUG"
        else:
            return "INFO"
    
    def get_logs(self, limit: int = 100, server_id: str | None = None) -> list[dict[str, Any]]:
        """Get historical logs from both internal buffer and MCP container or external server."""
        # For external servers, skip internal logs since they're not relevant
        if server_id is not None:
            internal_logs = []
        else:
            # Get internal logs (status messages) for main MCP server
            internal_logs = list(self.logs)
        
        # Try to get actual container logs synchronously
        try:
            # Use the existing event loop if available, otherwise create new one
            try:
                loop = asyncio.get_running_loop()
                # If we're in an event loop, use run_in_executor to avoid blocking
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(self._run_fetch_logs, limit, server_id)
                    container_logs = future.result(timeout=10)
            except RuntimeError:
                # No event loop running, safe to use asyncio.run
                container_logs = asyncio.run(self._fetch_mcp_container_logs(limit, server_id))
            
            # Combine internal logs with container logs
            all_logs = internal_logs + container_logs
            
            # Sort by timestamp if possible
            try:
                all_logs.sort(key=lambda x: x.get("timestamp", ""))
            except Exception:
                # If sorting fails, just use the combined list as-is
                pass
                
            # Apply limit
            if limit > 0:
                all_logs = all_logs[-limit:]
                
            return all_logs
            
        except Exception as e:
            if server_id:
                mcp_logger.warning(f"Failed to fetch logs for server {server_id}: {e}")
                return []  # No fallback for external servers
            else:
                mcp_logger.warning(f"Failed to fetch container logs, returning internal logs only: {e}")
                # Fall back to internal logs only for main server
                if limit > 0:
                    internal_logs = internal_logs[-limit:]
                return internal_logs
    
    def _run_fetch_logs(self, limit: int, server_id: str | None = None) -> list[dict[str, Any]]:
        """Helper method to run async log fetching in a new event loop."""
        return asyncio.run(self._fetch_mcp_container_logs(limit, server_id))
    
    def clear_logs(self):
        """Clear the log buffer."""
        self.logs.clear()
        self._add_log("INFO", "Logs cleared")
    
    async def add_websocket(self, websocket: WebSocket):
        """Add WebSocket for log streaming."""
        await websocket.accept()
        self.log_websockets.append(websocket)
        
        # Send connection info
        await websocket.send_json({
            "type": "connection",
            "message": f"WebSocket connected to Kubernetes MCP manager (pod: {self.pod_name})",
        })
        
        # Send recent logs from the container to initialize the stream
        # Note: For now, WebSocket only supports main MCP server
        # External server streaming would need separate WebSocket endpoints
        if self.k8s_client:
            try:
                recent_logs = await self._fetch_mcp_container_logs(20)  # Get last 20 lines
                for log in recent_logs:
                    await websocket.send_json(log)
            except Exception as e:
                mcp_logger.debug(f"Failed to send initial logs to WebSocket: {e}")
    
    def remove_websocket(self, websocket: WebSocket):
        """Remove WebSocket connection."""
        if websocket in self.log_websockets:
            self.log_websockets.remove(websocket)