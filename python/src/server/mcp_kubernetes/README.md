# MCP Kubernetes Module

This module provides comprehensive support for running MCP (Model Context Protocol) servers in Kubernetes environments, enabling dynamic creation and management of external MCP servers alongside the core Archon MCP server.

## Features

- **Dynamic Pod Management**: Create and manage MCP server pods on-demand
- **Multi-Protocol Support**: STDIO, SSE, WebSocket, and HTTP communication
- **Package Discovery**: Search and discover MCP packages from NPM and PyPI
- **Server Registry**: Built-in templates for popular MCP servers
- **Protocol Adapters**: Seamless bridging between different MCP transports
- **Resource Management**: Kubernetes-native resource limits and health checks

## Architecture

```
mcp_kubernetes/
├── sidecar/           # Kubernetes pod management and orchestration
├── stdio/             # STDIO communication via Kubernetes exec API
├── protocols/         # Protocol adapters for different MCP transports
├── registry/          # MCP server discovery and template management
├── packages/          # Package management for NPM and PyPI servers
├── client/            # High-level client interface
└── tests/             # Test suite
```

## Quick Start

### Basic Usage

```python
from src.server.mcp_kubernetes import MCPKubernetesManager

# Create manager
manager = MCPKubernetesManager(namespace="archon")

# Start external MCP server
config = {
    "server_type": "npx",
    "package": "@modelcontextprotocol/server-brave-search", 
    "transport": "stdio",
    "env": {"BRAVE_API_KEY": "your-api-key"}
}

result = await manager.start_external_server(config)
print(f"Started server: {result['server_id']}")

# List running servers
servers = await manager.list_external_servers()
print(f"Running servers: {len(servers)}")

# Stop server
await manager.stop_external_server(result['server_id'])
```

### Server Types Supported

#### NPX Servers (Node.js)
```python
config = {
    "server_type": "npx",
    "package": "@modelcontextprotocol/server-playwright",
    "transport": "stdio"
}
```

#### UV Servers (Python)
```python
config = {
    "server_type": "uv", 
    "package": "mcp-server-fetch",
    "transport": "stdio"
}
```

#### Archon Core Server
```python
config = {
    "server_type": "archon",
    "transport": "sse",
    "port": 8051
}
```

## Component Details

### Sidecar Manager (`sidecar/`)

The sidecar manager handles Kubernetes pod lifecycle management:

- **Pod Creation**: Dynamic pod manifest generation based on server type
- **Resource Management**: CPU/memory limits, security contexts
- **Health Monitoring**: Liveness and readiness probes
- **Cleanup**: Automatic pod deletion when servers are stopped

### STDIO Bridge (`stdio/`)

Provides bidirectional communication with MCP servers via Kubernetes exec API:

- **Stream Management**: stdin/stdout/stderr handling
- **JSON-RPC Processing**: Message parsing and routing
- **Connection Pooling**: Efficient resource utilization
- **Error Recovery**: Automatic reconnection on failures

### Protocol Adapters (`protocols/`)

Support for multiple MCP communication protocols:

- **STDIO Adapter**: JSON-RPC over stdin/stdout
- **SSE Adapter**: Server-Sent Events for real-time updates
- **WebSocket Adapter**: Bidirectional real-time communication
- **Protocol Bridge**: Message routing between different protocols

### Server Registry (`registry/`)

Template-based server discovery and management:

- **Built-in Templates**: Popular servers (Brave Search, GitHub, PostgreSQL, etc.)
- **Capability Management**: Server feature discovery
- **Configuration Generation**: Template-to-config conversion
- **Validation**: Template and configuration validation

### Package Manager (`packages/`)

Package discovery across multiple registries:

- **NPM Integration**: Search and validate NPM packages
- **PyPI Integration**: Search and validate Python packages
- **Version Management**: Package version discovery
- **Dependency Analysis**: Package dependency information

## Configuration

### Environment Variables

```bash
# Kubernetes configuration
KUBERNETES_NAMESPACE=archon
ARCHON_MCP_IMAGE=archon-mcp:latest

# Resource limits
MCP_SERVER_CPU_LIMIT=500m
MCP_SERVER_MEMORY_LIMIT=512Mi

# Security settings
MCP_ALLOW_NPX=true
MCP_ALLOW_UV=true
MCP_ALLOW_CUSTOM_IMAGES=false
```

### Helm Configuration

```yaml
config:
  mcp:
    servers:
      braveSearch:
        enabled: true
      filesystem:
        enabled: true
        allowedPaths: ["/tmp", "/var/cache"]
    security:
      allowNpx: true
      allowUv: true
      internetAccess: true
    resources:
      limits:
        cpu: "500m"
        memory: "512Mi"
```

## Security Considerations

### Pod Security

- **Non-root execution**: All containers run as non-root users
- **Read-only filesystem**: Where possible, containers use read-only root filesystems
- **Capability dropping**: Unnecessary Linux capabilities are dropped
- **Security contexts**: Proper security contexts applied to all pods

### Network Security

- **Network policies**: Optional pod-to-pod communication restrictions
- **Internet access**: Configurable internet access for external packages
- **Service isolation**: Servers isolated from each other by default

### Package Security

- **Package verification**: Optional package signature verification
- **Allowlists/Blocklists**: Configurable package filtering
- **Registry validation**: Package registry validation and authentication

## Monitoring and Observability

### Health Checks

- **Liveness Probes**: HTTP health checks for HTTP-based servers
- **Readiness Probes**: Startup health validation
- **Resource Monitoring**: CPU and memory usage tracking

### Logging

- **Structured Logging**: JSON-formatted logs with correlation IDs
- **Log Aggregation**: Integration with Kubernetes logging systems
- **Debug Modes**: Configurable log levels for troubleshooting

### Metrics

- **Pod Metrics**: Creation/deletion rates, resource usage
- **Communication Metrics**: Message throughput, error rates
- **Registry Metrics**: Package search and discovery statistics

## Development

### Adding New Server Types

1. Update `ServerConfig` model in `sidecar/config.py`
2. Add image and command logic in `sidecar/pod_manager.py`
3. Create template in `registry/builtin_servers.py`
4. Add tests in `tests/`

### Adding New Protocols

1. Create new adapter class extending `ProtocolAdapter`
2. Implement protocol-specific communication logic
3. Add to adapter factory in `protocols/adapters.py`
4. Update protocol bridge routing

### Testing

```bash
# Run unit tests
uv run pytest src/server/mcp_kubernetes/tests/

# Run integration tests
uv run pytest src/server/mcp_kubernetes/tests/integration/

# Run with coverage
uv run pytest --cov=src.server.mcp_kubernetes
```

## Troubleshooting

### Common Issues

#### Pod Creation Failures
- Check RBAC permissions for pod creation
- Verify namespace exists and is accessible
- Check resource quotas and limits

#### STDIO Communication Issues
- Verify pod is running and ready
- Check container logs for startup errors
- Validate JSON-RPC message format

#### Package Discovery Issues
- Check internet connectivity for registry access
- Verify package names and versions
- Check registry rate limits

### Debug Mode

Enable debug logging:

```python
import logging
logging.getLogger('src.server.mcp_kubernetes').setLevel(logging.DEBUG)
```

### Health Checks

Check component health:

```python
manager = MCPKubernetesManager()

# Check sidecar health
health = await manager.sidecar.health_check()

# Check individual server health  
server_health = await manager.sidecar.get_server_status(server_id)
```

## Contributing

1. Follow the existing module structure
2. Add comprehensive tests for new functionality
3. Update documentation for API changes
4. Ensure backward compatibility where possible
5. Add appropriate error handling and logging

## License

This module is part of the Archon project and follows the same licensing terms.