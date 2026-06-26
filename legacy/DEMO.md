# Demo on-prem de Mnemo (un comando)

Levanta Mnemo completo en local (Supabase self-hosted + Ollama + backend + frontend),
sin que ningún dato salga a la nube.

## Requisitos
- Docker + Docker Compose.
- **~15 GB de disco libre** (imágenes + modelo de Ollama ~5 GB + Postgres).

## Arranque
```bash
docker compose --env-file .env.docker up -d
# La primera vez: baja imágenes y, al usar la causa raíz, descarga el modelo.
docker compose exec ollama ollama pull deepseek-r1:8b   # ~5 GB (una vez)
```
Espera a que `backend` esté sano:
```bash
curl -fsS http://localhost:8080/v2/health
```

## Probar
1. Abre http://localhost:3000 y entra con **demo@mnemo.local** / **mnemo-demo-1234**.
2. En **Defect DNA** verás familias ya sembradas (un TimeoutException compartido entre
   `cliente-alpha` y `cliente-beta`). Abre una familia y pulsa **"Analizar causa raíz"**.
3. En **Assurance**, sube `examples/allure-ejemplo.json` o `examples/junit-ejemplo.xml` y
   mira el veredicto.

## Smoke automático
```bash
ANON=<anon key de .env.docker> ./scripts/smoke_demo.sh
```

## Apagar / limpiar
```bash
docker compose down            # conserva datos
docker compose down -v         # borra volúmenes (db + modelos)
```
