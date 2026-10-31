# Registro de validação

## Executado localmente

- Ambiente: macOS ARM64, Python 3.14.2; versões instaladas em `requirements-lock.txt`.
- `python -m pytest -q`: **64 testes passaram**, incluindo round trip do SDK com transporte HTTP
  simulado e preservação da base após falha de setup. Sem chamadas à API.
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

Não há afirmação de aprovação de respostas do modelo sem avaliação real.
