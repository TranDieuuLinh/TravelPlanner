-- Apply the second reviewed Hanoi curation batch and repair the Kim Dong
-- cultural center identity. Exact IDs keep the migration bounded and
-- idempotent; entity IDs and unrelated graph edges remain stable.
BEGIN;

WITH desired_types(id, entity_type) AS (
    VALUES
        ('travel_place_ChIJaWlsPwCrNTER8NNLjrKU4p0', 'Entertainment'),
        ('travel_place_ChIJCeHW656rNTERCw7xzWfHGd8', 'Entertainment'),
        ('travel_place_ChIJVzb6uL-rNTERVQlcs4CJtqA', 'Entertainment'),
        ('travel_place_ChIJm6F3sZGrNTERguWWeYzilbo', 'Entertainment'),
        ('travel_place_ChIJ1U4UlL-rNTERdM3qf41Cgdk', 'Entertainment'),
        ('travel_place_ChIJr22rT3irNTER_VrIImiuOsA', 'Entertainment'),
        ('entertainment_dessert_ChIJ__9v1LqrNTERw6DdpcC6Lsg', 'TravelPlace'),
        ('entertainment_ChIJVXl_L2YdNTERnaDvJaLx_G8', 'TravelPlace'),
        ('travel_place_ChIJnX7lbwCvNTERY1Cc91DXwIE', 'Restaurant'),
        ('travel_place_ChIJMU276MOrNTERt2P1o7zuxzM', 'Restaurant')
)
UPDATE knowledge_entities entity
SET entity_type = desired.entity_type,
    updated_at = now()
FROM desired_types desired
WHERE entity.id = desired.id
  AND entity.entity_type <> desired.entity_type;

UPDATE knowledge_entities
SET canonical_name = 'Đỉnh Hàm Lợn',
    normalized_name = 'dinh ham lon',
    updated_at = now()
WHERE id = 'entertainment_ChIJVXl_L2YdNTERnaDvJaLx_G8';

UPDATE knowledge_entities
SET canonical_name = 'Tiệm phở Nam Dư',
    normalized_name = 'tiem pho nam du',
    updated_at = now()
WHERE id = 'travel_place_ChIJnX7lbwCvNTERY1Cc91DXwIE';

WITH excluded_ids(id) AS (
    VALUES
        ('travel_place_ChIJl8jcSX-tNTERufw-8C7NebU'),
        ('travel_place_ChIJLTKXCpCrNTERQVai5LIjkRw'),
        ('travel_place_ChIJj8D-PBypNTERak_WAOBnCuI'),
        ('travel_place_ChIJz8bxNnGsNTEROsoHD1FYCUA'),
        ('travel_place_ChIJL7i834arNTEReG0v9BPH-_I'),
        ('travel_place_ChIJn_phsK6rNTERTX_4_tRYEXI'),
        ('travel_place_ChIJ6fsNbQCtNTERr3XTaHtf4C0'),
        ('travel_place_ChIJ0QSE99uuNTER-d6du9EjO-c')
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

UPDATE knowledge_entities
SET canonical_name = 'Trung tâm Văn hóa Kim Đồng',
    normalized_name = 'trung tam van hoa kim dong',
    entity_type = 'Entertainment',
    review_count = NULL,
    updated_at = now()
WHERE id = 'travel_place_ChIJl-LyseyrNTERQ-BBP-MJQ5k';

DELETE FROM knowledge_aliases
WHERE entity_id = 'travel_place_ChIJl-LyseyrNTERQ-BBP-MJQ5k';

INSERT INTO knowledge_aliases(
    entity_id, alias, normalized_alias, language, source
)
VALUES
    ('travel_place_ChIJl-LyseyrNTERQ-BBP-MJQ5k',
     'Kim Dong Theater', 'kim dong theater', 'en',
     'manual_curation:2026-08-21'),
    ('travel_place_ChIJl-LyseyrNTERQ-BBP-MJQ5k',
     'Rạp Kim Đồng', 'rap kim dong', 'vi',
     'manual_curation:2026-08-21');

DELETE FROM knowledge_properties
WHERE entity_id = 'travel_place_ChIJl-LyseyrNTERQ-BBP-MJQ5k'
  AND key IN (
      'image', 'meta_json', 'rating', 'review_count',
      'time_close', 'time_open', 'url_google_map'
  );

INSERT INTO knowledge_properties(entity_id, key, value, source, updated_at)
VALUES
    ('travel_place_ChIJl-LyseyrNTERQ-BBP-MJQ5k', 'description',
     'Trung tâm Văn hóa Kim Đồng là rạp chiếu phim và trung tâm văn hóa thiếu nhi tại số 19–21 phố Hàng Bài, quận Hoàn Kiếm, Hà Nội; tiền thân là rạp chiếu phim quen thuộc dành cho thiếu nhi và học sinh Thủ đô.',
     'manual_curation:2026-08-21', now()),
    ('travel_place_ChIJl-LyseyrNTERQ-BBP-MJQ5k', 'address',
     '19–21 P. Hàng Bài, Hoàn Kiếm, Hà Nội, Việt Nam',
     'https://www.openstreetmap.org/way/863234970', now()),
    ('travel_place_ChIJl-LyseyrNTERQ-BBP-MJQ5k', 'latitude',
     '21.0237571', 'https://www.openstreetmap.org/way/863234970', now()),
    ('travel_place_ChIJl-LyseyrNTERQ-BBP-MJQ5k', 'longitude',
     '105.8532364', 'https://www.openstreetmap.org/way/863234970', now())
ON CONFLICT (entity_id, key) DO UPDATE
SET value = EXCLUDED.value,
    source = EXCLUDED.source,
    updated_at = EXCLUDED.updated_at;

DELETE FROM knowledge_entity_images
WHERE entity_id = 'travel_place_ChIJl-LyseyrNTERQ-BBP-MJQ5k';

DELETE FROM knowledge_relationships
WHERE relationship_type = 'Special_Near'
  AND (
      from_entity_id = 'travel_place_ChIJl-LyseyrNTERQ-BBP-MJQ5k'
      OR to_entity_id = 'travel_place_ChIJl-LyseyrNTERQ-BBP-MJQ5k'
  );

DELETE FROM knowledge_relationships
WHERE from_entity_id = 'travel_place_ChIJl-LyseyrNTERQ-BBP-MJQ5k'
  AND relationship_type = 'Has_Style'
  AND to_entity_id = 'style_shopping_discovery';

UPDATE knowledge_relationships
SET to_entity_id = 'adm2_81c15c52a0',
    source = 'https://www.openstreetmap.org/way/863234970',
    updated_at = now()
WHERE from_entity_id = 'travel_place_ChIJl-LyseyrNTERQ-BBP-MJQ5k'
  AND relationship_type = 'Located_In';

COMMIT;
