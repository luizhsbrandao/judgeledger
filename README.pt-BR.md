# judgeledger

Um ledger local de julgamentos analíticos. Você registra a pergunta **e o critério que vai
resolvê-la** antes do fato; a entrada é hasheada num log append-only; quando o desfecho chega, você
resolve com uma citação. O relatório então mostra se a incerteza declarada era real.

```console
$ jl add "O Programa Alfa entrega o módulo 2 até 31/03" \
    --criteria "Release notes assinadas e deploy em produção registrado no changelog" \
    --due 2025-03-31 --interval 0.60 0.80
E001 created as draft — [0.60, 0.80], due 2025-03-31
```

## Por que não um tracker de calibração existente

A aritmética não é a lacuna. `scikit-learn` traz `brier_score_loss` e `calibration_curve`;
`forecast-calibration-kit` implementa Brier, log loss, ECE e a decomposição de Murphy; `brierly` já
faz o laço registrar → resolver → pontuar num PWA local. Recalcular esses números não acrescentaria
nada.

A lacuna é **integridade**. Nenhum deles impede reescrever a pergunta, ou o critério de resolução,
depois de já saber a resposta — o que torna o histórico que produzem contestável, e um histórico
contestável não defende julgamento nenhum. O `judgeledger` impõe as propriedades:

- **travado na criação** — pergunta, critério e prazo entram hasheados no log de eventos; editar
  depois é erro de integridade, não edição;
- **sem retrodatação** — o prazo tem de ser posterior à data de criação;
- **sem fonte, não aconteceu** — a resolução exige citação e uma URL (ou URL de arquivo);
- **anulada não é erro** — questão com critério falho vira `void`, com motivo, contada à parte de
  acertos e erros;
- **a cadeia é verificável** — cada ação carrega o digest da anterior.

## Instalação

A publicação no PyPI está pendente (o trusted publisher está configurado do lado da conta, ainda
não do projeto). Até lá, instale direto do repositório:

```console
$ pipx install git+https://github.com/luizhsbrandao/judgeledger
# ou: uv tool install git+https://github.com/luizhsbrandao/judgeledger
```

Quando a 0.1.0 estiver no índice, vira `pipx install judgeledger`. Python ≥ 3.11, sem dependência
de runtime.

## Uso

```console
$ jl init ledger-2027 --actor LH
$ jl add "H2 colapsa antes de 2027-06" \
    --criteria "Duas leituras mensais consecutivas abaixo do limiar declarado" \
    --due 2027-06-30 --interval 0.55 0.80 --tags ira --origin achlab:caso-11#H2
$ jl open                     # trava todos os rascunhos; nada pode ser reescrito daqui em diante
$ jl resolve E001 --outcome 1 \
    --citation "Relatório Z, p. 12" --url https://example.org/z-12 --excerpt "…"
$ jl score                    # CRPS, Brier, base rate, sharpness, Murphy
$ jl report --md report.md    # Markdown determinístico, com as fontes
$ jl validate                 # exit 2 em qualquer violação de integridade
$ jl verify                   # exit 2 quando a cadeia de hash quebra
$ jl demo                     # 44 julgamentos sintéticos, 40 resolvidos
```

Códigos de saída são contrato: `0` ok, `2` violação de integridade, `3` dados insuficientes para
curva de calibração (menos de 20 julgamentos resolvidos).

## Pontuação

A unidade de previsão é um intervalo `[l, u]`; previsão pontual é o intervalo degenerado `[p, p]`.
O score primário é o CRPS da uniforme nesse intervalo contra o desfecho binário:

```
CRPS([l,u], y) = (u−l)/3 + (l−y)                se y ≤ l
                 (u−l)/3 + (y−u)                se y ≥ u
                 [(y−l)³ + (u−y)³] / (3(u−l)²)   se l < y < u
```

Como `y ∈ {0,1}`, na prática a fórmula colapsa para `(u + 2l)/3` (desfecho 0) e
`(3 − 2u − l)/3` (desfecho 1). CRPS é próprio: declarar a incerteza real é a estratégia ótima, então
alargar a banda para se proteger custa caro, e estreitar sem base também. O Brier no ponto médio é
reportado ao lado, por familiaridade, mas nunca ranqueia — ele premia banda estreita por si só. A
curva de calibração sai por bin, as bandas declaradas são comparadas com a frequência observada por
faixa de largura, e a decomposição `BS = REL − RES + UNC` é impressa para qualquer leitor
recomputar. Fórmulas e exemplo calculado à mão em
[`docs/pontuacao.md`](docs/pontuacao.md).

## Importar de uma análise ACH

`jl import achlab caso.json --hypothesis H2 --interval 0.6 0.85` transforma uma hipótese de um caso
do [`achlab`](https://github.com/luizhsbrandao/achlab) num julgamento escorável. O `--interval` é
**obrigatório**: a faixa de confiança descreve a análise, não a probabilidade da hipótese, então ela
viaja como metadado e nunca é convertida em número pela ferramenta.

## O que ele não faz

- sem servidor, sem conta, sem interface web — o ledger é um diretório que você põe no git;
- sem LLM e sem resolução automática (nada de scraping ou preço de mercado): quem resolve é uma
  pessoa, com fonte;
- sem ranking de pessoas e sem comparação entre ledgers;
- sem assinatura criptográfica — a cadeia de hash detecta edição acidental ou oportunista, não um
  adversário que tem o arquivo inteiro. O `SECURITY.md` diz o mesmo.

## Dados

Tudo em `examples/` é sintético. Um ledger real é dado pessoal: mantenha fora do repositório público
(o `.gitignore` cobre `ledger/`). Sem informação classificada, sem dado pessoal.

## Desenvolvimento

```console
$ python -m venv .venv && . .venv/bin/activate
$ pip install -e ".[dev]"
$ python -m pytest
$ bash scripts/smoke.sh
```

A suíte cobre a fórmula fechada do CRPS contra integração numérica, cada regra de integridade,
adulteração dos dois arquivos, determinismo do relatório e os códigos de saída da CLI.

## Licença

MIT.
