# Planning agent contracts

Tài liệu này định nghĩa cách các agent trong module `plans` giao tiếp với nhau.
Schema code nằm ở `backend/app/modules/plans/dto/agent_contracts.py`.

## Flow chính

```text
ExplorerAgentInput
        |
        v
Explorer
        |
        v
ExplorerAgentOutput
        |
        v
PlannerAgentInput
        |
        v
Planner
        |
        v
PlannerAgentOutput
        |
        v
FinderAgentInput
        |
        v
Finder
        |
        v
FinderAgentOutput
```

## Nguyên tắc giao tiếp

- Agent chỉ nhận input qua schema input của mình.
- Agent chỉ trả output qua schema output của mình.
- Không truyền payload raw từ tool/provider sang agent tiếp theo.
- Mọi output nên có `trace` để biết agent đã làm gì và vì sao.
- `Explorer` tạo `TravelIntent`; `Planner` tạo `MacroPlan`; `Finder` tạo
  `PlanDay[]`.
- `url_reels` chỉ được đưa vào Explorer dưới dạng `UrlReelSignal`, không đi thẳng
  vào Planner hoặc Finder.
- `destination` luôn là khu vực chung, ví dụ `Da Nang`, `Da Lat`, `Tokyo`.
- Explorer context là output công khai. Place extraction là stream nội bộ; mọi
  loại địa điểm, gồm food/cafe, nằm trong một `placeCandidates` và category dùng
  để phân loại.
- `PlaceCandidateAggregator` gộp candidate từ prompt/OCR/URL và giữ danh sách
  source. Resolver tự động lưu chúng vào `user_must_place`; không hỏi user lại.
- Explorer chỉ bàn giao `intakeId + userId + explorer`; không tự gọi Planner
  hoặc Finder. Planner downstream dùng context và giữ hai correlation key.
- Finder là consumer của `user_must_place` trong planning flow và phải đọc theo
  cả `intakeId + userId`.
- Nhu cầu final như khách sạn, phương tiện, giá tiền và lịch theo ngày nằm trong
  schema output của Finder: `finalDays` và `tripCostEstimate`.

## Explorer

Explorer nhận request ban đầu, destination, `tripSpec`, địa điểm chi tiết nếu có
và tín hiệu từ URL reels.

Input chính:

```json
{
  "rawRequest": "Tạo lịch trình Đà Nẵng 3 ngày từ vài reels đồ ăn",
  "destination": "Da Nang",
  "placeCandidates": [
    {
      "name": "Son Tra",
      "category": "attraction",
      "placeId": null,
      "address": null,
      "source": "user",
      "sourceUrl": null,
      "confidence": 1,
      "priority": 1,
      "notes": "User wants this in the trip"
    }
  ],
  "urlReelSignals": [
    {
      "url": "https://www.instagram.com/reel/...",
      "platform": "instagram",
      "extractedPlaces": ["Quan mi quang A"],
      "extractedPlaceDetails": [
        {
          "name": "Quan mi quang A",
          "category": "food",
          "placeId": null,
          "address": "12 Nguyen Hue, Da Nang",
          "source": "url_reel",
          "sourceUrl": "https://www.instagram.com/reel/...",
          "confidence": 0.82,
          "priority": 1,
          "notes": "Caption mentioned this address"
        }
      ],
      "interests": ["food"],
      "constraints": [],
      "confidence": 0.82,
      "notes": ["extracted from caption/transcript"]
    }
  ],
  "userState": {
    "userId": "user_123",
    "locale": "vi-VN",
    "timezone": "Asia/Ho_Chi_Minh",
    "travelStyle": "local",
    "travelPreferences": ["food", "coffee"]
  },
  "tripSpec": {
    "days": 3,
    "partySize": 2,
    "startDate": null,
    "endDate": null,
    "accommodation": {
      "required": true,
      "hotelArea": "near city center",
      "checkInDate": null,
      "checkOutDate": null,
      "roomCount": 1,
      "guestCount": 2,
      "preferences": ["clean", "easy transport"]
    },
    "transport": {
      "required": true,
      "preferredModes": ["taxi", "walk"],
      "avoidModes": [],
      "includeBetweenPlaces": true,
      "includeArrivalDeparture": true
    },
    "budget": {
      "targetAmount": 5000000,
      "currency": "VND",
      "level": "medium"
    }
  }
}
```

Mỗi phần tử `selectedPlaces` có thể mang hướng dẫn itinerary từ URL:

```json
{
  "name": "Xôi Yến",
  "sourceRefs": ["https://www.tiktok.com/..."],
  "sourceOrder": 1,
  "sourceDay": 1,
  "sourceTimeHint": "breakfast",
  "sourceActivity": "Order traditional topping turmeric sticky rice",
  "sourceDurationMinutes": null
}
```

`sourceTimeHint` là cue có provenance, không phải giờ mở cửa hoặc giờ chính xác
đã xác minh. `sourceDurationMinutes` chỉ có giá trị khi nguồn nói rõ duration.
Khi có `sourceOrder`, Planner ưu tiên các stop URL, cho phép blueprint có nhiều
stop hơn capacity mặc định của pace, và Finder dùng strategy
`source_itinerary`. Route optimizer giữ thứ tự nguồn; hard constraint vẫn có thể
loại stop nhưng phải trả reason/warning.

Output chính:

Ngân sách chỉ nằm tại `tripSpec.budget`, gồm `targetAmount` gần đúng, `currency`
và `level` nhận `low`, `medium` hoặc `high`. `intent` không lặp lại budget.

```json
{
  "intent": {
    "destination": "Da Nang",
    "travelStyle": "local",
    "pace": "balanced",
    "interests": ["food", "coffee"],
    "mustVisitPlaces": ["Son Tra"],
    "avoidPlaces": [],
    "constraints": [],
    "constraintPolicy": {
      "excludedPlaceTypes": [],
      "geographicScope": {
        "type": "unrestricted"
      }
    },
    "clarifyingQuestions": []
  },
  "tripSpec": {
    "days": 3,
    "partySize": 2,
    "startDate": null,
    "endDate": null,
    "accommodation": {
      "required": true,
      "hotelArea": "near city center",
      "checkInDate": null,
      "checkOutDate": null,
      "roomCount": 1,
      "guestCount": 2,
      "preferences": ["clean", "easy transport"]
    },
    "transport": {
      "required": true,
      "preferredModes": ["taxi", "walk"],
      "avoidModes": [],
      "includeBetweenPlaces": true,
      "includeArrivalDeparture": true
    },
    "budget": {
      "targetAmount": 5000000,
      "currency": "VND",
      "level": "medium"
    }
  },
  "assumptions": ["Use medium budget because user did not specify exact amount."],
  "missingInfoQuestions": [],
  "trace": {
    "agent": "explorer",
    "status": "completed",
    "summary": "Normalized user request into TravelIntent.",
    "notes": []
  }
}
```

Output place riêng:

```json
{
  "placeCandidates": [
    {
      "name": "Quan mi quang A",
      "category": "food",
      "addressHint": "12 Nguyen Hue, Da Nang",
      "sources": [
        {
          "type": "url",
          "url": "https://www.instagram.com/reel/..."
        }
      ],
      "confidence": 0.82,
      "priority": 1,
      "notes": "Caption mentioned this address"
    }
  ]
}
```

## Planner

Planner nhận `TravelIntent` đã chuẩn hóa, `selectedPlaces` và snapshot thống kê
theo `regionKey`, sau đó tạo macro plan/day briefs. Ngay trước khi lập kế hoạch,
workflow gọi `auto_statistics.get_for_planner(regionKey)`; Place thay đổi thì
snapshot mới được tạo, không thay đổi thì dùng snapshot hiện tại. Planner chỉ
phân bổ Place đã xác nhận vào ngày ở mức constraint, không chọn giờ, route hoặc
commit `TripItem` chi tiết.

Input chính:

```json
{
  "mode": "main",
  "intent": {},
  "tripSpec": {},
  "regionContext": {
    "regionKey": "vn,ha-noi",
    "snapshotRef": {
      "regionKey": "vn,ha-noi",
      "snapshotId": "snapshot_123",
      "catalogVersion": 3,
      "algorithmVersion": "auto_statistics_v3_0",
      "generatedAt": "2026-07-28T10:00:00+00:00"
    },
    "placeCount": 100,
    "activePlaceCount": 90,
    "tagCounts": {},
    "timeOfDayCoverage": {},
    "plannerEligible": {},
    "areaProfiles": [
      {
        "regionKey": "vn,ha-noi,hoan-kiem",
        "activePlaceCount": 25,
        "topTags": ["culture", "food"]
      }
    ],
    "plannerSignals": {
      "statisticsLevel": "smallest_available_region",
      "candidateAreas": []
    }
  },
  "selectedPlaces": [],
  "placeCandidates": [],
  "planState": {
    "tripId": "trip_123",
    "lockedItemIds": [],
    "excludedPlaceNames": [],
    "warnings": []
  },
  "originalMacroPlan": null,
  "checkReport": null
}
```

Output chính:

```json
{
  "mode": "main",
  "tripSpec": {},
  "macroPlan": {
    "title": "Main plan for Hà Nội",
    "destination": "Hà Nội",
    "regionKey": "vn,ha-noi",
    "dayBriefs": [
      {
        "day": 1,
        "theme": "Culture and local food",
        "targetArea": "Hoan Kiem",
        "targetRegionKey": "vn,ha-noi,hoan-kiem",
        "focusTags": ["culture", "food"],
        "pace": "balanced",
        "dayPartGoals": {
          "morning": "Prioritize culture activities supported in the morning.",
          "lunch": "Use a balanced food block in the lunch.",
          "afternoon": "Use a balanced culture block in the afternoon.",
          "evening": "Keep evening flexible; regional data coverage is weak."
        },
        "allocatedSelectedPlaceRefs": ["place_123"],
        "notes": ["Exact schedule is delegated to Finder."]
      }
    ]
  },
  "dayBriefsReady": true,
  "unallocatedSelectedPlaces": [],
  "assumptions": [],
  "warnings": [],
  "trace": {
    "agent": "planner",
    "status": "completed",
    "summary": "Created MacroPlan and DayBriefs.",
    "notes": ["snapshotId=snapshot_123"]
  }
}
```

Snapshot thống kê Planner đã query chỉ được ghi trong internal trace/log, không
đưa vào `MacroPlan` hoặc Finder context. Mọi `selectedPlace` phải xuất hiện trong
`allocatedSelectedPlaceRefs` hoặc `unallocatedSelectedPlaces` kèm `reasonCode`.
Planner không nhận toàn bộ danh mục Place hay payload thô của provider; research
tool chỉ trả capability counts, region keys và tối đa một số sample Place làm
evidence.

Planner MVP dùng hai structured LLM call:

1. `journey_research_v2` tạo `PlannerResearchDraft`: journey style, chiến lược
   đa dạng, capability queries và yêu cầu mở rộng vùng.
2. Backend chạy `RepositoryPlannerResearchTool` trên Place active. Capability
   local được match theo taxonomy; region lân cận được xếp từ centroid và khoảng
   cách địa lý, chưa phải route đã xác minh.
3. `macro_planner_v3` nhận cả proposal và `PlannerVerifiedResearch`, sau đó sinh
   `PlannerMacroPlanDraft`.

`MacroPlan` có thêm `journeyStyle` và `journeyPhases` để biểu diễn local base,
hub-and-spoke, multi-base hoặc road trip. Model nhận intent, trip spec, profile
dài hạn, selected places và statistics khu vực nhỏ. Code không tự sinh template
khi LLM lỗi; thay vào đó validate đủ ngày liên tiếp, target region thuộc snapshot
hoặc verified nearby regions, journey phases hợp lệ, và mọi `selectedPlace` được
phân bổ đúng một lần hoặc nằm trong `unallocatedSelectedPlaces`.

Statistics dùng riêng `plannerEligible` và `plannerSignals` từ Place active;
metric catalog tổng vẫn được giữ để quan sát chất lượng dữ liệu. Khi catalog
active trống nhưng có Place đã xác nhận, Planner vẫn có thể tạo DayBrief và cảnh
báo Finder chỉ dùng các Place đó. Khi cả hai nguồn đều trống,
`dayBriefsReady=false`.

`selectedPlaces` thông thường vẫn tuân theo số activity block của pace và số
ngày. URL stop có `sourceOrder` nhưng không có `sourceDay` được phân bổ theo thứ
tự vào số ngày hiện hành và không bị loại chỉ vì capacity pace; `sourceDay` rõ
ràng được giữ. `avoidPlaces` và `constraintPolicy` vẫn thắng blueprint URL; stop
xung đột hoặc có ngày nguồn vượt duration được giữ trong
`unallocatedSelectedPlaces` với `reasonCode`, không bị bỏ hoặc đổi ngày ngầm.

## Finder

Finder nhận `MacroPlan`, `selectedPlaces`, `UserStatus` và `FinderPlanStatus`,
sau đó tạo DaySkeleton động và fill lịch cụ thể. Số block phụ thuộc pace và
UserStatus: `relaxed` ít block, `anchor_led` trung bình, `multi_stop` nhiều block.

Input chính:

```json
{
  "mode": "main",
  "intent": {},
  "tripSpec": {},
  "macroPlan": {},
  "selectedPlaces": [],
  "placeCandidates": [],
  "planState": {
    "tripId": "trip_123",
    "lockedItemIds": [],
    "excludedPlaceNames": [],
    "warnings": []
  },
  "userState": {
    "userId": "user_123",
    "locale": "vi-VN",
    "timezone": "Asia/Ho_Chi_Minh",
    "travelPreferences": []
  },
  "userStatus": {},
  "finderPlanStatus": {},
  "allowFinderSuggestions": true
}
```

`allowFinderSuggestions=false` được dùng khi intake URL/ảnh/OCR tự quyết định
duration theo coverage của nguồn, hoặc khi nguồn đã phủ hết duration user yêu
cầu. Nếu user nói rõ số ngày dài hơn coverage nguồn, giá trị là `true`, nhưng
Finder chỉ gọi catalog cho ngày chưa có stop nguồn; không lấp thêm activity block
trong ngày URL/OCR. Prompt thuần dùng giá trị `true` cho mọi ngày.

Output chính:

```json
{
  "mode": "main",
  "finalDays": [
    {
      "day": 1,
      "theme": "Food and local neighborhoods",
      "strategy": "anchor_led",
      "items": [
        {
          "itemId": "item_123",
          "placeId": "place_123",
          "name": "Selected museum",
          "timeWindow": "09:00-11:00",
          "placeType": "must_visit",
          "role": "main_activity",
          "source": "selected_place",
          "durationMinutes": 120,
          "activityIntensity": "moderate"
        },
        {
          "itemId": "item_124",
          "placeId": null,
          "name": "Break between main and support activities",
          "timeWindow": "11:00-12:00",
          "placeType": "break",
          "role": "break_main_support",
          "source": "finder_rule",
          "durationMinutes": 60
        }
      ]
    }
  ],
  "tripCostEstimate": null,
  "unscheduledPlaces": [],
  "finalUserStatus": {},
  "finalPlanStatus": {},
  "warnings": [],
  "trace": {
    "agent": "finder",
    "status": "completed",
    "summary": "Filled dynamic day skeletons from MacroPlan.",
    "notes": []
  }
}
```

Finder MVP hiện dùng rule deterministic, tối đa năm candidate cho mỗi activity
block. Break block không bắt buộc có Place. Budget/route chưa được tự ước lượng:
khi chưa có tool phù hợp, output giữ `tripCostEstimate: null` thay vì để LLM tự
sinh số.

Catalog retrieval của Finder dùng hai tầng. Tầng đầu rank mô tả Place theo query
được tạo từ `DayBrief.theme`, `focusTags`, `dayPartGoals`, target area và
`JourneyPhase` chứa ngày hiện tại, sau đó lấy shortlist. Tầng hai rerank bằng
`placeType`, `placeGroup`, tags, region, data confidence và tọa độ. Khi target
region nhỏ thiếu dữ liệu, tool có thể đọc dần region cha nhưng Place fallback
phải có locality tương ứng trong tên hoặc mô tả. Finder không dùng accommodation
cho activity thường và không dùng food/transport/shopping để lấp một theme
không tương thích. Selected Place do user xác nhận vẫn được ưu tiên và không bị
category guard tự động loại.

`metadata.description`, `metadata.placeGroup` và minimum duration trong
`metadata.recommendedDurationRange` được adapter đưa vào context nội bộ của
Finder. Minimum duration cho phép một chuyến ghé ngắn hợp lệ khi typical duration
lớn hơn slot; nếu minimum vẫn vượt slot thì candidate bị loại như trước.

Runtime phải inject `RepositoryFinderPlaceTool`; `EmptyFinderPlaceTool` chỉ dùng
cho test hoặc fallback cô lập. Service nhận/trả qua `FinderAgentInput` và
`FinderAgentOutput`; các helper `fill_main_plan`/`fill_backup_plan` chỉ được giữ
để tương thích code cũ.

Trước khi commit candidate, Finder kiểm tra:

- tên Place không nằm trong `avoidPlaces`;
- `placeType`/tag/tên không khớp `constraintPolicy.excludedPlaceTypes`;
- `placeType`, tag hoặc `regionKey` có bằng chứng phù hợp
  `constraintPolicy.geographicScope`; phạm vi `coastal` không được suy luận chỉ
  từ tên hiển thị;
- duration không vượt quá activity block;
- intensity và `maxConsecutiveActiveMinutes`;
- `availableAt`;
- accessibility feature đáp ứng toàn bộ `accessibilityNeeds`;
- constraint `avoid_outdoor` dựa trên type/tag, không suy luận chỉ từ tên.

Meal block là slot có candidate category `food_drink`, không còn mặc định luôn
tạo `Lunch break`/`Dinner break`. Finder đưa `local food`, `local cuisine`, sở
thích, theme và mục tiêu của ngày vào truy vấn. Nếu không có Place hợp lệ,
Finder giữ meal placeholder có `source=finder_rule` và trả planning warning để
không mô tả plan như đã hoàn thiện.

Trong shortlist đã được rank theo relevance, Finder dùng khoảng cách tới
`UserStatus.location` làm tín hiệu phụ để tránh chọn các Place đúng chủ đề nhưng
rời rạc. Candidate thiếu tọa độ vẫn được giữ nhưng chịu penalty có giới hạn.

`Group social activity` vẫn có trong skeleton dưới dạng `Coming soon`. Item này
không phải Place đã commit, không được tính vào usage hoặc provenance count và
không làm thay đổi timeline/UserStatus.

Khi chưa có route data, `maxWalkingMinutesPerDay` được trả thành warning thay vì
giả vờ đã kiểm tra. `requiredRestMinutes` cũng tạo warning nếu skeleton không đủ
thời gian nghỉ. Selected Place nhập tay không có ID giữ `placeId: null`; Finder
dùng stable ref nội bộ và không biến display name thành ID giả. `sourceRefs` và
`tags` của selected Place được giữ tới `PlanItem` và Backup Plan.

## Message envelope

Khi cần queue/background job hoặc multi-agent runtime, bọc payload bằng
`AgentMessage`.

```json
{
  "requestId": "req_123",
  "fromAgent": "explorer",
  "toAgent": "planner",
  "messageType": "planner.input",
  "payload": {},
  "trace": []
}
```

`payload` trong envelope phải validate được bằng schema tương ứng với
`messageType`.
