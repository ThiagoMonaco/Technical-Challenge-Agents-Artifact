# Conversas reais

As cinco conversas devem ser capturadas pelo programa, não escritas como respostas hipotéticas.

```sh
emporio evaluate --output evaluation/runs/full-01 --record-examples
```

Após configurar a API, o comando executa os 16 cenários e exporta `budget.md`,
`inactive_promotion.md`, `order.md`, `return.md` e `out_of_scope.md` se os checks automáticos passarem.
Revise semanticamente cada conversa e registre os resultados em `evaluation/runs/full-01/review.md`
antes de considerar a entrega concluída. Sem execução real, estes cinco arquivos permanecem ausentes.
