-- Remove only known-corrupt/wrong aliases and add reviewed aliases for the
-- Hanoi top-place pool. Existing valid aliases remain untouched. Aliases are
-- normalized with the same ASCII policy used by PlaceChecker named search.
BEGIN;

DELETE FROM knowledge_aliases
WHERE entity_id = ANY(ARRAY[
    'travel_place_ChIJp0o4Er6rNTERjlTif_IXU1k',
    'travel_place_ChIJRbk0UJSrNTERjtl_eCB2tZA',
    'travel_place_ChIJZ73nJpmrNTERHt_VdIgHDlg',
    'travel_place_ChIJF13BXqGrNTERTE3hz8KFDmI',
    'travel_place_ChIJr7enHa-rNTERbivpCTqoenY',
    'travel_place_ChIJEQB--OurNTERK41Q2gDyemQ',
    'travel_place_ChIJfVZXRpGrNTERbkZTVxqHSD0',
    'travel_place_ChIJlclXM5WrNTERDqL5tGu_ugE',
    'travel_place_ChIJUWAbMH-rNTERQMeqJ1gRJlg',
    'travel_place_ChIJuSIb5aOrNTERU_JW9ESZg4U',
    'travel_place_ChIJuerTwf2qNTERnvjmhZRDyik',
    'travel_place_ChIJFaOYFDirNTERzRkPZSn2R8Q',
    'travel_place_ChIJawZgcv6qNTER26OqCYOYLEw',
    'travel_place_ChIJp56AAMCrNTERHTeCAuwWJ7s',
    'travel_place_ChIJld5RqparNTERVK8x7gvhAZc',
    'travel_place_ChIJRXwMyjSsNTERcAR9OfSTxfk',
    'travel_place_ChIJIbhTQzmrNTERHBoID7tQyUc',
    'travel_place_ChIJLw2OlQKtNTER7UrxRgC7Cic',
    'travel_place_ChIJyVBDX32sNTERWF7ITQqdcrY',
    'travel_place_ChIJSXwdOKOrNTERNylYj9mnIbU'
]::text[])
  AND (
      alias LIKE '%?%'
      OR alias IN (
          'phd cd hd ndi',
          'qudng trddng ba ddnh',
          'Hồ Con Rùa'
      )
  );

INSERT INTO knowledge_aliases(
    entity_id, alias, normalized_alias, language, source
)
VALUES
    ('travel_place_ChIJp0o4Er6rNTERjlTif_IXU1k', 'Phố cổ Hà Nội', 'pho co ha noi', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJp0o4Er6rNTERjlTif_IXU1k', 'Hà Nội 36 phố phường', 'ha noi 36 pho phuong', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJp0o4Er6rNTERjlTif_IXU1k', '36 phố phường', '36 pho phuong', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJp0o4Er6rNTERjlTif_IXU1k', 'Old Quarter Hanoi', 'old quarter hanoi', 'en', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJp0o4Er6rNTERjlTif_IXU1k', 'Hanoi 36 Streets', 'hanoi 36 streets', 'en', 'manual_alias_curation:2026-08-21'),

    ('travel_place_ChIJRbk0UJSrNTERjtl_eCB2tZA', 'Nhà thờ Lớn', 'nha tho lon', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJRbk0UJSrNTERjtl_eCB2tZA', 'Nhà thờ Chính tòa Thánh Giuse', 'nha tho chinh toa thanh giuse', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJRbk0UJSrNTERjtl_eCB2tZA', 'Nhà thờ Chính tòa Hà Nội', 'nha tho chinh toa ha noi', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJRbk0UJSrNTERjtl_eCB2tZA', 'St. Joseph''s Cathedral', 'st joseph s cathedral', 'en', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJRbk0UJSrNTERjtl_eCB2tZA', 'St. Joseph''s Cathedral Hanoi', 'st joseph s cathedral hanoi', 'en', 'manual_alias_curation:2026-08-21'),

    ('travel_place_ChIJZ73nJpmrNTERHt_VdIgHDlg', 'Văn Miếu – Quốc Tử Giám', 'van mieu quoc tu giam', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJZ73nJpmrNTERHt_VdIgHDlg', 'Văn Miếu Quốc Tử Giám', 'van mieu quoc tu giam', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJZ73nJpmrNTERHt_VdIgHDlg', 'Văn Miếu', 'van mieu', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJZ73nJpmrNTERHt_VdIgHDlg', 'Temple of Literature Hanoi', 'temple of literature hanoi', 'en', 'manual_alias_curation:2026-08-21'),

    ('travel_place_ChIJF13BXqGrNTERTE3hz8KFDmI', 'Lăng Chủ tịch Hồ Chí Minh', 'lang chu tich ho chi minh', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJF13BXqGrNTERTE3hz8KFDmI', 'Lăng Hồ Chí Minh', 'lang ho chi minh', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJF13BXqGrNTERTE3hz8KFDmI', 'Lăng Bác', 'lang bac', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJF13BXqGrNTERTE3hz8KFDmI', 'Ho Chi Minh Mausoleum', 'ho chi minh mausoleum', 'en', 'manual_alias_curation:2026-08-21'),

    ('travel_place_ChIJr7enHa-rNTERbivpCTqoenY', 'Chùa Trấn Quốc', 'chua tran quoc', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJr7enHa-rNTERbivpCTqoenY', 'Trấn Quốc Pagoda', 'tran quoc pagoda', 'en', 'manual_alias_curation:2026-08-21'),

    ('travel_place_ChIJEQB--OurNTERK41Q2gDyemQ', 'Nhà hát Lớn Hà Nội', 'nha hat lon ha noi', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJEQB--OurNTERK41Q2gDyemQ', 'Nhà hát Lớn', 'nha hat lon', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJEQB--OurNTERK41Q2gDyemQ', 'Hanoi Opera', 'hanoi opera', 'en', 'manual_alias_curation:2026-08-21'),

    ('travel_place_ChIJfVZXRpGrNTERbkZTVxqHSD0', 'Chùa Quán Sứ Hà Nội', 'chua quan su ha noi', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJfVZXRpGrNTERbkZTVxqHSD0', 'Quan Su Pagoda', 'quan su pagoda', 'en', 'manual_alias_curation:2026-08-21'),

    ('travel_place_ChIJlclXM5WrNTERDqL5tGu_ugE', 'Hồ Hoàn Kiếm', 'ho hoan kiem', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJlclXM5WrNTERDqL5tGu_ugE', 'Hồ Gươm', 'ho guom', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJlclXM5WrNTERDqL5tGu_ugE', 'Sword Lake', 'sword lake', 'en', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJlclXM5WrNTERDqL5tGu_ugE', 'Lake of the Returned Sword', 'lake of the returned sword', 'en', 'manual_alias_curation:2026-08-21'),

    ('travel_place_ChIJUWAbMH-rNTERQMeqJ1gRJlg', 'Nhà thờ Thái Hà', 'nha tho thai ha', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJUWAbMH-rNTERQMeqJ1gRJlg', 'Thái Hà Church', 'thai ha church', 'en', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJUWAbMH-rNTERQMeqJ1gRJlg', 'Thai Ha Parish Church', 'thai ha parish church', 'en', 'manual_alias_curation:2026-08-21'),

    ('travel_place_ChIJuSIb5aOrNTERU_JW9ESZg4U', 'Quảng trường Ba Đình', 'quang truong ba dinh', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJuSIb5aOrNTERU_JW9ESZg4U', 'Ba Dinh Plaza', 'ba dinh plaza', 'en', 'manual_alias_curation:2026-08-21'),

    ('travel_place_ChIJuerTwf2qNTERnvjmhZRDyik', 'Phủ Tây Hồ', 'phu tay ho', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJuerTwf2qNTERnvjmhZRDyik', 'Tay Ho Palace', 'tay ho palace', 'en', 'manual_alias_curation:2026-08-21'),

    ('travel_place_ChIJFaOYFDirNTERzRkPZSn2R8Q', 'Ha Pagoda', 'ha pagoda', 'en', 'manual_alias_curation:2026-08-21'),

    ('travel_place_ChIJawZgcv6qNTER26OqCYOYLEw', 'Hồ Tây', 'ho tay', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJawZgcv6qNTER26OqCYOYLEw', 'Tây Hồ', 'tay ho', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJawZgcv6qNTER26OqCYOYLEw', 'Hanoi West Lake', 'hanoi west lake', 'en', 'manual_alias_curation:2026-08-21'),

    ('travel_place_ChIJp56AAMCrNTERHTeCAuwWJ7s', 'Đền Ngọc Sơn', 'den ngoc son', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJp56AAMCrNTERHTeCAuwWJ7s', 'Ngọc Sơn Temple', 'ngoc son temple', 'en', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJp56AAMCrNTERHTeCAuwWJ7s', 'Temple of the Jade Mountain', 'temple of the jade mountain', 'en', 'manual_alias_curation:2026-08-21'),

    ('travel_place_ChIJld5RqparNTERVK8x7gvhAZc', 'Nhà tù Hỏa Lò', 'nha tu hoa lo', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJld5RqparNTERVK8x7gvhAZc', 'Di tích Nhà tù Hỏa Lò', 'di tich nha tu hoa lo', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJld5RqparNTERVK8x7gvhAZc', 'Hỏa Lò Prison', 'hoa lo prison', 'en', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJld5RqparNTERVK8x7gvhAZc', 'Hoa Lo Prison', 'hoa lo prison', 'en', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJld5RqparNTERVK8x7gvhAZc', 'Hanoi Hilton', 'hanoi hilton', 'en', 'manual_alias_curation:2026-08-21'),

    ('travel_place_ChIJRXwMyjSsNTERcAR9OfSTxfk', 'Công viên Yên Sở', 'cong vien yen so', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJRXwMyjSsNTERcAR9OfSTxfk', 'Yên Sở Park', 'yen so park', 'en', 'manual_alias_curation:2026-08-21'),

    ('travel_place_ChIJIbhTQzmrNTERHBoID7tQyUc', 'Bảo tàng Dân tộc học Việt Nam', 'bao tang dan toc hoc viet nam', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJIbhTQzmrNTERHBoID7tQyUc', 'Vietnam Ethnology Museum', 'vietnam ethnology museum', 'en', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJIbhTQzmrNTERHBoID7tQyUc', 'Ethnology Museum Hanoi', 'ethnology museum hanoi', 'en', 'manual_alias_curation:2026-08-21'),

    ('travel_place_ChIJLw2OlQKtNTER7UrxRgC7Cic', 'Chùa Bằng', 'chua bang', 'vi', 'manual_alias_curation:2026-08-21'),

    ('travel_place_ChIJyVBDX32sNTERWF7ITQqdcrY', 'Bảo tàng Phòng không – Không quân', 'bao tang phong khong khong quan', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJyVBDX32sNTERWF7ITQqdcrY', 'Vietnam Air Force Museum', 'vietnam air force museum', 'en', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJyVBDX32sNTERWF7ITQqdcrY', 'Vietnam People''s Air Force Museum', 'vietnam people s air force museum', 'en', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJyVBDX32sNTERWF7ITQqdcrY', 'Air Defence – Air Force Museum', 'air defence air force museum', 'en', 'manual_alias_curation:2026-08-21'),

    ('travel_place_ChIJSXwdOKOrNTERNylYj9mnIbU', 'Hoàng thành Thăng Long', 'hoang thanh thang long', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJSXwdOKOrNTERNylYj9mnIbU', 'Khu trung tâm Hoàng thành Thăng Long', 'khu trung tam hoang thanh thang long', 'vi', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJSXwdOKOrNTERNylYj9mnIbU', 'Thang Long Imperial Citadel', 'thang long imperial citadel', 'en', 'manual_alias_curation:2026-08-21'),
    ('travel_place_ChIJSXwdOKOrNTERNylYj9mnIbU', 'Central Sector of the Imperial Citadel of Thang Long', 'central sector of the imperial citadel of thang long', 'en', 'manual_alias_curation:2026-08-21')
ON CONFLICT (entity_id, alias) DO UPDATE
SET normalized_alias = EXCLUDED.normalized_alias,
    language = EXCLUDED.language,
    source = EXCLUDED.source;

-- Exact duplicate of the reviewed Imperial Citadel entity above: same address,
-- coordinates and rating, but pending and missing review/description evidence.
-- Keep the row for auditability while excluding it from runtime lookup.
UPDATE knowledge_entities
SET status = 'rejected',
    updated_at = now()
WHERE id = 'google_maps:a507b3cf11037f0fb00a160a'
  AND status = 'pending';

COMMIT;
