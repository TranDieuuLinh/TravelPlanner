import assert from "node:assert/strict";
import test from "node:test";

import {
  formatNoteSources,
  formatPlanNote,
  formatSourceNoteForDisplay,
  planItemNotePresentation
} from "./plan-note.ts";

test("translates known itinerary notes into Vietnamese", () => {
  assert.equal(formatPlanNote("withdraw money"), "Rút tiền");
  assert.equal(
    formatPlanNote("Eat dessert and wait for sightseeing bus."),
    "Ăn món tráng miệng và chờ xe buýt tham quan"
  );
});

test("translates known source notes and preserves unknown English notes", () => {
  assert.equal(
    formatSourceNoteForDisplay(
      "explore cute cafés, shops, and a night market"
    ),
    "Khám phá các quán cà phê xinh xắn, cửa hàng và chợ đêm"
  );
  assert.equal(
    formatSourceNoteForDisplay("nature viewpoint hike"),
    "Đi bộ đường dài đến điểm ngắm cảnh thiên nhiên"
  );
  assert.equal(
    formatSourceNoteForDisplay(
      "purchase the audio guide as the show is in vietnamese"
    ),
    "Mua hướng dẫn âm thanh vì chương trình biểu diễn bằng tiếng Việt"
  );
  assert.equal(
    formatSourceNoteForDisplay(
      "relaxing head spa treatment that leaves hair shining"
    ),
    "Thư giãn với liệu trình spa đầu giúp tóc bóng mượt"
  );
  assert.equal(
    formatSourceNoteForDisplay("A new untranslated generated note"),
    "A new untranslated generated note"
  );
});

test("translates all curated Hanoi destination stories into Vietnamese", () => {
  const translations = [
    [
      "Hanoi has more than a thousand years of history. In 1010, Emperor Ly Thai To chose it as the imperial capital and named it Thang Long, “Ascending Dragon.” Dynasties, French colonial rule, wars and modernization shaped the layered city seen today.",
      "Hà Nội có hơn một nghìn năm lịch sử. Năm 1010, vua Lý Thái Tổ chọn nơi đây làm kinh đô và đặt tên là Thăng Long, nghĩa là “Rồng bay lên”. Các triều đại, thời kỳ Pháp thuộc, chiến tranh và quá trình hiện đại hóa đã tạo nên một thành phố nhiều lớp lang như ngày nay."
    ],
    [
      "Traffic in Hanoi is busy and unpredictable. Vehicles may approach from unexpected directions, so look carefully—even on one-way streets—and cross only when it is safe.",
      "Giao thông ở Hà Nội đông đúc và khó đoán. Các phương tiện có thể xuất hiện từ những hướng bất ngờ, vì vậy hãy quan sát kỹ — kể cả trên đường một chiều — và chỉ sang đường khi an toàn."
    ],
    [
      "Use Grab or Xanh SM. Confirm that the licence plate, vehicle and driver match the information in the app before entering.",
      "Hãy sử dụng Grab hoặc Xanh SM. Trước khi lên xe, hãy xác nhận biển số, phương tiện và tài xế khớp với thông tin trong ứng dụng."
    ],
    [
      "Do not drink tap water. Choose sealed bottled or adequately treated water, and be cautious about ice.",
      "Không uống nước máy. Hãy chọn nước đóng chai còn nguyên niêm phong hoặc nước đã được xử lý đạt yêu cầu, đồng thời thận trọng với đá."
    ],
    [
      "Keep bags zipped and in front of you in the Old Quarter, markets and public transport. Stay alert to motorcycles approaching from behind.",
      "Hãy kéo khóa túi và giữ túi ở phía trước khi ở Phố Cổ, chợ và trên phương tiện công cộng. Chú ý các xe máy đi tới từ phía sau."
    ],
    [
      "Agree on the complete price and service before taking a cyclo or using an informal service.",
      "Hãy thống nhất toàn bộ mức giá và dịch vụ trước khi đi xích lô hoặc sử dụng một dịch vụ không chính thức."
    ],
    [
      "Cover your shoulders and knees when visiting temples and cultural sites, and follow instructions displayed at the entrance.",
      "Hãy che vai và đầu gối khi tham quan đền, chùa và các địa điểm văn hóa, đồng thời làm theo hướng dẫn được niêm yết tại lối vào."
    ],
    [
      "Train Street is an active railway. Never cross barriers, stand on the tracks or ignore current local restrictions.",
      "Phố đường tàu là tuyến đường sắt vẫn đang hoạt động. Tuyệt đối không vượt rào chắn, đứng trên đường ray hoặc phớt lờ các quy định hiện hành của địa phương."
    ]
  ];

  for (const [english, vietnamese] of translations) {
    assert.equal(formatSourceNoteForDisplay(english), vietnamese);
  }
});

test("hides missing and NaN-like note values", () => {
  for (const value of [null, undefined, Number.NaN, "", "  ", "NaN", " null ", "N/A"]) {
    assert.equal(formatPlanNote(value), null);
  }
});

test("preserves valid notes that do not need a compatibility translation", () => {
  assert.equal(formatPlanNote("Thử món địa phương"), "Thử món địa phương");
});

test("presents source and personal notes without merging their ownership", () => {
  assert.deepEqual(
    planItemNotePresentation({
      notes: "Gọi cà phê trứng vào buổi sáng.",
      noteSources: [
        {
          type: "url",
          text: "Creator gọi cà phê trứng vào buổi sáng và dặn nên gọi ít đường.",
          ref: "https://example.com/reel",
          evidenceTypes: ["stt"]
        },
        {
          type: "google_maps",
          text: "Theo dữ liệu từ Google, Cà phê Giảng là một quán cà phê.",
          ref: "google-place-id"
        }
      ],
      personalNotes: "Nhớ gọi ít đường."
    }),
    {
      sourceNotes: [
        {
          type: "url",
          label: "Gợi ý từ nguồn tham khảo",
          text: "Creator gọi cà phê trứng vào buổi sáng và dặn nên gọi ít đường."
        }
      ],
      sourceLabel: "Gợi ý từ nguồn tham khảo",
      sourceText: "Creator gọi cà phê trứng vào buổi sáng và dặn nên gọi ít đường.",
      personalText: "Nhớ gọi ít đường."
    }
  );
});

test("infers a source label for legacy plan revisions", () => {
  const legacyPresentation = planItemNotePresentation({
    name: "Cà phê Giảng",
    notes: null,
    sourceActivity: "Explore Cà phê Giảng in the morning",
    sourceRefs: ["https://example.com/reel"],
    sourceProvider: "google_maps_scraper",
    placeType: "Coffee shop"
  });
  assert.equal(legacyPresentation.sourceLabel, null);
  assert.deepEqual(legacyPresentation.sourceNotes, []);
  assert.equal(
    formatNoteSources([{ type: "google_maps" }]),
    null
  );
  assert.equal(
    formatNoteSources([
      { type: "url" },
      { type: "place_provider" }
    ]),
    "Gợi ý từ nguồn tham khảo"
  );
});

test("does not turn provider metadata into a note", () => {
  const presentation = planItemNotePresentation({
    name: "Private-Box Hookah",
    source: "finder_suggestion",
    sourceProvider: "google_maps",
    sourceRefs: ["https://example.com/video"],
    notes: "Private-Box Hookah belongs to the coffee shop category.",
    placeType: "Coffee shop",
    rating: 4.9,
    reviewCount: 951
  });

  assert.deepEqual(presentation.sourceNotes, []);
});

test("hides mention-only video provenance", () => {
  const presentation = planItemNotePresentation({
    name: "Hoàng thành Thăng Long",
    noteSources: [
      {
        type: "url",
        text: "Video tham khảo có nhắc đến Hoàng thành Thăng Long."
      }
    ]
  });

  assert.deepEqual(presentation.sourceNotes, []);
});
