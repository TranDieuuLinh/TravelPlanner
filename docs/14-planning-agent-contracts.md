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
- `placeCandidates` là gợi ý chưa được xác nhận và không được Planner xem là
  yêu cầu bắt buộc. `selectedPlaces` là các Place đã được user xác nhận và là
  đầu vào chính thức của Planner.
- URL tool có thể trích địa điểm từ reels và đưa vào `placeCandidates`. User cũng
  có thể nhập địa điểm cụ thể trực tiếp vào `placeCandidates` với `source: "user"`.
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
      "placeId": null,
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
      "totalBudget": {
        "amount": 5000000,
        "currency": "VND",
        "confidence": "medium",
        "notes": "User estimate"
      },
      "perPersonBudget": null,
      "includeFood": true,
      "includeTransport": true,
      "includeHotel": true,
      "includeTickets": true
    }
  }
}
```

Output chính:

```json
{
  "intent": {
    "destination": "Da Nang",
    "budgetLevel": "balanced",
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
      "totalBudget": {
        "amount": 5000000,
        "currency": "VND",
        "confidence": "medium",
        "notes": "Use as upper budget if possible"
      },
      "perPersonBudget": null,
      "includeFood": true,
      "includeTransport": true,
      "includeHotel": true,
      "includeTickets": true
    }
  },
  "placeCandidates": [
    {
      "name": "Son Tra",
      "placeId": null,
      "source": "user",
      "sourceUrl": null,
      "confidence": 1,
      "priority": 1,
      "notes": "Detailed place inside Da Nang"
    },
    {
      "name": "Quan mi quang A",
      "placeId": null,
      "source": "url_reel",
      "sourceUrl": "https://www.instagram.com/reel/...",
      "confidence": 0.82,
      "priority": 2,
      "notes": "Extracted from reel and accepted as a concrete food stop"
    },
    {
      "name": "Cafe with sea view",
      "source": "url_reel",
      "sourceUrl": "https://www.instagram.com/reel/...",
      "confidence": 0.55,
      "notes": "Not specific enough to schedule yet"
    }
  ],
  "assumptions": ["Use balanced budget because user did not specify exact amount."],
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
    "snapshotRef": {
      "regionKey": "vn,ha-noi",
      "snapshotId": "snapshot_123",
      "catalogVersion": 3,
      "algorithmVersion": "auto_statistics_v2_1",
      "generatedAt": "2026-07-28T10:00:00+00:00"
    },
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
    "notes": []
  }
}
```

`snapshotRef` bắt buộc đi cùng `MacroPlan` để có thể truy vết dữ liệu Planner đã
dùng. Mọi `selectedPlace` phải xuất hiện trong
`allocatedSelectedPlaceRefs` hoặc `unallocatedSelectedPlaces` kèm `reasonCode`.
Planner không nhận toàn bộ danh mục Place hay payload thô của provider.

## Finder

Finder nhận `MacroPlan`, `placeCandidates` và state hiện tại, sau đó fill lịch
trình cụ thể theo ngày.

Input chính:

```json
{
  "mode": "main",
  "intent": {},
  "tripSpec": {},
  "macroPlan": {},
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
  }
}
```

Output chính:

```json
{
  "mode": "main",
  "finalDays": [
    {
      "day": 1,
      "title": "Food and local neighborhoods",
      "hotel": {
        "name": "Hotel near Han River",
        "category": "hotel",
        "timeWindow": "overnight",
        "address": "Da Nang city center",
        "estimatedCost": {
          "amount": 800000,
          "currency": "VND",
          "confidence": "medium",
          "notes": "Estimated nightly cost"
        },
        "notes": "Suggested area, not booked"
      },
      "items": [
        {
          "name": "Son Tra",
          "category": "attraction",
          "timeWindow": "08:30-11:00",
          "address": null,
          "estimatedCost": {
            "amount": 0,
            "currency": "VND",
            "confidence": "medium",
            "notes": "Entrance estimate"
          },
          "notes": "Morning visit"
        },
        {
          "name": "Quan mi quang A",
          "category": "food",
          "timeWindow": "12:00-13:30",
          "address": null,
          "estimatedCost": {
            "amount": 100000,
            "currency": "VND",
            "confidence": "medium",
            "notes": "Per person estimate"
          },
          "notes": "Lunch"
        }
      ],
      "transportLegs": [
        {
          "fromPlace": "Hotel near Han River",
          "toPlace": "Son Tra",
          "mode": "taxi",
          "estimatedDurationMinutes": 25,
          "estimatedCost": {
            "amount": 180000,
            "currency": "VND",
            "confidence": "low",
            "notes": "Traffic-dependent estimate"
          },
          "notes": "Check traffic before leaving"
        }
      ],
      "dayCostEstimate": {
        "amount": 1080000,
        "currency": "VND",
        "confidence": "medium",
        "notes": "Hotel + food + transport"
      }
    }
  ],
  "tripCostEstimate": {
    "accommodation": {
      "amount": 2400000,
      "currency": "VND",
      "confidence": "medium",
      "notes": "3 nights estimate"
    },
    "food": {
      "amount": 1200000,
      "currency": "VND",
      "confidence": "medium",
      "notes": "Meals and cafes"
    },
    "transport": {
      "amount": 900000,
      "currency": "VND",
      "confidence": "low",
      "notes": "Taxi/walking mix"
    },
    "attractions": {
      "amount": 500000,
      "currency": "VND",
      "confidence": "medium",
      "notes": "Tickets/activities"
    },
    "total": {
      "amount": 5000000,
      "currency": "VND",
      "confidence": "medium",
      "notes": "Estimated total trip cost"
    }
  },
  "unscheduledPlaces": [],
  "warnings": [],
  "trace": {
    "agent": "finder",
    "status": "completed",
    "summary": "Filled day itinerary from MacroPlan.",
    "notes": []
  }
}
```

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
