import assert from "node:assert/strict";
import test from "node:test";

import {
  URL_SOURCE_ACTION_PROMPTS,
  canSubmitPlannerSource,
  parseUrlOnlyInput,
} from "./url-only-input.ts";

test("accepts and deduplicates http URLs separated by whitespace", () => {
  assert.deepEqual(
    parseUrlOnlyInput("https://example.com/reel/1\nhttps://example.com/reel/1 https://youtu.be/demo"),
    {
      ok: true,
      urls: ["https://example.com/reel/1", "https://youtu.be/demo"]
    }
  );
});

test("rejects prompts and unsupported URL protocols", () => {
  assert.deepEqual(parseUrlOnlyInput("Plan a weekend in Da Lat"), {
    ok: false,
    message: "Ô này chỉ nhận URL đầy đủ, ví dụ https://www.tiktok.com/…"
  });
  assert.deepEqual(parseUrlOnlyInput("ftp://example.com/file"), {
    ok: false,
    message: "Ô này chỉ nhận URL đầy đủ, ví dụ https://www.tiktok.com/…"
  });
});

test("requires at least one URL and limits each import batch", () => {
  assert.deepEqual(parseUrlOnlyInput("   "), {
    ok: false,
    message: "Dán ít nhất một URL để tiếp tục."
  });
  const tooManyUrls = Array.from(
    { length: 21 },
    (_, index) => `https://example.com/${index}`
  ).join("\n");
  assert.deepEqual(parseUrlOnlyInput(tooManyUrls), {
    ok: false,
    message: "Mỗi lần chỉ có thể nhập tối đa 20 URL."
  });
});

test("URL actions fill the composer but a source still needs a non-empty prompt", () => {
  assert.deepEqual(
    URL_SOURCE_ACTION_PROMPTS.map((item) => item.value),
    [
      "Tạo lịch trình chuyến đi từ liên kết này",
      "Tóm tắt nội dung liên kết này",
    ],
  );
  assert.equal(canSubmitPlannerSource("", ["https://example.com"]), false);
  assert.equal(canSubmitPlannerSource("   ", ["https://example.com"]), false);
  assert.equal(
    canSubmitPlannerSource(
      "Tạo lịch trình chuyến đi từ liên kết này",
      ["https://example.com"],
    ),
    true,
  );
});
