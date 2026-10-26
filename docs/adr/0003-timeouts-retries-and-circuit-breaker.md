# 0003. Timeouts, retries e circuit breaker

- **Status:** Aceito
- **Data:** 2026-10-26

## Contexto

O core é lento, tem janelas de manutenção e pode ficar doente. Dois riscos opostos:

- **Esperar demais** prende conexões e threads nossas e propaga a lentidão para quem nos chama.
- **Insistir demais** pode derrubar um core que já está sofrendo (tempestade de retries).

## Decisão

Camadas, de dentro para fora, todas em `adapters/corebanking/client.py` e
`infrastructure/resilience.py`:

1. **Timeout** em toda chamada (padrão 2 s), com `asyncio.timeout` cobrindo a chamada inteira, além dos timeouts do httpx.
2. **Circuit breaker** por falhas consecutivas (padrão 5). Aberto: recusa na hora (`CircuitOpen`)
   por 30 s. Depois, *half-open*: deixa **uma** chamada de teste passar; se der certo, fecha; se falhar, reabre.
3. **Retry** com backoff exponencial e **full jitter**: `espera = aleatório(0, min(max, base · 2^(n-1)))`.
   Leituras: 3 tentativas. Escritas: 2 (seguro porque a referência torna o reenvio idempotente, ver ADR 0002).
   `CircuitOpen` **não** sofre retry.
4. **O que conta como falha:** timeout, erro de conexão, `5xx`, `429`. Respostas `4xx` de negócio
   (conta não encontrada, saldo insuficiente) **não** contam: o core respondeu, está vivo.
5. **Readiness não depende do core.** `/health/ready` sempre responde `200` e mostra o estado do
   circuito. Derrubar todos os pods durante uma queda do core só pioraria a situação.

Tudo é configurável por variável de ambiente (`CBI_*`) e os relógios/sleeps são injetáveis, então os testes não dormem.

## Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| Biblioteca pronta (tenacity, pybreaker) | Em produção seria uma boa escolha. Aqui o objetivo é entender o mecanismo; são ~100 linhas legíveis e testadas |
| Backoff exponencial sem jitter | Todos os clientes tentam no mesmo instante: o "efeito manada" |
| Retry sem limite | Esconde falhas e segura recursos indefinidamente |
| Readiness falhando quando o core cai | Efeito cascata: sem pods prontos, nem as consultas que não precisam do core funcionam |
| Contar qualquer erro 4xx como falha | Uma sequência de consultas a contas inexistentes abriria o circuito sem o core ter problema nenhum |

## Consequências

- **Ganhamos:** falhas curtas passam despercebidas; falhas longas não derrubam o core nem nos travam.
- **Aceitamos:** durante um circuito aberto, **leituras também falham** (503 + `Retry-After`). Não há cache de saldo; seria outra decisão com riscos próprios (saldo velho em banco é perigoso).
- **Cuidado:** timeouts somados. 3 tentativas × 2 s = até ~6 s para uma leitura. Ao subir o número de tentativas, calcule o pior caso e compare com o timeout de quem nos chama.
- **Observabilidade:** `core_requests_total{operation,outcome}`, `core_request_duration_seconds` e `core_circuit_breaker_state` mostram tudo isso em `/metrics`.
