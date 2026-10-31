# Conversas reais

Estas cinco conversas foram capturadas em uma execução real da API (`gpt-5-mini`, `full-02`, 31/10/2026)
e revisadas por Codex contra ferramentas e políticas. As respostas não foram reescritas:

- [Busca por orçamento e pagamento PIX](budget.md)
- [Promoção inativa](inactive_promotion.md)
- [Status e total histórico de pedido](order.md)
- [Devolução com informações faltantes](return.md)
- [Pedido fora do escopo](out_of_scope.md)

Evidências e limitações: [matriz de avaliação](../evaluation/REVIEW.md).
Para gerar novas conversas reais em vez de usar respostas hipotéticas:

```sh
emporio evaluate --output evaluation/runs/novo-teste --record-examples
```

O comando executa os 16 cenários e exporta `budget.md`,
`inactive_promotion.md`, `order.md`, `return.md` e `out_of_scope.md` se os checks automáticos passarem.
Revise semanticamente cada conversa e registre os resultados no `review.md` da nova execução.
Novas transcrições começam com revisão pendente mesmo quando os checks automáticos passam.
