# Planning agent contracts

Tài liệu này mô tả contract runtime hiện tại của module `plans`. Schema nguồn
nằm tại `backend/app/modules/plans/dto/agent_contracts.py`.

## Flow chính

```text
Explorer
   |
   v
TripThemePlanner
   |
   v
PlaceSelector
   |
   v
Checker -> Main Plan / Backup Plan
```

`MacroPlan`, `DayBrief`, `PlannerService` và `FinderService` không còn là
contract runtime. TripThemePlanner không tạo lịch theo ngày. PlaceSelector sở
hữu việc tạo đủ số ngày, chọn Place, phân bổ capacity và tối ưu tuyến.

## Nguyên tắc giao tiếp

- Agent chỉ nhận/trả dữ liệu qua schema của chính nó.
- Payload thô của nguồn hoặc provider không đi thẳng vào planning domain.
- `Explorer` trả một `TripIntent` canonical và Place đã chuẩn hóa có provenance.
  Application chiếu aggregate này thành intent/trip spec nội bộ cho các agent
  downstream; hai projection đó không được lưu riêng.
- `TripThemePlanner` chỉ trả yêu cầu trải nghiệm ở cấp toàn chuyến.
- `PlaceSelector` tạo `PlanDay[]` và `UnscheduledPlace[]`.
- `Checker` kiểm tra plan đã hoàn chỉnh; warning giữ plan ở trạng thái `draft`.
- Backup Plan dùng lại `tripThemes` của Main Plan và chạy lại PlaceSelector với
  constraint dự phòng. Nó không chạy lại LLM và không sửa Main Plan.

## Explorer

Explorer chuẩn hóa request, URL signals, destination, duration, pace, interests,
constraints và selected Places. `Confirm` vẫn là ranh giới: claim do AI trích
xuất không tự động trở thành yêu cầu của user.

Explorer bàn giao `intakeId + userId + explorer.tripIntent`; các Place được
resolve và lưu theo provenance trước khi planning workflow sử dụng. Trong trip
chat, lần sửa tiếp theo chỉ đọc TripIntent hiện hành từ PostgreSQL, không đọc
Explorer JSON snapshot.

## TripThemePlanner

Input chính là `TripThemePlanningInput`:

```json
{
  "mode": "main",
  "intent": {
    "destination": "Hà Nội",
    "pace": "balanced",
    "interests": ["culture", "food"]
  },
  "tripSpec": {"days": 3},
  "regionContext": {
    "regionKey": "vn,ha-noi",
    "snapshotRef": {
      "regionKey": "vn,ha-noi",
      "snapshotId": "snapshot_123",
      "catalogVersion": 3,
      "algorithmVersion": "auto_statistics_v3_0",
      "generatedAt": "2026-07-28T10:00:00+00:00"
    },
    "activePlaceCount": 90
  },
  "selectedPlaces": []
}
```

Output là `TripThemePlanningOutput`:

```json
{
  "mode": "main",
  "tripSpec": {"days": 3},
  "tripThemesReady": true,
  "tripThemes": [
    {
      "theme": "Văn hóa Hà Nội",
      "focusTags": ["culture", "history"],
      "minimumActivities": 2,
      "targetRegionKeys": ["vn,ha-noi"]
    }
  ],
  "requiredExperiences": [
    {
      "requirementId": "req-walk-hoan-kiem",
      "theme": "Dạo Hồ Gươm",
      "activityId": "activity-walk-hoan-kiem",
      "selectionPolicy": "required_anchor",
      "anchorPlaceIds": ["place-hoan-kiem"],
      "candidatePlaceIds": [],
      "minimumRequired": 1,
      "priority": "must",
      "reason": "Trải nghiệm đặc trưng có graph evidence.",
      "evidenceClaimIds": ["claim-hoan-kiem-walk"],
      "sourceRefs": ["https://example.com/hoan-kiem"]
    }
  ],
  "assumptions": [],
  "warnings": [],
  "trace": {
    "agent": "trip_theme_planner",
    "status": "completed",
    "summary": "Created trip-wide experience requirements.",
    "notes": ["snapshotId=snapshot_123"]
  }
}
```

Output không được có ngày, route bucket, journey phase hoặc selected-place
allocation. Backend chạy graph research deterministic, tạo bounded
`graphCandidateCatalog`, rồi gọi LLM một lượt để tạo `TripThemeDraft`; CLI
`research-context` hiển thị cùng catalog mà không gọi LLM. Backend sửa contract
lỗi tối đa ba lần. Tổng
`minimumActivities` được chuẩn hóa theo capacity hai activity mỗi ngày; theme
chỉ nói về bữa ăn bị loại vì meal là trách nhiệm riêng của PlaceSelector.

Khi catalog trống nhưng có selected Place, TripThemePlanner vẫn có thể tạo
theme nhưng `requiredExperiences` phải rỗng. Khi cả hai nguồn trống,
`tripThemesReady=false`.

## PlaceSelector

`PlaceSelectionInput` hiện chưa chứa `requiredExperiences`; cutover này chưa
tích hợp các yêu cầu graph vào PlaceSelector.

Input là `PlaceSelectionInput`:

```json
{
  "mode": "main",
  "intent": {"destination": "Hà Nội", "pace": "balanced"},
  "tripSpec": {"days": 3},
  "regionKey": "vn,ha-noi",
  "tripThemes": [],
  "selectedPlaces": [],
  "placeSelectionStatus": {},
  "allowPlaceSuggestions": true
}
```

PlaceSelector tạo đúng số day slot từ `tripSpec.days`; không cần DayBrief từ
LLM. `sourceDay` hợp lệ được giữ, các Place còn lại được xếp theo
`sourceOrder/priority` với capacity cố định hai activity mỗi ngày. Place không
xếp được nằm trong `unscheduledPlaces` với reason code như
`no_day_capacity`, `avoided_by_user` hoặc `no_available_slot`.

Output là `PlaceSelectionOutput` với `finalDays`, `unscheduledPlaces`, trạng thái
cuối, warning và trace có agent `place_selector`.

Route-first chọn hai activity, tối ưu hoạt động ở cấp toàn chuyến, rồi chèn các
meal stop đã xác minh gần anchor tuyến. Stop từ URL giữ provenance và thứ tự
nguồn. Route provider lỗi thì dùng ước tính địa lý và đánh dấu `verified=false`.

## Plan persistence và tương thích

`Plan` lưu trực tiếp `tripThemes` cùng `days`; dữ liệu mới không ghi
`macroPlan`. Model có adapter chỉ-đọc để nạp plan cũ có `macroPlan.tripThemes`,
sau đó serialize lại theo contract mới.

Request cũ dùng `allowFinderSuggestions` vẫn được chấp nhận qua validation
alias, nhưng response mới chỉ xuất `allowPlaceSuggestions`.

Các source code lịch sử như `finder_suggestion` vẫn được đọc để không làm hỏng
revision đã lưu. Code mới không phụ thuộc module Finder.

## Message envelope

Tên agent hợp lệ là `explorer`, `trip_theme_planner`, `place_selector` và
`checker`. Mọi message phải có `requestId`, `fromAgent`, `toAgent`,
`messageType`, `payload`, `createdAt`; `tripId` và `traceId` dùng khi có.
