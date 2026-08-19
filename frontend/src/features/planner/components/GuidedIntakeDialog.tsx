"use client";

import { useRef } from "react";
import { PenguinMascot } from "@/components/PenguinMascot";

type GuidedIntakeStep = "destination" | "dates" | "budget" | "note";

const guidedIntakeQuestions: Record<GuidedIntakeStep, string> = {
  destination: "Bạn muốn đi đâu?",
  dates: "Khi nào bạn muốn đi?",
  budget: "Ngân sách của bạn?",
  note: "Có lưu ý gì không?",
};

const guidedIntakePlaceholders: Record<GuidedIntakeStep, string> = {
  destination: "Ví dụ: Kyoto, Đà Lạt, miền Tây…",
  dates: "Ví dụ: 12–15/09 hoặc cuối tuần sau…",
  budget: "Ví dụ: khoảng 4 triệu mỗi người…",
  note: "Thêm một lưu ý nếu có…",
};

type GuidedIntakeDialogProps = {
  open: boolean;
  step: GuidedIntakeStep;
  draft: string;
  startDate: string;
  endDate: string;
  saving: boolean;
  onClose: () => void;
  onDraftChange: (value: string) => void;
  onStartDateChange: (value: string) => void;
  onEndDateChange: (value: string) => void;
  onSubmitDates: () => void;
  onSubmitAnswer: (answer: string) => void;
};

export function GuidedIntakeDialog({
  open,
  step,
  draft,
  startDate,
  endDate,
  saving,
  onClose,
  onDraftChange,
  onStartDateChange,
  onEndDateChange,
  onSubmitDates,
  onSubmitAnswer,
}: GuidedIntakeDialogProps) {
  const guidedInputRef = useRef<HTMLInputElement>(null);
  return (
    <>
      {open ? (
                <div
                  className="guidedIntakeOverlay"
                  onMouseDown={(event) => {
                    if (event.target === event.currentTarget)
                      onClose();
                  }}
                >
                  <section
                    aria-labelledby="guided-intake-title"
                    aria-modal="true"
                    className={`guidedIntakeDialog isDestination ${
                      step === "dates" ? "isDates" : ""
                    }`}
                    role="dialog"
                  >
                    <button
                      aria-label="Đóng câu hỏi"
                      className="guidedIntakeClose"
                      onClick={() => onClose()}
                      type="button"
                    >
                      <svg aria-hidden="true" viewBox="0 0 24 24">
                        <path d="m7 7 10 10M17 7 7 17" />
                      </svg>
                    </button>
                    <div className="guidedIntakeMascot" aria-hidden="true">
                      <PenguinMascot priority size={132} variant="curious" />
                    </div>
                    <div className="guidedIntakeDialogBody">
                      <h2 id="guided-intake-title">
                        {guidedIntakeQuestions[step]}
                      </h2>
                      {step === "dates" ? (
                        <form
                          className="guidedDatePicker"
                          onSubmit={(event) => {
                            event.preventDefault();
                            onSubmitDates();
                          }}
                        >
                          <div className="guidedDateFields">
                            <label>
                              <span>Ngày bắt đầu</span>
                              <input
                                aria-label="Ngày bắt đầu"
                                onChange={(event) => {
                                  const nextStartDate = event.target.value;
                                  onStartDateChange(nextStartDate);
                                }}
                                type="date"
                                value={startDate}
                              />
                            </label>
                            <span className="guidedDateArrow">đến</span>
                            <label>
                              <span>Ngày kết thúc</span>
                              <input
                                aria-label="Ngày kết thúc"
                                min={startDate || undefined}
                                onChange={(event) =>
                                  onEndDateChange(event.target.value)
                                }
                                type="date"
                                value={endDate}
                              />
                            </label>
                          </div>
                          <div className="guidedIntakeActions">
                            <button
                              className="guidedIntakeUpdate"
                              disabled={saving}
                              type="submit"
                            >
                              {saving ? "Đang cập nhật…" : "Cập nhật"}
                            </button>
                          </div>
                        </form>
                      ) : (
                        <form
                          onSubmit={(event) => {
                            event.preventDefault();
                            void onSubmitAnswer(draft.trim() || "Bỏ qua");
                          }}
                        >
                          <div className="guidedIntakeAnswer">
                            <input
                              aria-label={
                                guidedIntakeQuestions[step]
                              }
                              autoComplete="off"
                              onChange={(event) =>
                                onDraftChange(event.target.value)
                              }
                              placeholder={
                                guidedIntakePlaceholders[step]
                              }
                              ref={guidedInputRef}
                              type="text"
                              value={draft}
                            />
                            <button
                              aria-label="Cập nhật thông tin"
                              className="guidedIntakeUpdate"
                              disabled={
                                saving ||
                                (step === "destination" && !draft.trim())
                              }
                              type="submit"
                            >
                              {saving ? "Đang cập nhật…" : "Cập nhật"}
                            </button>
                          </div>
                        </form>
                      )}
                    </div>
                  </section>
                </div>
              ) : null}
    </>
  );
}
