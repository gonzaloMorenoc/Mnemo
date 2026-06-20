-- Mnemo: indices de aseguramiento (defensa C1 + rendimiento del matching)
--
-- C1: el matching debe encontrar SIEMPRE la familia con la firma exacta, aunque
-- su centroide haya derivado fuera del top-K por coseno. El fix principal vive en
-- AssuranceRepository._query_candidates (UNION por signature). Este indice unico
-- parcial es la red de seguridad a nivel de BD: impide crear una familia duplicada
-- con la misma (org_id, signature) dentro del scope 'org'.
create unique index if not exists uq_defect_families_org_signature
    on public.defect_families (org_id, signature)
    where scope = 'org';

-- I2: indice ANN sobre el centroide para que el top-K por coseno del matching no
-- haga un seq scan a medida que crecen las familias.
create index if not exists idx_families_centroid
    on public.defect_families using ivfflat (centroid vector_cosine_ops)
    with (lists = 100);
