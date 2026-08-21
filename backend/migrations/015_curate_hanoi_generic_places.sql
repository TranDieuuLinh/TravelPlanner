-- Curate recurring low-suitability results in the generic Hanoi place pool.
-- Night markets intentionally remain TravelPlace and are not listed here.
-- Exact IDs keep this migration bounded and idempotent; named place lookup
-- ignores generic_discovery_excluded so explicit traveler requests still work.
BEGIN;

WITH entertainment_ids(id) AS (
    VALUES
        ('travel_place_ChIJP3uCwRirNTERMR_4Ly0Z1-4'), -- 39 Concept
        ('travel_place_ChIJx_1AlOKrNTERGaGwHtmDJyo'), -- Mango Art
        ('travel_place_ChIJn5NbZoerNTER07hPUEY20ns'), -- NOTH Garden
        ('travel_place_ChIJUw0zDRGpNTERBZaKeFiwGZY'), -- Avantgarde Arts Centre
        ('travel_place_ChIJESdMl2GrNTERYMJJJaz16H0'), -- Nguyen Art Gallery
        ('travel_place_ChIJS_9xC7qrNTERXV_5SkNZKwg'), -- 54 Traditions Gallery
        ('travel_place_ChIJl-LyseyrNTERQ-BBP-MJQ5k'), -- Kim Dong Theater
        ('travel_place_ChIJHQviCWCrNTERwjwY1eWpilQ'), -- Photosona
        ('travel_place_ChIJmdpCh92rNTERh9ivwFWD9Ek')  -- Om Factory Tay Ho
)
UPDATE knowledge_entities entity
SET entity_type = 'Entertainment',
    updated_at = now()
FROM entertainment_ids target
WHERE entity.id = target.id
  AND entity.entity_type <> 'Entertainment';

WITH excluded_ids(id) AS (
    VALUES
        ('travel_place_ChIJE6eVMAWrNTERA1PnLdj_UBo'), -- Vinhomes Riverside
        ('travel_place_ChIJ5Qon4lurNTER15u__ZMj5zE'), -- TiredCity
        ('travel_place_ChIJ73d-NZ6rNTER8CwoJCDkZ10'), -- CULCAT
        ('travel_place_ChIJxQBLbwCrNTERJkW43IxmLjw'), -- CULCAT
        ('travel_place_ChIJKXAYQgCrNTERH944h0U0Dp0'), -- CULCAT
        ('travel_place_ChIJ5ZChJQCrNTERIL4q4JKLvlg'), -- CULCAT
        ('travel_place_ChIJTR___ZarNTERjZHAcI40Iic'), -- Miniwood Design
        ('travel_place_ChIJ2Q0DBxWrNTEReRnyYIyHeC8'), -- OM Himalayas showroom
        ('travel_place_ChIJ36q3AOirNTERpcrdb4Ek31g'), -- Vườn Trong Nhà
        ('travel_place_ChIJa3B3AUGpNTERzKq2wTgX3Ls'), -- Mihu Art school
        ('travel_place_ChIJD6buBACrNTERgVw-GTWeyaU'), -- Từ Tuyết Nhung rental
        ('travel_place_ChIJEZU8SQyrNTERzEdCcpAHouQ'), -- Mountains Allure
        ('travel_place_ChIJwwhHBr-rNTERSjsLVn-9Bxk'), -- Empty Wall supply store
        ('travel_place_ChIJLaGePACrNTERcRItGuyVnUI'), -- Hẻm gốm sứ và tranh
        ('travel_place_ChIJQRcOhXetNTERMM7ZSbtrVxE'), -- Hanoi Show furniture
        ('travel_place_ChIJYwaraTFVNDERC98TKklH0ZQ'), -- Kính Hoa studio
        ('travel_place_ChIJW2MM4U6rNTER1-NHiPpveu8'), -- Thien y handicrafts
        ('travel_place_ChIJQ4AJpcSrNTERW5VMwV4_slk'), -- TD ART DECOR
        ('travel_place_ChIJN25kQn-tNTERVF5Tkc8onmk'), -- Music Talent school
        ('travel_place_ChIJfUdaLr6rNTERwEWCBpXPIYc'), -- Authentic Bat Trang shop
        ('travel_place_ChIJrZDuUQCrNTERhPUCLfowjSw'), -- Hoàng Anh rental
        ('travel_place_ChIJz4GteiarNTERU_H8lN4P-UQ'), -- Líu Lô gift shop
        ('travel_place_ChIJpXlJO1EBNTERbXEKoQprgs4'), -- Agarwood Factory shop
        ('travel_place_ChIJ94fevIqrNTERBSbPnqHkFAs'), -- Humanity gift shop
        ('travel_place_ChIJ_XDFSHmrNTERsRGng1QpMGU'), -- CEG Arts school
        ('travel_place_ChIJkYJ6-wurNTERqWAuCMp2IyE'), -- Vườn của mẹ service
        ('travel_place_ChIJ3dTuV8CrNTER52PZBCUnpws'), -- An Cường furniture
        ('travel_place_ChIJmXActLSrNTERoWRIhXOU7LI'), -- Linh Chi rental
        ('travel_place_ChIJlzHw0N6rNTERX1kn2LtrSkk'), -- Mothaiba photo service
        ('travel_place_ChIJKZ8vKpCvNTERZbm9yEckQeY'), -- Lavie wholesaler
        ('travel_place_ChIJR-e8EwCvNTERtbrH5LkASiU')  -- Tí tách manufacturer
)
INSERT INTO knowledge_properties(entity_id, key, value, source, updated_at)
SELECT id,
       'generic_discovery_excluded',
       'true',
       'manual_curation:2026-08-21',
       now()
FROM excluded_ids
ON CONFLICT (entity_id, key) DO UPDATE
SET value = EXCLUDED.value,
    source = EXCLUDED.source,
    updated_at = EXCLUDED.updated_at;

COMMIT;
