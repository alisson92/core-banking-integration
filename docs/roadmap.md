# Roadmap

Marque conforme for avançando. Cada fase termina com algo que roda e tem teste.

## Fase 0: Descoberta e contrato  ✅

- [x] Mapear as operações: saldo, extrato, transferência, consulta de transferência
- [x] Contrato público antes do código: `api/openapi.yaml`
- [x] Teste de contrato: o app em execução implementa tudo o que o contrato promete
- [x] ADRs das decisões principais (`docs/adr/`)

## Fase 1: Walking skeleton (somente leitura)  ✅

- [x] Mock do core com formato legado (`mocks/core_banking_mock`)
- [x] Saldo e extrato de ponta a ponta
- [x] Adapter anticorrupção (wire, mappers, tradução de erros)
- [x] Logs JSON mascarados, métricas, health checks
- [x] Dockerfile, chart Helm e Makefile para Kind

## Fase 2: Escritas seguras  ✅ (em memória)

- [x] Transferência idempotente (`Idempotency-Key`) com máquina de estados
- [x] Referência de 20 caracteres, deduplicada pelo core
- [x] Retry, timeout e circuit breaker
- [x] Reconciliação (endpoint + loop em background)
- [x] Injeção de falhas: `slow_after_commit` reproduz o pior cenário (dinheiro moveu, resposta se perdeu)

## Fase 3: Persistência de verdade  ⬜  ← próximo passo sugerido

- [ ] PostgreSQL no lugar do repositório em memória (mesma interface `TransferRepository`)
- [ ] `UNIQUE (idempotency_key)` no banco no lugar do lock em memória
- [ ] Migrações (Alembic)
- [ ] Reconciliação com `SELECT ... FOR UPDATE SKIP LOCKED`
- [ ] Subir para 2+ réplicas e provar (com teste) que a idempotência continua valendo

## Fase 4: Assíncrono  ⬜

- [ ] Fila (SQS, RabbitMQ ou Kafka) para transferências com core lento ou em lote
- [ ] Padrão *outbox*: gravar a transferência e o evento na mesma transação
- [ ] Notificação do resultado (webhook ou evento)

## Fase 5: Observabilidade completa  ⬜

- [ ] OpenTelemetry: traces de ponta a ponta (API → adapter → core)
- [ ] Dashboards e SLOs (disponibilidade e latência por operação)
- [ ] Alertas: taxa de erro, circuito aberto, transferências `PENDING` antigas
- [ ] Runbook para cada alerta

## Fase 6: Entrega e segurança  ⬜

- [ ] CI/CD completo (o `ci.yml` já roda lint, testes, lint do chart e build das imagens)
- [ ] GitOps com Argo CD
- [ ] mTLS ou OAuth2 client credentials no lugar da chave estática
- [ ] NetworkPolicy, External Secrets, scan de imagem
- [ ] Rollout gradual: feature flag, canary, *shadow mode* antes de habilitar escritas

## Fase 7: Teste de carga e caos  ⬜

- [ ] Carga (k6 ou Locust) respeitando o limite do core
- [ ] Caos: matar o pod no meio de uma transferência e conferir que a reconciliação resolve
- [ ] Reconciliação periódica completa (comparar nosso estado com o extrato do core)
