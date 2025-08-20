"""
MCP Protocol Adapters Module

Provides protocol adapters for different MCP communication methods.

This module supports:
- JSON-RPC over STDIO
- Server-Sent Events (SSE)
- WebSocket communication
- HTTP REST-style communication
- Protocol bridging and message routing

Components:
- adapters: Base adapter classes and factory
- stdio_adapter: STDIO-specific implementation
- sse_adapter: SSE-specific implementation
- websocket_adapter: WebSocket-specific implementation
"""

from .adapters import MCPMessage, MessageType, ProtocolAdapter, ProtocolType, create_adapter, get_protocol_bridge

__all__ = [
    "ProtocolAdapter",
    "ProtocolType",
    "MessageType",
    "MCPMessage",
    "create_adapter",
    "get_protocol_bridge"
]
