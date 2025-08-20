{{/*
Expand the name of the chart.
*/}}
{{- define "archon.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "archon.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "archon.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "archon.labels" -}}
helm.sh/chart: {{ include "archon.chart" . }}
{{ include "archon.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "archon.selectorLabels" -}}
app.kubernetes.io/name: {{ include "archon.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Note: Component-specific labels removed for unified deployment
All services now run in a single pod with shared labels
*/}}

{{/*
Create the name of the service account to use
*/}}
{{- define "archon.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "archon.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Create the name of the secret to use
*/}}
{{- define "archon.secretName" -}}
{{- if .Values.secrets.existingSecret }}
{{- .Values.secrets.existingSecret }}
{{- else }}
{{- include "archon.fullname" . }}-secrets
{{- end }}
{{- end }}

{{/*
Image name helpers
*/}}
{{- define "archon.serverImage" -}}
{{- $registry := .Values.global.imageRegistry | default "" }}
{{- $repository := .Values.image.server.repository }}
{{- $tag := .Values.image.server.tag | default .Chart.AppVersion }}
{{- if $registry }}
{{- printf "%s/%s:%s" $registry $repository $tag }}
{{- else }}
{{- printf "%s:%s" $repository $tag }}
{{- end }}
{{- end }}

{{- define "archon.mcpImage" -}}
{{- $registry := .Values.global.imageRegistry | default "" }}
{{- $repository := .Values.image.mcp.repository }}
{{- $tag := .Values.image.mcp.tag | default .Chart.AppVersion }}
{{- if $registry }}
{{- printf "%s/%s:%s" $registry $repository $tag }}
{{- else }}
{{- printf "%s:%s" $repository $tag }}
{{- end }}
{{- end }}

{{- define "archon.agentsImage" -}}
{{- $registry := .Values.global.imageRegistry | default "" }}
{{- $repository := .Values.image.agents.repository }}
{{- $tag := .Values.image.agents.tag | default .Chart.AppVersion }}
{{- if $registry }}
{{- printf "%s/%s:%s" $registry $repository $tag }}
{{- else }}
{{- printf "%s:%s" $repository $tag }}
{{- end }}
{{- end }}

{{- define "archon.uiImage" -}}
{{- $registry := .Values.global.imageRegistry | default "" }}
{{- $repository := .Values.image.ui.repository }}
{{- $tag := .Values.image.ui.tag | default .Chart.AppVersion }}
{{- if $registry }}
{{- printf "%s/%s:%s" $registry $repository $tag }}
{{- else }}
{{- printf "%s:%s" $repository $tag }}
{{- end }}
{{- end }}

{{- define "archon.sidecarImage" -}}
{{- $registry := .Values.global.imageRegistry | default "" }}
{{- $repository := .Values.image.sidecar.repository }}
{{- $tag := .Values.image.sidecar.tag | default .Chart.AppVersion }}
{{- if $registry }}
{{- printf "%s/%s:%s" $registry $repository $tag }}
{{- else }}
{{- printf "%s:%s" $repository $tag }}
{{- end }}
{{- end }}

{{/*
Environment variables for all services
*/}}
{{- define "archon.commonEnv" -}}
- name: LOG_LEVEL
  value: {{ .Values.config.logLevel | quote }}
- name: DEPLOYMENT_MODE
  value: {{ .Values.config.deploymentMode | quote }}
- name: SERVICE_DISCOVERY_MODE
  value: {{ .Values.config.serviceDiscoveryMode | quote }}
- name: TRANSPORT
  value: {{ .Values.config.transport | quote }}
- name: KUBERNETES_NAMESPACE
  value: {{ .Release.Namespace | quote }}
{{- end }}

{{/*
Service ports configuration
*/}}
{{- define "archon.servicePorts" -}}
- name: ARCHON_SERVER_PORT
  value: {{ .Values.service.server.port | quote }}
- name: ARCHON_MCP_PORT
  value: {{ .Values.service.mcp.port | quote }}
- name: ARCHON_AGENTS_PORT
  value: {{ .Values.service.agents.port | quote }}
- name: ARCHON_UI_PORT
  value: {{ .Values.service.ui.port | quote }}
{{- if .Values.config.sidecar.enabled }}
- name: MCP_SIDECAR_PORT
  value: {{ .Values.config.sidecar.port | quote }}
- name: MCP_SIDECAR_URL
  value: "http://localhost:{{ .Values.config.sidecar.port }}"
{{- end }}
{{- end }}

{{/*
Service hosts configuration (unified pod using localhost)
*/}}
{{- define "archon.serviceHosts" -}}
- name: ARCHON_SERVER_HOST
  value: localhost
- name: ARCHON_MCP_HOST
  value: localhost
- name: ARCHON_AGENTS_HOST
  value: localhost
- name: ARCHON_UI_HOST
  value: localhost
{{- end }}

{{/*
Legacy service URLs for backward compatibility (unified pod using localhost)
*/}}
{{- define "archon.legacyServiceUrls" -}}
- name: API_SERVICE_URL
  value: "http://localhost:{{ .Values.service.server.port }}"
- name: AGENTS_SERVICE_URL
  value: "http://localhost:{{ .Values.service.agents.port }}"
{{- end }}