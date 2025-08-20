"""
MCP STDIO Module

Provides STDIO communication bridge with MCP servers via Kubernetes exec API.

This module handles:
- Bidirectional STDIO communication with pods
- JSON-RPC message processing
- Connection management and pooling
- Error handling and recovery

Components:
- bridge: Main STDIO bridge class
- exec_handler: Kubernetes exec API handling
"""

from .bridge import MCPStdioBridge

__all__ = [
    "MCPStdioBridge"
]
