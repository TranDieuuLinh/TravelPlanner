"use client";

import { useState } from "react";

export function isPlanData(data: any): boolean {
  if (typeof data !== "object" || data === null) return false;
  // It could have `days` or `finalDays` or `backupPlan.days`
  if (Array.isArray(data.days) && data.days.length > 0) return true;
  if (Array.isArray(data.finalDays) && data.finalDays.length > 0) return true;
  if (data.backupPlan && Array.isArray(data.backupPlan.days) && data.backupPlan.days.length > 0) return true;
  return false;
}

function CarIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.4 2.9A3.7 3.7 0 0 0 2 12v4c0 .6.4 1 1 1h2" />
      <circle cx="7" cy="17" r="2" />
      <path d="M9 17h6" />
      <circle cx="17" cy="17" r="2" />
    </svg>
  );
}

function ClockIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  );
}

export function PlanViewer({ data }: { data: any }) {
  const isBackup = !!data.backupPlan;
  const daysArray = data.finalDays || data.days || (isBackup ? data.backupPlan.days : []);
  const title = data.title || (isBackup ? data.backupPlan.title : "Kế hoạch chi tiết");
  const destination = data.destination || (isBackup ? data.backupPlan.destination : "Hà Nội");

  const [activeDay, setActiveDay] = useState(1);
  const activeDayData = daysArray.find((d: any) => d.day === activeDay) || daysArray[0];

  if (!activeDayData) return null;

  return (
    <div className="planViewer">
      <header className="planViewerHeader">
        <div className="planIcon">🐧</div>
        <div>
          <h2>{title}</h2>
          <p>{destination} · {daysArray.length} ngày</p>
        </div>
      </header>

      <div className="planTabs">
        {daysArray.map((d: any) => (
          <button
            key={d.day}
            className={activeDay === d.day ? "active" : ""}
            onClick={() => setActiveDay(d.day)}
          >
            Ngày {d.day}
          </button>
        ))}
      </div>

      <div className="planDayContent">
        <h3 className="dayTheme">{activeDayData.theme || `Lịch trình Ngày ${activeDay}`}</h3>
        
        <div className="timeline">
          {activeDayData.items?.map((item: any, idx: number) => {
            const isTransport = item.placeType === "transport" || item.role === "transit";
            const isBreak = item.name?.toLowerCase().includes("break") || item.role === "break";
            const timeStr = item.timeWindow || "00:00-00:00";
            
            return (
              <div key={item.itemId || idx} className={`timelineItem ${isTransport ? "isTransport" : ""} ${isBreak ? "isBreak" : ""}`}>
                <div className="timeCol">{timeStr}</div>
                <div className="nodeCol">
                  <div className="line"></div>
                  <div className="nodeIcon">
                    {isTransport ? <CarIcon /> : <div className="innerDot" />}
                  </div>
                </div>
                <div className="contentCol">
                  {isTransport ? (
                    <div className="transportCard">
                      <div className="transportCardHead">
                        <span className="badge">ĐỀ XUẤT</span>
                        <div className="duration">
                          <ClockIcon />
                          <span>{item.durationMinutes} phút</span>
                        </div>
                      </div>
                      <div className="transportCardTitle">
                        <CarIcon />
                        <span>{item.name || "Di chuyển"}</span>
                      </div>
                      <div className="transportRoute">
                        A &rarr; B (Theo dữ liệu nội bộ)
                      </div>
                    </div>
                  ) : (
                    <div className="activityCard">
                      <h4>{item.name || "Điểm đến"}</h4>
                      <p>
                        {item.placeId 
                          ? `Địa điểm hệ thống (${item.placeType || 'unknown'}) | ${item.role || 'activity'}`
                          : item.role === "meal" 
                            ? "Meal/rest block inserted by Finder." 
                            : isBreak 
                              ? "No Place is required for this break block." 
                              : `Cần chuẩn bị (${item.durationMinutes} phút)`}
                      </p>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
