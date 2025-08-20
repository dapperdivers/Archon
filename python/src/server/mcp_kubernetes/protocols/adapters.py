"""
MCP Protocol Adapters

This module provides the base classes and factory for different MCP communication protocols.
"""

import asyncio
import json
import uuid
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from ...config.logfire_config import mcp_logger


class ProtocolType(Enum):
    """Supported MCP protocol types."""
    STDIO = "stdio"
    SSE = "sse"
    WEBSOCKET = "websocket"
    HTTP = "http"


class MessageType(Enum):
    """MCP message types."""
    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"
    ERROR = "error"


@dataclass
class MCPMessage:
    """Represents an MCP protocol message."""
    id: str
    type: MessageType
    method: str | None = None
    params: dict[str, Any] | None = None
    result: Any | None = None
    error: dict[str, Any] | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    protocol: ProtocolType | None = None

    def to_jsonrpc(self) -> dict[str, Any]:
        """Convert to JSON-RPC format."""
        message = {
            "jsonrpc": "2.0",
            "id": self.id
        }

        if self.type == MessageType.REQUEST:
            message["method"] = self.method
            if self.params:
                message["params"] = self.params
        elif self.type == MessageType.RESPONSE:
            if self.error:
                message["error"] = self.error
            else:
                message["result"] = self.result
        elif self.type == MessageType.NOTIFICATION:
            message["method"] = self.method
            if self.params:
                message["params"] = self.params
            # Notifications don't have an id
            del message["id"]

        return message

    @classmethod
    def from_jsonrpc(cls, data: dict[str, Any]) -> "MCPMessage":
        """Create from JSON-RPC format."""
        msg_id = data.get("id", str(uuid.uuid4()))

        if "method" in data:
            if "id" in data:
                msg_type = MessageType.REQUEST
            else:
                msg_type = MessageType.NOTIFICATION

            return cls(
                id=msg_id,
                type=msg_type,
                method=data["method"],
                params=data.get("params"),
                protocol=ProtocolType.STDIO
            )
        else:
            # Response message
            return cls(
                id=msg_id,
                type=MessageType.RESPONSE,
                result=data.get("result"),
                error=data.get("error"),
                protocol=ProtocolType.STDIO
            )

    def to_sse(self) -> str:
        """Convert to Server-Sent Events format."""
        data = self.to_jsonrpc()
        return f"data: {json.dumps(data)}\\n\\n"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "id": self.id,
            "type": self.type.value,
            "method": self.method,
            "params": self.params,
            "result": self.result,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
            "protocol": self.protocol.value if self.protocol else None
        }


class ProtocolAdapter(ABC):
    """Abstract base class for protocol adapters."""

    def __init__(self, connection_id: str):
        self.connection_id = connection_id
        self.message_handlers: dict[str, Callable] = {}
        self.pending_requests: dict[str, asyncio.Future] = {}
        self.message_queue: deque = deque(maxlen=1000)
        self.is_connected = False

    @abstractmethod
    async def connect(self, **kwargs) -> bool:
        """Establish connection."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection."""
        pass

    @abstractmethod
    async def send_message(self, message: MCPMessage) -> bool:
        """Send a message."""
        pass

    @abstractmethod
    async def receive_message(self, timeout: float = None) -> MCPMessage | None:
        """Receive a message."""
        pass

    def register_handler(self, method: str, handler: Callable):
        """Register a message handler for a specific method."""
        self.message_handlers[method] = handler

    async def send_request(self, method: str, params: dict[str, Any] = None, timeout: float = 30.0) -> Any:
        """Send a request and wait for response."""
        request_id = str(uuid.uuid4())
        request = MCPMessage(
            id=request_id,
            type=MessageType.REQUEST,
            method=method,
            params=params
        )

        # Create future for response
        future = asyncio.Future()
        self.pending_requests[request_id] = future

        try:
            # Send request
            success = await self.send_message(request)
            if not success:
                raise Exception("Failed to send request")

            # Wait for response
            response = await asyncio.wait_for(future, timeout=timeout)
            return response

        except TimeoutError:
            self.pending_requests.pop(request_id, None)
            raise
        except Exception:
            self.pending_requests.pop(request_id, None)
            raise

    async def send_notification(self, method: str, params: dict[str, Any] = None) -> bool:
        """Send a notification (no response expected)."""
        notification = MCPMessage(
            id="",  # Notifications don't have IDs
            type=MessageType.NOTIFICATION,
            method=method,
            params=params
        )

        return await self.send_message(notification)

    async def handle_incoming_message(self, message: MCPMessage):
        """Handle an incoming message."""
        self.message_queue.append(message)

        if message.type == MessageType.REQUEST:
            await self._handle_request(message)
        elif message.type == MessageType.RESPONSE:
            await self._handle_response(message)
        elif message.type == MessageType.NOTIFICATION:
            await self._handle_notification(message)

    async def _handle_request(self, message: MCPMessage):
        """Handle incoming request."""
        method = message.method
        if method in self.message_handlers:
            try:
                result = await self.message_handlers[method](message.params or {})

                # Send response
                response = MCPMessage(
                    id=message.id,
                    type=MessageType.RESPONSE,
                    result=result
                )
                await self.send_message(response)

            except Exception as e:
                # Send error response
                error_response = MCPMessage(
                    id=message.id,
                    type=MessageType.RESPONSE,
                    error={
                        "code": -32603,
                        "message": f"Internal error: {str(e)}"
                    }
                )
                await self.send_message(error_response)
        else:
            # Method not found
            error_response = MCPMessage(
                id=message.id,
                type=MessageType.RESPONSE,
                error={
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
            )
            await self.send_message(error_response)

    async def _handle_response(self, message: MCPMessage):
        """Handle incoming response."""
        request_id = message.id
        future = self.pending_requests.pop(request_id, None)

        if future and not future.done():
            if message.error:
                future.set_exception(Exception(f"RPC Error: {message.error}"))
            else:
                future.set_result(message.result)

    async def _handle_notification(self, message: MCPMessage):
        """Handle incoming notification."""
        method = message.method
        if method in self.message_handlers:
            try:
                await self.message_handlers[method](message.params or {})
            except Exception as e:
                mcp_logger.error(f"Error handling notification {method}: {e}")


class ProtocolBridge:
    """Bridge between different MCP protocols."""

    def __init__(self):
        self.adapters: dict[str, ProtocolAdapter] = {}
        self.bridges: dict[str, list[str]] = {}  # source -> [targets]

    def add_adapter(self, adapter_id: str, adapter: ProtocolAdapter):
        """Add a protocol adapter."""
        self.adapters[adapter_id] = adapter

    def create_bridge(self, source_adapter_id: str, target_adapter_ids: list[str]):
        """Create a bridge from source to target adapters."""
        self.bridges[source_adapter_id] = target_adapter_ids

        # Set up message forwarding
        source_adapter = self.adapters[source_adapter_id]
        source_adapter.register_handler("*", self._forward_message)

    async def _forward_message(self, source_adapter_id: str, message: MCPMessage):
        """Forward message from source to target adapters."""
        target_ids = self.bridges.get(source_adapter_id, [])

        for target_id in target_ids:
            target_adapter = self.adapters.get(target_id)
            if target_adapter:
                try:
                    await target_adapter.send_message(message)
                except Exception as e:
                    mcp_logger.error(f"Error forwarding message to {target_id}: {e}")


def create_adapter(protocol_type: ProtocolType, connection_id: str) -> ProtocolAdapter:
    """Factory function to create protocol adapters."""
    if protocol_type == ProtocolType.STDIO:
        from .stdio_adapter import StdioAdapter
        return StdioAdapter(connection_id)
    elif protocol_type == ProtocolType.SSE:
        from .sse_adapter import SSEAdapter
        return SSEAdapter(connection_id)
    elif protocol_type == ProtocolType.WEBSOCKET:
        from .websocket_adapter import WebSocketAdapter
        return WebSocketAdapter(connection_id)
    else:
        raise ValueError(f"Unsupported protocol type: {protocol_type}")


# Global protocol bridge instance
_protocol_bridge: ProtocolBridge | None = None


def get_protocol_bridge() -> ProtocolBridge:
    """Get the global protocol bridge instance."""
    global _protocol_bridge
    if _protocol_bridge is None:
        _protocol_bridge = ProtocolBridge()
    return _protocol_bridge
