"use client";

import { PenguinMascot } from "@/components/PenguinMascot";
import {
  SidebarIcon,
  NewChatIcon,
  TrashIcon,
} from "@/features/planner/components/PlannerIcons";
import type { TripChatSummary } from "@/features/planner/api/plans";

type TripProjectSidebarProps = {
  open: boolean;
  activeChatId: string | null;
  tripChats: TripChatSummary[];
  orderedTripChats: TripChatSummary[];
  activeJobChatIds: Set<string>;
  loading: boolean;
  deletingChatId: string | null;
  deletingAllChats: boolean;
  onClose: () => void;
  onNewChat: () => void;
  onDeleteAll: () => void;
  onOpenChat: (chatId: string) => void;
  onDeleteChat: (chat: TripChatSummary) => void;
};

export function TripProjectSidebar({
  open,
  activeChatId,
  tripChats,
  orderedTripChats,
  activeJobChatIds,
  loading,
  deletingChatId,
  deletingAllChats,
  onClose,
  onNewChat,
  onDeleteAll,
  onOpenChat,
  onDeleteChat,
}: TripProjectSidebarProps) {
  return (
    <>
{open ? (
            <>
              <button
                aria-label="Đóng lịch sử chuyến đi"
                className="tripSidebarBackdrop"
                onClick={() => onClose()}
                type="button"
              />
              <aside
                aria-label="Dự án chuyến đi"
                className="tripProjectSidebar"
              >
                <div className="tripProjectSidebarHeader">
                  <div className="tripProjectBrand">
                    <PenguinMascot size={38} variant="logo" />
                    <span>
                      <strong>TravelPlanner</strong>
                      <small>Trip projects</small>
                    </span>
                  </div>
                  <button
                    aria-label="Đóng lịch sử chuyến đi"
                    aria-expanded="true"
                    className="tripSidebarToggle"
                    onClick={() => onClose()}
                    title="Đóng sidebar"
                    type="button"
                  >
                    <SidebarIcon collapsed={false} />
                  </button>
                </div>

                <button
                  className={`sidebarNewChat ${!activeChatId ? "active" : ""}`}
                  onClick={onNewChat}
                  title="Chat mới"
                  type="button"
                >
                  <NewChatIcon />
                  <span>Chat mới</span>
                </button>

                <div className="tripProjectList">
                  <div className="tripProjectSectionTitle">
                    <strong>Dự án</strong>
                    <span>
                      <small>{tripChats.length}</small>
                      {tripChats.length ? (
                        <button
                          className="tripProjectDeleteAll"
                          disabled={loading || deletingChatId !== null || deletingAllChats}
                          onClick={() => void onDeleteAll()}
                          title="Xóa tất cả lịch sử chat"
                          type="button"
                        >
                          {deletingAllChats ? "Đang xóa…" : "Xóa tất cả"}
                        </button>
                      ) : null}
                    </span>
                  </div>
                  {tripChats.length ? (
                    <nav aria-label="Lịch sử dự án chuyến đi">
                      {orderedTripChats.map((chat) => (
                        <div
                          className={`tripProjectItem ${
                            chat.id === activeChatId ? "active" : ""
                          }`}
                          key={chat.id}
                        >
                          <button
                            aria-current={
                              chat.id === activeChatId ? "page" : undefined
                            }
                            className="tripProjectOpen"
                            disabled={deletingChatId === chat.id}
                            onClick={() => {
                              onClose();
                              void onOpenChat(chat.id);
                            }}
                            title={chat.title}
                            type="button"
                          >
                            <span>
                              <strong>{chat.title}</strong>
                              <small>
                                {chat.destination || "Chưa chọn điểm đến"}
                                {chat.revision ? ` · Bản ${chat.revision}` : ""}
                                {activeJobChatIds.has(chat.id)
                                  ? " · Đang xử lý"
                                  : ""}
                              </small>
                            </span>
                          </button>
                          <button
                            aria-label={`Xóa lịch sử chat ${chat.title}`}
                            className="tripProjectDelete"
                            disabled={loading || deletingChatId !== null || deletingAllChats}
                            onClick={() => void onDeleteChat(chat)}
                            title="Xóa lịch sử chat"
                            type="button"
                          >
                            <TrashIcon />
                          </button>
                        </div>
                      ))}
                    </nav>
                  ) : (
                    <p className="tripProjectEmpty">
                      Chưa có dự án. Bắt đầu bằng một yêu cầu chuyến đi mới.
                    </p>
                  )}
                </div>
              </aside>
            </>
          ) : null}
    </>
  );
}
