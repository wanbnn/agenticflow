# Changelog

Todas as mudanças relevantes do Agentic Flow serão documentadas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o
projeto adota [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não lançado]

## [0.3.0] - 2026-07-31

### Adicionado

- distribuição `agenticflow-studio` no PyPI e comando `agenticflow`;
- instalador PowerShell baseado em pipx;
- detecção automática e instalação de CUDA, ROCm, MPS ou CPU;
- instalação oficial do llama.cpp adequada à GPU;
- biblioteca Hugging Face paginada, modelos GGUF e seletor de quantização;
- runtimes locais para LLM, visão, áudio, imagem, vídeo e 3D.

### Alterado

- SQLite passa a ser o único banco interno da aplicação, sem servidor externo;
- drivers MySQL, PostgreSQL, SQL Server e BigQuery continuam disponíveis para nós;
- dados da instalação PyPI ficam no diretório de aplicação do usuário.

### Corrigido

- fila exclusiva e descarregamento sincronizado de modelos locais;
- adaptação de snapshots MLX/CoreML e pipelines Diffusers experimentais;
- entradas multimodais, previews no canvas e roteamento automático entre nós.

### Adicionado

- runtime self-hosted para LLM, visão, áudio, imagem, 3D e embeddings;
- catálogo, download e gerenciamento de modelos do Hugging Face Hub;
- suporte ROCm 7.14/PyTorch 2.12 com lock das arquiteturas AMD `gfx`;
- nós de modelo local multimodal e entrada tipada de áudio;
- documentação comunitária e templates do GitHub;
- workflow de integração contínua;
- README orientado a deploy Docker.

### Corrigido

- ordem de inserção do usuário, workspace e membership no bootstrap MySQL;
- favicon da aplicação, evitando respostas 404 nos acessos.
- bloqueio de endpoints OpenAI-compatible protegidos por Cloudflare devido ao
  `User-Agent` padrão do SDK.
- respostas HTTP 419 em APIs compatíveis, removendo headers automáticos
  `x-stainless-*` e usando transporte HTTP mínimo.

## [0.2.0] - 2026-07-24

### Adicionado

- bootstrap obrigatório do administrador;
- login, sessões e isolamento por workspace;
- dashboard com múltiplos workflows;
- persistência MySQL via SQLAlchemy;
- gerenciamento visual e criptografado de provedores;
- OpenAI, Anthropic, Ollama e APIs compatíveis;
- Dockerfile, Compose, healthchecks e volumes persistentes.

## [0.1.0] - 2026-07-24

### Adicionado

- editor visual PyReact;
- execução de workflows com LangGraph;
- nós de agentes, prompts, condições, HTTP, memória e saída;
- gatilhos webhook;
- histórico e tracing de execuções.
