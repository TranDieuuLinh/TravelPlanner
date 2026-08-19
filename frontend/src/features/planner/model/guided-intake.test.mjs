import assert from "node:assert/strict";
import test from "node:test";
import {
  budgetFromAnswer,
  buildGuidedIntakeRequest,
} from "./guided-intake.ts";

const currentBudget = {
  currency: "VND",
  level: "medium",
  targetAmount: null,
};

test("parses Vietnamese million amounts without losing decimals", () => {
  assert.deepEqual(budgetFromAnswer("2,5 triệu", currentBudget), {
    ...currentBudget,
    targetAmount: 2_500_000,
  });
});

test("updates the budget level while preserving the remaining envelope", () => {
  assert.deepEqual(budgetFromAnswer("mức cao", currentBudget), {
    ...currentBudget,
    level: "high",
  });
});

test("builds a request in the supported guided-intake order", () => {
  assert.equal(
    buildGuidedIntakeRequest({
      budget: "5 triệu",
      destination: "Đà Nẵng",
    }),
    [
      "Giúp mình lên kế hoạch chuyến đi.",
      "- Điểm đến: Đà Nẵng",
      "- Ngân sách: 5 triệu",
    ].join("\n")
  );
});

test("omits skipped answers", () => {
  assert.equal(
    buildGuidedIntakeRequest({ destination: "Bỏ qua" }),
    "Giúp mình tạo một chuyến đi mới từ các nguồn đã nhập."
  );
});
