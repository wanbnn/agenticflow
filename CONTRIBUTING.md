# Contribuindo com o Agentic Flow

Obrigado por ajudar a tornar a criação de agentes mais acessível.

Ao participar, você concorda com o [Código de Conduta](CODE_OF_CONDUCT.md).

## Antes de começar

1. Procure por uma issue ou discussão existente.
2. Para mudanças grandes, abra uma proposta antes da implementação.
3. Nunca inclua API keys, `.env`, bancos, tokens ou dados pessoais.
4. Mantenha cada pull request focado em um único objetivo.

## Ambiente recomendado

O Docker instala todo o ambiente de desenvolvimento:

```bash
git clone https://github.com/wanbnn/agenticflow.git
cd agenticflow
cp .env.example .env
docker compose up -d --build
```

Não é necessário instalar Python, MySQL, PyReact ou LangGraph no host.

Para executar a suíte de testes rapidamente no host:

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

## Fluxo de trabalho

```bash
git checkout -b tipo/descricao-curta
```

Prefixos sugeridos:

- `feat/` para funcionalidades;
- `fix/` para correções;
- `docs/` para documentação;
- `refactor/` para refatorações;
- `test/` para testes;
- `chore/` para manutenção.

Antes do commit:

```bash
python -m pytest
python -m compileall -q agentic_flow tests
node --check agentic_flow/static/app.js
```

Use mensagens objetivas, preferencialmente no padrão Conventional Commits:

```text
feat: add calendar trigger node
fix: isolate provider credentials by workspace
docs: clarify production deployment
```

## Pull requests

Um pull request deve:

- explicar problema, solução e trade-offs;
- referenciar a issue relacionada;
- incluir testes para comportamento novo;
- preservar compatibilidade de dados quando aplicável;
- atualizar README ou changelog em mudanças públicas;
- incluir imagens quando alterar a interface;
- passar pelo CI.

## Adicionando nós

1. Defina tipo, campos e defaults em `agentic_flow/catalog.py`.
2. Implemente a execução em `agentic_flow/engine.py`.
3. Garanta que dados sensíveis não sejam expostos nos eventos.
4. Adicione testes em `tests/`.
5. Documente entradas, saídas e possíveis erros.

## Segurança

Vulnerabilidades não devem ser abertas como issues. Siga
[SECURITY.md](SECURITY.md).
