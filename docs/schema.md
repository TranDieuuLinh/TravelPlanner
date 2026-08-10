# Schema module, agent và tool

Cập nhật lần cuối: 2026-08-10.

Backend dùng kiến trúc module hóa với LangGraph. Mỗi module expose public
contract qua `public.py`; state và node nội bộ không được module khác truy cập
trực tiếp.

## Ranh giới API

| Endpoint | Input | Output |
|---|---|---|
| `GET /health` | Không có | `{ "status": "ok" }` |
| `POST /v1/agent/invoke` | `InvokeRequest` | `InvokeResponse` |

## Các module

| Module | Input | Output |
|---|---|---|
| `supervisor` | `SupervisorInput` | `SupervisorDecision` |
| `explorer` | `ExplorerInput` | `ExplorerOutput` |
| `information_finder` | `InformationFinderInput` | `InformationFinderOutput` |
| `place_checker` | `PlaceCheckerInput` | `PlaceCheckerOutput` |
| `itinerary_planner` | `ItineraryPlannerInput` | `ItineraryPlannerOutput` |
| `plan_editor` | `PlanEditorInput` | `PlanEditorOutput` |

## Các agent hiện có

Tên agent được định nghĩa trong `AgentName`:

- `supervisor`
- `explorer`
- `information_finder`
- `place_checker`
- `itinerary_planner`
- `plan_editor`

Root orchestration graph gọi các agent theo flow:

```text
supervisor
├── information_finder
├── plan_editor
└── explorer -> place_checker -> itinerary_planner
```

Input của root graph là `RootGraphInput`; output là `RootGraphOutput`.

## Tool và provider adapter

Hiện chưa có standalone tool registry. Các tool/adapter đang có:

| Tool / adapter | Module | Input | Output |
|---|---|---|---|
| `UnconfiguredInformationProvider` | `information_finder` | `query: str` | `InformationFinderOutput` |
| `DevelopmentCatalog.resolve` | `place_checker` | `PlaceCandidate`, `TripIntent` | `VerifiedPlace \| None` |
| `DevelopmentCatalog.discover` | `place_checker` | `TripIntent`, `limit: int` | `list[VerifiedPlace]` |
| `EstimatedRoutingProvider.travel_minutes` | `itinerary_planner` | Hai giá trị `VerifiedPlace` | Số phút dạng `int` |

Các provider interface bên ngoài hiện có:

- `InformationProvider`
- `PlaceResolver`
- `PlaceDiscovery`
- `RoutingProvider`

## Shared contract

Các schema dùng chung chính:

- `TripIntent`
- `Coordinates`
- `PlaceCandidate`
- `VerifiedPlace`
- `ItineraryItem`
- `ItineraryDay`
- `Itinerary`
- `EditOperation`
- `AgentTrace`
- `AgentError`

## Schema request và response của API

- `InvokeRequest`: `thread_id`, `message`, `supplied_candidates`,
  `existing_itinerary`, `edit_operation`.
- `InvokeResponse`: `request_id`, `route`, `response`, `itinerary`,
  `clarification_question`, `warnings`.

Tài liệu này chỉ mô tả scaffold hiện tại. Authentication, repository dùng
database, tool import URL, tìm place live, routing live và agent Marketplace
chưa được triển khai.
