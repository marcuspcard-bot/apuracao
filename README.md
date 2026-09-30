# Importação de Boletins de Urna

Aplicação React + FastAPI para importar PDFs do Boletim na Mão, conferir os resultados e salvar o boletim em PostgreSQL e o arquivo original em um bucket privado do Supabase. Inclui listagem, detalhes, acompanhamento parcial e telão configurável de Bacabal/MA em 2026, primeiro turno. O acesso é sem login, conforme autorizado: qualquer pessoa que alcance a API pode consultar e importar boletins, substituir a lista de seções e configurar o telão. Veja [a configuração de produção](DEPLOY.md).

## Fluxo implementado

1. O navegador envia um PDF para `POST /api/boletins/preview`.
2. O backend verifica extensão, MIME, assinatura do arquivo e limite de tamanho, calcula SHA-256, consulta duplicidade, extrai texto com PyMuPDF e interpreta o BU.
3. A resposta contém os dados, inconsistências e `preview_token`. Nenhuma linha é inserida e nenhum upload é feito no storage nesta etapa.
4. A tela apresenta eleição, município, todas as seções, eleitores, urna, candidatos, totais e assinatura. Os campos eleitorais são somente leitura. O PDF selecionado pode ser aberto para comparação.
5. A confirmação envia **somente** `preview_token`. O backend recupera o PDF, calcula o hash, extrai e valida novamente e verifica seções conflitantes.
6. Uma transação grava boletim, seções, resultados e votos. O upload precisa concluir antes do commit. Falhas causam rollback; se necessário, o backend remove o objeto enviado.
7. A listagem e os detalhes consultam os registros persistidos. O original abre por URL assinada de 60 segundos.

## Estrutura

```text
backend/app/api/            Endpoints FastAPI
backend/app/core/           Configuração, pool PostgreSQL e locks transacionais
backend/app/models/         Tabelas SQLAlchemy de boletins e cadastro de seções
backend/app/schemas/        Contratos Pydantic
backend/app/services/       PDF, parser, validação, prévia, duplicidade e storage
backend/alembic/            Migrations incrementais e ambiente Alembic
backend/tests/              Testes com PostgreSQL e PDF real
frontend/src/components/   Upload, conferência e tabelas
frontend/src/pages/        Importação, boletins e detalhes
frontend/src/hooks/        Atualização automática do acompanhamento
frontend/src/types/        Contratos de boletins, acompanhamento e seções
frontend/tests/            Testes de navegador Playwright
render.yaml               Blueprint Render
backend/railway.toml       Configuração alternativa Railway
frontend/vercel.json       Rotas SPA e headers Vercel
.github/workflows/ci.yml   Testes e build no GitHub Actions
```

O PDF `Xangai_(ZZ)_-_0001_-_0483.pdf`, fornecido no diretório original, é o fixture de integração. A imagem de referência visual está em `frontend/public/boletim-referencia.jpeg` e é usada na página de importação.

## Executar localmente

Requisitos: Python 3.10+ (Docker usa 3.12), Node.js 22.12+ e PostgreSQL 17. O Docker Compose abaixo é apenas uma conveniência para desenvolvimento; a produção não depende deste computador.

Na raiz:

```bash
docker compose up -d
```

Se o plugin Compose não estiver instalado:

```bash
docker run -d --name apuracao-postgres \
  -e POSTGRES_USER=apuracao -e POSTGRES_PASSWORD=apuracao -e POSTGRES_DB=apuracao \
  -p 127.0.0.1:55432:5432 postgres:17-alpine
```

Backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Preencha `PREVIEW_SECRET_KEY` em `.env` com a chave gerada. Preencha também `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY` para salvar PDFs de verdade. A prévia e a listagem funcionam com o PostgreSQL local; a confirmação exige um storage configurado e um bucket existente.

```bash
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Em outro terminal:

```bash
cd frontend
npm ci
cp .env.example .env
npm run dev -- --port 5173 --strictPort
```

Acesse `http://localhost:5173`. Swagger: `http://localhost:8000/docs`. Se a porta estiver ocupada, escolha outra e ajuste `VITE_API_URL` ou `FRONTEND_URL` conforme o serviço alterado. Reinicie os processos depois de alterar `.env`.

### Ambiente deixado em execução nesta entrega

O frontend usa `http://localhost:5173`, pelo serviço de usuário `apuracao-web`. A API usa `http://localhost:8000`, no container `apuracao-api`; o PostgreSQL de testes está no container `apuracao-postgres`, porta 55432. A aplicação está configurada para Supabase pelo `.env` privado. Os testes usam outro banco e schemas separados, removidos ao final, sem inserir boletins no Supabase.

Para parar este ambiente:

```bash
systemctl --user stop apuracao-web
docker stop apuracao-api apuracao-postgres
```

Para iniciar novamente na mesma sessão do sistema:

```bash
docker start apuracao-postgres apuracao-api
systemctl --user start apuracao-web
```

O serviço de desenvolvimento é temporário e não instala inicialização automática. Ao alterar `backend/.env`, o container existente não relê as variáveis: pare-o e execute o backend pelo comando `uvicorn` acima com o novo ambiente, ou recrie o container. Não execute duas instâncias locais na mesma porta.

## Variáveis

| Backend | Configuração |
| --- | --- |
| `DATABASE_URL` | URL PostgreSQL; aceita `postgresql://` ou `postgresql+psycopg://`. Na nuvem, acrescente `?sslmode=require`. |
| `SUPABASE_URL` | URL do projeto, como `https://SEU-PROJETO.supabase.co`. |
| `SUPABASE_SERVICE_ROLE_KEY` | Chave `service_role`, somente no backend. |
| `SUPABASE_STORAGE_BUCKET` | `boletins`. |
| `FRONTEND_URL` | Origem exata, sem caminho; por exemplo `https://seu-app.vercel.app`. Não aceita `*`. |
| `MAX_PDF_SIZE_MB` | Limite por PDF, padrão `10`, máximo `50`. |
| `PREVIEW_SECRET_KEY` | Chave Fernet gerada pelo comando acima, igual em todas as instâncias. |
| `PREVIEW_TTL_SECONDS` | Validade da prévia, padrão `900` (15 minutos), máximo `3600`. |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | Conexões mantidas e extras por processo: `5` + `5` por padrão. |
| `DB_POOL_TIMEOUT_SECONDS` | Espera máxima por conexão disponível: `10`. |
| `DB_CONNECT_TIMEOUT_SECONDS` | Tempo máximo para abrir conexão: `10`. |
| `DB_LOCK_TIMEOUT_MS` | Espera por lock PostgreSQL: `10000` ms; conflito prolongado retorna `503`. |
| `PDF_WORKERS` | Processos de leitura de PDFs: `2`, máximo `4` por processo da API. |
| `PDF_MAX_PENDING` | Limite de trabalhos de leitura em execução e na fila: `10`. |
| `PDF_TIMEOUT_SECONDS` | Espera pela leitura do PDF: `30`; fila cheia ou timeout retorna `503`. |
| `IMPORT_MAX_CONCURRENT` | Importações ativas por processo, incluindo recepção, parser, banco e Storage: `5`. Requisições excedentes recebem `503` com `Retry-After: 2`. |
| `REQUEST_BODY_TIMEOUT_SECONDS` | Prazo total para receber o corpo de um POST/PUT: `120` segundos; envio incompleto retorna `408`. Não é o prazo da transação. |
| `STORAGE_MAX_CONNECTIONS` | Limite do pool HTTP compartilhado com o Supabase Storage: `10`. |
| `STORAGE_TIMEOUT_SECONDS` | Timeout de inatividade de leitura/escrita do Storage: `45` segundos; conexão: `10`, espera no pool: `5`. |
| `TELAO_REALTIME_ENABLED` | Ativa a assinatura Supabase Realtime no backend, padrão `true`. O polling funciona independentemente dela. |
| `PORT` | Porta injetada por Render/Railway, padrão `8000` no container. |

| Frontend | Configuração |
| --- | --- |
| `VITE_API_URL` | URL pública do backend, sem `/api` no final. É incorporada ao build; alterá-la exige novo deploy. |

Os `.env` estão ignorados pelo Git e excluídos do contexto Docker. Nunca configure a chave de serviço ou a chave Fernet em variáveis `VITE_*`.

## Prévia segura e transações

A prévia usa uma alternativa sem estado ao armazenamento temporário: um token Fernet autenticado e criptografado contendo o PDF e o nome sanitizado. O navegador guarda o token somente em memória e o devolve na confirmação. Não consegue modificar seu conteúdo sem invalidá-lo. O servidor reanalisa o original em vez de aceitar valores eleitorais do cliente. Não há cache local, Redis, tabela temporária nem dependência de uma instância específica. Reiniciar ou escalar o backend mantém tokens válidos desde que a chave permaneça igual; trocar a chave invalida prévias existentes.

Esse desenho aumenta o token para aproximadamente 1,8 vez o tamanho do PDF. A API limita também o corpo de requisições, incluindo uploads sem `Content-Length`. Para um PDF de 10 MB, o proxy de produção deve aceitar pelo menos 21 MB na confirmação. As requisições do frontend vão diretamente ao backend, sem passar por uma Vercel Function. O token é um segredo temporário: não registre corpos de confirmação em logs.

O hash é único no banco. Todas as seções, principais e agregadas, têm unicidade por data da eleição, turno, município e zona. A data identifica a eleição nesta versão. Os identificadores originais são strings preservadas, incluindo zeros; chaves auxiliares normalizadas impedem que `0483` e `483` sejam cadastradas separadamente. Locks transacionais PostgreSQL serializam somente confirmações com o mesmo hash ou seções em comum. Seções diferentes da mesma zona podem ser importadas simultaneamente. Os locks são adquiridos em ordem determinística, e constraints do banco também protegem as seções.

PostgreSQL e Supabase Storage não participam da mesma transação distribuída. O banco sempre usa uma única transação para os quatro tipos de registro. Se o commit falhar após upload, o backend verifica o banco antes de remover o arquivo e obtém novamente os locks para não afetar outra confirmação. Se um upload terminou mas sua resposta se perdeu, a repetição recupera o objeto apenas se os bytes forem idênticos. Uma interrupção abrupta do processo ou indisponibilidade simultânea ainda pode deixar um **arquivo órfão no storage**, mas não linhas parcialmente gravadas no banco. Não há promessa de atomicidade distribuída.

Para incidentes, consulte os logs de compensação (bucket e caminho), suspenda temporariamente novas importações e confirme a ausência do hash em `boletins` antes de remover manualmente um órfão no painel Storage. Objetos com boletim associado devem ser preservados. Após um timeout de confirmação, confira a listagem antes de tentar novamente.

As migrations ativam RLS nas tabelas da aplicação sem criar políticas públicas; use no backend o usuário proprietário ou um papel com BYPASSRLS. O frontend acessa somente FastAPI. Importação, listagem e abertura de PDFs não exigem login. O bucket continua privado, mas qualquer pessoa com acesso à API pode obter a URL temporária de um PDF salvo. CORS controla origens de navegadores, não funciona como autenticação. A validação confere estrutura e aritmética; não certifica autenticidade eleitoral ou a assinatura QR Code.

### Uso simultâneo e organização

`api/boletins.py` trata HTTP; `services/importacao_service.py` coordena prévia, validação, transação e compensação. `core/locks.py` centraliza a aquisição ordenada e o timeout dos locks, também usados pelo cadastro de seções. A prévia libera sua conexão antes de ler o PDF; abrir o original libera a conexão antes de solicitar a URL ao Storage. Cada requisição usa sua própria sessão SQLAlchemy.

`core/request_limits.py` concentra os limites HTTP, fora da montagem da aplicação. Até cinco requisições de prévia/confirmação por processo são admitidas, desde antes da leitura do corpo até o fim da resposta. Uma sexta recebe `503` sem carregar outro PDF em memória; não há fila HTTP ilimitada nem repetição automática. Consultas de boletins, recibos, visão geral e divulgação não entram nesse limite. Tamanho declarado excessivo é recusado antes da leitura; o limite também é verificado em corpos sem `Content-Length`. Timeout, desconexão e falha liberam a vaga.

O Storage usa um único `httpx.Client` por processo, criado no lifespan e encerrado no shutdown, com até dez conexões reutilizáveis. A reutilização evita abrir uma conexão nova em cada operação, conforme a [documentação de clients HTTPX](https://www.python-httpx.org/advanced/clients/). Timeouts de conexão, leitura/escrita e espera no pool são distintos. Uploads continuam sem `upsert`; a recuperação de um objeto existente exige os mesmos bytes e continua sob o lock do arquivo.

A extração com PyMuPDF roda em processos separados, não nas threads das rotas FastAPI, conforme a [orientação do PyMuPDF](https://pymupdf.readthedocs.io/en/latest/recipes-multiprocessing.html). Fila e espera são limitadas. Um trabalho já em execução que excede o timeout continua ocupando sua vaga até terminar; não há encerramento forçado de um único worker. Um worker que falha invalida o pool, que pode ser recriado na próxima solicitação. Em travamento persistente, reinicie o serviço e investigue o arquivo. O tamanho e a complexidade dos PDFs influenciam a capacidade real.

O pool padrão permite até dez conexões PostgreSQL por processo da API, não dez por usuário. Até cinco confirmações podem segurar conexões durante o upload ao Storage; as demais ficam disponíveis para consultas. As cinco importações de teste chegam ao Storage simultaneamente, enquanto consultas continuam respondendo, usando o mesmo limite de conexões da aplicação. Mais réplicas ou `uvicorn --workers` multiplicam os limites de importações, conexões e processos PDF; confira o orçamento do banco antes de aumentar. Os testes usam PostgreSQL local e Storage controlado, não medem a latência ou a capacidade do plano Supabase.

Na atualização desta revisão, encerre as instâncias antigas antes de iniciar as novas. Não mantenha simultaneamente a versão anterior com locks por zona e a nova com locks por seção, pois a compensação do Storage depende de todos os importadores compartilharem a mesma estratégia de bloqueio.

O acompanhamento agrega votos no PostgreSQL, sem carregar todas as linhas de candidatos na aplicação. Cada resposta fixa primeiro o conjunto de boletins confirmados para manter contagens, seções e votos coerentes durante novas importações. O hook `useAcompanhamento` atualiza a tela dez segundos após a resposta anterior, cancela consultas ao sair da página e mantém os dados anteriores identificados quando uma atualização falha.

Esta versão não autentica usuários nem identifica o responsável por cada importação. Se for necessário restringir o acesso à equipe, a restrição deve cobrir frontend **e API**, por exemplo em uma rede privada; esconder apenas o endereço do site não protege os endpoints.

### Resposta de confirmação perdida

`frontend/src/hooks/useImportacao.ts` concentra o estado do envio, cancelamento da prévia, validade, confirmação e recuperação; a página `Importar.tsx` fica responsável pela apresentação. O botão de salvar tem proteção síncrona contra cliques repetidos. O navegador aguarda até 180 segundos na prévia e 240 na confirmação, mas o proxy também pode impor um timeout menor. Esses prazos do cliente não cancelam uma transação já iniciada no servidor.

Em falha de rede ou resposta `5xx` na confirmação, a tela faz apenas uma consulta de leitura por hash. Se o boletim já estiver persistido, mostra o recibo e o link correto. Se a consulta falhar ou ainda não localizar um commit, não afirma que houve sucesso e não apaga a prévia. O botão **Verificar salvamento** consulta novamente sem reenviar o PDF nem repetir o POST. Um resultado `null` não prova falha: outra requisição pode ainda estar em andamento. Duplicidades `409` e inconsistências continuam identificadas como tais. Nenhuma confirmação é repetida automaticamente.

### Cinco computadores pela internet

Os cinco computadores devem usar a mesma aplicação HTTPS, apontando para a mesma API e banco. `localhost` e `127.0.0.1` servem apenas para testes no computador atual, não para acesso remoto. O `render.yaml` inclui o perfil inicial de cinco importações, dez conexões de banco/Storage e dois workers PDF; mantenha inicialmente um processo da API e dimensione CPU/memória conforme os PDFs reais. Os limites são por processo, não um contador global de computadores.

Antes da operação remota:

1. Publique frontend e API com HTTPS; configure `VITE_API_URL` e a origem exata em `FRONTEND_URL`, sem chaves do Supabase no navegador.
2. Não é necessário criar contas no Supabase Auth. Confirme a exposição desejada: sem restrição externa, qualquer pessoa que alcance a API pode importar boletins e modificar o cadastro de seções e o telão. CORS e limites de carga não são controle de acesso.
3. Configure o proxy para aceitar o tamanho do token de confirmação (ao menos 21 MB para PDFs de 10 MB), sem repetir automaticamente POSTs, e confira seus timeouts. Um proxy com prazo menor pode acionar a recuperação por hash mesmo com o backend ainda trabalhando.
4. Mantenha o mesmo `PREVIEW_SECRET_KEY` nas instâncias, bucket privado e pool de banco dentro do limite contratado. Não aumente réplicas ou workers sem recalcular o total de conexões.
5. Faça um ensaio com os cinco computadores e os PDFs reais, verificando listagem, soma e abertura dos originais. Os testes automatizados simulam concorrência e falhas, mas não substituem medir as redes reais dos operadores.

A configuração do telão segue o mesmo acesso sem login das outras páginas; não há bloqueio por usuário ou por rede na aplicação. A remoção do login não publica serviços na nuvem, não altera o parser e não exige migration ou limpeza do banco.

## Parser e validação

Seções agregadas são opcionais. Uma quantidade explícita zero aceita lista vazia ou ausente. Se quantidade e lista estiverem ausentes, uma única seção principal identificada permite assumir zero agregadas. Uma lista existente sem quantidade, ou mais de uma principal distinta, é recusada por ambiguidade. A lista encontrada é preservada mesmo quando o documento declara zero: divergências entre quantidade e lista retornam `INCONSISTENTE` e bloqueiam a confirmação.

`total_secoes_representadas` é calculado como `1 + quantidade_secoes_agregadas`, sem coluna adicional nem migration, e é retornado na prévia, listagem e detalhes. A gravação sempre inclui a principal; a verificação de duplicidade inclui principal e todas as agregadas. Preview e detalhes exibem `Nenhuma` para seções sem agregadas. Esse total não é a quantidade de boletins e só representa dados validados quando o status é `OK`.

O PDF real de Xangai tem duas páginas. A leitura usa texto digital com ordenação por coordenadas. A configuração `backend/app/services/offices.py` reconhece DEPUTADO FEDERAL, DEPUTADO ESTADUAL, DEPUTADO DISTRITAL, SENADOR, GOVERNADOR e PRESIDENTE. `normalize_office_name()` centraliza caixa, espaços e separadores. Novos cargos podem ser acrescentados nessa configuração.

A leitura é dividida em `parse_header()`, `detect_office_blocks()`, `parse_office_block()`, `parse_candidates()` e `parse_office_totals()`. Cada bloco termina no próximo cargo; títulos repetidos do mesmo cargo são tratados como continuação. Cabeçalhos de tabela e de página são removidos sem remover valores numéricos isolados. Cargos podem atravessar páginas. Os candidatos são analisados apenas dentro de seu bloco, sem quantidade ou comprimento de número fixos. Números permanecem strings, incluindo zeros. Conteúdo não reconhecido não é descartado silenciosamente.

São validados: aptos >= comparecimento; faltosos = aptos - comparecimento; por cargo, nominais + **legenda** + brancos + nulos = apurado; soma dos candidatos = nominais; número de seções agregadas; seções e candidatos repetidos. `votos_legenda` é inteiro e recebe zero somente se não houver esse campo no documento. Um rótulo de legenda presente com valor ilegível gera problema, sem assumir zero. Totais obrigatórios ausentes ou conflitantes aparecem como `null`, com status `INCONSISTENTE`, e impedem a confirmação. Nenhum total é obtido de outro cargo ou recalculado para preencher uma ausência.

Tabelas de votos de legenda por partido são lidas separadamente dos candidatos. A soma dos partidos é conferida contra o total de legenda explicitamente apresentado; nunca substitui um total ausente. Partidos repetidos e linhas ilegíveis bloqueiam a importação. O banco guarda `votos_legenda` por cargo, e o detalhamento por partido permanece no PDF original, sem inserir partidos em `votos_candidatos`. A identificação da urna aceita também o rótulo `Urna efetivada`; identificadores conflitantes são recusados. Nomes com abreviações como `DRª` conservam o texto original.

Para SENADOR, não existe comparação entre total apurado e comparecimento. Sub-blocos explicitamente identificados, como `SENADOR - 1ª VAGA`, `2ª VAGA` ou `VAGA 2`, são preservados em `cargos[].vagas[]`, com candidatos e totais separados. Quando o documento só contém resultados por vaga, os totais gerais do cargo permanecem `null`; os resultados completos das vagas podem ser gravados sem inventar uma soma geral. Um campo obrigatório ausente dentro de uma vaga bloqueia a importação. No banco há um único `resultados` por cargo; `resultados.vagas` guarda identificadores/totais, e `votos_candidatos.vaga` associa os candidatos à respectiva vaga. O frontend usa o mesmo componente dinâmico na prévia e nos detalhes.

As variações de múltiplos cargos e vagas são fixtures sintéticos exclusivos de teste, complementando a regressão do PDF real. Não representam uma coleção de todos os layouts reais de cada eleição. PDFs escaneados, protegidos por senha, com mais de 100 páginas, mais de 2 milhões de caracteres ou estruturas não reconhecidas são recusados. Não há OCR nem leitura de QR Code.

### Atualizar instalações existentes

A nova migration `b718df906e32`, posterior a `97a4a50a18c8`, adiciona `resultados.votos_legenda INTEGER NOT NULL DEFAULT 0`, `resultados.vagas` e `votos_candidatos.vaga`. Totais gerais aceitam `NULL` para documentos com resultados apenas por vaga. A unicidade dos candidatos inclui a vaga. Registros antigos preservam IDs, vínculos e votos e recebem legenda zero e lista de vagas vazia. A migration inicial não foi alterada.

```bash
cd backend
.venv/bin/alembic upgrade head
```

Atualize o backend e publique um novo build do frontend depois da migration. O downgrade é bloqueado se existirem informações de legenda/vaga que seriam perdidas. O teste da migration cria registros no schema antigo, faz o upgrade e verifica que os dados permanecem intactos.

## API

| Método | Endpoint | Resultado |
| --- | --- | --- |
| `POST` | `/api/boletins/preview` | Multipart com campo `file`; dados, hash, status, problemas e token. |
| `POST` | `/api/boletins/confirmar` | JSON `{"preview_token":"..."}`; `201` com ID e mensagem. Campos extras são recusados. |
| `GET` | `/api/boletins/por-hash/{hash}` | Somente leitura, sem cache: `{"id":"..."}` para arquivo já salvo, ou `null`. SHA-256 em hexadecimal com 64 caracteres. Não retorna PDF, token nem URL do Storage. |
| `GET` | `/api/boletins?limit=50&offset=0` | Lista recente, limite máximo 100. |
| `GET` | `/api/boletins/{id}` | Metadados, seções, `dados_gerais` e `cargos`, com legenda e vagas. `dados.cargos` é mantido por compatibilidade. |
| `GET` | `/api/boletins/{id}/pdf` | URL assinada válida por 60 segundos. |
| `GET` | `/health` | Liveness do processo. Não substitui um teste de banco/storage. |
| `GET` | `/docs` | Swagger interativo. |

Erros: `408` prazo de envio, `413` tamanho, `415` extensão/MIME, `422` PDF/parser/inconsistência, `409` duplicidade, `410` token inválido/expirado, `404` ID inexistente, `502` storage, `503` capacidade de importação, banco ou leitura de PDF ocupada. Erros internos não expõem stack trace ao cliente. Confirmações não são repetidas automaticamente pelo frontend.

## Testes

Com PostgreSQL local disponível:

```bash
cd backend
.venv/bin/ruff check app tests
.venv/bin/pytest -q
```

Os testes criam um schema PostgreSQL exclusivo, executam Alembic nele e o removem ao finalizar. **Não usam SQLite.** Por padrão usam o PostgreSQL local da porta 55432, ignorando `DATABASE_URL` e as credenciais do `.env`. Opcionalmente configure `TEST_DATABASE_URL` para um banco de testes dedicado; não use credenciais de produção. Cobrimos os 11 candidatos, strings com zeros, todos os totais, parser dinâmico, erros de PDF, tamanho, token adulterado/expirado, payload extra, duplicidades entre tipos de seção, confirmação concorrente, rollback e compensação do storage. As requisições HTTP ao Supabase são verificadas com mock; credenciais reais não são usadas na suíte.

`test_concurrent_imports.py` testa cinco prévias e confirmações de seções diferentes, cinco envios do mesmo arquivo, cinco arquivos conflitantes, agregadas compartilhadas, timeout de lock e perda da resposta de um commit já concluído. Inclui uma falha de Storage em um dos cinco envios, sem rollback dos outros quatro, e recuperação posterior. Enquanto cinco uploads ficam bloqueados no Storage controlado, listagem, recibo, visão geral e divulgação respondem, e um sexto envio é recusado.

`test_request_limits.py` cobre excesso de carga antes da leitura, tamanho declarado inválido, envio em chunks, corpo lento, desconexão, cancelamento e liberação de capacidade. `test_resources.py` cobre liberação de conexões, inicialização única do pool, ciclo de vida do cliente Storage, fila PDF cheia, timeout e falha de worker. `test_storage.py` verifica cinco uploads concorrentes pelo mesmo cliente HTTP e os limites do pool.

Testes no navegador:

```bash
cd frontend
npm ci
npx playwright install chromium
npm run test:e2e
npm run build
```

Playwright inicia seus próprios servidores em `8001` e `5174`, usa outro schema PostgreSQL e um storage em memória somente para testes. Percorre a UI com o PDF real, confere persistência, detalhes, abertura do original, duplicidade e bloqueio por inconsistência. Screenshots desktop/mobile ficam em `.artifacts/`; traces de falhas ficam em `frontend/test-results/`. Os servidores são encerrados ao terminar. O backend de produção **não** possui fallback de storage em memória.

`frontend/tests/simultaneous-imports.spec.ts` usa cinco contextos independentes de navegador enviando PDFs para a API real de testes. Confere cinco gravações diferentes, um único registro para cinco envios duplicados, recuperação de resposta perdida após commit e verificação manual sem novo POST quando a conexão falha. Esses PDFs sintéticos ficam exclusivamente no ambiente isolado, nunca no Supabase da aplicação.

## Publicação em nuvem

### 1. Criar Supabase e obter a conexão

Crie um projeto no [painel Supabase](https://supabase.com/dashboard), escolha região próxima do backend e guarde a senha do banco. No botão **Connect**, selecione uma conexão PostgreSQL. Para hosts IPv4, use **Session pooler**, porta 5432. Copie o URI e substitua a senha, codificando caracteres especiais de URL. Exemplo de formato:

```text
postgresql+psycopg://postgres.PROJECT_REF:SENHA_URL_ENCODED@HOST_DO_POOLER:5432/postgres?sslmode=require
```

Use o host apresentado pelo seu projeto, sem adivinhar região/índice. A conexão direta também funciona quando o host tem IPv6 disponível. Prefira sessão para este backend persistente e Alembic. Veja [conexões PostgreSQL e SSL](https://supabase.com/docs/guides/database/connecting-to-postgres).

### 2. Criar bucket e obter URL/chave

Em **Storage**, crie o bucket `boletins`, mantenha **Public bucket desativado**, limite os arquivos a `application/pdf` e configure tamanho igual ou superior ao `MAX_PDF_SIZE_MB`. O arquivo será salvo como:

```text
boletins/2018/turno-1/30848/0001/0483/HASH_SHA256.pdf
```

`boletins` é o bucket; `storage_path` começa em `2018/`, sem repetir o nome do bucket. Não crie políticas anônimas de upload ou leitura. Em configurações do projeto, obtenha a **Project URL**. Em **Settings > API Keys**, abra a área de chaves legadas e copie **service_role** para `SUPABASE_SERVICE_ROLE_KEY`, nunca a chave `anon`. A implementação usa o JWT `service_role` nos headers de autenticação da API Storage. Veja [chaves de API](https://supabase.com/docs/guides/getting-started/api-keys), [upload](https://supabase.com/docs/reference/python/storage-from-upload) e [URLs assinadas](https://supabase.com/docs/reference/python/storage-from-createsignedurl).

### 3. Publicar o repositório no GitHub

Crie um repositório e envie esta pasta, incluindo o PDF fixture, migrations, lockfiles e configurações de deploy. Confira que `.env`, `.venv`, `node_modules` e `.artifacts` não aparecem no commit. O workflow de CI executa backend, build e Playwright automaticamente. Nenhum secret de produção é necessário para CI.

### 4. Configurar o backend no Render

No Render, crie um **Blueprint** a partir do repositório e selecione `render.yaml`. O arquivo escolhe um Web Service Docker com plano `starter` para permitir pre-deploy; confirme o plano/custo no painel antes de criar o serviço.

Preencha todas as variáveis marcadas `sync: false`: `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `FRONTEND_URL` e `PREVIEW_SECRET_KEY`. Gere uma chave nova para produção. Enquanto a URL Vercel não existir, use a origem final planejada e ajuste no passo 7.

Se configurar manualmente: **Root Directory** `backend`, **Dockerfile** `./Dockerfile`, **Docker Context** `.`, **Health Check Path** `/health` e **Pre-Deploy Command** `alembic upgrade head`. O CMD já usa `uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}`. Anote a URL pública HTTPS após o deploy. Referências: [Docker no Render](https://render.com/docs/docker) e [deploys](https://render.com/docs/deploys).

### 5. Executar migrations em produção

O pre-deploy executa `alembic upgrade head` usando as variáveis do backend antes de liberar a nova versão. Confira sucesso nos logs. Para executar manualmente pelo Shell do serviço:

```bash
alembic upgrade head
alembic current
```

A revisão inicial é `97a4a50a18c8` e a revisão atual é `d13e840a6c27`. As tabelas não são criadas no startup. Em um plano sem pre-deploy/shell, rode a migration em um job de CI com secrets de produção antes de publicar a versão da API, ou escolha um plano com pre-deploy. Não execute SQL de criação manualmente em paralelo com Alembic.

### Alternativa: Railway

Crie um serviço a partir do mesmo repositório, defina **Root Directory** como `/backend` e selecione `backend/railway.toml` como arquivo de configuração, caso não seja detectado. O Dockerfile e o pre-deploy `alembic upgrade head` estão declarados. Cadastre as mesmas variáveis do backend, gere o domínio público em Networking e confirme a migration nos logs antes do teste. A URL desse domínio será o `VITE_API_URL`.

Referências: [monorepos no Railway](https://docs.railway.com/deployments/monorepo) e [comando pre-deploy](https://docs.railway.com/deployments/pre-deploy-command).

### 6. Publicar o frontend na Vercel

Importe o repositório na Vercel, selecione **Root Directory** `frontend`, framework **Vite**, comando **Build** `npm run build`, diretório de saída `dist` e instalação `npm ci`.

Configure `VITE_API_URL=https://SEU-BACKEND` nos ambientes desejados e publique. Não inclua `/api` ao final. `frontend/vercel.json` permite recarregar URLs como `/boletins/ID` sem 404; consulte [Vite na Vercel](https://vercel.com/docs/frameworks/frontend/vite).

### 7. Ajustar CORS

Copie a origem HTTPS definitiva da Vercel para `FRONTEND_URL` no backend, por exemplo `https://apuracao.vercel.app`, sem `/importar` ou barra final. Faça redeploy do backend. A configuração permite uma origem; preview deployments com outros domínios precisam de ajuste explícito. Ao trocar a URL da API, atualize `VITE_API_URL` e faça novo build do frontend.

### 8. Testar em produção

1. Confira `/health` e `/docs` na URL pública do backend.
2. Abra o frontend e envie o PDF de Xangai.
3. Confira município `30848`, zona `0001`, seção `0483`, quatro agregadas, 626 aptos, 195 presentes, 431 faltosos e os 11 candidatos.
4. Confira 175 nominais, 5 brancos, 15 nulos e 195 apurados; clique em **Salvar boletim**.
5. Abra **Boletins**, entre em **Ver** e confira os detalhes.
6. Use **Ver PDF original** e confira o PDF baixado/aberto.
7. No Supabase, confira um registro em `boletins`, cinco em `boletim_secoes`, um em `resultados`, onze em `votos_candidatos` e o arquivo no bucket privado.
8. Reenvie o mesmo PDF e confirme que retorna duplicidade, sem novas linhas.
9. Recarregue a página de detalhes diretamente pela URL Vercel para conferir o roteamento SPA.

Não foram criados projetos ou publicados serviços automaticamente: são necessárias contas e credenciais do Supabase, GitHub e do provedor escolhido. O teste real do storage em nuvem deve ser realizado seguindo estes passos; os testes locais usam um substituto controlado.

## Acompanhamento de Bacabal

`/acompanhamento` consulta `GET /api/acompanhamento` a cada 10 segundos após a resposta anterior. O escopo está centralizado em `backend/app/services/acompanhamento.py`: Bacabal/MA, código TSE `07234`, primeiro turno de 2026, data `04/10/2026`. A identidade municipal foi conferida no [cadastro de municípios do TSE](https://resultados.tse.jus.br/oficial/ele2024/619/config/mun-e000619-cm.json), e a data no [CDE 2026](https://www.tse.jus.br/eleicoes/cde-2026). Nenhuma seção de eleições anteriores é usada como lista esperada.

A consulta é somente leitura e considera apenas boletins confirmados. Candidatos são agrupados por cargo e número, preservado como texto. Variações de nome ficam disponíveis no resultado. Votos de seções agregadas não multiplicam a soma. Detalhes de vagas de senador são preservados; quando existe uma linha geral do mesmo candidato no boletim, ela não é somada novamente ao detalhamento por vaga.

Em **Votos por candidato**, o filtro **Seção** alterna entre **Todas as seções** e uma seção específica, identificada junto com a zona. A consulta específica usa `GET /api/acompanhamento/votos-secao?zona=0013&secao=0010&data=2026-10-04`, sem alterar os indicadores gerais. O filtro inclui o cadastro de seções e os boletins recebidos. Quando a seção pertence a um BU com agregadas, o resultado identifica a principal e as agregadas como votos conjuntos, sem distribuir ou multiplicar o total. Se não houver boletim, cargo ou candidato, a ausência é informada em vez de inventar zero votos. A tabela separada de seções apuradas foi retirada; os indicadores e a área **Seções pendentes** foram mantidos.

O seletor **Data da eleição** permite consultar outras datas encontradas nos boletins de Bacabal do primeiro turno. A tela avisa quando há boletins salvos fora da data selecionada e oferece acesso direto, por exemplo `/acompanhamento?data=2026-10-02`. A API aceita `GET /api/acompanhamento?data=2026-10-02` e retorna `eleicao`, `eleicao_configurada` e `datas_disponiveis` com as contagens por data. Sem esse parâmetro, mantém `04/10/2026`. A consulta preserva as datas dos documentos e nunca soma votos ou cruza cadastros de seções de eleições diferentes. Ao trocar a data, limpa os filtros e dados anteriores, inclusive em caso de erro na nova consulta.

Enquanto não houver cadastro de seções, `secoes_esperadas` e `secoes_pendentes` retornam `null`. Não existe estimativa de conclusão. Em falha de atualização, a tela identifica os dados anteriores como desatualizados e permite tentar novamente.

Os indicadores do resumo usam `secoes_principais_esperadas`, `secoes_principais_apuradas` e `secoes_principais_pendentes`: cada seção principal ou isolada vale uma unidade, sem acrescentar as agregadas. Com cadastro, apenas o BU da própria principal cadastrada conta como recebido; boletins de seções fora da lista ou uma principal representada como agregada não aumentam esse contador. Sem cadastro, o resumo informa as principais recebidas, mas mantém total esperado e pendências como `null`. Os totais anteriores, os votos, os círculos e os vínculos de todas as seções permanecem disponíveis no detalhamento, inclusive grupos parciais.

### Lista e indicadores de seções

A área **Seções pendentes** permite importar um CSV UTF-8 (até 1 MB) com as colunas `zona;secao_principal;secoes_agregadas`. Há download do cabeçalho-modelo. Cada linha representa uma seção principal ou isolada. Separe as agregadas por espaços; deixe o campo vazio para uma seção isolada. Os números são texto e conservam zeros iniciais. O cadastro é exclusivo de Bacabal/MA, primeiro turno de 2026, em `04/10/2026`; não envie uma lista de outra eleição. Os controles de importação da lista aparecem apenas nessa data. As consultas de outras datas são somente leitura, sem lista esperada inferida.

`POST /api/acompanhamento/secoes/preview` valida o arquivo sem gravar. `POST /api/acompanhamento/secoes/confirmar` recebe os grupos e a versão da lista da prévia, validando novamente antes de substituir apenas o cadastro deste acompanhamento. Se outra importação alterar o cadastro no intervalo, a confirmação retorna 409. Seções duplicadas, inclusive uma agregada repetida como principal na mesma zona, são rejeitadas. Boletins e votos não são alterados por essa operação.

A migration `c92a617de408` acrescenta a tabela `secoes_esperadas`, com RLS habilitada e sem políticas públicas. Nenhuma lista é inserida automaticamente. Os testes usam somente listas sintéticas no banco isolado.

O círculo vermelho significa pendente; o verde significa seção efetivamente representada em um boletim confirmado. A lista mostra a principal e suas agregadas entre parênteses, com indicador individual. Se um BU não contiver todas as agregadas cadastradas, as ausentes permanecem vermelhas e o grupo aparece como **Parcial**. Um vínculo diferente entre o cadastro e o BU é sinalizado. Apenas enviar o PDF para prévia não muda a cor. O filtro **Todas** mantém os grupos concluídos visíveis; **Pendentes** inclui grupos parciais. A correspondência considera município, eleição, turno, zona e seção; as agregadas não multiplicam votos.

Os testes de navegador usam o PostgreSQL local por padrão, nunca o `DATABASE_URL` do `.env`. Para outro banco de testes, defina `TEST_DATABASE_URL` explicitamente.

## Configuração e Divulgação no Telão

`/configuracao-telao` abre diretamente, sem login. A busca consulta candidatos de boletins confirmados de **Bacabal/MA, zona 0013, 04/10/2026, primeiro turno**. O filtro é aplicado no backend e não pode ser substituído por parâmetros do navegador. Sem boletins desse escopo, a busca fica vazia; nenhum candidato é inventado ou selecionado automaticamente.

É possível adicionar candidatos de qualquer cargo reconhecido, inclusive vários senadores, mover para cima/baixo, ocultar ou remover apenas da exibição. **Salvar configuração do telão** persiste a lista e a ordem em uma única transação. **Visualizar telão** abre `/divulgacao` em outra aba. Cards por página (1 a 12) e rotação (5 a 300 segundos) são configuráveis; telas menores exibem menos cards por página para preservar a leitura. Os padrões são seis cards e dez segundos.

`/divulgacao` não tem navegação administrativa. Exibe somente os candidatos selecionados e ativos, na ordem salva, incluindo candidatos com zero votos. Votos nunca alteram a seleção nem a ordem. A soma é feita no PostgreSQL, por cargo e número, com o mesmo tratamento de vagas de senador do acompanhamento. Cada BU entra uma única vez; cobertura de seções é consultada separadamente. Não há percentuais na resposta, na configuração ou na tela.

**Boletins recebidos** conta documentos confirmados; **seções representadas** conta principais e agregadas distintas. Com o cadastro atual, o total esperado do telão é 334 seções; o resumo da Visão geral continua contando somente as 253 principais/isoladas. Esses indicadores têm propósitos diferentes. Sem cadastro, o total esperado é `null`, sem estimativa. Nenhum resultado pendente de confirmação, inconsistente ou duplicado entra na soma: essas situações não criam boletins persistidos no sistema atual.

### Banco e Concorrência

A migration incremental `d13e840a6c27` cria `telao_config` e `telao_candidatos`, com RLS sem políticas públicas. Não altera o parser nem as tabelas de importação. O sistema não tem catálogo global de candidatos: cada registro de `votos_candidatos` pertence a um BU. Por isso a seleção mantém o vínculo de origem e uma cópia do cargo, número e nome. Se o BU de origem for removido futuramente, o vínculo fica nulo, mas a seleção permanece e pode mostrar zero votos. Remover do telão nunca exclui votos ou boletins.

Um lock transacional e o campo `versao` evitam sobrescrita silenciosa por operadores simultâneos. Uma configuração desatualizada retorna `409`; a tela preserva o rascunho e oferece recarregar. A lista completa, incluindo remoções, ordem e status, usa `PUT /api/telao/config`, adaptando as operações ao botão de salvar. A leitura de configuração e candidatos usa uma única consulta; a consolidação fixa os IDs dos boletins antes de calcular votos e cobertura.

| Método | Endpoint | Acesso |
| --- | --- | --- |
| `GET` | `/api/telao/config` | Configuração, seleção e versão; sem login. |
| `PUT` / `POST` | `/api/telao/config` | Salva configuração completa de forma atômica; sem login. |
| `GET` | `/api/telao/candidatos-disponiveis?cargo=SENADOR&q=123&offset=0&limit=20` | Busca paginada por cargo, número ou nome; sem login. |
| `GET` | `/api/divulgacao` | Somente leitura; candidatos selecionados, votos e contadores. |
| `GET` | `/api/divulgacao/eventos` | SSE; transmite apenas notificações de mudança, nunca registros eleitorais ou credenciais. |

### Acesso sem login

Não há tela de entrada, botão de sair, sessão ou envio de tokens de usuário. As rotas `/api/auth/login`, `/api/auth/me` e `/api/auth/logout` foram removidas. O frontend descarta somente a antiga chave `apuracao.admin.session`, preservando outros dados do navegador, e funciona mesmo quando o armazenamento da aba está indisponível.

As rotas de boletins, acompanhamento e configuração do telão funcionam sem credenciais de usuário, incluindo clientes fora da rede local. `ADMIN_USER_IDS` não é mais usado e pode ser removido das configurações do provedor. Não é necessário criar nem excluir usuários no Supabase para operar esta versão.

As credenciais de banco e de serviço do Supabase continuam somente no backend. Bucket privado, RLS, URLs temporárias, validação de prévias, duplicidades e limites de carga permanecem. Essas proteções não restringem quem pode usar a API. Para atualizar uma instalação existente, publique backend e frontend; o código local não atualiza automaticamente Vercel ou Render. Consulte [DEPLOY.md](DEPLOY.md).

`backend/tests/test_public_access.py` cobre consultas e importação sem credenciais, remoção das rotas de login, validação e concorrência de configuração, e CORS. O cliente compartilhado dos testes de API não usa token e simula um IP externo. `frontend/tests/public-access.spec.ts` verifica navegação direta, recarga, descarte de sessão antiga e armazenamento indisponível; as importações simultâneas usam cinco contextos novos sem sessão.

### Atualização Automática

O backend mantém uma assinatura Supabase Realtime nas tabelas `boletins`, `secoes_esperadas`, `telao_config` e `telao_candidatos`. A migration acrescenta essas tabelas à publicação `supabase_realtime` quando ela existe no schema público. Não assina cada voto inserido: o commit do boletim já torna toda a transação consultável. O cliente Supabase usa a chave de serviço apenas no servidor e retransmite invalidações por SSE. Cada navegador agrupa eventos com debounce de 750 ms antes de consultar os totais.

O polling continua a cada dez segundos após a resposta anterior, mesmo quando o Realtime está indisponível; não há consultas simultâneas do mesmo telão. Uma falha mantém os últimos votos e contadores válidos com aviso de atualização. Reconexão, mudança de configuração e novos BUs atualizam os dados sem recarregar a página. A saída da tela cancela consultas, timers e SSE. O proxy público deve permitir SSE, sem buffering, com timeout superior ao heartbeat de 15 segundos.

Referências oficiais: [Postgres Changes no Supabase Realtime](https://supabase.com/docs/guides/realtime/subscribing-to-database-changes) e [assinaturas no cliente Python](https://supabase.com/docs/reference/python/subscribe).

### Testes do Telão

`backend/tests/test_telao.py` cobre escopo municipal/zona/data/turno, seleção manual e zero votos, múltiplos cargos e senadores, ordenação, remoção sem excluir votos, concorrência, RLS, acesso sem login, prévia/confirmação, duplicidades, inconsistências, cobertura sem multiplicar votos e invalidação Realtime. Os testes existentes de migration também verificam os novos modelos contra o Alembic.

`frontend/tests/telao.spec.ts` cobre configuração sem login, busca e ordem, SSE real de configuração, importação confirmada atualizando o telão, debounce, polling, falha temporária sem zerar votos, estados vazios, rotação, Fullscreen API e layouts 1920x1080, 1366x768, 3840x2160, tablet e celular. PDFs e respostas sintéticas desses testes não são inseridos no Supabase.
