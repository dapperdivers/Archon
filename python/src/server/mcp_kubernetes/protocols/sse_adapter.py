"""
SSE Protocol Adapter

This module provides the Server-Sent Events protocol adapter for MCP communication.
"""

import asyncio
import json
from typing import Any

from ...config.logfire_config import mcp_logger
from .adapters import MCPMessage, ProtocolAdapter, ProtocolType


class SSEAdapter(ProtocolAdapter):
    """Protocol adapter for Server-Sent Events."""

    def __init__(self, connection_id: str):
        super().__init__(connection_id)
        self.sse_url: str | None = None
        self.http_client: Any | None = None  # httpx.AsyncClient

    async def connect(self, sse_url: str, headers: dict[str, str] = None) -> bool:
        """Connect to SSE endpoint."""
        try:
            import httpx

            self.sse_url = sse_url
            self.http_client = httpx.AsyncClient(headers=headers or {})
            self.is_connected = True

            # Start SSE listening loop
            asyncio.create_task(self._listen_sse())

            return True
        except Exception as e:
            mcp_logger.error(f"Error connecting to SSE: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from SSE."""
        self.is_connected = False
        if self.http_client:
            await self.http_client.aclose()

    async def send_message(self, message: MCPMessage) -> bool:
        """Send message via HTTP POST."""
        if not self.is_connected or not self.http_client:
            return False

        try:
            # For SSE, we typically send via HTTP POST
            send_url = self.sse_url.replace("/events", "/send")
            if send_url == self.sse_url:
                # If URL doesn't contain /events, append /send
                send_url = self.sse_url.rstrip('/') + '/send'

            response = await self.http_client.post(
                send_url,
                json=message.to_jsonrpc()
            )
            return response.status_code == 200
        except Exception as e:
            mcp_logger.error(f"Error sending SSE message: {e}")
            return False

    async def receive_message(self, timeout: float = None) -> MCPMessage | None:
        """Receive message from SSE stream."""
        # For SSE, messages are typically received in the listening loop
        # This method could check a queue filled by the listener
        return None

    async def _listen_sse(self):
        """Listen to SSE stream."""
        if not self.http_client or not self.sse_url:
            return

        try:
            async with self.http_client.stream("GET", self.sse_url) as response:
                async for line in response.aiter_lines():
                    if not self.is_connected:
                        break

                    if line.startswith("data: "):
                        try:
                            data_str = line[6:]  # Remove "data: " prefix
                            data = json.loads(data_str)
                            message = MCPMessage.from_jsonrpc(data)
                            message.protocol = ProtocolType.SSE
                            await self.handle_incoming_message(message)
                        except json.JSONDecodeError:
                            continue
                        except Exception as e:
                            mcp_logger.error(f"Error processing SSE message: {e}")
        except Exception as e:
            mcp_logger.error(f"Error in SSE listener: {e}")
            self.is_connected = False

    async def send_event(self, event_type: str, data: dict) -> bool:
        """Send a custom SSE event."""
        if not self.is_connected or not self.http_client:
            return False

        try:
            event_data = {
                "event": event_type,
                "data": data
            }

            send_url = self.sse_url.replace("/events", "/send")
            if send_url == self.sse_url:
                send_url = self.sse_url.rstrip('/') + '/send'

            response = await self.http_client.post(send_url, json=event_data)
            return response.status_code == 200
        except Exception as e:
            mcp_logger.error(f"Error sending SSE event: {e}")
            return False

    def get_connection_info(self) -> dict:
        """Get connection information."""
        return {
            "connection_id": self.connection_id,
            "protocol": "sse",
            "is_connected": self.is_connected,
            "sse_url": self.sse_url,
            "pending_requests": len(self.pending_requests),
            "message_queue_size": len(self.message_queue)
        }
