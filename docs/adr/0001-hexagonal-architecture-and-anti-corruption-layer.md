# 0001. Arquitetura hexagonal e camada anticorrupção

- **Status:** Aceito
- **Data:** 2026-10-26

## Contexto

O core banking tem um formato próprio e antigo: campos em maiúsculas (`ACCT_NO`), datas
`YYYYMMDD`, status de uma letra (`A`/`B`/`C`), referências de no máximo 20 caracteres, códigos de
erro como `INSUFF_FUNDS`. Esse formato vai mudar (nova versão do core) ou ser substituído
(migração para outro core). Se ele se espalhar pelo nosso código, qualquer mudança vira uma
reforma geral.

Além disso, queremos testar as regras do nosso serviço sem precisar do core, de HTTP ou de banco.

## Decisão

Organizar o código em camadas com dependências apontando **para dentro**:

- `domain`: modelo do negócio (`Money`, `Transfer`, erros). Sem frameworks.
- `application`: casos de uso. Declara **portas** (`CoreBankingGateway`, `TransferRepository`) como `Protocol`.
- `adapters` e `infrastructure`: implementações das portas. **Todo** conhecimento do formato do
  core vive em `adapters/corebanking` (`wire.py` valida o que chega; `mappers.py` traduz).
- `api`: HTTP. Fina: valida entrada, chama um caso de uso, formata a saída.
- Montagem das peças em um único lugar: `bootstrap.py` (composition root).

Erros do core são traduzidos para erros de domínio na borda. O resto do código nunca vê
status HTTP do core nem códigos como `INSUFF_FUNDS`.

## Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| Chamar o core direto das rotas, usando o JSON dele | Rápido no início, mas o formato do core contamina tudo; testar exige o core |
| Reaproveitar os modelos do core como modelos de domínio | É exatamente o acoplamento que queremos evitar |
| Biblioteca de injeção de dependência / framework hexagonal | Peso desnecessário para o tamanho do projeto; um `bootstrap.py` explícito é mais fácil de ler |

## Consequências

- **Ganhamos:** trocar de core = escrever outro adapter. Casos de uso testáveis sem rede. O
  contrato do core é verificado em um lugar só (`tests/contract`).
- **Perdemos:** mais arquivos e uma camada de tradução para manter. Para um projeto minúsculo seria exagero; aqui o objetivo é justamente aprender o padrão.
- **Regra para o futuro:** se um `import` de `adapters` aparecer em `domain` ou `application`, algo está errado.
