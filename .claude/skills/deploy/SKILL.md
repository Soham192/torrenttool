# Deploy

Steps to deploy qbit_pipeline to a VPS:

1. SSH into the server
2. Clone: `git clone https://github.com/Soham192/torrenttool.git`
3. `cd torrenttool/qbit_pipeline`
4. Edit `docker-compose.yml` — change `QBIT_PASSWORD` from default
5. `docker compose up -d`
6. Verify: `curl http://localhost:8501` returns 200
7. (Optional) Put nginx in front with SSL for public access
