import type { PlanNoteSource } from "../api/plans";

const EMPTY_NOTE_VALUES = new Set([
  "nan",
  "none",
  "null",
  "undefined",
  "n/a"
]);

const VIETNAMESE_NOTE_TRANSLATIONS: Record<string, string> = {
  "hanoi has more than a thousand years of history. in 1010, emperor ly thai to chose it as the imperial capital and named it thang long, “ascending dragon.” dynasties, french colonial rule, wars and modernization shaped the layered city seen today":
    "Hà Nội có hơn một nghìn năm lịch sử. Năm 1010, vua Lý Thái Tổ chọn nơi đây làm kinh đô và đặt tên là Thăng Long, nghĩa là “Rồng bay lên”. Các triều đại, thời kỳ Pháp thuộc, chiến tranh và quá trình hiện đại hóa đã tạo nên một thành phố nhiều lớp lang như ngày nay.",
  "traffic in hanoi is busy and unpredictable. vehicles may approach from unexpected directions, so look carefully—even on one-way streets—and cross only when it is safe":
    "Giao thông ở Hà Nội đông đúc và khó đoán. Các phương tiện có thể xuất hiện từ những hướng bất ngờ, vì vậy hãy quan sát kỹ — kể cả trên đường một chiều — và chỉ sang đường khi an toàn.",
  "use grab or xanh sm. confirm that the licence plate, vehicle and driver match the information in the app before entering":
    "Hãy sử dụng Grab hoặc Xanh SM. Trước khi lên xe, hãy xác nhận biển số, phương tiện và tài xế khớp với thông tin trong ứng dụng.",
  "do not drink tap water. choose sealed bottled or adequately treated water, and be cautious about ice":
    "Không uống nước máy. Hãy chọn nước đóng chai còn nguyên niêm phong hoặc nước đã được xử lý đạt yêu cầu, đồng thời thận trọng với đá.",
  "keep bags zipped and in front of you in the old quarter, markets and public transport. stay alert to motorcycles approaching from behind":
    "Hãy kéo khóa túi và giữ túi ở phía trước khi ở Phố Cổ, chợ và trên phương tiện công cộng. Chú ý các xe máy đi tới từ phía sau.",
  "agree on the complete price and service before taking a cyclo or using an informal service":
    "Hãy thống nhất toàn bộ mức giá và dịch vụ trước khi đi xích lô hoặc sử dụng một dịch vụ không chính thức.",
  "cover your shoulders and knees when visiting temples and cultural sites, and follow instructions displayed at the entrance":
    "Hãy che vai và đầu gối khi tham quan đền, chùa và các địa điểm văn hóa, đồng thời làm theo hướng dẫn được niêm yết tại lối vào.",
  "train street is an active railway. never cross barriers, stand on the tracks or ignore current local restrictions":
    "Phố đường tàu là tuyến đường sắt vẫn đang hoạt động. Tuyệt đối không vượt rào chắn, đứng trên đường ray hoặc phớt lờ các quy định hiện hành của địa phương.",
  "withdraw money": "Rút tiền",
  "eat dessert and wait for sightseeing bus":
    "Ăn món tráng miệng và chờ xe buýt tham quan",
  "explore cute cafés, shops, and a night market":
    "Khám phá các quán cà phê xinh xắn, cửa hàng và chợ đêm",
  "nature viewpoint hike":
    "Đi bộ đường dài đến điểm ngắm cảnh thiên nhiên",
  "purchase the audio guide as the show is in vietnamese":
    "Mua hướng dẫn âm thanh vì chương trình biểu diễn bằng tiếng Việt",
  "relaxing head spa treatment that leaves hair shining":
    "Thư giãn với liệu trình spa đầu giúp tóc bóng mượt",
  "no place is required for this break block":
    "Khoảng nghỉ này không cần địa điểm cụ thể"
};

function normalizedLookupKey(value: string): string {
  return value
    .trim()
    .toLocaleLowerCase("en")
    .replace(/[.!?]+$/g, "")
    .trim();
}

/** Returns user-facing Vietnamese text, or null when a note has no real value. */
export function formatPlanNote(value: unknown): string | null {
  if (typeof value !== "string") return null;

  const note = value.trim();
  if (!note) return null;

  const lookupKey = normalizedLookupKey(note);
  if (EMPTY_NOTE_VALUES.has(lookupKey)) return null;

  return VIETNAMESE_NOTE_TRANSLATIONS[lookupKey] ?? note;
}

/**
 * Formats generated source context for the Vietnamese UI.
 *
 * Known legacy English values are translated above. Unknown non-Vietnamese
 * model output remains visible until a translation is available.
 */
export function formatSourceNoteForDisplay(value: unknown): string | null {
  return formatPlanNote(value);
}

const NOTE_SOURCE_LABELS: Record<string, string> = {
  url: "Gợi ý từ nguồn tham khảo",
  image: "Chi tiết từ ảnh tham khảo",
  creator: "Từ creator"
};

function inferredNoteSources(
  item: { sourceRefs?: string[] }
): PlanNoteSource[] {
  const sources: PlanNoteSource[] = [];
  for (const ref of item.sourceRefs ?? []) {
    if (ref.startsWith("http://") || ref.startsWith("https://")) {
      sources.push({ type: "url", ref });
    } else if (ref === "ocr") {
      sources.push({ type: "image", ref, evidenceTypes: ["ocr"] });
    }
  }
  return sources;
}

export function formatNoteSources(
  sources: PlanNoteSource[] | null | undefined
): string | null {
  const labels = (sources ?? [])
    .filter(
      (source) =>
        source.type !== "google_maps" && source.type !== "place_provider"
    )
    .map((source) => NOTE_SOURCE_LABELS[source.type] ?? "Nguồn tham khảo")
    .filter((label, index, values) => values.indexOf(label) === index);
  return labels.length ? labels.join("\n") : null;
}

export type PlanItemNotePresentation = {
  sourceNotes: PresentedSourceNote[];
  sourceLabel: string | null;
  sourceText: string | null;
  personalText: string | null;
};

export type PresentedSourceNote = {
  type: string;
  label: string;
  text: string;
};

type NoteBearingItem = {
  name?: string;
  notes?: string | null;
  noteSources?: PlanNoteSource[];
  personalNotes?: string | null;
  sourceActivity?: string | null;
  sourceRefs?: string[];
};

/** One shared note view-model for itinerary cards and map marker popups. */
export function planItemNotePresentation(
  item: NoteBearingItem
): PlanItemNotePresentation {
  const sources = item.noteSources?.length
    ? item.noteSources
    : inferredNoteSources(item);

  const sourceNotes = sources
    // Provider facts already have dedicated UI (address, rating, hours and
    // links). Repeating them as prose makes the note area look informative
    // without adding any planning value.
    .filter(
      (source) =>
        source.type !== "google_maps" && source.type !== "place_provider"
    )
    .map((source): PresentedSourceNote | null => {
      const label = NOTE_SOURCE_LABELS[source.type] ?? "Nguồn tham khảo";
      const fallback = fallbackSourceNote(item, source.type);
      const text = vietnameseSourceText(source.text, fallback);
      if (
        source.type === "url" &&
        text &&
        (!looksVietnamese(
          text.replaceAll(item.name?.trim() || "địa điểm này", "")
        ) ||
          !isUsefulCreatorStory(text, item.name?.trim() || "địa điểm này"))
      ) {
        return null;
      }
      return text ? { type: source.type, label, text } : null;
    })
    .filter((note): note is PresentedSourceNote => Boolean(note))
    .filter(
      (note, index, notes) =>
        notes.findIndex(
          (candidate) =>
            candidate.type === note.type && candidate.text === note.text
        ) === index
    );

  const firstSourceNote = sourceNotes[0] ?? null;
  return {
    sourceNotes,
    // Kept for callers reading older single-note presentation fields.
    sourceLabel: firstSourceNote?.label ?? null,
    sourceText: firstSourceNote?.text ?? null,
    personalText: formatPlanNote(item.personalNotes)
  };
}

function fallbackSourceNote(
  item: NoteBearingItem,
  sourceType: string
): string | null {
  const name = item.name?.trim() || "địa điểm này";
  if (sourceType === "url") {
    const activity = formatPlanNote(item.sourceActivity);
    return activity &&
      looksVietnamese(activity.replaceAll(name, "")) &&
      isUsefulCreatorStory(activity, name)
      ? activity
      : null;
  }
  if (sourceType === "image") {
    return `Ảnh tham khảo có thông tin về ${name}.`;
  }
  return formatPlanNote(item.notes);
}

function isUsefulCreatorStory(value: string, placeName: string): boolean {
  const normalize = (text: string) =>
    text
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[đĐ]/g, "d")
      .toLocaleLowerCase("vi")
      .replace(/[^\p{L}\p{N}]+/gu, " ")
      .trim();
  const normalized = normalize(value);
  const name = normalize(placeName);
  if (
    [
      "video tham khao co nhac den",
      "video co nhac den",
      "creator co nhac den",
      "tham quan dia diem",
      "kham pha dia diem"
    ].some((pattern) => normalized.includes(pattern))
  ) {
    return false;
  }
  const withoutName = name ? normalized.replace(name, "").trim() : normalized;
  return !["", "tham quan", "kham pha", "ghe", "den"].includes(withoutName);
}

function vietnameseSourceText(
  value: string | null | undefined,
  fallback: string | null
): string | null {
  const text = formatPlanNote(value);
  return text && looksVietnamese(text) ? text : fallback;
}

function looksVietnamese(value: string): boolean {
  if (/[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]/iu.test(value)) {
    return true;
  }
  const normalized = ` ${value.toLocaleLowerCase("vi")} `;
  return [
    " tham quan ",
    " khám phá ",
    " thưởng thức ",
    " ghé ",
    " ăn ",
    " uống ",
    " ngắm ",
    " thử ",
    " rút ",
    " địa điểm ",
    " dữ liệu ",
    " video ",
    " tại "
  ].some((word) => normalized.includes(word));
}
