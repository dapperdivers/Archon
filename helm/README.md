# Archon Helm Charts

This directory contains Helm charts for deploying Archon.

## Available Charts

- **[archon](./archon/)** - Complete Archon deployment with unified pod architecture

## Using the Charts

### Option 1: Helm Repository (Recommended)

Add the Helm repository:

```bash
helm repo add archon https://dapperdivers.github.io/Archon/charts
helm repo update
```

Install Archon:

```bash
helm install my-archon archon/archon
```

### Option 2: OCI Registry

Pull and install directly from GitHub Container Registry:

```bash
helm install my-archon oci://ghcr.io/dapperdivers/charts/archon
```

### Option 3: Local Charts

Clone the repository and install from local files:

```bash
git clone https://github.com/dapperdivers/Archon.git
cd Archon
helm install my-archon ./helm/archon
```

## Configuration

Before installing, create a values file with your configuration:

```yaml
# my-values.yaml
secrets:
  data:
    supabaseUrl: "https://your-project.supabase.co"
    supabaseServiceKey: "your-service-key"
    openaiApiKey: "your-openai-key"  # Optional

# Optional: Enable ingress
ingress:
  enabled: true
  className: "nginx"
  hosts:
    - host: archon.yourdomain.com
      paths:
        - path: /
          pathType: Prefix
          service: archon
          port: ui
        - path: /api
          pathType: Prefix
          service: archon
          port: server
```

Then install with your values:

```bash
helm install my-archon archon/archon -f my-values.yaml
```

## Development

### Testing Charts Locally

```bash
# Lint the chart
helm lint ./helm/archon

# Test template rendering
helm template test-release ./helm/archon

# Test with custom values
helm template test-release ./helm/archon -f my-values.yaml

# Package the chart
helm package ./helm/archon
```

### Chart Publishing

Charts are automatically published when:

1. **Push to main** with changes in `helm/archon/**` - Creates development version
2. **GitHub Release** - Creates stable version with release tag

The CI/CD pipeline:
- Lints and validates charts
- Publishes to GitHub Container Registry (OCI)
- Updates GitHub Pages with chart repository
- Attaches chart packages to GitHub releases

### Repository Structure

```
helm/
├── README.md                 # This file
└── archon/                   # Archon chart
    ├── Chart.yaml           # Chart metadata
    ├── README.md            # Chart-specific documentation
    ├── values.yaml          # Default values
    └── templates/           # Kubernetes templates
        ├── deployment.yaml  # Unified deployment
        ├── service.yaml     # Unified service
        ├── configmap.yaml   # Configuration
        ├── secret.yaml      # Secrets
        ├── ingress.yaml     # Ingress (optional)
        └── ...
```

## Support

- **Documentation**: [Chart README](./archon/README.md)
- **Issues**: [GitHub Issues](https://github.com/dapperdivers/Archon/issues)
- **Discussions**: [GitHub Discussions](https://github.com/dapperdivers/Archon/discussions)