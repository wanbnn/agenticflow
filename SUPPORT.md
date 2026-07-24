# Suporte

## Onde pedir ajuda

- **Dúvidas de uso e instalação:** abra uma
  [Discussion](https://github.com/wanbnn/agenticflow/discussions).
- **Bug reproduzível:** use o template de bug em
  [Issues](https://github.com/wanbnn/agenticflow/issues/new/choose).
- **Sugestão de funcionalidade:** use o template de feature request.
- **Vulnerabilidade:** siga [SECURITY.md](SECURITY.md); não abra issue pública.

## Antes de abrir uma solicitação

Consulte o [README](README.md), execute `docker compose ps` e revise:

```bash
docker compose logs --tail=200 agentic-flow
docker compose logs --tail=200 mysql
```

Remova senhas, cookies, API keys, tokens, payloads privados e dados pessoais
antes de anexar logs.

Inclua:

- versão ou SHA utilizado;
- sistema operacional e versão do Docker;
- passos para reprodução;
- resultado esperado e observado;
- logs sanitizados;
- configuração relevante sem segredos.

O projeto é mantido pela comunidade e não oferece SLA de suporte.
