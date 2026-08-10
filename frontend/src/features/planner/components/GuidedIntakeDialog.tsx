"use client";

import { useRef } from "react";
import { PenguinMascot } from "@/components/PenguinMascot";

type GuidedIntakeStep = "destination" | "dates" | "budget" | "travelers" | "note";
type TravelerCounts = { adults: number; children: number; infants: number; pets: number };

const guidedIntakeQuestions: Record<GuidedIntakeStep, string> = {
  destination: "Bạn muốn đi đâu?",
  dates: "Khi nào bạn muốn đi?",
  budget: "Ngân sách của bạn?",
  travelers: "Bạn đi cùng ai?",
  note: "Có lưu ý gì không?",
};

const guidedIntakePlaceholders: Record<GuidedIntakeStep, string> = {
  destination: "Ví dụ: Kyoto, Đà Lạt, miền Tây…",
  dates: "Ví dụ: 12–15/09 hoặc cuối tuần sau…",
  budget: "Ví dụ: khoảng 8 triệu cho cả nhóm…",
  travelers: "Ví dụ: 2 người lớn và 1 bé…",
  note: "Thêm một lưu ý nếu có…",
};

const travelerOptions: ReadonlyArray<{
  key: keyof TravelerCounts;
  label: string;
  description: string;
  minimum: number;
  maximum: number;
}> = [
  { key: "adults", label: "Người lớn", description: "Từ 13 tuổi", minimum: 1, maximum: 20 },
  { key: "children", label: "Trẻ em", description: "Từ 2–12 tuổi", minimum: 0, maximum: 20 },
  { key: "infants", label: "Em bé", description: "Dưới 2 tuổi", minimum: 0, maximum: 10 },
  { key: "pets", label: "Thú cưng", description: "Mang theo trong chuyến đi", minimum: 0, maximum: 5 },
];

type GuidedIntakeDialogProps = {
  open: boolean;
  step: GuidedIntakeStep;
  draft: string;
  startDate: string;
  endDate: string;
  counts: TravelerCounts;
  saving: boolean;
  onClose: () => void;
  onDraftChange: (value: string) => void;
  onStartDateChange: (value: string) => void;
  onEndDateChange: (value: string) => void;
  onSubmitDates: () => void;
  onSubmitAnswer: (answer: string) => void;
  onSubmitTravelers: () => void;
  onTravelerCountChange: (key: keyof TravelerCounts, delta: number) => void;
};

export function GuidedIntakeDialog({
  open,
  step,
  draft,
  startDate,
  endDate,
  counts,
  saving,
  onClose,
  onDraftChange,
  onStartDateChange,
  onEndDateChange,
  onSubmitDates,
  onSubmitAnswer,
  onSubmitTravelers,
  onTravelerCountChange,
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
                    } ${step === "travelers" ? "isTravelers" : ""}`}
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
                      ) : step === "travelers" ? (
                        <form
                          className="guidedTravelerPicker"
                          onSubmit={(event) => {
                            event.preventDefault();
                            void onSubmitTravelers();
                          }}
                        >
                          <div className="guidedTravelerRows">
                            {travelerOptions.map((option) => {
                              const count = counts[option.key];
                              return (
                                <div
                                  className="guidedTravelerRow"
                                  key={option.key}
                                >
                                  <span>
                                    <strong>{option.label}</strong>
                                    <small>{option.description}</small>
                                  </span>
                                  <div className="guidedCounter">
                                    <button
                                      aria-label={`Giảm ${option.label.toLocaleLowerCase(
                                        "vi-VN"
                                      )}`}
                                      disabled={count <= option.minimum}
                                      onClick={() =>
                                        onTravelerCountChange(option.key, -1)
                                      }
                                      type="button"
                                    >
                                      <svg
                                        aria-hidden="true"
                                        viewBox="0 0 24 24"
                                      >
                                        <path d="M5 12h14" />
                                      </svg>
                                    </button>
                                    <output
                                      aria-live="polite"
                                      aria-label={`${option.label}: ${count}`}
                                    >
                                      {count}
                                    </output>
                                    <button
                                      aria-label={`Tăng ${option.label.toLocaleLowerCase(
                                        "vi-VN"
                                      )}`}
                                      disabled={count >= option.maximum}
                                      onClick={() =>
                                        onTravelerCountChange(option.key, 1)
                                      }
                                      type="button"
                                    >
                                      <svg
                                        aria-hidden="true"
                                        viewBox="0 0 24 24"
                                      >
                                        <path d="M12 5v14M5 12h14" />
                                      </svg>
                                    </button>
                                  </div>
                                </div>
                              );
                            })}
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
