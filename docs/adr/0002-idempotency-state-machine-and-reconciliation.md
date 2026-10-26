# 0002. Idempotência, máquina de estados e reconciliação

- **Status:** Aceito
- **Data:** 2026-10-26

## Contexto

Redes falham. O cenário perigoso é este: enviamos uma transferência, o core **aplica**, mas a
resposta demora e nosso timeout estoura. Para quem chamou, a operação "falhou". Se ele tentar de
novo sem proteção, o dinheiro sai **duas vezes**. Um timeout numa escrita significa *"não sei"*,
nunca *"não aconteceu"*.

## Decisão

Três mecanismos que trabalham juntos:

1. **Idempotency-Key (cliente → nós).** Todo `POST /v1/transfers` exige o header. Mesma chave +
   mesmo corpo devolve a **mesma** transferência (`200` + `Idempotent-Replayed: true`). Mesma chave
   + corpo diferente é erro (`422`), porque é quase certamente um bug do cliente. Comparamos o
   corpo por um hash SHA-256 de uma forma canônica.

2. **Referência (nós → core).** Cada transferência gera uma referência de 20 caracteres
   (`TRF` + 17 hex) enviada ao core, que **deduplica** por ela (`409 DUPLICATE_REF`). Quando o
   core diz "duplicada", buscamos o resultado original em vez de tratar como erro.
   A chave do cliente e a referência do core são coisas diferentes: uma protege a nossa API, a
   outra protege o core.

3. **Máquina de estados + persistir antes de chamar.** `PENDING → CONFIRMED | FAILED`, estados
   finais imutáveis. Gravamos a transferência como `PENDING` **antes** de falar com o core.
   Quando não sabemos o resultado (timeout, 5xx, circuito aberto), ela **fica `PENDING`**; nunca
   inventamos um resultado. A **reconciliação** resolve depois: pergunta ao core pela referência;
   se ele conhece, copia o resultado; se nunca viu, reenvia (seguro por causa da referência).

Respostas HTTP: `201` resultado final conhecido (ver `status`: `CONFIRMED` ou `FAILED`),
`202` ainda `PENDING`, `200` replay.

## Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| Sem idempotência, "só não faça retry" | O cliente vai tentar de novo de qualquer jeito (botão duplo clique, timeout do lado dele) |
| Marcar `FAILED` no timeout | Mentira perigosa: o dinheiro pode ter saído. O cliente tentaria de novo e duplicaria |
| Retry infinito até obter resposta | Segura recursos, esconde o problema e pode ficar preso para sempre |
| Usar a chave do cliente também como referência do core | Acopla nosso contrato público ao formato legado (20 caracteres, só alfanumérico) |
| Confiar só na referência do core, sem chave nossa | Duas requisições simultâneas poderiam criar duas transferências diferentes |

## Consequências

- **Ganhamos:** dinheiro nunca move duas vezes, mesmo com retry, timeout, crash do processo ou clientes impacientes. Os testes `test_unknown_outcome.py` provam os cenários.
- **Aceitamos:** existe um estado intermediário (`PENDING`) que o cliente precisa saber tratar (consultar `GET /v1/transfers/{id}`).
- **Limitação atual:** o repositório é **em memória** e o lock de criação só vale dentro de um processo. Por isso o chart usa **1 réplica**. Na Fase 3, a chave vira `UNIQUE` no PostgreSQL e a reconciliação usa `SELECT ... FOR UPDATE SKIP LOCKED`.
- **Revisitar quando:** o core passar a ter transferências assíncronas (`STATUS_CD = P`, já mapeado) ou quando surgirem estornos.
