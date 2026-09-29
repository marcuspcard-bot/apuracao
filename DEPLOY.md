# Produção: branch prod

Frontend na Vercel, API Python no Render e Supabase atual. A autenticação já está implementada; sua ativação depende da configuração abaixo. Nenhum dado de produção precisa ser apagado ou recriado.

## 1. Administrador no Supabase

No projeto atual, abra Authentication → Users → Add user → Create new user. Defina seu e-mail e uma senha forte diretamente no painel e confirme o e-mail do usuário. Copie o User UID (UUID) para `ADMIN_USER_IDS` no backend. Não use e-mail nesse campo. Desative novos cadastros em Authentication se não forem necessários para outro aplicativo deste mesmo projeto.

`SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY` permanecem somente no backend. Não publique essas credenciais nem coloque a senha administrativa em arquivos versionados. O frontend precisa somente de `VITE_API_URL`.

## 2. GitHub

Crie um repositório privado vazio, envie os arquivos versionáveis e selecione `prod` como branch padrão. Os arquivos `.env`, `.vercel`, dependências e artefatos estão ignorados. Não envie o conteúdo de `.env` pelo chat.

## 3. API no Render

Crie uma conta usando GitHub e importe o repositório como Blueprint, branch `prod`, arquivo `render.yaml`. O arquivo usa plano **Starter pago**: confira o preço no painel antes de confirmar a criação.

Preencha `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `PREVIEW_SECRET_KEY`, `ADMIN_USER_IDS` e `FRONTEND_URL` usando os valores privados e a origem definitiva do frontend. Mantenha o bucket privado `boletins` existente. Use a conexão PostgreSQL adequada à rede do provedor e TLS (`sslmode=require`).

O comando `alembic upgrade head` aplica migrations pendentes ao banco existente antes da inicialização. Revise migrations pendentes e o backup antes do primeiro deploy; não execute reset nem envie PDFs sintéticos ao banco de produção.

Copie a URL HTTPS da API e verifique `/health`.

## 4. Frontend na Vercel

Importe o mesmo repositório. Configure Root Directory `frontend`, Production Branch `prod` e Node.js 22.x. O `vercel.json` já configura Vite, instalação, build e saída `dist`, e limita deploys automáticos à branch `prod`.

Defina `VITE_API_URL=https://URL-DA-API`, sem `/api` ao final, em Production. Publique e copie a origem estável (por exemplo `https://seu-projeto.vercel.app`) para `FRONTEND_URL` no Render; redeploy da API se a origem mudou. Alterações de `VITE_API_URL` exigem novo build do frontend.

## 5. Verificação

- Sem login, `/importar` mostra a tela de acesso e `/api/boletins` retorna 401.
- Entre com o usuário autorizado. Teste leitura dos boletins existentes e abertura do PDF.
- Verifique a configuração do telão; alterações salvam dados reais, portanto use somente a configuração desejada.
- Abra `/divulgacao` em janela anônima: o telão é público.
- Saia da conta: a aba retorna ao login.

A sessão dura até a expiração do token do Supabase e fica restrita à aba. Não há renovação automática nesta versão. Logout não invalida imediatamente um JWT já emitido; ele pode permanecer válido até expirar. Remover o UUID de `ADMIN_USER_IDS` e reiniciar a API retira a autorização administrativa.

Referências: [Supabase Auth](https://supabase.com/docs/guides/auth), [logout](https://supabase.com/docs/guides/auth/signout), [Render Blueprint](https://render.com/docs/blueprint-spec), [Vercel Git](https://vercel.com/docs/git).
