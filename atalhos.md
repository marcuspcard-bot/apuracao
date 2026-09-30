testar localmente:
docker start apuracao-api
cd /home/marcus/APURACAO/frontend
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort

MATAR PROCESSO:
#DESCOBRIR PORTA
sudo fuser -k 5173/tcp

