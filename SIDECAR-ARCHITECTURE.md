# Archon MCP Sidecar Architecture

This document explains the sidecar pattern implementation for Kubernetes environments, which eliminates the need for docker.sock access while maintaining full backwards compatibility.

## Architecture Overview

```
┌─── Kubernetes Pod ───────────────────────────────────┐
│                                                      │
│  ┌── archon-server ──┐    ┌── mcp-sidecar ──┐      │
│  │                   │    │                  │      │
│  │ Main FastAPI      │───▶│ Kubernetes API   │      │
│  │ Application       │    │ Client           │      │
│  │                   │    │                  │      │
│  │ /api/mcp/*        │    │ /mcp/* endpoints │      │
│  │                   │    │                  │      │
│  └───────────────────┘    └──────────────────┘      │
│                                                      │
└──────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─── Kubernetes API ───┐
                    │                       │
                    │ Pod Lifecycle         │
                    │ Management            │
                    │                       │
                    └───────────────────────┘
                              │
                              ▼
                    ┌─── Dynamic MCP Pods ───┐
                    │                         │
                    │ archon-mcp-<timestamp>  │
                    │                         │
                    └─────────────────────────┘
```

## Components

### 1. Main Archon Server
- **Purpose**: Core application functionality
- **MCP Management**: Delegates to sidecar when available, falls back to Docker
- **Auto-detection**: Checks sidecar availability on startup and per-request
- **Backwards Compatible**: Works with existing Docker Compose setup

### 2. MCP Sidecar
- **Purpose**: Kubernetes pod lifecycle management
- **Isolation**: Separate container with focused responsibility
- **Communication**: HTTP API on localhost:8053
- **Permissions**: Has RBAC permissions for pod operations

### 3. Sidecar Client
- **Purpose**: HTTP client for main server to communicate with sidecar
- **Timeout Handling**: Graceful failure detection
- **Interface Compatibility**: Implements same interface as Docker manager

## Benefits

### 🔒 Security
- **No Privileged Access**: No docker.sock mount required
- **Least Privilege**: Sidecar has minimal Kubernetes permissions
- **Isolation**: Kubernetes operations isolated in dedicated container

### 🔄 Backwards Compatibility  
- **Zero Migration**: Existing Docker Compose deployments unchanged
- **Automatic Detection**: No configuration required
- **Graceful Fallback**: Falls back to Docker if sidecar unavailable

### 🏗️ Clean Architecture
- **Separation of Concerns**: Kubernetes logic separate from main app
- **Testability**: Each component can be tested independently  
- **Maintainability**: Clear boundaries between Docker and Kubernetes modes

### ☁️ Cloud Native
- **Kubernetes Native**: Uses proper Kubernetes patterns
- **Scalable**: Leverages Kubernetes scheduling
- **Observable**: Standard Kubernetes monitoring works

## Deployment Modes

### Local Development (Docker Compose)
```yaml
# docker-compose.yml - No sidecar needed
services:
  archon-server:
    # Docker API used directly
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock  # Still removed!
```

**Result**: Main server detects no sidecar, uses Docker manager

### Kubernetes Production
```yaml
# archon-server-deployment.yaml - Sidecar included
spec:
  containers:
  - name: archon-server
    # Main application
  - name: mcp-sidecar  
    # Kubernetes pod manager
```

**Result**: Main server detects sidecar, delegates pod operations

## Communication Flow

### MCP Start Request
```
User Request → Main Server → Sidecar Check → Route to Backend
                    │
                    ├─ Sidecar Available → HTTP POST localhost:8053/mcp/start
                    └─ No Sidecar → Docker container.start()
```

### Status Check
```
Status Request → Main Server → Sidecar Check → Get Status
                      │
                      ├─ Sidecar → HTTP GET localhost:8053/mcp/status  
                      └─ Docker → container.status
```

## Configuration

### Environment Variables
- `MCP_SIDECAR_URL`: Sidecar service URL (default: http://localhost:8053)
- `KUBERNETES_NAMESPACE`: Namespace for pod operations (default: archon)
- `MCP_SIDECAR_PORT`: Port for sidecar service (default: 8053)

### Automatic Detection
The system automatically detects the deployment environment:
1. **Check sidecar availability** via health endpoint
2. **Use sidecar** if available and healthy
3. **Fall back to Docker** if sidecar unavailable

## Error Handling

### Sidecar Unavailable
- Main server detects during health check
- Falls back to Docker mode automatically
- Logs warning but continues operation

### Sidecar Communication Failure
- HTTP timeouts handled gracefully
- Error messages propagated to user
- Automatic retry on transient failures

### Kubernetes API Failures
- Sidecar handles Kubernetes errors
- Returns structured error responses
- Main server displays user-friendly messages

## Development Guidelines

### Adding New MCP Operations
1. **Extend Sidecar API**: Add new endpoint to mcp_sidecar.py
2. **Update Client**: Add method to mcp_sidecar_client.py  
3. **Update Docker Manager**: Ensure Docker manager has equivalent method
4. **Test Both Modes**: Verify works in Docker and Kubernetes

### Testing Strategy
- **Unit Tests**: Test each component independently
- **Integration Tests**: Test sidecar communication
- **E2E Tests**: Test full Docker and Kubernetes flows
- **Fallback Tests**: Test sidecar unavailable scenarios

## Migration Path

### From Docker Socket to Sidecar
1. **No Code Changes**: Existing Docker Compose works unchanged
2. **Deploy to Kubernetes**: Use provided manifests with sidecar
3. **Automatic Upgrade**: System detects and uses sidecar
4. **Zero Downtime**: No service interruption

### Future Enhancements
- **Multi-cluster**: Sidecar could manage pods across clusters
- **Advanced Scheduling**: Custom pod placement policies
- **Monitoring**: Enhanced observability features
- **Caching**: Pod status caching for performance

This architecture provides a clean, secure, and backwards-compatible solution for Kubernetes deployment while maintaining the simplicity of local Docker development.