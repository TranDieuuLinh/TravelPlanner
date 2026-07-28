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
- `placeCandidates` và `foodPlaces` là gợi ý chưa được xác nhận và không được
  Planner xem là yêu cầu bắt buộc. `placeCandidates` giữ điểm tham quan/hoạt
  động; `foodPlaces` giữ quán ăn và quán cà phê. `selectedPlaces` là các Place
  đã được user xác nhận và là đầu vào chính thức của Planner.
- URL tool có thể trích địa điểm từ reels và đưa vào đúng nhóm. User cũng có thể
  nhập địa điểm cụ thể trực tiếp với `source: "user"`.
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
      "inputMode": "exact",
      "minAmount": null,
      "targetAmount": 5000000,
      "maxAmount": null,
      "currency": "VND",
      "isHardCap": false,
      "confidence": "high",
      "calculationBasis": {
        "partySize": 2,
        "days": 3,
        "nights": 2,
        "destination": "Da Nang",
        "priceTier": "medium"
      },
      "notes": "User gave an approximate total budget."
    }
  }
}
```

Output chính:

`intent.budgetLevel` và `tripSpec.budget.calculationBasis.priceTier` chỉ nhận
`budget`, `medium` hoặc `high`. Giá trị `balanced` chỉ thuộc contract nhịp độ
`pace`.

```json
{
  "intent": {
    "destination": "Da Nang",
    "budgetLevel": "medium",
    "travelStyle": "local",
    "pace": "balanced",
    "interests": ["food", "coffee"],
    "mustVisitPlaces": ["Son Tra"],
    "avoidPlaces": [],
    "constraints": [],
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
      "inputMode": "exact",
      "minAmount": null,
      "targetAmount": 5000000,
      "maxAmount": null,
      "currency": "VND",
      "isHardCap": false,
      "confidence": "high",
      "calculationBasis": {
        "partySize": 2,
        "days": 3,
        "nights": 2,
        "destination": "Da Nang",
        "priceTier": "medium"
      },
      "notes": "User gave an approximate total budget."
    }
  },
  "placeCandidates": [
    {
      "name": "Son Tra",
      "category": "attraction",
      "placeId": null,
      "source": "user",
      "sourceUrl": null,
      "confidence": 1,
      "priority": 1,
      "notes": "Detailed place inside Da Nang"
    }
  ],
  "foodPlaces": [
    {
      "name": "Quan mi quang A",
      "category": "food",
      "placeId": null,
      "source": "url_reel",
      "sourceUrl": "https://www.instagram.com/reel/...",
      "confidence": 0.82,
      "priority": 2,
      "notes": "Extracted from reel and accepted as a concrete food stop"
    },
    {
      "name": "Cafe with sea view",
      "category": "cafe",
      "source": "url_reel",
      "sourceUrl": "https://www.instagram.com/reel/...",
      "confidence": 0.55,
      "notes": "Not specific enough to schedule yet"
    }
  ],
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
      "algorithmVersion": "auto_statistics_v2_1",
      "generatedAt": "2026-07-28T10:00:00+00:00"
    },
    "placeCount": 100,
    "tagCounts": {},
    "timeOfDayCoverage": {},
    "areaProfiles": [],
    "plannerSignals": {}
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
Planner không nhận toàn bộ danh mục Place hay payload thô của provider.

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
  "finderPlanStatus": {}
}
```

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
