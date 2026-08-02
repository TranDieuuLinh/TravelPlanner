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

Planner nhận `TravelIntent` đã chuẩn hóa và `selectedPlaces`, sau đó đi qua bốn
ranh giới nội bộ: `PlanningContextBuilder -> PlannerEvidenceCollector ->
MacroPlanGenerator -> MacroPlanPolicy`. Ngay trước khi lập kế hoạch, context
builder gọi `auto_statistics.get_for_planner(regionKey)`; Place thay đổi thì
snapshot mới được tạo, không thay đổi thì dùng snapshot hiện tại. Planner chỉ
phân bổ Place đã xác nhận vào ngày ở mức constraint, không chọn giờ, route hoặc
commit `TripItem` chi tiết.

`PlannerEvidenceCollector` tạo một `evidenceBundle` duy nhất gồm catalog
capability, tourism zones và warning.
`RegionOverviewTool` không còn được gọi trong đường chạy Planner vì category,
price coverage và catalog availability đã thuộc catalog snapshot. Knowledge
Graph sở hữu ý nghĩa theme/experience; catalog statistics chỉ chứng minh độ phủ,
độ mới và khả năng thực thi của dữ liệu hiện có.

Input chính:

```json
{
  "plannerInput": {
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
      "activePlaceCount": 90
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
  },
  "evidenceBundle": {
    "catalog": {
      "regionKey": "vn,ha-noi",
      "snapshotId": "snapshot_123",
      "catalogVersion": 3,
      "activePlaceCount": 90,
      "categoryCounts": {},
      "timeOfDayCoverage": {},
      "dataQuality": {},
      "priceCoverage": {},
      "geographicSummary": {},
      "candidateAreas": []
    },
    "tourismZones": [],
    "warnings": []
  }
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
        "tourismZoneRef": "vn-ha-noi-ba-dinh--place-museum",
        "anchorPlaceRefs": ["place-museum"],
        "primaryActivityCategory": "attraction",
        "maxLocalTravelMinutes": 20,
        "allowRegionFallback": false,
        "mainRegionLocked": true,
        "pace": "balanced",
        "dayPartGoals": {
          "morning": "Prioritize culture activities supported in the morning.",
          "lunch": "Use a balanced food block in the lunch.",
          "afternoon": "Use a balanced culture block in the afternoon.",
          "evening": "Keep evening flexible; regional data coverage is weak."
        },
        "dayWindow": {
          "earliestStart": "08:30",
          "latestEnd": "21:30"
        },
        "activityNeeds": [
          {
            "role": "main",
            "goal": "Khám phá di sản trong khu vực",
            "experienceType": "museum",
            "preferredExperiences": ["museum", "heritage"],
            "minDurationMinutes": 75,
            "maxDurationMinutes": 150,
            "required": true,
            "mustBeExactPlace": true
          },
          {
            "role": "support",
            "goal": "Bổ sung một trải nghiệm văn hóa khác loại",
            "preferredExperiences": ["temple", "architecture"],
            "minDurationMinutes": 45,
            "maxDurationMinutes": 120,
            "required": true
          }
        ],
        "mealNeeds": [
          {
            "role": "lunch",
            "earliestStart": "11:30",
            "latestEnd": "13:30",
            "minDurationMinutes": 45,
            "maxDurationMinutes": 75
          },
          {
            "role": "dinner",
            "earliestStart": "17:30",
            "latestEnd": "20:00",
            "minDurationMinutes": 45,
            "maxDurationMinutes": 90
          }
        ],
        "allocatedSelectedPlaceRefs": ["place_123"],
        "notes": ["Exact schedule is delegated to Finder."]
      }
  ],
  "warnings": []
}
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

Planner MVP dùng một hoặc hai structured LLM call tùy độ phức tạp:

1. Chuyến local đơn vùng tối đa ba ngày tạo `PlannerResearchDraft` deterministic
   từ intent; chuyến dài, road trip hoặc multi-base dùng
   `journey_research_v3_graph_experiences` để tạo
   journey style, chiến lược đa dạng, capability queries và yêu cầu mở rộng vùng.
2. Backend chạy `RepositoryPlannerResearchTool` trên Place active. Capability
   local được match theo taxonomy; region lân cận được xếp từ centroid và khoảng
   cách địa lý, chưa phải route đã xác minh.
   Mỗi theme đồng thời được mở rộng qua `TravelKnowledgeSearchTool` thành
   experience query terms, category và diversity groups có version.
3. Backend tạo `tourismZones` quanh các Place anchor có tọa độ, popularity và
   capability phù hợp. Tâm, bán kính và anchor đều là evidence từ catalog;
   LLM chỉ được chọn `zoneId`, không được tự sinh tọa độ.
4. `macro_planner_v6_main_experience_first` nhận `evidenceBundle`, proposal,
   `PlannerVerifiedResearch` và tourism zones, sau đó sinh
   `PlannerMacroPlanDraft`.

`MacroPlan` có thêm `journeyStyle` và `journeyPhases` để biểu diễn local base,
hub-and-spoke, multi-base hoặc road trip. Model nhận intent, trip spec, profile
dài hạn, selected places và statistics khu vực nhỏ. Code không tự sinh template
khi LLM lỗi; thay vào đó validate đủ ngày liên tiếp, target region thuộc snapshot
hoặc verified nearby regions, journey phases hợp lệ, và mọi `selectedPlace` được
phân bổ đúng một lần hoặc nằm trong `unallocatedSelectedPlaces`.

Statistics dùng riêng phần catalog capability từ Place active; các semantic
signal như theme và diversity phải đến từ Knowledge Graph, không suy ra từ tag
phổ biến. Metric catalog tổng vẫn được giữ để quan sát chất lượng dữ liệu. Khi catalog
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
sau đó tạo DaySkeleton và fill lịch cụ thể. Khung MVP hiện tại cố định ba bữa ăn
quanh hai activity: breakfast, main, lunch, support và dinner; pace chưa làm
thay đổi số activity.
`PlannerAgentOutput.tourismZones` được chuyển nguyên trạng vào `FinderAgentInput`;
Finder không nhận tọa độ do model tự tạo.

`DayBrief` mô tả nhu cầu thay vì lịch đóng đinh. `dayWindow` là biên ngày;
`activityNeeds` giữ đúng một main bắt buộc có `mustBeExactPlace=true`, support tùy
pace và bonus tùy chọn;
`mealNeeds` giữ ba bữa lõi bằng cửa sổ thời gian. Finder chọn toàn bộ activity
trước rồi mới fill meal Place và chọn giờ khả thi theo giờ mở cửa và route.
Lunch độc lập với theme;
coffee hoặc một nhà hàng thứ hai không được dùng để giả làm activity văn hóa.
Timing cue có provenance từ URL vẫn được giữ riêng và không bị cửa sổ mềm ghi đè.

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
  "tourismZones": [],
  "allowFinderSuggestions": true
}
```

`allowFinderSuggestions=false` được dùng khi intake URL/ảnh/OCR đã phủ đủ hai
activity cho mọi ngày. Coverage nguồn dùng sức chứa hai activity/ngày; ví dụ sáu
activity tạo ba ngày, còn năm activity cũng tạo ba ngày và bật suggestion để
Finder lấp activity thứ sáu. Meal Place vẫn được tìm từ catalog sau khi toàn bộ
activity trong ngày đã được chọn. Prompt thuần dùng giá trị `true` cho mọi ngày.

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

Finder MVP hiện dùng rule deterministic, tối đa 25 candidate cho mỗi activity
block. Break block không bắt buộc có Place và bị loại nếu activity ở một trong
hai phía không được xếp; không còn break mồ côi chỉ vì skeleton có sẵn. Budget/route chưa được tự ước lượng:
khi chưa có tool phù hợp, output giữ `tripCostEstimate: null` thay vì để LLM tự
sinh số.

Catalog retrieval của Finder dùng ba tầng. Tầng đầu dùng Knowledge Graph mở rộng
`DayBrief.theme`, `focusTags`, `dayPartGoals`, target area và `JourneyPhase`
thành experience query terms, category và diversity group. Tầng hai lọc cứng
active Place theo region/bbox, category và danh sách đã dùng/loại trừ. Tầng ba
rerank toàn bộ tập hợp lệ bằng structured relevance (`placeType`, `placeGroup`,
tags, name, region), rating, số review, data confidence và tọa độ. Description là
evidence phụ, không phải điều kiện để Place được retrieve. Khi target
region nhỏ thiếu dữ liệu, tool có thể đọc dần region cha nhưng Place fallback
phải có locality tương ứng trong tên hoặc mô tả. Finder không dùng accommodation
cho activity thường và không dùng food/transport/shopping để lấp một theme
không tương thích. Selected Place do user xác nhận vẫn được ưu tiên và không bị
category guard tự động loại.

Graph/category, region và constraint là hard filter. Trong tập activity đã hợp
lệ, popularity kết hợp rating với số review là tín hiệu xếp hạng chính; khoảng
cách chỉ được dùng sau popularity. Vì vậy activity gần hơn không tự động thắng
một địa điểm được đánh giá tốt và có nhiều review hơn.

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
tạo meal break. Finder đưa `local food`, `local cuisine`, loại bữa ăn, sở
thích, theme và mục tiêu của ngày vào truy vấn. Nếu không có Place hợp lệ,
Finder giữ meal placeholder có `source=finder_rule` và trả planning warning để
không mô tả plan như đã hoàn thiện.

Sau khi hai activity được cố định, Finder mới fill meal theo hình học tuyến:
breakfast gần điểm bắt đầu/đường tới main, lunch giảm detour trên hành lang từ
main tới support, và dinner gần support. Meal ranking không được tác động ngược
lại lựa chọn activity. Tất cả activity candidate được reserve trước bước này để
meal không thể dùng lại Place của support chưa xuất hiện trên timeline. Nếu
support là trải nghiệm ẩm thực do Finder gợi ý, candidate phải là điểm ăn nhẹ
(café, bakery, dessert, snack hoặc food market), không phải nhà hàng cho một bữa
ăn đầy đủ.

Khi DayBrief có `tourismZoneRef`, catalog query ưu tiên bbox và mọi Place gợi ý
được kiểm tra lại bằng khoảng cách Haversine. Candidate thường nằm trong bán kính
2,5 km; địa điểm nổi tiếng có evidence mạnh (rating, số review, confidence) được
mở rộng có kiểm soát tối đa 8 km. Candidate thiếu tọa độ hoặc xa hơn ngưỡng này bị
loại; fallback lên region cha không thể làm hành trình rộng không giới hạn.
Khi graph khớp một area được người dùng nêu rõ, Planner đặt
`mainRegionLocked=true`: main activity bắt buộc ở trong tourism zone; ngoại lệ
"địa điểm nổi tiếng" chỉ còn áp dụng cho support/bonus/meal.
Nếu chưa có zone và `allowRegionFallback=false`, candidate phải thuộc đúng
`targetRegionKey`. Sau hard boundary, Finder dùng khoảng cách tới
`UserStatus.location` làm tín hiệu rerank phụ.

Runtime Planner/Finder không dùng embedding. Các cột và job backfill embedding có
thể còn tồn tại trong storage trong giai đoạn chuyển tiếp nhưng không tham gia
candidate retrieval hoặc tourism-zone ranking.

Runtime routing hiện tạm tắt public transit vì latency. Finder chỉ gọi Valhalla
cho pedestrian và car; OpenTripPlanner adapter vẫn tồn tại nhưng không được gọi
và bus không xuất hiện trong `PlanTransportLeg.alternatives`.

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
