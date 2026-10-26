# Guia de estudo (de baixo para cima)

Ordem sugerida: comece pelas peças pequenas e sem dependências e vá subindo até a API.
Em cada etapa: **leia → rode o teste → quebre de propósito → veja o teste falhar**.

## Trilha de leitura

| # | Arquivo | O que aprender | Teste para rodar |
|---|---|---|---|
| 1 | `domain/money.py` | Por que dinheiro é `Decimal` e nunca `float` | `tests/unit/test_money.py` |
| 2 | `domain/models.py` (`Transfer`) | Máquina de estados; referência de 20 caracteres | `tests/unit/test_transfer_state.py` |
| 3 | `domain/errors.py` | Três famílias de erro: recusa final, "não sei", protocolo | (leia os comentários) |
| 4 | `application/ports.py` | O que a aplicação *precisa* do mundo externo (interfaces) | — |
| 5 | `infrastructure/resilience.py` | Backoff com jitter e circuit breaker | `tests/unit/test_circuit_breaker.py` |
| 6 | `mocks/core_banking_mock/store.py` | As regras do "banco" (duplicidade de referência etc.) | `tests/contract/test_contracts.py` |
| 7 | `adapters/corebanking/wire.py` + `mappers.py` | Anticorrupção: o formato legado fica preso aqui | `tests/unit/test_mappers.py` |
| 8 | `adapters/corebanking/client.py` | Timeout, breaker, retry e tradução de erros juntos | `tests/integration/test_resilience.py` |
| 9 | `application/transfers.py` | Idempotência, "salvar antes de chamar", reconciliação | `tests/integration/test_transfers.py` e `test_unknown_outcome.py` |
| 10 | `api/*` | Rotas finas, erros RFC 9457, middleware | `tests/integration/test_reads.py` |

## Experimentos práticos

Suba os dois serviços (dois terminais):

```bash
make run-core      # mock do core na porta 8081
make run-api       # serviço de integração na porta 8080
```

Variáveis úteis nos comandos abaixo:

```bash
H='X-API-Key: dev-service-key'          # chave do nosso serviço
C='X-API-Key: core-dev-key'             # chave do mock do core
```

### Experimento 1: idempotência

Envie a mesma transferência duas vezes com a mesma `Idempotency-Key`.

```bash
for i in 1 2; do
  curl -s -i -H "$H" -H 'Idempotency-Key: estudo-1' -H 'Content-Type: application/json' \
    -d '{"source_account":"0001234567","destination_account":"0007654321","amount":"100.00"}' \
    localhost:8080/v1/transfers | grep -iE '^HTTP|idempotent'
done
curl -s -H "$H" localhost:8080/v1/accounts/0001234567/balance
```

**Pergunte-se:** por que a segunda resposta é `200` e não `201`? O saldo caiu uma ou duas vezes?
Agora troque o valor mantendo a chave. O que acontece? (Dica: ADR 0002.)

### Experimento 2: o core "morre" por um momento

```bash
curl -s -X POST -H "$C" -H 'Content-Type: application/json' -d '{"fail_next": 2}' localhost:8081/admin/faults
curl -s -H "$H" localhost:8080/v1/accounts/0001234567/balance     # retry resolve
curl -s -X POST -H "$C" -H 'Content-Type: application/json' -d '{"fail_next": 20}' localhost:8081/admin/faults
for i in 1 2 3 4; do curl -s -o /dev/null -w "%{http_code}\n" -H "$H" localhost:8080/v1/accounts/0001234567/balance; done
curl -s localhost:8080/health/ready                                # veja o estado do circuito
curl -s localhost:8080/metrics | grep core_circuit
curl -s -X DELETE -H "$C" localhost:8081/admin/faults
```

**Pergunte-se:** em qual chamada o circuito abriu? O que mudou no tempo de resposta depois disso?
Por que o `/health/ready` continua `200` com o circuito aberto? (Dica: ADR 0003.)

### Experimento 3: o pior cenário (o dinheiro moveu, a resposta se perdeu)

```bash
# o core aplica a transferência e demora 2,5 s para responder (nosso timeout é 2 s)
curl -s -X POST -H "$C" -H 'Content-Type: application/json' \
  -d '{"slow_after_commit_ms": 2500, "slow_after_commit_next": 1}' localhost:8081/admin/faults
curl -s -w "\nHTTP %{http_code}\n" -H "$H" -H 'Idempotency-Key: estudo-3' -H 'Content-Type: application/json' \
  -d '{"source_account":"0001234567","destination_account":"0007654321","amount":"10.00"}' localhost:8080/v1/transfers
curl -s -H "$H" localhost:8080/v1/accounts/0001234567/balance
```

Aqui o retry resolve sozinho: a 2ª tentativa recebe `DUPLICATE_REF` e busca o resultado original.
**Agora desligue o retry** para ver o `PENDING` de verdade, reiniciando a API com
`CBI_WRITE_MAX_ATTEMPTS=1 make run-api` e repetindo o experimento com outra chave. Depois:

```bash
curl -s -X POST -H "$H" localhost:8080/internal/reconcile
```

**Pergunte-se:** o saldo já tinha caído antes da reconciliação? O que a reconciliação fez com a
transferência? E se ela tivesse reenviado, o dinheiro sairia duas vezes? Por quê?

### Experimento 4: segurança dos logs

Rode uma consulta de saldo e leia o log da API. Procure o número da conta e a chave de API.
**Pergunte-se:** onde eles foram parar? Que dois mecanismos impedem o vazamento?
(Dica: `observability/structured_logging.py`.)

## Exercícios de código

1. **Fácil:** adicione `GET /v1/accounts/{id}` (dados da conta) usando `get_account`, que já existe no client. Comece pelo contrato em `api/openapi.yaml` e rode o teste de contrato para vê-lo falhar.
2. **Médio:** faça o mock devolver `STATUS_CD: "P"` (processando) em algum cenário e escreva o teste do fluxo `PENDING` → reconciliação → `CONFIRMED`. O mapper já entende `P`.
3. **Médio:** limite de valor por transferência (regra nossa, no `application`). Qual código HTTP deve voltar?
4. **Difícil:** troque o repositório em memória por SQLite (mesma interface `TransferRepository`). O teste de idempotência concorrente ainda passa? O que você precisa no banco para garantir isso?

## Perguntas para fixar

1. Por que a transferência é salva **antes** da chamada ao core?
2. Por que um timeout numa escrita **não** significa que falhou?
3. O que garante que reenviar uma transferência não duplica o dinheiro? (São duas camadas.)
4. Por que erros de negócio do core não contam para o circuit breaker?
5. Por que o label de métrica é `/v1/accounts/{account_id}/balance` e não o caminho real?
6. Por que o Helm roda uma única réplica por enquanto?

## Glossário (português ↔ inglês)

| Inglês (no código) | Português | Em uma frase |
|---|---|---|
| core banking | sistema central do banco | Sistema de registro de contas e saldos |
| anti-corruption layer | camada anticorrupção | Isola o formato do core do nosso modelo |
| port / adapter | porta / adaptador | Interface que a aplicação exige / implementação concreta dela |
| idempotency | idempotência | Repetir a operação não muda o resultado |
| idempotency key | chave de idempotência | Identifica a *intenção* de fazer uma transferência |
| state machine | máquina de estados | Estados e transições permitidas |
| timeout | tempo limite | Quanto esperamos antes de desistir |
| retry | nova tentativa | Tentar de novo depois de uma falha |
| backoff | espera crescente | Esperar mais a cada tentativa |
| jitter | variação aleatória | Espalha as tentativas no tempo |
| circuit breaker | disjuntor | Para de chamar quem está falhando |
| reconciliation | reconciliação | Comparar/corrigir nosso estado com o do core |
| outcome unknown | resultado desconhecido | Não sabemos se a operação foi aplicada |
| fault injection | injeção de falhas | Provocar falhas de propósito para testar |
| walking skeleton | esqueleto andante | Fatia mínima que funciona de ponta a ponta |
| contract-first | contrato primeiro | Escrever a API antes do código |
