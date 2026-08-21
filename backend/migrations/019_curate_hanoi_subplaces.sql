-- Convert reviewed component TravelPlaces into non-independent SubPlaces.
-- Entity IDs, aliases, properties, images and non-structural relationships are
-- preserved. Each converted entity receives one parent and at least one item.
BEGIN;

CREATE TEMP TABLE curated_subplace_conversion (
    child_id text PRIMARY KEY,
    parent_id text NOT NULL,
    child_name text NOT NULL,
    normalized_name text NOT NULL,
    evidence_source text NOT NULL,
    evidence_note text NOT NULL
) ON COMMIT DROP;

INSERT INTO curated_subplace_conversion VALUES
    ('travel_place_ChIJ7XWEcqGrNTERrsLf6W8259s',
     'travel_place_ChIJl-gkmYKrNTERVsfrJs8ODZ8',
     'Chùa Một Cột', 'chua mot cot',
     'https://sovhtt.hanoi.gov.vn/du-an-tu-bo-ton-tao-chua-mot-cot-dien-huu/',
     'Chùa Một Cột/Liên Hoa Đài thuộc quần thể chùa Diên Hựu.'),
    ('travel_place_ChIJm5BAy6arNTERO1z1B3z-0BU',
     'travel_place_ChIJF13BXqGrNTERTE3hz8KFDmI',
     'Nhà sàn Bác Hồ', 'nha san bac ho',
     'https://www.vietnam.travel/things-to-do/11-must-see-attractions-ha-noi',
     'Thành phần trong tuyến tham quan quần thể Lăng Chủ tịch Hồ Chí Minh.'),
    ('travel_place_ChIJqyT4JJmrNTERSCX5Yt9nwiY',
     'travel_place_ChIJZ73nJpmrNTERHt_VdIgHDlg',
     'Khuê Văn Các', 'khue van cac',
     'https://vanmieu.gov.vn/vi/inner-temple',
     'Công trình thuộc nội tự Văn Miếu - Quốc Tử Giám.'),
    ('travel_place_ChIJT3FxVJmrNTERJUNbu3m4YOo',
     'travel_place_ChIJZ73nJpmrNTERHt_VdIgHDlg',
     'Hồ Giám', 'ho giam',
     'https://vanmieu.gov.vn/vi/inner-temple',
     'Hồ Văn/Hồ Giám thuộc tổng thể Văn Miếu - Quốc Tử Giám.'),
    ('travel_place_ChIJxZVbuqKrNTER4I2XSRfxbLg',
     'travel_place_ChIJSXwdOKOrNTERNylYj9mnIbU',
     'Cột cờ Hà Nội', 'cot co ha noi',
     'https://hoangthanhthanglong.vn/khu-di-tich-trung-tam-hoang-thanh-thang-long/',
     'Điểm tham quan thuộc Khu trung tâm Hoàng thành Thăng Long.'),
    ('travel_place_ChIJZTU9yIOrNTERvPnGMXnLfkU',
     'travel_place_ChIJSXwdOKOrNTERNylYj9mnIbU',
     'Khu khảo cổ 18 Hoàng Diệu', 'khu khao co 18 hoang dieu',
     'https://hoangthanhthanglong.vn/di-tich-khao-co-hoc-18-hoang-dieu/',
     'Khu khảo cổ thuộc Khu trung tâm Hoàng thành Thăng Long.'),
    ('travel_place_ChIJM3JHHACrNTERbMN_HLnBE7c',
     'travel_place_ChIJp56AAMCrNTERHTeCAuwWJ7s',
     'Cầu Thê Húc', 'cau the huc',
     'https://sovhtt.hanoi.gov.vn/den-ngoc-son/',
     'Cầu dẫn vào và là hạng mục của quần thể Đền Ngọc Sơn.'),
    ('travel_place_ChIJ8S--CRIzNDER4EBfws0rMNU',
     'travel_place_ChIJlcuEuA0zNDER9Hxtioalcgs',
     'Chùa Thiên Trù', 'chua thien tru',
     'https://cmshn.hanoi.gov.vn/tin-tuc-su-kien-noi-bat/chu-tich-ubnd-thanh-pho-ha-noi-vu-dai-thang-kiem-tra-cong-tac-to-chuc-le-hoi-du-lich-chua-huong-nam-2026-4260219135434839.htm',
     'Điểm chùa thuộc quần thể danh thắng Chùa Hương.'),
    ('travel_place_ChIJoVrS6p9hNDERF1LgO2exJMk',
     'travel_place_ChIJh3K0K1RhNDEREXbFmPaEF_w',
     'Vườn hoa dã quỳ Ba Vì', 'vuon hoa da quy ba vi',
     'manual_curation:2026-08-21',
     'Địa chỉ provider xác định điểm nằm trong Vườn Quốc gia Ba Vì.'),
    ('travel_place_ChIJefmI_YirNTERUBrJAy78Hrw',
     'travel_place_ChIJfyTf5o6rNTER6dKWJmY9GOY',
     'Hồ Bảy Mẫu', 'ho bay mau',
     'manual_curation:2026-08-21',
     'Hồ cảnh quan nằm trong khuôn viên Công viên Thống Nhất.'),
    ('travel_place_ChIJMzodSgCrNTERIWO398vkozs',
     'travel_place_ChIJfyTf5o6rNTER6dKWJmY9GOY',
     'Cổng Lê Duẩn – Công viên Thống Nhất',
     'cong le duan cong vien thong nhat',
     'manual_curation:2026-08-21',
     'Cổng vào là thành phần của Công viên Thống Nhất.'),
    ('travel_place_ChIJ54NLyzCsNTERBXIslXqB30s',
     'travel_place_ChIJRXwMyjSsNTERcAR9OfSTxfk',
     'Hồ Yên Sở', 'ho yen so',
     'manual_curation:2026-08-21',
     'Hồ cảnh quan thuộc Công viên Yên Sở.'),
    ('travel_place_ChIJb-KKBACrNTERxpM9WpKjFJ0',
     'travel_place_ChIJawZgcv6qNTER26OqCYOYLEw',
     'Tượng rồng đôi Hồ Tây', 'tuong rong doi ho tay',
     'manual_curation:2026-08-21',
     'Công trình cảnh quan ven Hồ Tây, không phải itinerary stop độc lập.'),
    ('travel_place_ChIJIa5NbACrNTERQXWu5etnRv4',
     'travel_place_ChIJ3x01HQCrNTERtBCN9T55LnI',
     'Lối vào chợ đêm Hàng Giấy', 'loi vao cho dem hang giay',
     'manual_curation:2026-08-21',
     'Điểm bắt đầu phía Hàng Giấy của Chợ đêm Phố cổ Hà Nội.'),
    ('travel_place_ChIJC1uSGbmrNTERvIuiy_FZMzA',
     'travel_place_ChIJ3x01HQCrNTERtBCN9T55LnI',
     'Khu ẩm thực chợ đêm Đồng Xuân',
     'khu am thuc cho dem dong xuan',
     'manual_curation:2026-08-21',
     'Phân khu ẩm thực thuộc tuyến Chợ đêm Phố cổ Hà Nội.'),
    ('travel_place_ChIJaRerdQCrNTERQelayRB7Upk',
     'travel_place_ChIJ3x01HQCrNTERtBCN9T55LnI',
     'Lối vào chợ đêm Hàng Đào', 'loi vao cho dem hang dao',
     'manual_curation:2026-08-21',
     'Điểm vào tuyến Chợ đêm Phố cổ tại Hàng Đào.');

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM curated_subplace_conversion conversion
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
        RAISE EXCEPTION 'SubPlace curation preflight failed';
    END IF;
END $$;

-- Replace two synthetic children with richer provider-backed entities while
-- retaining the existing relationship IDs, item edges and provenance.
UPDATE knowledge_relationships
SET to_entity_id = 'travel_place_ChIJm5BAy6arNTERO1z1B3z-0BU',
    updated_at = now()
WHERE from_entity_id = 'travel_place_ChIJF13BXqGrNTERTE3hz8KFDmI'
  AND relationship_type = 'Has_Subplace'
  AND to_entity_id = 'subplace_hochiminh_stilt_house';

UPDATE knowledge_relationships
SET from_entity_id = 'travel_place_ChIJm5BAy6arNTERO1z1B3z-0BU',
    updated_at = now()
WHERE from_entity_id = 'subplace_hochiminh_stilt_house'
  AND relationship_type = 'Offer_Item';

UPDATE knowledge_relationships
SET to_entity_id = 'travel_place_ChIJqyT4JJmrNTERSCX5Yt9nwiY',
    updated_at = now()
WHERE from_entity_id = 'travel_place_ChIJZ73nJpmrNTERHt_VdIgHDlg'
  AND relationship_type = 'Has_Subplace'
  AND to_entity_id = 'subplace_temple_literature_khue_van_cac';

UPDATE knowledge_relationships
SET from_entity_id = 'travel_place_ChIJqyT4JJmrNTERSCX5Yt9nwiY',
    updated_at = now()
WHERE from_entity_id = 'subplace_temple_literature_khue_van_cac'
  AND relationship_type = 'Offer_Item';

UPDATE knowledge_entities
SET status = 'rejected', updated_at = now()
WHERE id IN (
    'subplace_hochiminh_stilt_house',
    'subplace_temple_literature_khue_van_cac'
)
  AND status <> 'rejected';

UPDATE knowledge_entities entity
SET entity_type = 'SubPlace',
    canonical_name = conversion.child_name,
    normalized_name = conversion.normalized_name,
    updated_at = now()
FROM curated_subplace_conversion conversion
WHERE entity.id = conversion.child_id
  AND (
      entity.entity_type <> 'SubPlace'
      OR entity.canonical_name <> conversion.child_name
      OR entity.normalized_name <> conversion.normalized_name
  );

INSERT INTO knowledge_relationships(
    from_entity_id, relationship_type, to_entity_id,
    recommendations, source, source_note, created_at, updated_at
)
SELECT conversion.parent_id,
       'Has_Subplace',
       conversion.child_id,
       json_build_object('status', 'pending', 'priority', 90),
       conversion.evidence_source,
       conversion.evidence_note ||
           ';batch=kg_curated_hanoi_subplace_conversion_v1_20260821',
       now(), now()
FROM curated_subplace_conversion conversion
ON CONFLICT (from_entity_id, relationship_type, to_entity_id) DO UPDATE
SET recommendations = EXCLUDED.recommendations,
    source = EXCLUDED.source,
    source_note = EXCLUDED.source_note,
    updated_at = EXCLUDED.updated_at;

-- Keep the weekend night market as the independent parent; entrance markers
-- and its food section are the SubPlaces above.
UPDATE knowledge_entities
SET canonical_name = 'Hanoi Old Quarter Night Market',
    normalized_name = 'hanoi old quarter night market',
    updated_at = now()
WHERE id = 'travel_place_ChIJ3x01HQCrNTERtBCN9T55LnI';

INSERT INTO knowledge_aliases(
    entity_id, alias, normalized_alias, language, source
)
VALUES
    ('travel_place_ChIJ3x01HQCrNTERtBCN9T55LnI',
     'Chợ đêm Phố cổ Hà Nội', 'cho dem pho co ha noi', 'vi',
     'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJ3x01HQCrNTERtBCN9T55LnI',
     'Hanoi Weekend Night Market', 'hanoi weekend night market', 'en',
     'manual_alias_curation:2026-08-21')
ON CONFLICT (entity_id, alias) DO UPDATE
SET normalized_alias = EXCLUDED.normalized_alias,
    language = EXCLUDED.language,
    source = EXCLUDED.source;

CREATE TEMP TABLE curated_subplace_item (
    subplace_id text PRIMARY KEY,
    item_id text NOT NULL,
    item_name text NOT NULL,
    normalized_name text NOT NULL,
    item_type text NOT NULL,
    action text NOT NULL
) ON COMMIT DROP;

INSERT INTO curated_subplace_item VALUES
    ('travel_place_ChIJ7XWEcqGrNTERrsLf6W8259s',
     'activity_one_pillar_lien_hoa_dai', 'tham quan Liên Hoa Đài',
     'tham quan lien hoa dai', 'ActivityItem', 'visit'),
    ('travel_place_ChIJT3FxVJmrNTERJUNbu3m4YOo',
     'activity_temple_literature_ho_van', 'tham quan Hồ Văn',
     'tham quan ho van', 'ActivityItem', 'visit'),
    ('travel_place_ChIJxZVbuqKrNTER4I2XSRfxbLg',
     'activity_hanoi_flag_tower_visit', 'tham quan Cột cờ Hà Nội',
     'tham quan cot co ha noi', 'ActivityItem', 'visit'),
    ('travel_place_ChIJZTU9yIOrNTERvPnGMXnLfkU',
     'activity_thang_long_archaeological_site_visit',
     'tham quan di chỉ khảo cổ 18 Hoàng Diệu',
     'tham quan di chi khao co 18 hoang dieu', 'ActivityItem', 'visit'),
    ('travel_place_ChIJM3JHHACrNTERbMN_HLnBE7c',
     'activity_the_huc_bridge_crossing', 'đi qua cầu Thê Húc',
     'di qua cau the huc', 'ActivityItem', 'walk'),
    ('travel_place_ChIJ8S--CRIzNDER4EBfws0rMNU',
     'activity_thien_tru_pagoda_visit', 'tham quan chùa Thiên Trù',
     'tham quan chua thien tru', 'ActivityItem', 'visit'),
    ('travel_place_ChIJoVrS6p9hNDERF1LgO2exJMk',
     'activity_ba_vi_wild_sunflower_viewing', 'ngắm hoa dã quỳ',
     'ngam hoa da quy', 'ActivityItem', 'view'),
    ('travel_place_ChIJefmI_YirNTERUBrJAy78Hrw',
     'activity_bay_mau_lakeside_walk', 'dạo quanh hồ Bảy Mẫu',
     'dao quanh ho bay mau', 'ActivityItem', 'walk'),
    ('travel_place_ChIJMzodSgCrNTERIWO398vkozs',
     'activity_thong_nhat_le_duan_entry',
     'vào Công viên Thống Nhất từ cổng Lê Duẩn',
     'vao cong vien thong nhat tu cong le duan', 'ActivityItem', 'enter'),
    ('travel_place_ChIJ54NLyzCsNTERBXIslXqB30s',
     'activity_yen_so_lakeside_walk', 'dạo ven hồ Yên Sở',
     'dao ven ho yen so', 'ActivityItem', 'walk'),
    ('travel_place_ChIJb-KKBACrNTERxpM9WpKjFJ0',
     'activity_west_lake_double_dragons_view',
     'ngắm tượng rồng đôi Hồ Tây', 'ngam tuong rong doi ho tay',
     'ActivityItem', 'view'),
    ('travel_place_ChIJIa5NbACrNTERQXWu5etnRv4',
     'activity_hanoi_night_market_hang_giay_entry',
     'bắt đầu tuyến chợ đêm từ Hàng Giấy',
     'bat dau tuyen cho dem tu hang giay', 'ActivityItem', 'enter'),
    ('travel_place_ChIJC1uSGbmrNTERvIuiy_FZMzA',
     'food_item_hanoi_night_market_street_food', 'ẩm thực đường phố',
     'am thuc duong pho', 'FoodItem', 'eat'),
    ('travel_place_ChIJaRerdQCrNTERQelayRB7Upk',
     'activity_hanoi_night_market_hang_dao_entry',
     'bắt đầu tuyến chợ đêm từ Hàng Đào',
     'bat dau tuyen cho dem tu hang dao', 'ActivityItem', 'enter');

INSERT INTO knowledge_entities(
    id, canonical_name, normalized_name, entity_type,
    status, created_at, updated_at
)
SELECT item_id, item_name, normalized_name, item_type,
       'pending', now(), now()
FROM curated_subplace_item
ON CONFLICT (id) DO NOTHING;

INSERT INTO knowledge_relationships(
    from_entity_id, relationship_type, to_entity_id,
    recommendations, source, source_note, created_at, updated_at
)
SELECT item.subplace_id,
       'Offer_Item',
       item.item_id,
       json_build_object(
           'status', 'pending',
           'priority', 90,
           'action', item.action,
           'displayTemplate', '{action} {item} tại {subplace}'
       ),
       conversion.evidence_source,
       'curated;verification=pending;batch=' ||
           'kg_curated_hanoi_subplace_conversion_v1_20260821',
       now(), now()
FROM curated_subplace_item item
JOIN curated_subplace_conversion conversion
  ON conversion.child_id = item.subplace_id
ON CONFLICT (from_entity_id, relationship_type, to_entity_id) DO UPDATE
SET recommendations = EXCLUDED.recommendations,
    source = EXCLUDED.source,
    source_note = EXCLUDED.source_note,
    updated_at = EXCLUDED.updated_at;

-- Exact provider duplicates would otherwise remain independent TravelPlaces.
UPDATE knowledge_entities
SET status = 'rejected', updated_at = now()
WHERE id IN (
    'google_maps:c7a5cf8454d85f8d5dd80922',
    'travel_place_ChIJ1XOqXgCrNTERxFRWuGQ85d8'
)
  AND status <> 'rejected';

COMMIT;
