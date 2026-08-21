-- Convert only nearby TravelPlaces whose containment is supported by an
-- authoritative source. Proximity alone is not sufficient evidence.
BEGIN;

CREATE TEMP TABLE nearby_subplace_conversion (
    child_id text PRIMARY KEY,
    parent_id text NOT NULL,
    child_name text NOT NULL,
    item_id text NOT NULL,
    item_name text NOT NULL,
    item_normalized_name text NOT NULL,
    item_action text NOT NULL,
    source text NOT NULL,
    source_note text NOT NULL,
    description text NOT NULL,
    priority integer NOT NULL
) ON COMMIT DROP;

INSERT INTO nearby_subplace_conversion VALUES
    (
        'travel_place_ChIJqVNnOpmrNTER2dDqRQCoIZQ',
        'travel_place_ChIJZ73nJpmrNTERHt_VdIgHDlg',
        'Đại Trung Môn',
        'activity_temple_literature_dai_trung_gate',
        'tham quan Đại Trung Môn',
        'tham quan dai trung mon',
        'visit',
        'https://vanmieu.gov.vn/vi/visit/architecture/dai-trung-gate',
        'Cổng Đại Trung nằm sau khu Nhập đạo và dẫn vào khu thứ hai của Văn Miếu.',
        'Đại Trung Môn là công trình kiến trúc nằm trên trục tham quan bên trong Văn Miếu – Quốc Tử Giám.',
        86
    ),
    (
        'travel_place_ChIJ1ciNRL71NDERfMFkrRWU370',
        'travel_place_ChIJ-6HFHmX1NDERUJ39_6BiTL8',
        'Cổng làng Mông Phụ',
        'activity_duong_lam_mong_phu_gate',
        'tham quan Cổng làng Mông Phụ',
        'tham quan cong lang mong phu',
        'visit',
        'https://sovhtt.hanoi.gov.vn/don-nhan-mo-hinh-cong-lang-mong-phu/',
        'Sở Văn hóa và Thể thao Hà Nội xác định đây là kiến trúc thuộc di sản Làng cổ Đường Lâm.',
        'Cổng làng Mông Phụ là cổng làng cổ và một công trình thuộc di sản Làng cổ Đường Lâm.',
        88
    ),
    (
        'travel_place_ChIJq1IYO-auNTER60_Eo9L1vh0',
        'travel_place_ChIJKSrIeqWvNTERMIh8kSr2sgs',
        'Chợ gốm Bát Tràng',
        'activity_bat_trang_ceramic_market',
        'khám phá Chợ gốm Bát Tràng',
        'kham pha cho gom bat trang',
        'shop',
        'https://sovhtt.hanoi.gov.vn/hoi-lang-bat-trang/',
        'Sở Văn hóa và Thể thao Hà Nội mô tả chợ gốm nằm ở vị trí trung tâm của làng.',
        'Chợ gốm Bát Tràng nằm ở trung tâm làng gốm, tập trung các gian hàng gốm và hoạt động mua sắm.',
        84
    );

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM nearby_subplace_conversion conversion
        LEFT JOIN knowledge_entities child ON child.id = conversion.child_id
        LEFT JOIN knowledge_entities parent ON parent.id = conversion.parent_id
        WHERE child.id IS NULL
           OR child.entity_type NOT IN ('TravelPlace', 'SubPlace')
           OR parent.id IS NULL
           OR parent.entity_type <> 'TravelPlace'
           OR NOT EXISTS (
               SELECT 1 FROM knowledge_properties property
               WHERE property.entity_id = conversion.child_id
                 AND property.key = 'latitude'
           )
           OR NOT EXISTS (
               SELECT 1 FROM knowledge_properties property
               WHERE property.entity_id = conversion.child_id
                 AND property.key = 'longitude'
           )
    ) THEN
        RAISE EXCEPTION 'Nearby SubPlace curation preflight failed';
    END IF;
END $$;

UPDATE knowledge_entities entity
SET entity_type = 'SubPlace',
    canonical_name = conversion.child_name,
    updated_at = now()
FROM nearby_subplace_conversion conversion
WHERE entity.id = conversion.child_id;

DELETE FROM knowledge_relationships relationship
USING nearby_subplace_conversion conversion
WHERE relationship.relationship_type = 'Has_Subplace'
  AND relationship.to_entity_id = conversion.child_id
  AND relationship.from_entity_id <> conversion.parent_id;

INSERT INTO knowledge_relationships(
    from_entity_id, relationship_type, to_entity_id,
    recommendations, source, source_note, created_at, updated_at
)
SELECT conversion.parent_id,
       'Has_Subplace',
       conversion.child_id,
       json_build_object('status', 'pending', 'priority', conversion.priority),
       conversion.source,
       conversion.source_note ||
           ';batch=kg_nearby_subplace_curation_v1_20260821',
       now(), now()
FROM nearby_subplace_conversion conversion
ON CONFLICT (from_entity_id, relationship_type, to_entity_id) DO UPDATE
SET recommendations = EXCLUDED.recommendations,
    source = EXCLUDED.source,
    source_note = EXCLUDED.source_note,
    updated_at = EXCLUDED.updated_at;

INSERT INTO knowledge_entities(
    id, canonical_name, normalized_name, entity_type,
    status, created_at, updated_at
)
SELECT conversion.item_id,
       conversion.item_name,
       conversion.item_normalized_name,
       'ActivityItem',
       'pending', now(), now()
FROM nearby_subplace_conversion conversion
ON CONFLICT (id) DO UPDATE
SET canonical_name = EXCLUDED.canonical_name,
    normalized_name = EXCLUDED.normalized_name,
    entity_type = EXCLUDED.entity_type,
    updated_at = EXCLUDED.updated_at;

INSERT INTO knowledge_relationships(
    from_entity_id, relationship_type, to_entity_id,
    recommendations, source, source_note, created_at, updated_at
)
SELECT conversion.child_id,
       'Offer_Item',
       conversion.item_id,
       json_build_object(
           'status', 'pending',
           'priority', conversion.priority,
           'action', conversion.item_action,
           'displayTemplate', '{action} {item} tại {subplace}'
       ),
       conversion.source,
       'curated;verification=pending;batch=' ||
           'kg_nearby_subplace_curation_v1_20260821',
       now(), now()
FROM nearby_subplace_conversion conversion
ON CONFLICT (from_entity_id, relationship_type, to_entity_id) DO UPDATE
SET recommendations = EXCLUDED.recommendations,
    source = EXCLUDED.source,
    source_note = EXCLUDED.source_note,
    updated_at = EXCLUDED.updated_at;

INSERT INTO knowledge_properties(entity_id, key, value, source, updated_at)
SELECT conversion.child_id,
       'description',
       conversion.description,
       conversion.source,
       now()
FROM nearby_subplace_conversion conversion
ON CONFLICT (entity_id, key) DO UPDATE
SET value = EXCLUDED.value,
    source = EXCLUDED.source,
    updated_at = EXCLUDED.updated_at;

COMMIT;
