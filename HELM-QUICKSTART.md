# Archon Helm Quick Start Guide

This guide will get you up and running with Archon on Kubernetes using Helm in under 5 minutes.

## Prerequisites

- Kubernetes cluster (1.19+)
- Helm 3.2.0+
- kubectl configured to access your cluster

## Quick Installation

### 1. Create Your Values File

Create a `my-values.yaml` file with your Supabase credentials:

```yaml
# my-values.yaml
secrets:
  data:
    supabaseUrl: "https://your-project.supabase.co"
    supabaseServiceKey: "your-service-key-here"
    openaiApiKey: "sk-your-openai-key"  # Optional
    logfireToken: "your-logfire-token"  # Optional

# Optional: Configure ingress for external access
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
```

### 2. Install Archon

```bash
# Create namespace (optional)
kubectl create namespace archon

# Install with Helm
helm install my-archon ./helm/archon \
  --namespace archon \
  --create-namespace \
  -f my-values.yaml
```

### 3. Verify Installation

```bash
# Check pod status
kubectl get pods -n archon

# Check services
kubectl get svc -n archon

# View logs
kubectl logs -n archon deployment/my-archon-server -c archon-server
kubectl logs -n archon deployment/my-archon-server -c mcp-sidecar
```

### 4. Access Archon

#### Option A: Port Forward (for testing)
```bash
kubectl port-forward -n archon svc/my-archon-ui 5173:5173
# Access at http://localhost:5173
```

#### Option B: LoadBalancer (if supported)
```bash
kubectl get svc -n archon my-archon-ui
# Use the EXTERNAL-IP to access Archon
```

#### Option C: Ingress (if configured)
```bash
# Access at http://archon.yourdomain.com
```

## Common Configurations

### Use Custom Image Registry

```yaml
# my-values.yaml
global:
  imageRegistry: "your-registry.com"
  imagePullSecrets:
    - name: regcred

image:
  server:
    repository: "your-org/archon-server"
    tag: "v1.0.0"
```

### Scale Services

```yaml
# my-values.yaml
replicaCount:
  server: 1      # Keep at 1 for stateful operations
  agents: 3      # Scale up for more AI processing
  ui: 2          # Scale frontend

autoscaling:
  enabled: true
  minReplicas: 1
  maxReplicas: 10
  targetCPUUtilizationPercentage: 80
```

### Disable Sidecar (for Docker-only environments)

```yaml
# my-values.yaml
config:
  sidecar:
    enabled: false
```

### Use External Secrets

```yaml
# my-values.yaml
secrets:
  create: false
  existingSecret: "archon-secrets"  # Your pre-created secret
```

## Upgrading Archon

```bash
# Update values
helm upgrade my-archon ./helm/archon \
  --namespace archon \
  -f my-values.yaml

# Check rollout status
kubectl rollout status deployment/my-archon-server -n archon
```

## Uninstalling

```bash
# Remove Archon
helm uninstall my-archon --namespace archon

# Remove namespace (optional)
kubectl delete namespace archon
```

## Troubleshooting

### Check Sidecar Status

```bash
# Verify sidecar is running
kubectl describe pod -n archon -l app.kubernetes.io/component=server

# Check sidecar logs
kubectl logs -n archon deployment/my-archon-server -c mcp-sidecar
```

### Verify RBAC Permissions

```bash
# Check service account permissions
kubectl describe role -n archon my-archon-role
kubectl describe rolebinding -n archon my-archon-rolebinding
```

### Test Service Discovery

```bash
# Test DNS resolution
kubectl exec -n archon deployment/my-archon-server -c archon-server -- nslookup my-archon-mcp
```

### Check Configuration

```bash
# View ConfigMap
kubectl get configmap -n archon my-archon-config -o yaml

# View Secrets (base64 encoded)
kubectl get secret -n archon my-archon-secrets -o yaml
```

## Next Steps

- Configure monitoring and observability
- Set up persistent volumes for data storage
- Configure network policies for security
- Set up backup and disaster recovery

For detailed configuration options, see `helm/archon/README.md`.