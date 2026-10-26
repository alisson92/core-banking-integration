# 0004. Mock do core com injeção de falhas

- **Status:** Aceito
- **Data:** 2026-10-26

## Contexto

Este é um projeto de estudo: não temos (nem devemos ter) acesso a um core banking real. Mas os
problemas mais interessantes (timeout após commit, core lento, circuito abrindo) só aparecem
quando o core se comporta mal, e não dá para esperar um incidente real para praticar.

## Decisão

Construir um **mock com estado**, em FastAPI (`mocks/core_banking_mock`), que:

- Imita o estilo legado de propósito (campos em maiúsculas, `YYYYMMDD`, status de uma letra, referência de 20 caracteres, deduplicação por `REF_ID`).
- Tem contas semeadas: ativa, ativa, bloqueada, encerrada.
- Expõe `/admin/faults` para **injetar falhas sob demanda**:
  `latency_ms`, `error_rate`, `fail_next` e, principalmente, `slow_after_commit_*`: o core
  **aplica** a transferência e só depois demora a responder, o pior cenário possível.
- Roda tanto como processo quanto em memória dentro dos testes (via `httpx.ASGITransport`), sem portas nem rede.

Um teste de **contrato** valida que o que o mock responde cabe nos modelos `wire` do adapter.
Com um core de verdade, o mesmo teste rodaria contra o sandbox dele.

## Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| WireMock / Prism com respostas fixas | Sem estado: não dá para ter saldo que muda, duplicidade de referência nem "aplicou mas demorou" |
| Mockar o `httpx` nos testes | Testa menos: não exercita HTTP de verdade, serialização nem os timeouts |
| Esperar acesso a um sandbox real | Bloqueia o aprendizado; e sandboxes raramente permitem provocar falhas |

## Consequências

- **Ganhamos:** falhas reproduzíveis, testes rápidos (86 em ~2 s) e um laboratório para estudar incidentes.
- **Aceitamos:** o mock só é tão fiel quanto o nosso entendimento do core. O teste de contrato reduz o risco de o mock e o adapter combinarem entre si e divergirem do core real.
- **Cuidado:** o mock vive em `mocks/` e **vai na mesma imagem** do serviço (por simplicidade do build). Em um projeto real, ficaria fora da imagem de produção.
- **Revisitar quando:** tivermos a documentação de um core real: ajustar `wire.py`, `mappers.py` e o mock a ela.
