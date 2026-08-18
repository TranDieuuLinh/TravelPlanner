import type {
  TripChat,
  TripChatMessage,
  TripChatSummary,
  TripChatSource,
  TravelPlan,
} from "@/features/planner/api/plans";
import type { ItineraryPlannerOutput } from "@/features/planner/lib/planner-output";
import type { AnswerBlock } from "@/features/planner/lib/answer-blocks";

export type CurrentTripChatSummary = {
  id: string;
  title: string;
  revision: number;
  hasItinerary: boolean;
  createdAt: string;
  updatedAt: string;
};

export type CurrentTripChat = CurrentTripChatSummary & {
  threadId: string;
  currentItinerary?: Record<string, any> | null;
  currentPlannerOutput?: ItineraryPlannerOutput | null;
  messages?: Array<{
    id: string;
    role: "assistant" | "user";
    content: string;
    sources?: TripChatSource[];
    contentBlocks?: AnswerBlock[];
    createdAt: string;
  }>;
};

function normalizeChatSources(value: unknown): TripChatSource[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const source = item as Record<string, unknown>;
    const url = String(source.url ?? source.sourceUrl ?? "").trim();
    if (!/^https?:\/\//i.test(url)) return [];
    return [{
      sourceId: String(source.sourceId ?? source.source_id ?? url),
      title: String(source.title ?? "Nguồn tham khảo"),
      url,
      updatedAt: source.updatedAt as string | null | undefined,
      dateKind: source.dateKind as string | null | undefined,
      reviewStatus: source.reviewStatus as string | null | undefined,
      publishedAt: source.publishedAt as string | null | undefined,
    }];
  });
}

function formatMinute(value: unknown): string {
  const minute = Number(value);
  if (!Number.isFinite(minute)) return "--:--";
  return `${String(Math.floor(minute / 60)).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}`;
}

function currentItineraryToPlan(
  itinerary: Record<string, any> | null | undefined,
): TravelPlan | null {
  if (!itinerary) return null;
  const intent = itinerary.intent ?? {};
  return {
    id: itinerary.itineraryId ?? itinerary.itinerary_id ?? "agent-itinerary",
    title: `${intent.destination ?? "Chuyến đi"} · ${itinerary.days?.length ?? 0} ngày`,
    destination: intent.destination ?? "",
    travelerCount: intent.people ?? null,
    kind: "main",
    warnings: itinerary.warnings ?? [],
    days: (itinerary.days ?? []).map((day: any) => ({
      day: day.day,
      transportLegs: [],
      items: (day.items ?? []).map((item: any) => {
        const place = item.place ?? {};
        const start = item.startMinute ?? item.start_minute;
        const end = item.endMinute ?? item.end_minute;
        return {
          itemId: item.itemId ?? item.item_id,
          placeId: place.placeId ?? place.place_id,
          name: place.name ?? "Địa điểm",
          address: null,
          timeWindow: `${formatMinute(start)} – ${formatMinute(end)}`,
          placeType: "activity",
          source: place.source ?? "agent",
          sourceRefs: [],
          latitude: place.coordinates?.latitude ?? null,
          longitude: place.coordinates?.longitude ?? null,
          tags: place.tags ?? [],
        };
      }),
    })),
  };
}

export function mapCurrentTripChatSummary(
  chat: CurrentTripChatSummary,
): TripChatSummary {
  return {
    id: chat.id,
    title: chat.title,
    destination: null,
    revision: chat.revision,
    hasPlan: chat.hasItinerary,
    createdAt: chat.createdAt,
    updatedAt: chat.updatedAt,
  };
}

export function mapCurrentTripChat(
  chat: CurrentTripChat,
  mapPlannerOutput: (
    output: ItineraryPlannerOutput | null | undefined,
    options: { id?: string },
  ) => TravelPlan | null,
): TripChat {
  const plan = mapPlannerOutput(chat.currentPlannerOutput, {
    id: `agent-${chat.id}`,
  }) ?? currentItineraryToPlan(chat.currentItinerary);
  return {
    ...mapCurrentTripChatSummary(chat),
    destination: plan?.destination ?? null,
    hasPlan: Boolean(plan),
    tripIntentVersion: 0,
    tripIntentPlanStatus: "synced",
    currentPlan: plan,
    currentTripIntent: null,
    candidateReviews: [],
    messages: (chat.messages ?? []).map<TripChatMessage>((message) => ({
      id: message.id,
      role: message.role,
      content: message.content,
      sources: normalizeChatSources(message.sources),
      attachmentNames: [],
      planRevision: plan ? chat.revision : null,
      createdAt: message.createdAt,
      messageKind: message.role,
      contentBlocks: message.contentBlocks ?? [],
    })),
    turns: [],
  };
}
