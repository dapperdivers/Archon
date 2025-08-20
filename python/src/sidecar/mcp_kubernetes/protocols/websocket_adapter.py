"""
WebSocket Protocol Adapter

This module provides the WebSocket protocol adapter for MCP communication.
"""

import asyncio
import json
from typing import Any

from ...config import mcp_logger
from .adapters import MCPMessage, ProtocolAdapter, ProtocolType


class WebSocketAdapter(ProtocolAdapter):
    """Protocol adapter for WebSocket communication."""

    def __init__(self, connection_id: str):
        super().__init__(connection_id)
        self.websocket: Any | None = None  # websockets.WebSocketServerProtocol

    async def connect(self, websocket) -> bool:
        """Connect with WebSocket."""
        self.websocket = websocket
        self.is_connected = True

        # Start message processing loop
        asyncio.create_task(self._process_websocket_messages())

        return True

    async def disconnect(self) -> None:
        """Disconnect WebSocket."""
        self.is_connected = False
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception:
                pass

    async def send_message(self, message: MCPMessage) -> bool:
        """Send message via WebSocket."""
        if not self.is_connected or not self.websocket:
            return False

        try:
            json_data = json.dumps(message.to_jsonrpc())
            await self.websocket.send(json_data)
            return True
        except Exception as e:
            mcp_logger.error(f"Error sending WebSocket message: {e}")
            return False

    async def receive_message(self, timeout: float = None) -> MCPMessage | None:
        """Receive message from WebSocket."""
        if not self.is_connected or not self.websocket:
            return None

        try:
            if timeout:
                data = await asyncio.wait_for(self.websocket.recv(), timeout=timeout)
            else:
                data = await self.websocket.recv()

            json_data = json.loads(data)
            message = MCPMessage.from_jsonrpc(json_data)
            message.protocol = ProtocolType.WEBSOCKET
            return message

        except TimeoutError:
            return None
        except json.JSONDecodeError as e:
            mcp_logger.error(f"Invalid JSON in WebSocket message: {e}")
            return None
        except Exception as e:
            mcp_logger.error(f"Error receiving WebSocket message: {e}")
            return None

    async def _process_websocket_messages(self):
        """Process incoming WebSocket messages."""
        while self.is_connected:
            try:
                message = await self.receive_message(timeout=1.0)
                if message:
                    await self.handle_incoming_message(message)
            except Exception as e:
                mcp_logger.error(f"Error processing WebSocket messages: {e}")
                await asyncio.sleep(1.0)

    async def send_binary(self, data: bytes) -> bool:
        """Send binary data via WebSocket."""
        if not self.is_connected or not self.websocket:
            return False

        try:
            await self.websocket.send(data)
            return True
        except Exception as e:
            mcp_logger.error(f"Error sending binary WebSocket data: {e}")
            return False

    async def receive_binary(self, timeout: float = None) -> bytes | None:
        """Receive binary data from WebSocket."""
        if not self.is_connected or not self.websocket:
            return None

        try:
            if timeout:
                data = await asyncio.wait_for(self.websocket.recv(), timeout=timeout)
            else:
                data = await self.websocket.recv()

            if isinstance(data, bytes):
                return data
            else:
                # Convert string to bytes if needed
                return data.encode('utf-8')

        except TimeoutError:
            return None
        except Exception as e:
            mcp_logger.error(f"Error receiving binary WebSocket data: {e}")
            return None

    async def ping(self) -> bool:
        """Send a WebSocket ping."""
        if not self.is_connected or not self.websocket:
            return False

        try:
            await self.websocket.ping()
            return True
        except Exception as e:
            mcp_logger.error(f"Error sending WebSocket ping: {e}")
            return False

    def get_connection_info(self) -> dict:
        """Get connection information."""
        ws_info = {}
        if self.websocket:
            try:
                ws_info = {
                    "remote_address": str(self.websocket.remote_address) if hasattr(self.websocket, 'remote_address') else None,
                    "local_address": str(self.websocket.local_address) if hasattr(self.websocket, 'local_address') else None,
                    "state": str(self.websocket.state) if hasattr(self.websocket, 'state') else None,
                    "path": str(self.websocket.path) if hasattr(self.websocket, 'path') else None
                }
            except Exception:
                pass

        return {
            "connection_id": self.connection_id,
            "protocol": "websocket",
            "is_connected": self.is_connected,
            "websocket_info": ws_info,
            "pending_requests": len(self.pending_requests),
            "message_queue_size": len(self.message_queue)
        }
