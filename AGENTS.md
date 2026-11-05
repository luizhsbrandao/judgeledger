# AGENTS.md — judgeledger

Regras para qualquer agente (Claude Code, Antigravity, OpenCode) que trabalhe neste repositório.
Vale junto com `~/.agents/STATION-RULES.md`; onde as duas falarem, vale a mais restritiva.

## O que é

`judgeledger` — registro local, encadeado por hash, de **juízos analíticos**: a pergunta e o critério
que a resolve são travados **antes** do fato; a resolução entra com citação. O relatório diz se a
incerteza declarada era real (CRPS). CLI `jl`, schema versionado, suíte de testes em `tests/`.

O produto é a **integridade da cadeia**: `schema/` e a lógica de hash/verificação são o núcleo. Se um
teste de integridade falhar, o repositório está quebrado — não o teste.

## Comandos

```bash
.venv/bin/python -m pytest -q          # verificação canônica
.venv/bin/pip install -e ".[dev]"      # se .venv não existir
.venv/bin/jl --help                    # CLI
bash scripts/smoke.sh                  # fumaça ponta a ponta (se existir)
```

Não rode `npm`, `make` ou instalador de terceiro. `ruff` não está configurado aqui.

## Regras

- **`schema/` é contrato público**: mudança ali exige versão nova e nota de migração, nunca edição
  silenciosa. Registro antigo que deixa de verificar é perda de dado, não bug cosmético.
- **Nunca** reescreva história de ledger em teste (nem com `VCR`/fixture): gere entradas novas.
- **Não edite** `dist/`, `build/` nem `examples/` sem pedido — exemplo é documentação executável.
- Diff pequeno, um assunto por commit. Mensagem em português, imperativa, com o porquê.
- **Nunca** `git push`, `git add -A`, `git reset --hard`, `git clean`; árvore pronta, commit e push
  são do operador.
- Segredo não se lê (`.env`, `*.pem`, `*.key`, `.ssh`, `.gnupg`). O `pre-commit` roda gitleaks com
  `.gitleaks.toml` e **falha fechado**.

## Verificação

Quem roda teste é o operador ou o wrapper — não você. Com shell, use **apenas**
`.venv/bin/python -m pytest`. Relate o que verificou de fato, com comando e saída.
