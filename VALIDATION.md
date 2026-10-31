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

## Pendente

- Avaliação real dos 16 cenários e revisão semântica: aguardando `OPENAI_API_KEY`.
- Cinco exemplos reais: aguardando a avaliação completa.
- Repositório público: publicação ainda não executada.

A tentativa inicial de publicação foi rejeitada pela revisão automática por conter nomes e contatos
de clientes. O processo de publicação agora usa uma cópia separada com esses campos sintéticos em
todos os commits. Os originais e seu histórico são mantidos somente no checkout local.

Não há afirmação de aprovação de respostas do modelo sem avaliação real.
