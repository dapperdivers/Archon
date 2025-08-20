"""
Sidecar Configuration

Simplified configuration for the MCP sidecar service.
"""

import logging
import structlog

# Configure simple structured logging for sidecar
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Create sidecar logger
mcp_logger = structlog.get_logger("mcp_sidecar")