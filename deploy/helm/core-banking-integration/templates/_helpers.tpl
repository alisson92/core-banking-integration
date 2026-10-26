{{/* Short chart name. */}}
{{- define "cbi.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Fully qualified name: <release>-<chart>, unless the release name already has the chart name. */}}
{{- define "cbi.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/* Labels shared by every object. */}}
{{- define "cbi.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: core-banking-integration
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end -}}

{{/* Selector labels. Call with: (dict "root" . "component" "integration"). */}}
{{- define "cbi.selectorLabels" -}}
app.kubernetes.io/name: {{ include "cbi.name" .root }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{/* Secret used by both workloads: ours, or one the user manages. */}}
{{- define "cbi.secretName" -}}
{{- if .Values.secrets.existingSecret -}}
{{- .Values.secrets.existingSecret -}}
{{- else -}}
{{- include "cbi.fullname" . -}}
{{- end -}}
{{- end -}}

{{/* Where the integration finds the core. */}}
{{- define "cbi.coreBaseUrl" -}}
{{- if .Values.core.baseUrl -}}
{{- .Values.core.baseUrl -}}
{{- else -}}
{{- printf "http://%s-mock-core:%v" (include "cbi.fullname" .) .Values.mockCore.service.port -}}
{{- end -}}
{{- end -}}
