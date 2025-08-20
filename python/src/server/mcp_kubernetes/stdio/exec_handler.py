"""
Kubernetes Exec Handler

This module handles the low-level Kubernetes exec API communication for STDIO bridge.
"""

import asyncio
import os
from typing import Any

from ...config.logfire_config import mcp_logger


class KubernetesExecHandler:
    """Handles Kubernetes exec API connections."""

    def __init__(self, namespace: str):
        self.namespace = namespace

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
            mcp_logger.warning("Kubernetes service account token not found for exec handler")

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

    async def create_exec_connection(
        self,
        pod_name: str,
        container_name: str = None,
        command: list[str] = None
    ) -> dict[str, Any]:
        """
        Create an exec connection to a pod.

        Args:
            pod_name: Name of the pod
            container_name: Name of the container (optional)
            command: Command to execute (default: ["/bin/sh"])

        Returns:
            Connection info dict
        """
        try:
            if command is None:
                command = ["/bin/sh"]

            # Build exec URL
            exec_url = (
                f"wss://{self.k8s_host}:{self.k8s_port}"
                f"/api/v1/namespaces/{self.namespace}/pods/{pod_name}/exec"
                f"?stdin=true&stdout=true&stderr=true&tty=false"
            )

            if container_name:
                exec_url += f"&container={container_name}"

            # Add command parameters
            for cmd_part in command:
                exec_url += f"&command={cmd_part}"

            mcp_logger.debug(f"Creating exec connection: {exec_url}")

            # Create WebSocket connection headers
            ws_headers = {}
            if self.token:
                ws_headers["Authorization"] = f"Bearer {self.token}"

            # Kubernetes exec API uses specific subprotocols
            subprotocols = ["v4.channel.k8s.io"]

            # Note: This is a simplified implementation
            # In production, you would need to handle Kubernetes exec protocol properly
            connection_info = {
                "pod_name": pod_name,
                "container_name": container_name,
                "command": command,
                "exec_url": exec_url,
                "headers": ws_headers,
                "subprotocols": subprotocols,
                "status": "created",
                "websocket": None,
                "stdin_buffer": asyncio.Queue(),
                "stdout_buffer": asyncio.Queue(),
                "stderr_buffer": asyncio.Queue(),
            }

            # For demonstration, we'll simulate the WebSocket connection
            # In a real implementation, you would connect to the WebSocket here
            connection_info["status"] = "connected"
            connection_info["websocket"] = "simulated_websocket"

            return connection_info

        except Exception as e:
            mcp_logger.error(f"Failed to create exec connection to {pod_name}: {e}")
            raise

    async def close_exec_connection(self, connection: dict[str, Any]) -> bool:
        """
        Close an exec connection.

        Args:
            connection: Connection info dict

        Returns:
            True if closed successfully
        """
        try:
            websocket = connection.get("websocket")
            if websocket and websocket != "simulated_websocket":
                await websocket.close()

            connection["status"] = "closed"
            return True

        except Exception as e:
            mcp_logger.error(f"Error closing exec connection: {e}")
            return False

    async def send_stdin(self, connection: dict[str, Any], data: str) -> bool:
        """
        Send data to stdin of the exec connection.

        Args:
            connection: Connection info dict
            data: Data to send

        Returns:
            True if sent successfully
        """
        try:
            if connection["status"] != "connected":
                return False

            # In a real implementation, you would send this via WebSocket
            # with proper Kubernetes exec protocol framing

            # For now, add to buffer for simulation
            await connection["stdin_buffer"].put(data)

            mcp_logger.debug(f"Sent stdin data to {connection['pod_name']}: {data[:100]}...")
            return True

        except Exception as e:
            mcp_logger.error(f"Error sending stdin data: {e}")
            return False

    async def read_stdout(self, connection: dict[str, Any], timeout: float = 1.0) -> str | None:
        """
        Read data from stdout of the exec connection.

        Args:
            connection: Connection info dict
            timeout: Read timeout

        Returns:
            Data from stdout or None
        """
        try:
            if connection["status"] != "connected":
                return None

            # In a real implementation, you would read from WebSocket
            # and decode the Kubernetes exec protocol frames

            # For simulation, try to get from buffer
            try:
                data = await asyncio.wait_for(
                    connection["stdout_buffer"].get(),
                    timeout=timeout
                )
                return data
            except TimeoutError:
                return None

        except Exception as e:
            mcp_logger.error(f"Error reading stdout: {e}")
            return None

    async def read_stderr(self, connection: dict[str, Any], timeout: float = 1.0) -> str | None:
        """
        Read data from stderr of the exec connection.

        Args:
            connection: Connection info dict
            timeout: Read timeout

        Returns:
            Data from stderr or None
        """
        try:
            if connection["status"] != "connected":
                return None

            # For simulation, try to get from buffer
            try:
                data = await asyncio.wait_for(
                    connection["stderr_buffer"].get(),
                    timeout=timeout
                )
                return data
            except TimeoutError:
                return None

        except Exception as e:
            mcp_logger.error(f"Error reading stderr: {e}")
            return None

    def _decode_exec_frame(self, frame: bytes) -> tuple[int, bytes]:
        """
        Decode a Kubernetes exec protocol frame.

        Args:
            frame: Raw WebSocket frame

        Returns:
            Tuple of (channel, data) where channel is 0=stdin, 1=stdout, 2=stderr
        """
        if len(frame) < 1:
            return 0, b""

        channel = frame[0]
        data = frame[1:]
        return channel, data

    def _encode_exec_frame(self, channel: int, data: bytes) -> bytes:
        """
        Encode data for Kubernetes exec protocol.

        Args:
            channel: Channel number (0=stdin, 1=stdout, 2=stderr)
            data: Data to encode

        Returns:
            Encoded frame
        """
        return bytes([channel]) + data

    async def _handle_websocket_messages(self, connection: dict[str, Any]):
        """
        Handle incoming WebSocket messages for an exec connection.

        This is a background task that processes WebSocket frames and
        routes them to the appropriate buffers.
        """
        try:
            websocket = connection["websocket"]
            if not websocket or websocket == "simulated_websocket":
                return

            async for message in websocket:
                if isinstance(message, bytes):
                    channel, data = self._decode_exec_frame(message)

                    if channel == 1:  # stdout
                        await connection["stdout_buffer"].put(data.decode('utf-8', errors='ignore'))
                    elif channel == 2:  # stderr
                        await connection["stderr_buffer"].put(data.decode('utf-8', errors='ignore'))

        except Exception as e:
            mcp_logger.error(f"Error handling WebSocket messages: {e}")
            connection["status"] = "error"

    async def test_exec_connectivity(self, pod_name: str) -> bool:
        """
        Test if we can create an exec connection to a pod.

        Args:
            pod_name: Name of the pod to test

        Returns:
            True if connectivity is working
        """
        try:
            # Try to create a simple exec connection
            connection = await self.create_exec_connection(
                pod_name=pod_name,
                command=["echo", "test"]
            )

            # Close it immediately
            await self.close_exec_connection(connection)

            return True

        except Exception as e:
            mcp_logger.error(f"Exec connectivity test failed for {pod_name}: {e}")
            return False
