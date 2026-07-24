# Agentic Flow

Uma ferramenta low-code para criar e executar agentes de IA visualmente. O frontend é declarado com **PyReact**, a API usa **FastAPI** e cada canvas é compilado dinamicamente para um **LangGraph `StateGraph`**.

## O que está pronto

- Editor visual com arrastar e soltar, conexões, zoom, minimapa e auto-layout.
- Inspetor de propriedades gerado pelo schema de cada tipo de nó.
- Nós de Entrada, Webhook, Prompt, Modelo LLM, Agente IA, Condição, Transformação, HTTP, Memória e Saída.
- Vários agentes no mesmo workflow, com papéis e campos de entrada/saída independentes.
- URL de webhook aleatória e persistente para cada nó de gatilho.
- LLM em modo simulado (funciona sem chave) ou OpenAI real.
- Condições com rotas `true` / `false`.
- Persistência SQLite, versões e histórico de execuções.
- Playground JSON com resposta e tracing por nó.
- Validação de referências, tipos, ciclos e ramificações.
- API documentada automaticamente em `/docs`.

## Primeiro acesso e autenticação

Na primeira inicialização, `http://127.0.0.1:8000` redireciona obrigatoriamente para `/setup`. Crie:

- o usuário administrador;
- a senha inicial;
- o primeiro workspace.

Depois disso, a configuração inicial é desativada e os próximos acessos exigem login. A sessão é armazenada em cookie assinado, com validade de 14 dias. Workflows e execuções só podem ser acessados por membros do workspace correspondente.

Após o login, `/dashboard` lista todos os workflows e permite criar novos canvases independentes. O editor agora fica em `/workflows/{id}`.

## Executar localmente

O ambiente atual já contém o PyReact. Instale o projeto e inicie:

```powershell
python -m pip install -e .
python -m agentic_flow.main
```

Abra `http://127.0.0.1:8000`. Um workflow de exemplo será criado automaticamente.

Para usar um modelo real:

```powershell
$env:OPENAI_API_KEY="sua-chave"
python -m agentic_flow.main
```

No nó **Agente IA** ou **Modelo LLM**, altere o provedor de `mock` para `openai`. A chave não é salva no workflow; apenas o nome da variável de ambiente é persistido.

Sem `DATABASE_URL` ou `DB_HOST`, o desenvolvimento local usa SQLite em `data/agentic-flow-v2.db`.

## Docker e MySQL

Copie as configurações e troque todas as senhas:

```powershell
Copy-Item .env.example .env
```

No mínimo, defina valores fortes e únicos para:

```dotenv
MYSQL_PASSWORD=...
MYSQL_ROOT_PASSWORD=...
SESSION_SECRET=...
```

Inicie toda a stack:

```powershell
docker compose up -d --build
docker compose ps
```

O Compose sobe:

- `agentic-flow`: aplicação FastAPI/PyReact na porta `8000`;
- `mysql`: MySQL 8.4 com healthcheck e UTF-8 completo.

Os volumes nomeados persistem fora dos containers:

- `agentic_flow_mysql_data`: usuários, workspaces, memberships, workflows e runs;
- `agentic_flow_app_data`: dados auxiliares da aplicação.

Assim, `docker compose down` e novos builds não removem os dados. Para remover tudo deliberadamente seria necessário executar `docker compose down -v`.

Em produção com HTTPS, configure também:

```dotenv
COOKIE_SECURE=true
```

## Webhooks

Arraste o nó **Webhook** para o canvas, conecte-o ao primeiro agente e salve. O inspetor exibirá uma URL exclusiva:

```text
http://127.0.0.1:8000/webhooks/wh_TOKEN_ALEATORIO
```

Qualquer ferramenta externa pode iniciar aquele workflow com:

```powershell
Invoke-RestMethod `
  -Method Post `
  -ContentType "application/json" `
  -Uri "http://127.0.0.1:8000/webhooks/wh_TOKEN_ALEATORIO" `
  -Body '{"message":"Nova mensagem externa"}'
```

O JSON recebido é disponibilizado diretamente aos agentes. Cada URL inicia somente o nó de gatilho e o workflow associados, e a execução fica salva no histórico.

## Testes

```powershell
pytest
```

## Estrutura

```text
agentic_flow/
├── catalog.py       # catálogo/schema dos nós
├── engine.py        # validação e compilação LangGraph
├── main.py          # API FastAPI e bootstrap
├── models.py        # contratos Pydantic
├── store.py         # persistência relacional MySQL/SQLite
├── ui.py            # componentes declarativos PyReact
└── static/
    ├── app.js       # interações do canvas
    └── styles.css   # sistema visual
```

`store.py` usa SQLAlchemy e funciona com MySQL em deploy e SQLite no desenvolvimento/testes.

## Como adicionar um nó

1. Inclua sua definição em `NODE_CATALOG`, com campos e valores padrão.
2. Implemente o executor correspondente em `WorkflowEngine._execute_node`.
3. Adicione um teste de execução.

O mesmo catálogo alimenta a barra lateral, o inspetor, a validação e a execução, evitando configurações duplicadas entre UI e backend.
