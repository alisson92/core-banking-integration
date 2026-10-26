# Como rodar

## 1. Sem containers (mais rápido para estudar)

```bash
python3 -m venv .venv && source .venv/bin/activate
make install        # instala o projeto e as ferramentas de desenvolvimento
make test           # 86 testes, cerca de 2 segundos
make lint
```

Dois terminais:

```bash
make run-core       # mock do core    -> http://localhost:8081
make run-api        # nosso serviço   -> http://localhost:8080  (documentação em /docs)
make smoke          # teste rápido de ponta a ponta
```

Variáveis de ambiente (prefixo `CBI_`): veja `src/core_integration/infrastructure/settings.py`.
Exemplo: `CBI_CORE_TIMEOUT_SECONDS=1 CBI_BREAKER_FAILURE_THRESHOLD=2 make run-api`.

Chaves de desenvolvimento: nosso serviço `dev-service-key`, mock do core `core-dev-key`.
**Só para laboratório.** O serviço avisa no log quando usa a chave padrão.

## 2. Kind + Helm

> Nota: os arquivos de container e do chart foram escritos e tiveram a sintaxe conferida, mas
> ainda **não foram executados** (o ambiente onde foram criados não tinha Docker, Kind nem Helm).
> Ao rodar pela primeira vez, leia os erros com calma: é parte do aprendizado e vale registrar
> no `CLAUDE.md`.

Pré-requisitos: Docker, Kind, kubectl e Helm instalados.

**Sempre faça o teste a seco antes de aplicar** (`template` e `dry-run`).

```bash
make docker-build                 # imagens cbi/integration:dev e cbi/mock-core:dev
make kind-up                      # cluster "cbi-lab" (1 control-plane + 1 worker)
make kind-load                    # copia as imagens locais para dentro do Kind

make helm-lint
make helm-template | less         # leia os manifestos renderizados antes de instalar
make helm-dry-run                 # o cluster valida sem alterar nada
make helm-install                 # instala e espera ficar pronto

kubectl -n cbi get pods
make port-forward                 # em outro terminal
make smoke
```

Limpeza:

```bash
make helm-uninstall
make kind-down CONFIRM=yes        # sem CONFIRM=yes o comando se recusa a apagar o cluster
```

### O que observar no chart

- `strategy: Recreate` e `replicas: 1`: o estado está em memória (ver ADR 0005 e a seção de limitações em `architecture.md`).
- `securityContext`: usuário não-root, sistema de arquivos somente leitura, sem capabilities.
- Segredos: o chart cria um `Secret` com valores de laboratório. Em um ambiente real, use
  `secrets.existingSecret` apontando para um Secret gerenciado fora do Git (External Secrets, Vault, Sealed Secrets).
- `/health/ready` não depende do core (ver ADR 0003).

### Para testar falhas dentro do cluster

```bash
kubectl -n cbi port-forward svc/cbi-core-banking-integration-mock-core 8081:8081
curl -s -X POST -H 'X-API-Key: core-dev-key' -H 'Content-Type: application/json' \
     -d '{"fail_next": 3}' localhost:8081/admin/faults
```

## 3. Convenções do projeto

- Commits: Conventional Commits, em inglês (`feat: add statement endpoint`).
- Branches: `type/<ticket>-<objetivo-curto>` (`feat/12-postgres-repository`).
- Nomes de arquivos e pastas em inglês; só o conteúdo de `docs/` é em português.
- Decisões novas viram um ADR em `docs/adr/` (copie o `0000-template.md`).
