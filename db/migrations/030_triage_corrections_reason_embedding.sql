-- La razón del etiquetador se vuelve buscable por su propio vector (auditoría 12-ago, H1).
--
-- La búsqueda de familias ordenaba solo por el centroide de los MENSAJES DE ERROR:
-- una pregunta que coincide con la razón humana («sandbox del PSP en frío») y no
-- con el texto del error («socket hang up») dejaba la familia fuera del corte
-- MAX_SEMANTIC_DISTANCE. Medido en Demo MTP: 3 de 5 familias del PSP caían fuera
-- (0,757-0,868 por centroide vs 0,096-0,475 por razón).
--
-- Aditiva y nullable: las filas existentes quedan a NULL hasta que
-- `python3 -m scripts.reembed` las rellene; mientras, se buscan como antes.
-- Sin índice: la búsqueda promedia dos distancias (centroide y razón), cosa que
-- ningún índice vectorial sirve, y el volumen por org es de decenas de familias.
--
-- `if not exists` porque scripts/docker_init.py re-aplica todas las migraciones.

alter table public.triage_corrections
    add column if not exists reason_embedding vector(384);
