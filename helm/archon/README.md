# Archon Helm Chart

This Helm chart deploys Archon, an MCP (Model Context Protocol) server for integrating web crawling and RAG (Retrieval-Augmented Generation) capabilities into AI agents.

## Architecture

Archon uses a **unified deployment model** where all services run in a single pod:

- **Server**: FastAPI backend with Socket.IO for real-time updates (port 8181)
- **MCP Server**: Lightweight HTTP-based MCP protocol server (port 8051)  
- **Agents Service**: PydanticAI agents for AI/ML operations (port 8052)
- **UI**: React frontend (port 5173)
- **Sidecar** (optional): Kubernetes pod management for MCP (port 8053)

### Benefits of Unified Deployment
- **Simplified networking**: Services communicate via localhost
- **Atomic deployments**: All services deploy together
- **Reduced complexity**: Single pod to manage
- **Faster inter-service communication**: No network overhead

## Prerequisites

- Kubernetes 1.19+
- Helm 3.2.0+
- PV provisioner support in the underlying infrastructure (if persistence is enabled)

## Installing the Chart

To install the chart with the release name `my-archon`:

```bash
# Add the Helm repository (if applicable)
# helm repo add archon https://charts.archon.dev
# helm repo update

# Install from local chart
helm install my-archon ./helm/archon

# Or install with custom values
helm install my-archon ./helm/archon -f my-values.yaml
```

The command deploys Archon on the Kubernetes cluster with the default configuration. The [Parameters](#parameters) section lists the parameters that can be configured during installation.

## Uninstalling the Chart

To uninstall/delete the `my-archon` deployment:

```bash
helm uninstall my-archon
```

The command removes all the Kubernetes components associated with the chart and deletes the release.

## Configuration

### Required Configuration

Before installing, you **must** set your Supabase credentials:

```yaml
# my-values.yaml
secrets:
  data:
    supabaseUrl: "https://your-project.supabase.co"
    supabaseServiceKey: "your-service-key-here"
    openaiApiKey: "your-openai-key"  # Optional
    logfireToken: "your-logfire-token"  # Optional
```

### Quick Start Example

```bash
# Create a values file
cat > my-values.yaml << EOF
secrets:
  data:
    supabaseUrl: "https://your-project.supabase.co"
    supabaseServiceKey: "your-service-key"

# Optional: Use a specific image registry
global:
  imageRegistry: "your-registry.com"

# Optional: Enable ingress
ingress:
  enabled: true
  hosts:
    - host: archon.yourdomain.com
      paths:
        - path: /
          pathType: Prefix
          service: ui
        - path: /api
          pathType: Prefix
          service: server
EOF

# Install with your values
helm install my-archon ./helm/archon -f my-values.yaml
```

## Architecture

The chart deploys the following components:

- **Server**: Main FastAPI application with MCP sidecar
- **MCP**: MCP protocol server
- **Agents**: AI agents service
- **UI**: React frontend

### Sidecar Pattern

The server pod includes a sidecar container that handles Kubernetes pod management:

- **Main Container**: Archon server application
- **Sidecar Container**: Lightweight Kubernetes pod manager
- **Communication**: HTTP via localhost:8053
- **Benefits**: No docker.sock access required, cloud-native

## Parameters

### Global Parameters

| Name | Description | Value |
|------|-------------|-------|
| `global.imageRegistry` | Global Docker image registry | `""` |
| `global.imagePullSecrets` | Global Docker registry secret names as an array | `[]` |

### Image Parameters

| Name | Description | Value |
|------|-------------|-------|
| `image.server.repository` | Server image repository | `ghcr.io/dapperdivers/archon-dev-backend` |
| `image.server.tag` | Server image tag | `latest` |
| `image.server.pullPolicy` | Server image pull policy | `IfNotPresent` |
| `image.mcp.repository` | MCP image repository | `ghcr.io/dapperdivers/archon-dev-backend` |
| `image.mcp.tag` | MCP image tag | `latest` |
| `image.mcp.pullPolicy` | MCP image pull policy | `IfNotPresent` |
| `image.agents.repository` | Agents image repository | `ghcr.io/dapperdivers/archon-dev-backend` |
| `image.agents.tag` | Agents image tag | `latest` |
| `image.agents.pullPolicy` | Agents image pull policy | `IfNotPresent` |
| `image.ui.repository` | UI image repository | `ghcr.io/dapperdivers/archon-dev-frontend` |
| `image.ui.tag` | UI image tag | `latest` |
| `image.ui.pullPolicy` | UI image pull policy | `IfNotPresent` |

### Service Parameters

| Name | Description | Value |
|------|-------------|-------|
| `service.type` | Unified service type | `LoadBalancer` |
| `service.server.port` | Server service port | `8181` |
| `service.mcp.port` | MCP service port | `8051` |
| `service.agents.port` | Agents service port | `8052` |
| `service.ui.port` | UI service port | `5173` |

### Configuration Parameters

| Name | Description | Value |
|------|-------------|-------|
| `config.deploymentMode` | Deployment mode | `kubernetes` |
| `config.serviceDiscoveryMode` | Service discovery mode | `kubernetes` |
| `config.logLevel` | Log level | `INFO` |
| `config.transport` | MCP transport protocol | `sse` |
| `config.sidecar.enabled` | Enable MCP sidecar | `true` |
| `config.sidecar.port` | Sidecar port | `8053` |

### Security Parameters

| Name | Description | Value |
|------|-------------|-------|
| `secrets.create` | Create secret from values | `true` |
| `secrets.existingSecret` | Use existing secret | `""` |
| `secrets.data.supabaseUrl` | Supabase URL | `""` |
| `secrets.data.supabaseServiceKey` | Supabase service key | `""` |
| `secrets.data.openaiApiKey` | OpenAI API key | `""` |
| `secrets.data.logfireToken` | Logfire token | `""` |

### RBAC Parameters

| Name | Description | Value |
|------|-------------|-------|
| `serviceAccount.create` | Create service account | `true` |
| `serviceAccount.annotations` | Service account annotations | `{}` |
| `serviceAccount.name` | Service account name | `""` |
| `rbac.create` | Create RBAC resources | `true` |

### Resource Parameters

| Name | Description | Value |
|------|-------------|-------|
| `resources.server.limits.cpu` | Server CPU limit | `1000m` |
| `resources.server.limits.memory` | Server memory limit | `1Gi` |
| `resources.server.requests.cpu` | Server CPU request | `500m` |
| `resources.server.requests.memory` | Server memory request | `512Mi` |
| `resources.sidecar.limits.cpu` | Sidecar CPU limit | `200m` |
| `resources.sidecar.limits.memory` | Sidecar memory limit | `256Mi` |
| `resources.sidecar.requests.cpu` | Sidecar CPU request | `100m` |
| `resources.sidecar.requests.memory` | Sidecar memory request | `128Mi` |

### Ingress Parameters

| Name | Description | Value |
|------|-------------|-------|
| `ingress.enabled` | Enable ingress | `false` |
| `ingress.className` | Ingress class name | `""` |
| `ingress.annotations` | Ingress annotations | `{}` |
| `ingress.hosts` | Ingress hosts configuration | See values.yaml |
| `ingress.tls` | Ingress TLS configuration | `[]` |

## Advanced Configuration

### Using External Secrets

For production deployments, use external secret management:

```yaml
secrets:
  create: false
  existingSecret: "archon-secrets"
```

### Scaling Configuration

```yaml
# Unified deployment - all services scale together
replicaCount: 1  # Keep at 1 for stateful operations and simplicity

autoscaling:
  enabled: false  # Not recommended for unified deployment
  minReplicas: 1
  maxReplicas: 3   # Limited scaling due to unified architecture
  targetCPUUtilizationPercentage: 80
```

### Custom Image Registry

```yaml
global:
  imageRegistry: "your-registry.com"
  imagePullSecrets:
    - name: regcred

image:
  server:
    repository: "your-org/archon-server"
    tag: "v1.0.0"
```

### Node Affinity and Tolerations

```yaml
nodeSelector:
  kubernetes.io/arch: amd64

tolerations:
  - key: "dedicated"
    operator: "Equal"
    value: "archon"
    effect: "NoSchedule"

affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
      - matchExpressions:
        - key: node-type
          operator: In
          values:
          - compute
```

## Troubleshooting

### Common Issues

1. **Sidecar not starting**: Check RBAC permissions
   ```bash
   kubectl describe pod -l app.kubernetes.io/component=server
   ```

2. **Service discovery issues**: Verify DNS resolution
   ```bash
   kubectl exec -it deployment/my-archon-server -- nslookup my-archon-mcp
   ```

3. **Image pull errors**: Check image registry and secrets
   ```bash
   kubectl describe pod -l app.kubernetes.io/name=archon
   ```

### Debugging Commands

```bash
# Check pod status
kubectl get pods -l app.kubernetes.io/instance=my-archon

# View logs
kubectl logs deployment/my-archon-server -c archon-server
kubectl logs deployment/my-archon-server -c mcp-sidecar

# Check services
kubectl get svc -l app.kubernetes.io/instance=my-archon

# Port forward for testing
kubectl port-forward svc/my-archon-ui 5173:5173
```

## Contributing

1. Make changes to templates or values
2. Update version in Chart.yaml
3. Test with `helm template` and `helm lint`
4. Submit pull request

## License

This chart is licensed under the same license as the Archon project.