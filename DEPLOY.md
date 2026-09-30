# Produção: branch prod

Frontend na Vercel, API Python no Render e Supabase atual. A aplicação não exige login, conforme autorizado. Quem alcançar a API pode consultar e importar boletins, substituir a lista de seções e alterar o telão. Nenhum dado de produção precisa ser apagado ou recriado.

## 1. Credenciais do Supabase

Não é necessário criar contas no Supabase Auth. A variável `ADMIN_USER_IDS` deixou de ser usada e pode ser removida do ambiente do Render. Usuários que já existam no Supabase não precisam ser alterados nem excluídos.

`DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` e `PREVIEW_SECRET_KEY` permanecem somente no backend. Não publique essas credenciais em arquivos versionados. O frontend precisa somente de `VITE_API_URL`. Mantenha RLS e o bucket privado; os PDFs são acessados por URLs temporárias emitidas pela API.

## 2. GitHub

Crie um repositório privado vazio, envie os arquivos versionáveis e selecione `prod` como branch padrão. Os arquivos `.env`, `.vercel`, dependências e artefatos estão ignorados. Não envie o conteúdo de `.env` pelo chat.

## 3. API no Render

Crie uma conta usando GitHub e importe o repositório como Blueprint, branch `prod`, arquivo `render.yaml`. O arquivo usa plano **Starter pago**: confira o preço no painel antes de confirmar a criação.

Preencha `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `PREVIEW_SECRET_KEY` e `FRONTEND_URL` usando os valores privados e a origem definitiva do frontend. Mantenha o bucket privado `boletins` existente. Use a conexão PostgreSQL adequada à rede do provedor e TLS (`sslmode=require`).

O comando `alembic upgrade head` aplica migrations pendentes ao banco existente antes da inicialização. Revise migrations pendentes e o backup antes do primeiro deploy; não execute reset nem envie PDFs sintéticos ao banco de produção.

Copie a URL HTTPS da API e verifique `/health`.

## 4. Frontend na Vercel

Importe o mesmo repositório. Configure Root Directory `frontend`, Production Branch `prod` e Node.js 22.x. O `vercel.json` já configura Vite, instalação, build e saída `dist`, e limita deploys automáticos à branch `prod`.

Defina `VITE_API_URL=https://URL-DA-API`, sem `/api` ao final, em Production. Publique e copie a origem estável (por exemplo `https://seu-projeto.vercel.app`) para `FRONTEND_URL` no Render; redeploy da API se a origem mudou. Alterações de `VITE_API_URL` exigem novo build do frontend.

## 5. Verificação

- Em uma janela anônima, `/importar` abre diretamente e `/api/boletins` retorna 200, sem cabeçalhos de autenticação.
- Teste a visão geral, leitura dos boletins existentes e abertura do PDF.
- Verifique a configuração do telão; alterações salvam dados reais, portanto use somente a configuração desejada.
- Abra `/divulgacao` em janela anônima: o telão é público.
- Recarregue as páginas: não deve aparecer tela de entrada nem botão de sair.

Publique tanto a API quanto o frontend ao atualizar uma instalação que ainda exige login. O navegador descarta a sessão antiga na primeira carga da versão nova. Esta alteração não inclui migration nem limpeza de boletins, usuários ou Storage.

CORS e limites de upload não substituem controle de acesso. Para limitar o uso à equipe sem login na aplicação, a infraestrutura precisa restringir tanto o frontend quanto a API, por exemplo por rede privada. Sem essa restrição externa, as operações ficam acessíveis a qualquer pessoa que alcance o endereço.

Referências: [Render Blueprint](https://render.com/docs/blueprint-spec), [Vercel Git](https://vercel.com/docs/git).
