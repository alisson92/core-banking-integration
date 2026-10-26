# Architecture Decision Records (ADRs)

Um ADR registra **uma decisão, o contexto em que ela foi tomada e o que se perdeu ao tomá-la**.
Daqui a seis meses você não vai lembrar *por quê*. O ADR lembra.

| # | Decisão | Status |
|---|---|---|
| [0001](0001-hexagonal-architecture-and-anti-corruption-layer.md) | Arquitetura hexagonal e camada anticorrupção | Aceito |
| [0002](0002-idempotency-state-machine-and-reconciliation.md) | Idempotência, máquina de estados e reconciliação | Aceito |
| [0003](0003-timeouts-retries-and-circuit-breaker.md) | Timeouts, retries e circuit breaker | Aceito |
| [0004](0004-mock-core-with-fault-injection.md) | Mock do core com injeção de falhas | Aceito |
| [0005](0005-kind-and-helm-for-local-deployment.md) | Kind e Helm para o ambiente local | Aceito |

Para criar um novo: copie [`0000-template.md`](0000-template.md), numere em sequência e adicione na tabela acima.
Um ADR aceito **não se edita**: se a decisão mudar, escreva outro que o substitua.
