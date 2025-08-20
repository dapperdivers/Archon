"""
STDIO Protocol Adapter

This module provides the STDIO protocol adapter for MCP communication.
"""

import asyncio
import json

from ...config.logfire_config import mcp_logger
from .adapters import MCPMessage, ProtocolAdapter, ProtocolType


class StdioAdapter(ProtocolAdapter):
    """Protocol adapter for stdio communication."""

    def __init__(self, connection_id: str):
        super().__init__(connection_id)
        self.stdin_queue: asyncio.Queue | None = None
        self.stdout_queue: asyncio.Queue | None = None
        self.stderr_queue: asyncio.Queue | None = None

    async def connect(self, stdin_queue: asyncio.Queue, stdout_queue: asyncio.Queue,
                     stderr_queue: asyncio.Queue = None) -> bool:
        """Connect with provided queues."""
        self.stdin_queue = stdin_queue
        self.stdout_queue = stdout_queue
        self.stderr_queue = stderr_queue
        self.is_connected = True

        # Start message processing loop
        asyncio.create_task(self._process_messages())

        return True

    async def disconnect(self) -> None:
        """Disconnect."""
        self.is_connected = False

    async def send_message(self, message: MCPMessage) -> bool:
        """Send message via stdin."""
        if not self.is_connected or not self.stdin_queue:
            return False

        try:
            json_data = json.dumps(message.to_jsonrpc())
            await self.stdin_queue.put(json_data + "\\n")
            return True
        except Exception as e:
            mcp_logger.error(f"Error sending stdio message: {e}")
            return False

    async def receive_message(self, timeout: float = None) -> MCPMessage | None:
        """Receive message from stdout."""
        if not self.is_connected or not self.stdout_queue:
            return None

        try:
            if timeout:
                line = await asyncio.wait_for(self.stdout_queue.get(), timeout=timeout)
            else:
                line = await self.stdout_queue.get()

            # Parse JSON-RPC message
            data = json.loads(line.strip())
            message = MCPMessage.from_jsonrpc(data)
            message.protocol = ProtocolType.STDIO
            return message

        except TimeoutError:
            return None
        except json.JSONDecodeError as e:
            mcp_logger.error(f"Invalid JSON in stdio message: {e}")
            return None
        except Exception as e:
            mcp_logger.error(f"Error receiving stdio message: {e}")
            return None

    async def _process_messages(self):
        """Process incoming messages."""
        while self.is_connected:
            try:
                message = await self.receive_message(timeout=1.0)
                if message:
                    await self.handle_incoming_message(message)
            except Exception as e:
                mcp_logger.error(f"Error processing stdio messages: {e}")
                await asyncio.sleep(1.0)

    async def send_raw_data(self, data: str) -> bool:
        """Send raw data to stdin (for direct communication)."""
        if not self.is_connected or not self.stdin_queue:
            return False

        try:
            await self.stdin_queue.put(data)
            return True
        except Exception as e:
            mcp_logger.error(f"Error sending raw stdio data: {e}")
            return False

    async def receive_raw_data(self, timeout: float = None) -> str | None:
        """Receive raw data from stdout."""
        if not self.is_connected or not self.stdout_queue:
            return None

        try:
            if timeout:
                data = await asyncio.wait_for(self.stdout_queue.get(), timeout=timeout)
            else:
                data = await self.stdout_queue.get()
            return data
        except TimeoutError:
            return None
        except Exception as e:
            mcp_logger.error(f"Error receiving raw stdio data: {e}")
            return None

    def get_connection_info(self) -> dict:
        """Get connection information."""
        return {
            "connection_id": self.connection_id,
            "protocol": "stdio",
            "is_connected": self.is_connected,
            "stdin_queue_size": self.stdin_queue.qsize() if self.stdin_queue else 0,
            "stdout_queue_size": self.stdout_queue.qsize() if self.stdout_queue else 0,
            "stderr_queue_size": self.stderr_queue.qsize() if self.stderr_queue else 0,
            "pending_requests": len(self.pending_requests),
            "message_queue_size": len(self.message_queue)
        }
