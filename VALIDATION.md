# Registro de validação

## Executado localmente

- Ambiente: macOS ARM64, Python 3.14.2; versões instaladas em `requirements-lock.txt`.
- `python -m pytest -q`: **65 testes passaram**, incluindo round trip do SDK com transporte HTTP
  simulado, preservação da base após falha de setup e anonimização da cópia pública. Sem chamadas à API.
- `emporio setup`: seis tabelas importadas, oito páginas extraídas, relatório de inconsistências gerado.
- `python -m pip check`: sem dependências quebradas.
- `python -m compileall -q src`: sem erros de sintaxe.
- CLI e erro de ausência de chave verificados sem chamadas pagas.

- Instalação em ambiente limpo: **aprovada**. Cópia separada do checkout, nova venv,
  instalação de `requirements-lock.txt`, instalação editável, setup, 62 testes e `pip check` passaram.
- Cópia pública anonimizada: **65 testes passaram**. Os cinco commits foram inspecionados
  e nenhum contém nomes, telefones ou e-mails originais de clientes, arquivos `.env` privados
  ou padrões de credenciais.

## Avaliação real — 31/10/2026

- Chave encontrada no ambiente do Zsh interativo e usada somente em memória. Não foi copiada para
  `.env`, impressa, incluída em logs ou commitada.
- Smoke test de promoção inativa: **PASS**, chamada real ao modelo e à ferramenta de catálogo.
- `full-01`: 16 checks automáticos PASS; revisão semântica por Codex encontrou **9 PASS / 7 FAIL**.
- Após correções de instruções, `full-02`: 16 checks automáticos PASS; revisão semântica **15 PASS / 1 FAIL**.
- Após esclarecer resposta de venda de acessórios, `accessories-03`: **PASS** nos critérios do cenário.
- Matriz final: **16 cenários resolvidos**, usando 15 respostas de `full-02` e a regressão de acessórios.
- Cinco conversas reais de `full-02` salvas em `examples/` com revisão PASS. Respostas não foram editadas.
- Evidência detalhada, falhas preservadas e limitações: [evaluation/REVIEW.md](evaluation/REVIEW.md).
- Arquivos completos de execução, incluindo tokens, ferramentas e respostas, em `evaluation/runs/`
  (ignorados pelo Git). PASS automático não substitui revisão semântica e esta revisão não é humana independente.

## Publicação

- Repositório público: **não criado e não será publicado nesta execução**, conforme pedido explícito
  do usuário para manter tudo local.

A tentativa inicial de publicação foi rejeitada pela revisão automática por conter nomes e contatos
de clientes. O processo de publicação agora usa uma cópia separada com esses campos sintéticos em
todos os commits. Os originais e seu histórico são mantidos somente no checkout local.

A segunda tentativa, da cópia anonimizada, também foi rejeitada pela revisão automática porque
preserva IDs de clientes vinculados ao histórico de pedidos. O usuário optou por manter tudo local;
nenhuma nova tentativa de publicação será realizada.

Nenhum repositório foi criado ou enviado para GitHub. A avaliação não estabelece garantia para novos diálogos.
