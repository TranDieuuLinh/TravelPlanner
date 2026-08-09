import assert from "node:assert/strict";
import test from "node:test";

import {
  normalizeItinerarySearchText,
  searchItineraryPlaces,
} from "./itinerary-search.ts";

const chatOneDays = [
  {
    day: 1,
    items: [
      {
        itemId: "coffee",
        name: "Café Giảng",
        address: "39 Nguyễn Hữu Huân, Hà Nội",
        placeType: "cafe",
        timelineCategory: "food",
      },
      {
        itemId: "break",
        name: "Nghỉ trưa",
        timelineCategory: "break",
      },
    ],
  },
  {
    day: 2,
    items: [
      {
        itemId: "museum",
        name: "Bảo tàng Dân tộc học Việt Nam",
        address: "Cầu Giấy",
        placeType: "museum",
        timelineCategory: "activity",
      },
    ],
  },
];

test("normalizes Vietnamese accents for itinerary search", () => {
  assert.equal(normalizeItinerarySearchText("  Bảo Tàng Đẹp "), "bao tang dep");
});

test("finds only places supplied by the current itinerary", () => {
  assert.deepEqual(
    searchItineraryPlaces(chatOneDays, "cafe").map(
      (result) => result.item.itemId
    ),
    ["coffee"]
  );
  assert.deepEqual(searchItineraryPlaces(chatOneDays, "place from other chat"), []);
});

test("searches name, address, and place type but excludes breaks", () => {
  assert.equal(searchItineraryPlaces(chatOneDays, "cau giay")[0]?.item.itemId, "museum");
  assert.equal(searchItineraryPlaces(chatOneDays, "museum")[0]?.item.itemId, "museum");
  assert.deepEqual(searchItineraryPlaces(chatOneDays, "nghi trua"), []);
});
