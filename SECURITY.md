# Política de segurança

## Versões suportadas

O Agentic Flow está em desenvolvimento ativo. Correções de segurança são
aplicadas à versão mais recente da branch `main`.

| Versão | Suporte |
| --- | --- |
| `main` / release mais recente | ✅ |
| Versões anteriores | ❌ |

## Como reportar uma vulnerabilidade

Não publique vulnerabilidades, chaves, tokens, dados pessoais ou detalhes de
exploração em issues públicas.

Use o recurso **Report a vulnerability** do GitHub:

<https://github.com/wanbnn/agenticflow/security/advisories/new>

Inclua, quando possível:

- componente e versão afetados;
- impacto observado;
- passos mínimos para reprodução;
- prova de conceito sem dados reais;
- mitigação sugerida;
- forma segura de contato.

O recebimento será confirmado assim que possível. Após triagem, os mantenedores
informarão severidade, plano de correção e previsão de divulgação. Pedimos que
os detalhes permaneçam privados até a publicação coordenada da correção.

## Responsabilidade do operador

Uma implantação segura deve:

- trocar todas as senhas padrão do `.env`;
- usar HTTPS e `COOKIE_SECURE=true` em produção;
- manter `SESSION_SECRET` e `CREDENTIALS_ENCRYPTION_KEY` fortes e estáveis;
- restringir o MySQL à rede interna;
- não publicar portas administrativas do banco;
- atualizar imagens e dependências regularmente;
- proteger backups e volumes Docker;
- rotacionar credenciais de provedores quando houver suspeita de exposição;
- revisar logs antes de compartilhá-los.

As API keys de provedores são criptografadas em repouso, mas a segurança final
depende também da proteção da chave de criptografia e do host.

## Escopo

São bem-vindos relatos sobre autenticação, autorização entre workspaces,
exposição de credenciais, webhooks, SSRF, injeção, execução de workflows,
dependências e configuração dos containers.

Relatos de engenharia social, negação de serviço volumétrica ou ataques contra
serviços de terceiros não devem ser executados.
