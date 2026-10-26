# 0005. Kind e Helm para o ambiente local

- **Status:** Aceito
- **Data:** 2026-10-26

## Contexto

O objetivo é praticar o ciclo completo (build → imagem → cluster → deploy → operação), e o dia a
dia de trabalho é Kubernetes e Helm. Um ambiente local que se pareça com o real ensina mais que um
`docker compose`, mas precisa ser descartável e barato.

## Decisão

- **Kind** (`deploy/kind/kind-config.yaml`): cluster descartável com 1 control-plane e 1 worker.
- **Helm** (`deploy/helm/core-banking-integration`): um chart com os dois workloads (serviço e mock).
  O mock é opcional (`mockCore.enabled`) e `core.baseUrl` permite apontar para outro core.
- **Um Dockerfile, duas imagens** (alvos `integration` e `mock-core`), multi-stage, usuário não-root (UID 10001).
- **Segurança do pod por padrão:** `runAsNonRoot`, `readOnlyRootFilesystem`, `capabilities: drop ALL`, `seccompProfile: RuntimeDefault`, sondas `liveness` e `readiness`.
- **Uma réplica, estratégia `Recreate`**, porque o estado está em memória (ADR 0002).
- **Segredos:** o chart cria um `Secret` com valores de laboratório e aceita `secrets.existingSecret` para um Secret gerenciado fora do Git.
- **Hábito de segurança operacional:** `make helm-template` e `make helm-dry-run` antes de `make helm-install`; `make kind-down` só apaga com `CONFIRM=yes`.

## Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| Docker Compose | Mais simples, mas não treina probes, Secrets, Services nem Helm |
| Manifestos YAML puros / Kustomize | Boa opção; Helm foi escolhido por ser o que já se usa no trabalho e por ter `lint`/`template`/`--dry-run` |
| Minikube / k3d | Equivalentes; Kind é o mais leve e o mais usado em CI |
| Dois charts (um para o mock, outro para o serviço) | Mais um artefato para versionar; o mock é só de estudo |

## Consequências

- **Ganhamos:** um ambiente que lembra produção, descartável com um comando.
- **Aceitamos:** sem alta disponibilidade por enquanto. Subir `replicaCount` com o repositório em memória **quebra a idempotência** (cada pod teria o seu próprio mapa de chaves).
- **Verificação pendente:** os arquivos foram escritos e conferidos por sintaxe, mas o primeiro `helm lint` e o primeiro `kind load` ainda precisam rodar na sua máquina.
- **Próximos passos:** GitOps com Argo CD (Fase 6) e `NetworkPolicy`, que hoje não existe (`/metrics` e a API ficam acessíveis a qualquer pod do cluster).
