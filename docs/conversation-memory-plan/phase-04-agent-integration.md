# Phase 04 — Tích hợp Explorer, Information Finder, Place Checker và Planner

Cập nhật lần cuối: 2026-08-14

## Explorer

Explorer nhận projection gồm destination, duration, preferences, mentioned/selected places và resolved references. Root orchestration dùng memory làm nguồn chuẩn cho destination/duration khi projection đã có giá trị, đồng thời hợp nhất địa điểm từ memory với địa điểm Explorer đã nhận (không thay thế evidence URL/input của Explorer). Explorer hoàn thiện input nhưng không ghi đè fact confirmed.

## Information Finder

- Dùng destination/reference để rewrite query khi user hỏi tiếp.
- Chỉ thêm context ngắn gọn (destination và tối đa các entity đã resolve) vào query; không đưa toàn bộ transcript hoặc raw third-party payload vào Information Finder.
- Fact lấy từ nguồn ghi provenance URL và confidence.
- Câu trả lời web không tự trở thành user preference hoặc selected place.

## Place Checker

Place Checker chỉ đọc destination/ADM context, mentioned/selected places, resolved reference đơn nhất, constraints và source provenance. Các place candidate từ memory được bổ sung sau candidate Explorer và giữ `source_url`/excerpt trong evidence; candidate tham chiếu mơ hồ không được tự động đưa vào pool. Nó trả `input_name`, `canonical_place_id`, `status`, `confidence`, `evidence`, `warnings`.

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
