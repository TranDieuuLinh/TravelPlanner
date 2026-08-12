# Task 02: Chuẩn hóa và TripContext

## Mục tiêu

Chuyển destination text và trip constraint thành canonical evaluation context
được mọi stage downstream của PlaceChecker sử dụng.

## Phụ thuộc

Task 01.

## Đầu vào và đầu ra

Input: ADM text, days, budget, people, preferences và avoids đã validate.

Output: `TripEvaluationContext` chứa ADM text ban đầu, canonical ADM ID/name,
country, region key, resolution status, pace, capacity range, budget mode,
preference/avoid đã chuẩn hóa và people profile.

Projection kỳ vọng cho Hanoi:

```json
{
  "input_name": "Hanoi",
  "adm_id": "adm1_vn_ha_noi",
  "canonical_name": "Hà Nội",
  "country_code": "VN",
  "region_key": "vn,ha_noi",
  "status": "resolved"
}
```

## Quy tắc

- Chuẩn hóa Unicode, khoảng trắng, case và alias trước khi lookup ADM.
- Resolve ADM qua KG scope resolution; không hardcode Hanoi trong service.
- ADM ambiguous chặn global candidate search và trả clarification data.
- Pace mặc định là `balanced` nếu Explorer chưa cung cấp.
- Capacity tham khảo là 360/480/600 experience minute mỗi ngày cho
  slow/balanced/fast; đây là phân tích tổng, không phải lịch.
- Budget có target amount dùng monetary mode. Budget level không có target dùng
  relative tier mode.
- Avoid mặc định là soft nếu Explorer không cung cấp explicit hard policy.

## Công cụ và phương án dự phòng

Dùng port hẹp `AdmResolver`. Cache có thể trả lookup. Khi KG lỗi có thể dùng
internal normalized ADM index; external place search không được dùng để resolve
destination scope.

## Test và điều kiện hoàn thành

Test alias, Unicode name, ambiguity, missing scope, relative budget, target
budget, default pace và normalize `nightlife`. Hoàn thành khi fake resolver tạo
được resolved/ambiguous/unresolved context một cách deterministic.
