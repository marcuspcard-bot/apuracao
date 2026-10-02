testar localmente:
docker start apuracao-api
cd /home/marcus/APURACAO/frontend
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort

MATAR PROCESSO:
#DESCOBRIR PORTA
sudo fuser -k 5173/tcp

#Limpar supabase
BEGIN;

DELETE FROM public.boletins;

COMMIT;

---------------------------------------------

SELECT
  (SELECT COUNT(*) FROM public.boletins) AS boletins,
  (SELECT COUNT(*) FROM public.resultados) AS resultados,
  (SELECT COUNT(*) FROM public.votos_candidatos) AS votos,
  (SELECT COUNT(*) FROM public.boletim_secoes) AS secoes_importadas;

-----------------------------

###Commit completa

cd ~/APURACAO

git status

git add .

git commit -m "Atualiza configuração e estrutura do projeto"

git push origin prod