"""
MCP STDIO Bridge for Kubernetes

This module provides bidirectional communication with MCP servers running in Kubernetes pods
using the Kubernetes exec API. It handles stdin/stdout/stderr streams for stdio-based MCP servers.
"""

import asyncio
import json
import os
import traceback
from collections import deque
from collections.abc import Callable
from datetime import datetime

from ...config.logfire_config import mcp_logger
from .exec_handler import KubernetesExecHandler


class MCPStdioBridge:
    """Bridge for stdio communication with MCP servers in Kubernetes pods."""

    def __init__(self, namespace: str = None, timeout: float = 30.0):
        self.namespace = namespace or os.getenv("KUBERNETES_NAMESPACE", "default")
        self.timeout = timeout
        self.active_connections: dict[str, dict] = {}
        self.message_handlers: dict[str, Callable] = {}

        # Initialize exec handler
        self.exec_handler = KubernetesExecHandler(self.namespace)

    async def create_stdio_connection(self, pod_name: str, container_name: str = None) -> str:
        """
        Create a stdio connection to a pod using Kubernetes exec API.

        Args:
            pod_name: Name of the pod to connect to
            container_name: Name of the container (optional, uses first container if not specified)

        Returns:
            Connection ID for managing the connection
        """
        try:
            # Generate unique connection ID
            connection_id = f"{pod_name}-{int(asyncio.get_event_loop().time())}"

            mcp_logger.info(f"Creating stdio connection to pod {pod_name}")

            # Create connection using exec handler
            exec_connection = await self.exec_handler.create_exec_connection(
                pod_name=pod_name,
                container_name=container_name,
                command=["/bin/sh"]  # Interactive shell for MCP communication
            )

            connection_info = {
                "connection_id": connection_id,
                "pod_name": pod_name,
                "container_name": container_name,
                "exec_connection": exec_connection,
                "status": "connected",
                "created_at": datetime.utcnow().isoformat(),
                "message_queue": deque(maxlen=1000),
                "stdin_queue": asyncio.Queue(),
                "stdout_queue": asyncio.Queue(),
                "stderr_queue": asyncio.Queue(),
            }

            # Store the connection
            self.active_connections[connection_id] = connection_info

            # Start message processing task
            asyncio.create_task(self._process_connection_messages(connection_id))

            mcp_logger.info(f"STDIO connection {connection_id} created successfully")
            return connection_id

        except Exception as e:
            mcp_logger.error(f"Failed to create stdio connection to pod {pod_name}: {e}")
            mcp_logger.error(traceback.format_exc())
            raise

    async def close_stdio_connection(self, connection_id: str) -> bool:
        """
        Close a stdio connection.

        Args:
            connection_id: ID of the connection to close

        Returns:
            True if connection was closed successfully
        """
        try:
            if connection_id not in self.active_connections:
                mcp_logger.warning(f"Connection {connection_id} not found")
                return False

            connection_info = self.active_connections[connection_id]

            # Close the exec connection
            exec_connection = connection_info.get("exec_connection")
            if exec_connection:
                await self.exec_handler.close_exec_connection(exec_connection)

            # Remove from active connections
            del self.active_connections[connection_id]

            mcp_logger.info(f"STDIO connection {connection_id} closed")
            return True

        except Exception as e:
            mcp_logger.error(f"Error closing connection {connection_id}: {e}")
            return False

    async def send_message(self, connection_id: str, message: dict) -> bool:
        """
        Send a JSON-RPC message via stdin to the connected MCP server.

        Args:
            connection_id: ID of the connection
            message: JSON-RPC message to send

        Returns:
            True if message was sent successfully
        """
        try:
            if connection_id not in self.active_connections:
                mcp_logger.error(f"Connection {connection_id} not found")
                return False

            connection_info = self.active_connections[connection_id]

            if connection_info["status"] != "connected":
                mcp_logger.error(f"Connection {connection_id} is not connected")
                return False

            # Convert message to JSON string with newline
            json_message = json.dumps(message) + "\n"

            # Send via stdin queue
            await connection_info["stdin_queue"].put(json_message)

            # Also send via exec handler
            exec_connection = connection_info["exec_connection"]
            await self.exec_handler.send_stdin(exec_connection, json_message)

            mcp_logger.debug(f"Sent message to {connection_id}: {message.get('method', 'response')}")
            return True

        except Exception as e:
            mcp_logger.error(f"Error sending message to {connection_id}: {e}")
            return False

    async def receive_message(self, connection_id: str, timeout: float = None) -> dict | None:
        """
        Receive a JSON-RPC message from stdout of the connected MCP server.

        Args:
            connection_id: ID of the connection
            timeout: Timeout in seconds (uses default if not specified)

        Returns:
            Parsed JSON-RPC message or None if timeout/error
        """
        try:
            if connection_id not in self.active_connections:
                mcp_logger.error(f"Connection {connection_id} not found")
                return None

            connection_info = self.active_connections[connection_id]

            if connection_info["status"] != "connected":
                mcp_logger.error(f"Connection {connection_id} is not connected")
                return None

            timeout = timeout or self.timeout

            # Try to get message from queue
            try:
                message_str = await asyncio.wait_for(
                    connection_info["stdout_queue"].get(),
                    timeout=timeout
                )

                # Parse JSON message
                message = json.loads(message_str.strip())

                mcp_logger.debug(f"Received message from {connection_id}: {message.get('method', 'response')}")
                return message

            except TimeoutError:
                mcp_logger.debug(f"Timeout waiting for message from {connection_id}")
                return None

        except json.JSONDecodeError as e:
            mcp_logger.error(f"Invalid JSON received from {connection_id}: {e}")
            return None
        except Exception as e:
            mcp_logger.error(f"Error receiving message from {connection_id}: {e}")
            return None

    async def _process_connection_messages(self, connection_id: str):
        """
        Background task to process messages for a connection.

        Args:
            connection_id: ID of the connection to process
        """
        try:
            connection_info = self.active_connections.get(connection_id)
            if not connection_info:
                return

            exec_connection = connection_info["exec_connection"]

            # Start stdout/stderr reading tasks
            asyncio.create_task(self._read_stdout(connection_id, exec_connection))
            asyncio.create_task(self._read_stderr(connection_id, exec_connection))

        except Exception as e:
            mcp_logger.error(f"Error processing messages for {connection_id}: {e}")

    async def _read_stdout(self, connection_id: str, exec_connection: dict):
        """Read stdout from exec connection."""
        try:
            while connection_id in self.active_connections:
                try:
                    # Read stdout data
                    data = await self.exec_handler.read_stdout(exec_connection, timeout=1.0)
                    if data:
                        # Split by lines and add to queue
                        lines = data.strip().split('\n')
                        connection_info = self.active_connections.get(connection_id)
                        if connection_info:
                            for line in lines:
                                if line.strip():
                                    await connection_info["stdout_queue"].put(line)
                    else:
                        # No data, short sleep to prevent busy waiting
                        await asyncio.sleep(0.1)

                except TimeoutError:
                    continue
                except Exception as e:
                    mcp_logger.error(f"Error reading stdout for {connection_id}: {e}")
                    break

        except Exception as e:
            mcp_logger.error(f"Stdout reader for {connection_id} failed: {e}")

    async def _read_stderr(self, connection_id: str, exec_connection: dict):
        """Read stderr from exec connection."""
        try:
            while connection_id in self.active_connections:
                try:
                    # Read stderr data
                    data = await self.exec_handler.read_stderr(exec_connection, timeout=1.0)
                    if data:
                        mcp_logger.warning(f"stderr from {connection_id}: {data}")
                        connection_info = self.active_connections.get(connection_id)
                        if connection_info:
                            await connection_info["stderr_queue"].put(data)
                    else:
                        await asyncio.sleep(0.1)

                except TimeoutError:
                    continue
                except Exception as e:
                    mcp_logger.error(f"Error reading stderr for {connection_id}: {e}")
                    break

        except Exception as e:
            mcp_logger.error(f"Stderr reader for {connection_id} failed: {e}")

    def register_message_handler(self, method: str, handler: Callable):
        """
        Register a handler for a specific JSON-RPC method.

        Args:
            method: JSON-RPC method name
            handler: Async callable to handle the method
        """
        self.message_handlers[method] = handler

    async def send_request(self, connection_id: str, method: str, params: dict = None, timeout: float = None) -> dict | None:
        """
        Send a JSON-RPC request and wait for response.

        Args:
            connection_id: ID of the connection
            method: JSON-RPC method name
            params: Method parameters
            timeout: Response timeout

        Returns:
            Response message or None if timeout/error
        """
        import uuid

        request_id = str(uuid.uuid4())
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method
        }

        if params:
            request["params"] = params

        # Send request
        success = await self.send_message(connection_id, request)
        if not success:
            return None

        # Wait for response with matching ID
        timeout = timeout or self.timeout
        start_time = asyncio.get_event_loop().time()

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            response = await self.receive_message(connection_id, timeout=1.0)
            if response and response.get("id") == request_id:
                return response

        mcp_logger.warning(f"Timeout waiting for response to {method} on {connection_id}")
        return None

    async def send_notification(self, connection_id: str, method: str, params: dict = None) -> bool:
        """
        Send a JSON-RPC notification (no response expected).

        Args:
            connection_id: ID of the connection
            method: JSON-RPC method name
            params: Method parameters

        Returns:
            True if notification was sent successfully
        """
        notification = {
            "jsonrpc": "2.0",
            "method": method
        }

        if params:
            notification["params"] = params

        return await self.send_message(connection_id, notification)

    def get_connection_status(self, connection_id: str) -> dict | None:
        """
        Get status information for a connection.

        Args:
            connection_id: ID of the connection

        Returns:
            Connection status dict or None if not found
        """
        connection_info = self.active_connections.get(connection_id)
        if not connection_info:
            return None

        return {
            "connection_id": connection_id,
            "pod_name": connection_info["pod_name"],
            "container_name": connection_info["container_name"],
            "status": connection_info["status"],
            "created_at": connection_info["created_at"],
            "message_queue_size": len(connection_info["message_queue"]),
            "stdin_queue_size": connection_info["stdin_queue"].qsize(),
            "stdout_queue_size": connection_info["stdout_queue"].qsize(),
            "stderr_queue_size": connection_info["stderr_queue"].qsize(),
        }

    def list_connections(self) -> list[dict]:
        """
        List all active connections.

        Returns:
            List of connection status dicts
        """
        return [
            self.get_connection_status(conn_id)
            for conn_id in self.active_connections.keys()
        ]

    async def cleanup_connections(self):
        """Close all active connections."""
        connection_ids = list(self.active_connections.keys())
        for connection_id in connection_ids:
            await self.close_stdio_connection(connection_id)


# Global bridge instance
_stdio_bridge: MCPStdioBridge | None = None


def get_stdio_bridge(namespace: str = None) -> MCPStdioBridge:
    """Get the global STDIO bridge instance."""
    global _stdio_bridge
    if _stdio_bridge is None:
        _stdio_bridge = MCPStdioBridge(namespace=namespace)
    return _stdio_bridge
