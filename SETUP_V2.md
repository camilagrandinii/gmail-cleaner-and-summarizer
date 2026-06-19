# Clean Email Inbox — Setup Guide v2 (Agêntico + WhatsApp oficial)

Esta versão roda **na nuvem** (GitHub Actions) todo dia às 7h BRT, sem depender do seu computador estar ligado. O resumo chega via **WhatsApp** usando a API oficial do Meta (gratuita, sem intermediários).

A v1 (Task Scheduler + Telegram) continua disponível com `python3 main.py --notifier telegram`.

---

## O que muda na v2

| | v1 (anterior) | v2 (esta) |
|---|---|---|
| Execução | Windows Task Scheduler (PC precisa estar ligado) | GitHub Actions (nuvem, gratuito) |
| Notificação | Telegram Bot | WhatsApp — Meta Cloud API (oficial) |
| Remetente | Bot Telegram | Número de teste do Meta (aparece como número desconhecido) |
| Custo | Gratuito | Gratuito (1.000 conversas/mês no free tier, bem acima do necessário) |

---

## Visão geral do processo

1. Criar um app no Meta for Developers e habilitar WhatsApp
2. Adicionar o seu número como destinatário de teste
3. Criar e aguardar aprovação do message template (geralmente minutos)
4. Gerar um token permanente via System User
5. Criar o repositório no GitHub e configurar os secrets
6. Testar e ativar o agendamento diário

---

## Passo 1 — Criar o app no Meta for Developers

1. Acesse [developers.facebook.com](https://developers.facebook.com) e logue com sua conta Facebook.
2. Clique em **My Apps → Create App**.
3. Em "What do you want your app to do?", selecione **Other** → Next.
4. Em "Select an app type", selecione **Business** → Next.
5. Dê um nome (ex: `email-cleaner`) e clique em **Create App**.
6. Na dashboard do app, role até encontrar **WhatsApp** e clique em **Set up**.
7. Em "Getting Started", o Meta vai mostrar:
   - Um **Test phone number** (número de envio gratuito — ex: `+1 555 000 xxxx`)
   - O **Phone Number ID** — copie esse valor, você vai precisar
   - Um **Temporary access token** — ignore por enquanto, vamos gerar um permanente
8. Em "To", adicione o seu número de celular (com código do país, ex: `+55 11 98765-4321`) e clique em **Add phone number**.
   - O Meta vai enviar um código de verificação no seu WhatsApp para confirmar.

---

## Passo 2 — Criar o message template

As mensagens bot-iniciadas pelo WhatsApp Business API **obrigatoriamente usam templates aprovados**.

1. No painel do app, vá em **WhatsApp → Manage → Message Templates → Create Template**.
2. Preencha:
   - **Category**: Utility
   - **Name**: `email_digest_daily` (exatamente este nome, em minúsculas com underscore)
   - **Language**: Portuguese (Brazil) — `pt_BR`
3. Em **Body**, cole o texto abaixo:

   ```
   📧 Email Digest — {{1}}

   {{2}}

   Gerado automaticamente · Clean Email Inbox
   ```

   - `{{1}}` vai receber a data (ex: `19/06/2026`)
   - `{{2}}` vai receber o resumo do dia

4. Clique em **Submit** e aguarde aprovação.
   - Templates Utility normalmente são aprovados em minutos.
   - Se rejeitado, o motivo aparece no painel — geralmente basta ajustar o texto.

---

## Passo 3 — Gerar um token permanente (System User)

O token temporário expira em 24 horas. Para o agendamento diário funcionar sem intervenção, você precisa de um token permanente via **System User** no Meta Business Manager.

1. Acesse [business.facebook.com](https://business.facebook.com) → **Settings** (ícone de engrenagem) → **Users → System Users**.
2. Clique em **Add** → dê um nome (ex: `email-cleaner-bot`) → Role: **Admin** → Create System User.
3. Com o System User criado, clique em **Generate New Token**:
   - Selecione o app que você criou no Passo 1
   - Em Permissions, marque: `whatsapp_business_messaging` e `whatsapp_business_management`
   - Token Expiration: **Never**
   - Clique em **Generate Token** e **copie o token** — ele só aparece uma vez
4. Ainda nessa tela, clique em **Add Assets** → selecione **Apps** → selecione seu app → marque **Full Control** → Save.

---

## Passo 4 — Preencher accounts.yaml

Abra `accounts.yaml` e adicione/substitua o campo `whatsapp_phone` com o seu número sem `+` e sem espaços:

```yaml
accounts:
  - name: camila
    ...
    whatsapp_phone: "5511987654321"   # 55 = Brasil, seu DDD + número
```

---

## Passo 5 — Criar o repositório no GitHub

1. Crie um repositório **privado** no GitHub.
2. Se ainda não existe um `.gitignore`, ele já foi criado pelo projeto. Verifique se inclui:
   ```
   .env
   credentials/*/token.json
   credentials/*/credentials.json
   state/
   logs/
   ```
3. Inicialize e faça o push:

   ```bash
   cd '/mnt/c/Users/camila/OneDrive/Área de Trabalho/Camila/1.6 Freelances/Claude Utils/Clean-Email-Inbox'
   git init
   git add .
   git commit -m "initial commit v2"
   git remote add origin https://github.com/SEU_USUARIO/clean-email-inbox.git
   git push -u origin main
   ```

---

## Passo 6 — Configurar os GitHub Secrets

No repositório, vá em **Settings → Secrets and variables → Actions → New repository secret**.

### Secrets necessários

| Secret | Valor | Como obter |
|--------|-------|------------|
| `GMAIL_CREDENTIALS_CAMILA` | base64 do credentials.json | `base64 -w 0 credentials/camila/credentials.json` |
| `GMAIL_TOKEN_CAMILA` | base64 do token.json | `base64 -w 0 credentials/camila/token.json` |
| `NOTION_TOKEN` | token do .env local | arquivo `.env` |
| `WHATSAPP_PHONE_NUMBER_ID` | Phone Number ID do Passo 1 | Dashboard do app Meta, seção "Getting Started" |
| `WHATSAPP_ACCESS_TOKEN` | Token permanente do Passo 3 | Gerado via System User |
| `PAT_UPDATE_SECRETS` | GitHub Personal Access Token | Veja abaixo |

### Criando o PAT_UPDATE_SECRETS

Este secret permite que o workflow atualize o `GMAIL_TOKEN_CAMILA` automaticamente após cada execução (para manter o token do Gmail fresco).

1. Vá em **GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)**
2. **Generate new token (classic)**:
   - Nome: `email-cleaner-secrets-update`
   - Expiration: No expiration (ou 1 ano — lembre de renovar)
   - Scope: marque apenas **`repo`**
3. Copie o token gerado e salve como secret `PAT_UPDATE_SECRETS`

---

## Passo 7 — Testar

1. No GitHub, vá em **Actions → Daily Email Cleaner → Run workflow**
2. Marque **dry_run = true** e clique em Run workflow
3. Aguarde ~2 minutos e verifique o log — deve mostrar os emails classificados sem fazer alterações
4. Se o dry-run passou, rode de novo **sem** dry_run
5. Você deve receber no WhatsApp uma mensagem do número de teste do Meta com o digest

---

## Passo 8 — Verificar o agendamento

O workflow roda automaticamente todo dia às **10:00 UTC (07:00 BRT)**.

- Vá em **Actions → Daily Email Cleaner** para confirmar que está habilitado
- Após a primeira execução automática, os logs ficam disponíveis ali

---

## Rodar localmente (v1 — Telegram)

```bash
source .venv/bin/activate
python3 main.py --notifier telegram     # produção local com Telegram
python3 main.py --dry-run               # dry-run (7 dias, sem ações ou notificações)
```

---

## Adicionando uma nova conta (v2)

1. Configure o OAuth do Gmail localmente e adicione em `accounts.yaml` com `whatsapp_phone`
2. Adicione os secrets do Gmail da nova conta:
   - `GMAIL_CREDENTIALS_{NOME_UPPER}` e `GMAIL_TOKEN_{NOME_UPPER}`
3. Adicione o número da nova conta como destinatário de teste no painel Meta (ou faça Business Verification para remover o limite de 5 destinatários)
4. Atualize `.github/workflows/daily-clean.yml` para restaurar as credenciais da nova conta

---

## Troubleshooting

**WhatsApp não recebeu a mensagem:**
- Confirme que o template `email_digest_daily` foi aprovado (status "Active" em WhatsApp → Manage → Message Templates)
- Confirme que o seu número foi adicionado e verificado no painel Meta (Passo 1)
- Verifique o log do GitHub Actions — erros da API aparecem com o código de resposta

**Workflow falha com erro de autenticação Gmail:**
- O token pode ter sido corrompido. Rode `python3 main.py --dry-run` localmente para renovar, depois atualize `GMAIL_TOKEN_CAMILA` com `base64 -w 0 credentials/camila/token.json`

**Template rejeitado pelo Meta:**
- A categoria Utility é a mais aceita para notificações transacionais. Se rejeitado, tente reformular o texto sem linguagem promocional e reenvie

**Workflow não executou no horário:**
- GitHub Actions pode atrasar até 15 minutos nos schedules em horário de pico — é normal
- Se ficou mais de 1 hora, verifique se o workflow está habilitado em Actions

**Limite de destinatários de teste:**
- Em modo de desenvolvimento, o Meta permite até 5 números de teste. Para mais, é necessário Business Verification (gratuita, requer documentos do negócio)
