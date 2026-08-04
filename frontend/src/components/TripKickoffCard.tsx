"use client";

import { useState, type FormEvent } from "react";
import { PenguinMascot } from "@/components/PenguinMascot";

type TripKickoffCardProps = {
  initialDestination?: string;
  onContinue: (message: string) => void;
  onSkip: () => void;
};

const travelStyles = [
  { label: "Đi thong thả", value: "đi thong thả" },
  { label: "Khám phá địa phương", value: "trải nghiệm địa phương" },
  { label: "Ẩm thực", value: "ưu tiên ẩm thực" },
  { label: "Thiên nhiên", value: "gần thiên nhiên" },
  { label: "Văn hoá", value: "văn hoá và lịch sử" },
  { label: "Nghỉ dưỡng", value: "nghỉ dưỡng" }
];

function formatDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return value;
  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric"
  }).format(new Date(year, month - 1, day));
}

export function TripKickoffCard({
  initialDestination = "",
  onContinue,
  onSkip
}: TripKickoffCardProps) {
  const [destination, setDestination] = useState(initialDestination);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [budget, setBudget] = useState("");
  const [travelers, setTravelers] = useState("");
  const [styles, setStyles] = useState<string[]>([]);
  const [importantNote, setImportantNote] = useState("");

  function toggleStyle(value: string) {
    setStyles((current) =>
      current.includes(value)
        ? current.filter((style) => style !== value)
        : [...current, value]
    );
  }

  function buildMessage(): string {
    const details: string[] = [];
    if (destination.trim()) details.push(`Điểm đến: ${destination.trim()}`);
    if (startDate && endDate) {
      details.push(`Thời gian: ${formatDate(startDate)} đến ${formatDate(endDate)}`);
    } else if (startDate) {
      details.push(`Bắt đầu: ${formatDate(startDate)}`);
    } else if (endDate) {
      details.push(`Kết thúc trước: ${formatDate(endDate)}`);
    }
    if (budget.trim()) details.push(`Ngân sách dự kiến: ${budget.trim()}`);
    if (travelers) details.push(`Số người: ${travelers}`);
    if (styles.length) details.push(`Phong cách: ${styles.join(", ")}`);
    if (importantNote.trim()) details.push(`Điều cần lưu ý: ${importantNote.trim()}`);

    return details.length
      ? `Giúp mình lên kế hoạch chuyến đi.\n${details.map((detail) => `- ${detail}`).join("\n")}`
      : "";
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onContinue(buildMessage());
  }

  return (
    <form className="tripKickoffCard" onSubmit={handleSubmit}>
      <div className="tripKickoffIntro">
        <div className="tripKickoffMascot">
          <PenguinMascot priority size={112} variant="curious" />
        </div>
        <div>
          <span className="tripKickoffEyebrow">Trước khi bắt đầu</span>
          <h2 id="trip-kickoff-title">Mình tò mò một chút…</h2>
          <p>Chia sẻ vài ý để mình gợi ý sát hơn nhé. Mọi câu đều có thể bỏ qua.</p>
        </div>
      </div>

      <div className="tripKickoffFields">
        <label className="tripKickoffField tripKickoffFieldWide">
          <span>Bạn muốn đi đâu?</span>
          <input
            autoComplete="off"
            onChange={(event) => setDestination(event.target.value)}
            placeholder="Ví dụ: Hà Nội, Đà Lạt…"
            type="text"
            value={destination}
          />
        </label>

        <fieldset className="tripKickoffField tripKickoffFieldWide">
          <legend>Khi nào bạn muốn đi?</legend>
          <div className="tripKickoffDateRange">
            <label>
              <small>Bắt đầu</small>
              <input
                aria-label="Ngày bắt đầu"
                max={endDate || undefined}
                onChange={(event) => setStartDate(event.target.value)}
                type="date"
                value={startDate}
              />
            </label>
            <span aria-hidden="true">→</span>
            <label>
              <small>Kết thúc</small>
              <input
                aria-label="Ngày kết thúc"
                min={startDate || undefined}
                onChange={(event) => setEndDate(event.target.value)}
                type="date"
                value={endDate}
              />
            </label>
          </div>
        </fieldset>

        <label className="tripKickoffField">
          <span>Ngân sách khoảng bao nhiêu?</span>
          <input
            inputMode="text"
            onChange={(event) => setBudget(event.target.value)}
            placeholder="Ví dụ: 6 triệu"
            type="text"
            value={budget}
          />
        </label>

        <label className="tripKickoffField">
          <span>Có bao nhiêu người?</span>
          <select onChange={(event) => setTravelers(event.target.value)} value={travelers}>
            <option value="">Chưa chắc</option>
            <option value="1 người">1 người</option>
            <option value="2 người">2 người</option>
            <option value="3–5 người">3–5 người</option>
            <option value="trên 5 người">Trên 5 người</option>
          </select>
        </label>

        <fieldset className="tripKickoffField tripKickoffFieldWide">
          <legend>Bạn thích chuyến đi như thế nào?</legend>
          <div className="tripStyleChoices">
            {travelStyles.map((style) => {
              const selected = styles.includes(style.value);
              return (
                <button
                  aria-pressed={selected}
                  className={selected ? "selected" : ""}
                  key={style.value}
                  onClick={() => toggleStyle(style.value)}
                  type="button"
                >
                  {style.label}
                </button>
              );
            })}
          </div>
        </fieldset>

        <label className="tripKickoffField tripKickoffFieldWide">
          <span>Có điều gì mình cần đặc biệt lưu ý?</span>
          <input
            onChange={(event) => setImportantNote(event.target.value)}
            placeholder="Ví dụ: có trẻ nhỏ, hạn chế đi bộ, dị ứng thực phẩm…"
            type="text"
            value={importantNote}
          />
        </label>
      </div>

      <div className="tripKickoffActions">
        <button className="tripKickoffSkip" onClick={onSkip} type="button">
          Bỏ qua tất cả
        </button>
        <button className="tripKickoffContinue" type="submit">
          Tiếp tục
          <svg aria-hidden="true" viewBox="0 0 24 24">
            <path d="m9 5 7 7-7 7" />
          </svg>
        </button>
      </div>
    </form>
  );
}
