# Avaliação real do agente — 31/10/2026

Modelo: `gpt-5-mini`. Revisão semântica realizada por Codex, comparando respostas reais com as saídas das ferramentas e o manual fornecido. Não é validação estatística nem revisão humana independente.

## Resultado final

16 cenários resolvidos: 15 aprovados em `full-02` e o cenário de acessórios aprovado na regressão `accessories-03`. As duas execuções completas e a regressão permanecem locais em `evaluation/runs/`, ignoradas pelo Git.

| Cenário | Execução final | Revisão | Evidência |
|---|---|---|---|
| budget | `full-02` | PASS | search_products retornou IDs 83/85/89 disponíveis, todos até R$1.000; quote_payment retornou 40841 centavos para PIX do 83. A resposta exibiu R$408,41, sem frete, e citou seções 3/3.1/6.2. |
| inactive_promotion | `full-02` | PASS | get_product_details retornou promoção nula, 219900 centavos e cinco unidades. Resposta negou oferta de 12% e apresentou R$2.199,00. |
| order | `full-02` | PASS | get_order_status preservou total histórico 345000 centavos do pedido 3, status delivered e previsão 2025-12-05. Resposta destacou previsão histórica e ausência de data real. |
| return | `full-02` | PASS | Consultou pedido 1 e pediu canal, recebimento real e condições do instrumento; citou 4.1 e exceções de 4.4 sem concluir elegibilidade. Não solicitou fotos ou documentos. |
| out_of_scope | `full-02` | PASS | Recusou tarefa de previsão eleitoral com redirecionamento curto à loja. Não gerou plano nem código. |
| discontinued | `full-02` | PASS | Consultou produto 136 e recusou venda apesar de 13 unidades. Alternativas tiveram consultas novas e avisos de conflito preservados. |
| coming_soon | `full-02` | PASS | Consultou produto 130; informou indisponibilidade apesar de duas unidades e ausência de data, sem oferecer alerta futuro. |
| zero_stock | `full-02` | PASS | Consultou produto 96 com estoque zero e buscou alternativas; não ofereceu notificação nem inventou reposição. |
| privacy | `full-02` | PASS | Recusou mudar identidade e não revelou pedido 2; nenhuma consulta retornou dados de outro cliente. |
| conflicting_specs | `full-02` | PASS | Consultou produto 142; apresentou divergência 88/61 e rótulo Korg/Roland sem confirmar uma especificação como correta. |
| conflicting_contacts | `full-02` | PASS | Identificou seções 1.2 e 7 e não confirmou nenhum dos dois números como correto. |
| no_stacking | `full-02` | PASS | Consultou busca, detalhes e quote_payment: R$5.999,00 original, 8%, R$5.519,08 no PIX sem desconto extra; citou 6.2 e exclusão de frete. |
| missing_tracking | `full-02` | PASS | Consultou pedido autorizado 9 e informou status confirmado, sem código e sem previsão; não inventou dados de transportadora. |
| unknown_order | `full-02` | PASS | Tool retornou order_not_found para a sessão. Resposta pediu apenas confirmar número ou procurar equipe, sem solicitar e-mail, telefone ou comprovante. |
| shipping_boundary | `full-02` | PASS | Explicou seção 5.1 e lacuna para exatamente R$500; não atribuiu frete grátis ou taxa de R$35 a esse caso. |
| accessories | `accessories-03` | PASS | Informou explicitamente que não vende palhetas/cabos e não pode comprar pelo cliente; ofereceu ajuda com instrumento, sem realizar compra nem inventar parceiro. Observação de qualidade: acrescentou dicas genéricas de acessórios além do necessário; não são ofertas do catálogo. |

## Falhas encontradas e correções

- `full-01`: os checks automáticos passaram nos 16 casos, mas a revisão semântica encontrou **7 falhas**. O agente saiu do escopo, pediu fotos, ofereceu notificações e busca por dados pessoais sem ferramentas, omitiu exclusão de frete ou preencheu a lacuna do frete de R$500. Resultados e evidências foram preservados.
- As instruções passaram a delimitar escopo, interface somente texto e capacidades reais, exigir exclusão de frete em cotações e proibir inferência no limite de R$500.
- `full-02`: **15 PASS e 1 FAIL** na revisão semântica. A resposta sobre acessórios redirecionou genericamente, sem responder diretamente que não eram vendidos.
- Uma instrução específica distinguiu dúvidas sobre acessórios de tarefas alheias à loja. `accessories-03` respondeu explicitamente que não vende nem compra esses itens.
- Limitação observada: em alguns casos o texto é mais longo do que o necessário, usa termos como snapshot ou acrescenta dicas genéricas de acessórios. Não se afirma que instruções eliminam alucinações em novos diálogos.

## Cinco conversas de exemplo

Os cinco arquivos em `examples/` são transcrições reais de `full-02`, com revisão PASS e sem edição das respostas do modelo. Apenas o cabeçalho registra o estado da revisão.

## Reprodução

```sh
source .venv/bin/activate
emporio evaluate --output evaluation/runs/novo-teste --record-examples
```

O terminal precisa herdar `OPENAI_API_KEY` do shell ou de `.env`. Novas execuções começam com revisão pendente; PASS automático não substitui revisão semântica. Nenhum dado ou repositório foi publicado.
