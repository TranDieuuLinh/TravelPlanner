import assert from "node:assert/strict";
import test from "node:test";

import {
  getDOMFloatingChatRect,
  getPlannerChatClasses,
  getPlannerLayoutClasses,
  preserveFloatingChatRect,
} from "./planner-chat-layout.mjs";

function assertWithinTolerance(actual, expected, maxDiff = 2, message = "") {
  const diff = Math.abs(actual - expected);
  assert.ok(
    diff <= maxDiff,
    `${message} Expected ${actual} to be within ${maxDiff}px of ${expected} (diff: ${diff})`
  );
}

function mockDOMElement({ left, top, width, height }) {
  return {
    getBoundingClientRect() {
      return {
        x: left,
        y: top,
        left,
        top,
        right: left + width,
        bottom: top + height,
        width,
        height,
      };
    },
  };
}

test("DOM Integration Test: BoundingClientRect stability across 3 states (Before -> Loading -> After result)", () => {
  const initialBounds = { left: 100, top: 120, width: 410, height: 600 };
  const mockChatElement = mockDOMElement(initialBounds);

  // Stage 1: Before sending prompt (Idle)
  const rectBefore = getDOMFloatingChatRect(mockChatElement);
  assert.notEqual(rectBefore, null);
  const stateBefore = preserveFloatingChatRect(null, rectBefore, false);

  // Stage 2: During loading (isProcessing = true)
  // Lock rect when request starts
  const domDuringLoading = mockDOMElement({ left: 100.5, top: 120.2, width: 410, height: 600 });
  const rectLoadingDOM = getDOMFloatingChatRect(domDuringLoading);
  const stateLoading = preserveFloatingChatRect(stateBefore, rectLoadingDOM, true);

  // Stage 3: After result (Ready)
  const domAfterResult = mockDOMElement({ left: 100.2, top: 120.1, width: 410.1, height: 600 });
  const rectAfterDOM = getDOMFloatingChatRect(domAfterResult);
  const stateAfter = preserveFloatingChatRect(stateLoading, rectAfterDOM, false);

  // Compare getBoundingClientRect coordinates across all 3 states
  assertWithinTolerance(stateLoading.x, stateBefore.x, 2, "X coordinate changed during loading!");
  assertWithinTolerance(stateLoading.y, stateBefore.y, 2, "Y coordinate changed during loading!");
  assertWithinTolerance(stateLoading.width, stateBefore.width, 2, "Width changed during loading!");
  assertWithinTolerance(stateLoading.height, stateBefore.height, 2, "Height changed during loading!");

  assertWithinTolerance(stateAfter.x, stateBefore.x, 2, "X coordinate changed after result!");
  assertWithinTolerance(stateAfter.y, stateBefore.y, 2, "Y coordinate changed after result!");
  assertWithinTolerance(stateAfter.width, stateBefore.width, 2, "Width changed after result!");
  assertWithinTolerance(stateAfter.height, stateBefore.height, 2, "Height changed after result!");
});

test("Dragged Chat: Preserves custom left/top position before, during, and after request", () => {
  const customDraggedBounds = { left: 42, top: 75, width: 380, height: 520 };
  const mockElement = mockDOMElement(customDraggedBounds);

  const rectBefore = getDOMFloatingChatRect(mockElement);
  // User custom position is locked
  const stateLoading = preserveFloatingChatRect(rectBefore, { left: 250, top: 300, width: 400, height: 600 }, true);

  assert.equal(stateLoading.x, 42);
  assert.equal(stateLoading.y, 75);
  assert.equal(stateLoading.width, 380);
  assert.equal(stateLoading.height, 520);
});

test("Resized Chat: Preserves custom width/height dimensions across request lifecycle", () => {
  const customResizedBounds = { left: 150, top: 100, width: 520, height: 720 };
  const mockElement = mockDOMElement(customResizedBounds);

  const rectBefore = getDOMFloatingChatRect(mockElement);
  const stateLoading = preserveFloatingChatRect(rectBefore, { left: 100, top: 100, width: 400, height: 600 }, true);
  const stateAfter = preserveFloatingChatRect(stateLoading, { left: 100, top: 100, width: 400, height: 600 }, false);

  assert.equal(stateAfter.width, 520);
  assert.equal(stateAfter.height, 720);
});

test("Collapsed Chat: Class preservation during loading without position jumps", () => {
  const classesBefore = getPlannerChatClasses({ isCollapsed: true, isCompact: false, isProcessing: false });
  const classesLoading = getPlannerChatClasses({ isCollapsed: true, isCompact: false, isProcessing: true });
  const classesAfter = getPlannerChatClasses({ isCollapsed: true, isCompact: true, isProcessing: false });

  assert.equal(classesBefore.includes("is-collapsed"), true);
  assert.equal(classesLoading.includes("is-collapsed"), true);
  assert.equal(classesLoading.includes("is-processing"), true);
  assert.equal(classesLoading.includes("plannerChat--compact"), false);
  assert.equal(classesAfter.includes("is-collapsed"), true);
});

test("Mobile Layout: getDOMFloatingChatRect handles null / zero size bounds gracefully", () => {
  const hiddenMobileElement = mockDOMElement({ left: 0, top: 0, width: 0, height: 0 });
  const rect = getDOMFloatingChatRect(hiddenMobileElement);
  assert.equal(rect, null);
});

test("Error / Cancelled Request: Chat rect remains locked at stored coordinates when request fails", () => {
  const storedRect = { x: 80, y: 110, width: 400, height: 580 };
  // Request begins
  const stateLoading = preserveFloatingChatRect(storedRect, { x: 200, y: 200, width: 300, height: 300 }, true);
  // Request fails with error
  const stateError = preserveFloatingChatRect(stateLoading, { x: 200, y: 200, width: 300, height: 300 }, false);

  assert.deepEqual(stateError, storedRect);
});
