-- Ensure every active SubPlace can ground its frontend Gemini note in an
-- explicit SubPlace -> Offer_Item -> ActivityItem chain. Existing ProductItem,
-- DrinkItem and FoodItem offers remain intact as separate catalog semantics.
BEGIN;

CREATE TEMP TABLE subplace_activity_completion (
    subplace_id text PRIMARY KEY,
    activity_id text NOT NULL UNIQUE,
    activity_name text NOT NULL,
    normalized_name text NOT NULL,
    action text NOT NULL,
    source text NOT NULL,
    source_note text NOT NULL
) ON COMMIT DROP;

INSERT INTO subplace_activity_completion VALUES
    (
        'subplace_hanoi_old_quarter_ta_hien_beer_corner',
        'activity_hanoi_old_quarter_ta_hien_atmosphere',
        'trải nghiệm không khí góc bia Tạ Hiện – Lương Ngọc Quyến',
        'trai nghiem khong khi goc bia ta hien luong ngoc quyen',
        'experience',
        'https://www.vietnam.travel/things-to-do/11-must-see-attractions-ha-noi',
        'curated;verification=pending;evening'
    ),
    (
        'subplace_hanoi_old_quarter_hang_bac',
        'activity_hanoi_old_quarter_hang_bac_craft',
        'khám phá nghề bạc tại Phố Hàng Bạc',
        'kham pha nghe bac tai pho hang bac',
        'explore',
        'https://vietnam.travel/things-to-do/explore-old-quarter-your-way',
        'curated;verification=pending'
    ),
    (
        'subplace_hanoi_old_quarter_hang_gai',
        'activity_hanoi_old_quarter_hang_gai_silk',
        'khám phá phố lụa Hàng Gai',
        'kham pha pho lua hang gai',
        'explore',
        'https://vietnam.travel/things-to-do/explore-old-quarter-your-way',
        'curated;verification=pending'
    ),
    (
        'subplace_hanoi_old_quarter_hang_ma',
        'activity_hanoi_old_quarter_hang_ma_decorations',
        'ngắm đồ trang trí lễ hội tại Phố Hàng Mã',
        'ngam do trang tri le hoi tai pho hang ma',
        'view',
        'https://vietnam.travel/things-to-do/explore-old-quarter-your-way',
        'curated;verification=pending;seasonal_context=festival'
    ),
    (
        'subplace_hanoi_old_quarter_lan_ong',
        'activity_hanoi_old_quarter_lan_ong_herbs',
        'tìm hiểu phố thảo mộc Lãn Ông',
        'tim hieu pho thao moc lan ong',
        'explore',
        'https://vietnam.travel/things-to-do/explore-old-quarter-your-way',
        'curated;verification=pending;non_medical_recommendation'
    ),
    (
        'travel_place_ChIJC1uSGbmrNTERvIuiy_FZMzA',
        'activity_dong_xuan_night_market_food_area',
        'khám phá khu ẩm thực chợ đêm Đồng Xuân',
        'kham pha khu am thuc cho dem dong xuan',
        'explore',
        'manual_curation:2026-08-21',
        'curated;verification=pending'
    );

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM subplace_activity_completion completion
        LEFT JOIN knowledge_entities subplace
          ON subplace.id = completion.subplace_id
         AND subplace.entity_type = 'SubPlace'
         AND subplace.status <> 'rejected'
        WHERE subplace.id IS NULL
    ) THEN
        RAISE EXCEPTION 'SubPlace ActivityItem completion preflight failed';
    END IF;
END $$;

INSERT INTO knowledge_entities(
    id, canonical_name, normalized_name, entity_type,
    status, created_at, updated_at
)
SELECT activity_id, activity_name, normalized_name, 'ActivityItem',
       'pending', now(), now()
FROM subplace_activity_completion
ON CONFLICT (id) DO UPDATE
SET canonical_name = EXCLUDED.canonical_name,
    normalized_name = EXCLUDED.normalized_name,
    entity_type = EXCLUDED.entity_type,
    updated_at = EXCLUDED.updated_at;

INSERT INTO knowledge_relationships(
    from_entity_id, relationship_type, to_entity_id,
    recommendations, source, source_note, created_at, updated_at
)
SELECT subplace_id,
       'Offer_Item',
       activity_id,
       json_build_object(
           'status', 'pending',
           'priority', 90,
           'action', action,
           'displayTemplate', '{action} {item} tại {subplace}'
       ),
       source,
       source_note ||
           ';batch=kg_subplace_activity_completion_v1_20260821',
       now(), now()
FROM subplace_activity_completion
ON CONFLICT (from_entity_id, relationship_type, to_entity_id) DO UPDATE
SET recommendations = EXCLUDED.recommendations,
    source = EXCLUDED.source,
    source_note = EXCLUDED.source_note,
    updated_at = EXCLUDED.updated_at;

COMMIT;
