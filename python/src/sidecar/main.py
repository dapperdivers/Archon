"""
MCP Sidecar Service

A standalone FastAPI service for managing MCP servers in Kubernetes environments.
This service provides HTTP endpoints for starting, stopping, and monitoring MCP servers.
"""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .mcp_kubernetes.sidecar.manager import MCPSidecarManager
from .mcp_kubernetes.sidecar.config import ServerConfig, MCPResponse


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global sidecar manager instance
sidecar_manager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global sidecar_manager
    
    # Startup
    namespace = os.getenv("KUBERNETES_NAMESPACE", "default")
    sidecar_manager = MCPSidecarManager(namespace=namespace)
    logger.info(f"MCP Sidecar started in namespace: {namespace}")
    
    yield
    
    # Shutdown
    if sidecar_manager:
        try:
            await sidecar_manager.stop_server()
            logger.info("MCP Sidecar shutdown complete")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")


# Create FastAPI app
app = FastAPI(
    title="MCP Sidecar Service",
    description="Kubernetes-native MCP server management service",
    version="1.0.0",
    lifespan=lifespan
)


class StartServerRequest(BaseModel):
    """Request model for starting a server."""
    server_type: str = "archon"
    name: str | None = None
    transport: str = "sse"
    image: str | None = None
    port: int | None = None
    env: dict[str, str] | None = None


class StopServerRequest(BaseModel):
    """Request model for stopping a server."""
    server_id: str | None = None


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        if sidecar_manager:
            result = await sidecar_manager.health_check()
            if result.success:
                return {"status": "healthy", "message": result.message}
            else:
                raise HTTPException(status_code=503, detail=result.message)
        else:
            raise HTTPException(status_code=503, detail="Sidecar manager not initialized")
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/status")
async def get_status():
    """Get sidecar and server status."""
    try:
        if not sidecar_manager:
            raise HTTPException(status_code=503, detail="Sidecar manager not initialized")
        
        result = await sidecar_manager.get_status()
        if result.success:
            return result.data
        else:
            raise HTTPException(status_code=500, detail=result.message)
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/servers/start")
async def start_server(request: StartServerRequest):
    """Start a new MCP server."""
    try:
        if not sidecar_manager:
            raise HTTPException(status_code=503, detail="Sidecar manager not initialized")
        
        # Create server config from request
        server_config = ServerConfig(
            server_type=request.server_type,
            name=request.name,
            transport=request.transport,
            image=request.image,
            port=request.port,
            env=request.env or {}
        )
        
        result = await sidecar_manager.start_server(server_config)
        
        if result.success:
            return {
                "success": True,
                "server_id": result.server_id,
                "message": result.message,
                "data": result.data
            }
        else:
            raise HTTPException(status_code=400, detail=result.message)
            
    except Exception as e:
        logger.error(f"Start server failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/servers/stop")
async def stop_server(request: StopServerRequest):
    """Stop MCP server(s)."""
    try:
        if not sidecar_manager:
            raise HTTPException(status_code=503, detail="Sidecar manager not initialized")
        
        result = await sidecar_manager.stop_server(request.server_id)
        
        if result.success:
            return {
                "success": True,
                "message": result.message
            }
        else:
            raise HTTPException(status_code=400, detail=result.message)
            
    except Exception as e:
        logger.error(f"Stop server failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/servers/list")
async def list_servers():
    """List all running servers."""
    try:
        if not sidecar_manager:
            raise HTTPException(status_code=503, detail="Sidecar manager not initialized")
        
        result = await sidecar_manager.list_external_servers()
        
        if result.success:
            return result.data
        else:
            raise HTTPException(status_code=500, detail=result.message)
            
    except Exception as e:
        logger.error(f"List servers failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/logs")
async def get_logs(limit: int = 100):
    """Get recent log entries."""
    try:
        if not sidecar_manager:
            raise HTTPException(status_code=503, detail="Sidecar manager not initialized")
        
        logs = sidecar_manager.get_logs(limit)
        return {"logs": logs}
        
    except Exception as e:
        logger.error(f"Get logs failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    
    # Get configuration from environment
    host = os.getenv("MCP_SIDECAR_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_SIDECAR_PORT", "8053"))
    
    logger.info(f"Starting MCP Sidecar on {host}:{port}")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )