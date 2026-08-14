# Phase 04 — Tích hợp Explorer, Information Finder, Place Checker và Planner

Cập nhật lần cuối: 2026-08-14

## Explorer

Explorer nhận projection gồm destination, duration, preferences, mentioned/selected places và resolved references. Explorer hoàn thiện input nhưng không ghi đè fact confirmed.

## Information Finder

- Dùng destination/reference để rewrite query khi user hỏi tiếp.
- Fact lấy từ nguồn ghi provenance URL và confidence.
- Câu trả lời web không tự trở thành user preference hoặc selected place.

## Place Checker

Place Checker chỉ đọc destination/ADM context, mentioned/selected places, constraints và source provenance. Nó trả `input_name`, `canonical_place_id`, `status`, `confidence`, `evidence`, `warnings`.

Memory module merge canonical resolution/evidence. Place Checker không sở hữu memory và không tự thay thế địa điểm user bằng candidate KG.

## Itinerary Planner

- Chỉ nhận selected/resolved candidates và TripIntent chuẩn hóa.
- Không đọc raw transcript.
- Khi plan chốt, ghi `current_plan_ref`; không ghi toàn bộ plan thành user preference.

## Nghiệm thu end-to-end

1. “Hà Nội có gì chơi?”
2. “Lên plan các điểm bên trên trong 3 ngày.”
3. Place Checker giữ và resolve đúng các địa điểm đã nêu.
4. Planner tạo plan Hà Nội 3 ngày mà không hỏi lại destination.
5. “Thêm chỗ đó vào ngày 2.” cập nhật đúng hoặc hỏi clarification nếu mơ hồ.
