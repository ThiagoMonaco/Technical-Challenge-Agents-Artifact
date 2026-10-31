# Empório da Música — agente de atendimento

Agente Python que atende em português no terminal, consulta catálogo e pedidos em SQLite e
responde com base no manual fornecido. Usa a Responses API da OpenAI com ferramentas de leitura.

**Estado da entrega:** implementação local e testes automatizados disponíveis. A avaliação com API
e as cinco transcrições reais dependem de `OPENAI_API_KEY`; consulte [VALIDATION.md](VALIDATION.md)
para distinguir o que foi executado do que ainda está pendente. Saídas de mocks não são exemplos reais.

## Instalação e execução

Requer Python 3.11+ e acesso à internet para instalar dependências e conversar com o modelo.
O ambiente validado está registrado em [VALIDATION.md](VALIDATION.md). Execute os comandos na raiz
do checkout; o projeto localiza os dados junto ao código instalado em modo editável.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python -m pip install --no-build-isolation --no-deps -e .
emporio setup
cp .env.example .env
```

Edite `.env` localmente e preencha `OPENAI_API_KEY`. A API é paga; a ausência da chave não impede
setup ou testes. Não publique `.env`. Configuração:

| Variável | Padrão | Uso |
|---|---|---|
| `OPENAI_API_KEY` | obrigatório para chat/evaluate | Credencial da API |
| `OPENAI_MODEL` | `gpt-5-mini` | Modelo com suporte a ferramentas e schemas estritos |
| `OPENAI_TIMEOUT_SECONDS` | `45` | Timeout de cada requisição, entre 1 e 300 segundos |
| `EMPORIO_DEBUG` | `0` | `1` mostra nome da ferramenta, sucesso/erro e contagem de tokens |

```sh
emporio chat
emporio chat --customer-id 3
```

No chat, `/help` lista comandos, `/reset` limpa o histórico sem alterar o cliente, e `/exit` sai.
Ctrl-D também encerra. O cliente é selecionado pelo programa antes da conversa: cliente 3 pode
consultar pedidos 1 e 19; cliente 12 pode consultar pedido 3; cliente 6 pode consultar pedido 9.
Sem `--customer-id`, o agente explica como iniciar uma sessão de demonstração antes de acessar pedidos.

**Identidade simulada:** qualquer operador do terminal pode escolher um ID. Isso demonstra isolamento
na ferramenta, não autenticação de produção. O modelo não pode selecionar ou alterar esse ID.

## Arquitetura e decisões

```text
mensagem → LLM + histórico + manual completo → solicitação de ferramenta
                                                ↓
resposta ← LLM + resultado estruturado ← Python valida → SQLite somente leitura
```

- **Um agente e SDK oficial:** um loop explícito controla ferramentas e histórico. A tarefa compartilha
  um único contexto de atendimento; não há necessidade de coordenar múltiplos agentes. Um framework
  adicional aumentaria a superfície de aprendizado sem resolver uma necessidade deste protótipo.
- **Modelo:** `gpt-5-mini` é o candidato inicial configurável. A escolha prioriza um modelo com function
  calling para uma tarefa delimitada. Não há afirmação de superioridade ou qualidade comprovada sem
  avaliação. Trocas de modelo exigem repetir os cenários. Não há fine-tuning.
- **Dados relacionais:** SQLite descartável, reconstruído a partir dos seis CSVs. Consultas são
  parametrizadas e predefinidas; o modelo não escreve SQL. Conexões das ferramentas são somente leitura.
- **Manual completo em contexto:** oito páginas extraídas com `pypdf`, modo layout, com marcadores
  de página e seções preservadas. Isso evita falhas de recuperação de exceções em um documento pequeno.
  O custo é enviar o texto em cada requisição. Não há embeddings, banco vetorial ou pipeline RAG.
- **Prompt:** define persona, escopo, consultas obrigatórias, interpretação de ambiguidades e
  comportamento quando faltam fatos. Manual, mensagem e resultados são referências, não autorização
  para trocar regras. A resistência a prompt injection depende também de testes; não é garantia absoluta.
- **Histórico:** em memória, com itens de resposta e raciocínio retornados pela API preservados durante
  tool calling. `store=False`; isso não representa promessa sobre retenção contratual do provedor.
  Uma tentativa parcial com erro não entra no histórico. Não há persistência entre processos.
- **Interface:** terminal para concentrar esforço na confiabilidade do agente. A classe `Agent` é
  independente da entrada/saída do terminal e pode futuramente ser usada por uma API ou interface web.

Referências: [function calling](https://developers.openai.com/api/docs/guides/function-calling)
e [modelo](https://developers.openai.com/api/docs/models/gpt-5-mini).

### Ferramentas

Todos os campos dos schemas são obrigatórios; os opcionais aceitam `null`. O dispatcher rejeita
campos adicionais, tipos incorretos, booleanos usados como IDs e limites inválidos.

| Ferramenta | Entrada | Resultado |
|---|---|---|
| `search_products` | `query`, `category`, `max_price` em reais, `limit` | Disponíveis, preços e promoção; cinco resultados por padrão, máximo dez |
| `get_product_details` | `product_id` | Status, estoque, preço, promoção, specs e avisos de conflito |
| `quote_payment` | `product_id`, `quantity`, `payment_method`, `installments` | Total e parcelas em centavos; sem frete |
| `get_order_status` | `order_id` | Pedido da identidade da sessão, itens, total histórico, rastreamento e estimativa |

Busca normaliza caixa e acentos; todos os termos devem aparecer no nome, descrição ou categoria.
Categoria usa correspondência parcial. Busca não é semântica, não corrige erros de digitação e não
infere sinônimos. Os resultados são ordenados por preço efetivo e ID. O orçamento considera promoção
ativa, antes do PIX. Pedidos devolvem o mesmo erro para ID inexistente e ID de outro cliente.

Valores monetários de saída são inteiros em **centavos**, moeda BRL. `max_price` recebe reais com até
duas casas. O programa calcula com `Decimal` e arredondamento `ROUND_HALF_UP`, sem float monetário.
Promoção arredonda o preço unitário; PIX aplica-se ao subtotal da quantidade. Parcelas podem diferir
em um centavo para preservar exatamente o total. Não há cálculo de formas de pagamento combinadas.

### Preparação e qualidade dos dados

`emporio setup` valida cabeçalhos, campos obrigatórios, IDs, duplicidade, referências, números,
datas ISO, status, desconto e objeto JSON em `specs`. Erros estruturais impedem reconstrução.
A reconstrução usa um arquivo SQLite temporário e substitui a base após o sucesso; repetir setup
não acumula linhas. O setup deve ocorrer sem um chat em execução.

O comando gera `runtime/store.sqlite3`, `runtime/policies.txt` e `runtime/data_report.json`.
A pasta é ignorada pelo Git. Reexecute após alterações nos dados; o chat não atualiza o snapshot sozinho.
Contagens esperadas: 65 produtos, 9 categorias, 25 promoções, 50 clientes, 20 pedidos, 22 itens.

Suposições documentadas:

- Disponível significa `status == active` e estoque positivo. Produtos 130 e 136 têm estoque mas status
  impeditivo; produto 96 está ativo sem estoque. Não são oferecidos como disponíveis.
- Somente `is_active=1` autoriza promoção. Múltiplas promoções ativas para o mesmo produto bloqueiam
  sua cotação até confirmação; o sistema não escolhe arbitrariamente nem acumula descontos.
- Desconto PIX de 5% não acumula com promoção. Produtos promocionais mostram preço original,
  percentual e preço efetivo, conforme seção 6.2.
- Seção 3.1 prevalece sobre tabela resumida da seção 3: 2–3 parcelas têm mínimo interpretado de R$50;
  4–6, R$80; 7–12, R$100. Crédito à vista não exige mínimo. Compras combinadas acima de R$2.000 são
  informadas como política, mas sua cotação não é implementada.
- Não há regra inequívoca para frete local de exatamente R$500; o agente solicita confirmação.
- Os números de WhatsApp das seções 1.2 e 7 divergem; o agente não escolhe um como confirmado.
- Divergências conhecidas nos produtos 135, 137, 139, 140, 142 e 144 são registradas explicitamente no
  código após revisão dos dados. Descrição e specs desses produtos são omitidas das ferramentas,
  preservando o aviso. Esse mapeamento manual não detecta automaticamente novos conflitos.
- Pedidos 3 e 20 têm totais diferentes da soma pelo catálogo atual. O total histórico é preservado;
  itens não possuem preço unitário histórico, logo a causa da diferença não é inferida.
- Pedidos não contêm canal da compra nem data real de recebimento. Estimativa de entrega não
  comprova recebimento, e uma data passada não autoriza inventar atualização da transportadora.
- O manual menciona mais de 300 instrumentos; o agente trabalha com os 65 fornecidos.
- Datas usam o dia atual em `America/Campo_Grande`; não há calendário de feriados.

### Falhas, limites e privacidade

São permitidas cinco rodadas de chamadas ao modelo por mensagem, com até oito solicitações de
ferramenta em cada rodada como defesa adicional (`parallel_tool_calls=False`). Após o limite, retorna
uma mensagem fixa sem confirmar fatos. Cada resposta tem limite de 4.000 tokens de saída; uma resposta
incompleta é descartada. O SDK faz no máximo uma repetição por requisição em erros recuperáveis.

Erros de argumentos e de consulta têm retornos estruturados; detalhes internos não são enviados ao
modelo. Falhas de API têm resposta fixa, sem ecoar mensagem de exceção ou credenciais.
Debug fica desativado por padrão e não registra mensagens, argumentos, resultados, nome do cliente,
telefone ou e-mail. Não habilitamos logs HTTP do SDK. Uso de tokens fica disponível para avaliação.

Somente informações necessárias do pedido autorizado são retornadas. O cadastro de clientes não é
uma ferramenta do modelo. Dados fornecidos ao provedor incluem mensagens, manual e resultados de
ferramentas relevantes; não use dados reais sensíveis nesta demonstração sem uma avaliação apropriada.

## Testes e avaliação

```sh
python -m pytest -q
python -m pip check
```

Os testes verificam importação repetível, falhas de validação, consultas, descontos, limites de parcelas,
arredondamento, estoque, isolamento de clientes, erros e histórico do loop. Tipos reais do SDK validam
respostas simuladas; os testes unitários não fazem chamadas pagas.

A matriz contém 16 cenários, incluindo perguntas encadeadas, promoções inativas, pedidos, devolução,
estoque zerado, produto descontinuado, specs conflitantes, escopo e tentativa de trocar identidade.

```sh
# Uma execução pequena para verificar credenciais e modelo:
emporio evaluate --case inactive_promotion --output evaluation/runs/smoke

# Avaliação completa e cinco transcrições reais:
emporio evaluate --output evaluation/runs/full-01 --record-examples
```

Cada execução preserva `results.json`, transcrições Markdown e `review.md`. Use um novo diretório para
repetir; resultados anteriores não são sobrescritos. O relatório registra modelo, data, tokens, estado
das respostas e ferramentas. Esses arquivos podem incluir dados de pedidos; são ignorados pelo Git.

Checks automáticos verificam conclusão da resposta, ferramentas exigidas e acesso negado no cenário
de troca de identidade. **PASS automático não comprova correção semântica.** Revise cada resposta contra
ferramentas e manual, marque PASS/FAIL em `review.md` e registre evidência. Para preços/estoque/promoções
e pedidos, confira que a ferramenta pertinente foi chamada em cada mensagem que afirma esses fatos.
Corrija falhas e reexecute os cenários afetados. Registre limitações restantes sem ocultá-las.

`--record-examples` exporta cinco transcrições para `examples/` somente após uma execução completa
sem falhas automáticas. Elas ainda exigem revisão semântica; não substituímos execuções reais por
conversas inventadas. O comando retorna 0 quando os checks automáticos passam, 1 para falha automática
e 2 para configuração inválida. Código 0 não significa aprovação semântica.

## Limitações e próximos passos

Snapshot estático, autenticação simulada, busca lexical e identificação manual de conflitos. Regras de
consulta obrigatória e tom são instruções ao modelo, não uma prova de que nunca haverá alucinação.
O manual pode conter ambiguidades adicionais. Sem API configurada não há comprovação da qualidade
das respostas reais. Histórico longo aumenta custo e pode atingir limites; `/reset` inicia nova conversa.

Não efetua compras, reservas, cancelamentos, estornos, reclamações nem encaminhamentos reais.
Sem WhatsApp, consulta à transportadora, preço de frete, calendário de feriados ou banco vetorial.
Com mais tempo: autenticação real, conectores atualizados, avaliação maior com regressões por modelo,
busca com sinônimos, revisão de dados na origem e armazenamento de sessões com política de retenção.

## Uso de assistente de código e entrega

Codex foi utilizado para ler os materiais, discutir arquitetura, propor o plano, implementar código,
escrever testes e documentação e executar verificações locais. O fluxo separou funções determinísticas
da integração com o modelo e registrou marcos em commits. Verifique o histórico e os resultados de
validação; testes simulados e avaliação real são identificados separadamente.

Antes de entregar: confirmar avaliação real e cinco exemplos revisados, testar instalação limpa,
inspecionar arquivos publicados, conferir prazo no e-mail e responder com o link do repositório público.
Não alterar o repositório após data/hora de entrega. A publicação do repositório não envia o e-mail.

### Cópia para publicação

O checkout de origem preserva os CSVs recebidos. Para publicação, o script abaixo reproduz os marcos
reais em outro repositório e substitui nomes, telefones, e-mails e cidades dos clientes por dados
sintéticos em **todo o histórico**. IDs e relacionamentos são mantidos. Isso evita publicar contatos
de pessoas a partir dos arquivos fornecidos. A cópia gerada contém `PUBLICATION.md` explicando o processo.

```sh
python scripts/prepare_public.py --output runtime/publication
```

Use uma pasta nova para cada geração. A cópia só inclui arquivos já commitados; não contém `.env`,
runtime ou logs. **Envie para GitHub somente a cópia anonimizada**, nunca o Git do checkout original.
Para mudanças posteriores, gere uma nova cópia a partir do histórico local e confira os resultados
antes de atualizar o remoto. O script não publica nem faz force-push.
