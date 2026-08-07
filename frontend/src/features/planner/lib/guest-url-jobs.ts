"use client";

import {
  createPlanFromExplorer,
  enrichPlanRoutes,
  exploreFullIntake,
  type ExploreResponse,
  type ExplorerTimingReport,
  type PlanTimingReport,
  type TravelPlan,
  type UrlImportJob
} from "@/features/planner/api/plans";

export const GUEST_URL_JOBS_EVENT = "travelplanner:guest-url-jobs-update";
export const GUEST_URL_JOB_RESULT_EVENT = "travelplanner:guest-url-job-result";

export type GuestUrlJobPhase = "queued" | "exploring" | "planning" | "complete";

export type GuestUrlJobResult = {
  explore: ExploreResponse;
  plan: TravelPlan;
  plannerTiming: PlanTimingReport | null;
};

export type GuestUrlImportJob = UrlImportJob & {
  storage: "guest-memory";
  phase: GuestUrlJobPhase;
  requestContent: string;
  contextUrls: string[];
  contextImages: File[];
  result: GuestUrlJobResult | null;
};

let jobs: GuestUrlImportJob[] = [];
let processing = false;
const controllers = new Map<string, AbortController>();

function snapshot(): GuestUrlImportJob[] {
  const queued = jobs.filter((job) => job.status === "queued");
  return jobs.map((job) => ({
    ...job,
    queuePosition: job.status === "queued"
      ? queued.findIndex((item) => item.id === job.id) + 1
      : null
  }));
}

function publish(): void {
  jobs = snapshot();
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(GUEST_URL_JOBS_EVENT, {
      detail: jobs
    }));
  }
}

function replace(jobId: string, update: Partial<GuestUrlImportJob>): GuestUrlImportJob | null {
  const index = jobs.findIndex((job) => job.id === jobId);
  if (index < 0) return null;
  jobs[index] = { ...jobs[index], ...update };
  publish();
  return jobs.find((job) => job.id === jobId) ?? null;
}

async function processQueue(): Promise<void> {
  if (processing) return;
  processing = true;
  try {
    while (true) {
      const next = jobs.find((job) => job.status === "queued");
      if (!next) break;
      const controller = new AbortController();
      controllers.set(next.id, controller);
      replace(next.id, {
        status: "running",
        phase: "exploring",
        startedAt: new Date().toISOString(),
        finishedAt: null,
        attemptCount: next.attemptCount + 1,
        errorCode: null,
        errorMessage: null
      });
      try {
        const explore = await exploreFullIntake({
          rawRequest: next.requestContent,
          urls: next.contextUrls,
          images: next.contextImages,
          forceRefresh: next.forceRefresh
        }, controller.signal);
        if (controller.signal.aborted || !jobs.some((job) => job.id === next.id)) continue;
        replace(next.id, {
          phase: "planning",
          explorerTiming: explore.timingReport ?? null
        });
        const generation = await createPlanFromExplorer({
          context: explore.explorer,
          intakeId: explore.intakeId,
          userId: explore.userId,
          allowFinderGapFill: explore.allowFinderGapFill,
          allowReplaceSourcePlaces: explore.allowReplaceSourcePlaces,
          signal: controller.signal
        });
        if (controller.signal.aborted || !jobs.some((job) => job.id === next.id)) continue;
        const result: GuestUrlJobResult = {
          explore,
          plan: generation.plan,
          plannerTiming: generation.timingReport ?? null
        };
        const completed = replace(next.id, {
          status: "succeeded",
          phase: "complete",
          plannerTiming: generation.timingReport ?? null,
          result,
          finishedAt: new Date().toISOString()
        });
        if (completed && typeof window !== "undefined") {
          window.dispatchEvent(new CustomEvent(GUEST_URL_JOB_RESULT_EVENT, {
            detail: completed
          }));
        }
        if (generation.plan.routeEnrichmentStatus === "pending") {
          void enrichPlanRoutes(generation.plan.id)
            .then((enrichedPlan) => {
              const enriched = replace(next.id, {
                result: { ...result, plan: enrichedPlan }
              });
              if (enriched && typeof window !== "undefined") {
                window.dispatchEvent(new CustomEvent(GUEST_URL_JOB_RESULT_EVENT, {
                  detail: enriched
                }));
              }
            })
            .catch(() => {
              // Keep the already delivered coarse plan available for retry.
            });
        }
      } catch (caught) {
        if (controller.signal.aborted || !jobs.some((job) => job.id === next.id)) continue;
        replace(next.id, {
          status: "failed",
          phase: "complete",
          errorCode: caught instanceof Error && "code" in caught
            ? String((caught as Error & { code?: string }).code || "GUEST_URL_JOB_FAILED")
            : "GUEST_URL_JOB_FAILED",
          errorMessage: caught instanceof Error
            ? caught.message
            : "Không thể xử lý nguồn này.",
          finishedAt: new Date().toISOString()
        });
      } finally {
        controllers.delete(next.id);
      }
    }
  } finally {
    processing = false;
  }
}

export function listGuestUrlJobs(): GuestUrlImportJob[] {
  return snapshot();
}

export function enqueueGuestUrlJobs(input: {
  content: string;
  urls: string[];
}): GuestUrlImportJob[] {
  const createdAt = new Date().toISOString();
  const created = input.urls.map((url, index): GuestUrlImportJob => ({
    id: crypto.randomUUID(),
    chatId: "guest-memory",
    sourceType: "url",
    sourceLabel: url,
    url,
    forceRefresh: false,
    status: "queued",
    queuePosition: null,
    attemptCount: 0,
    resultRevision: null,
    errorCode: null,
    errorMessage: null,
    createdAt,
    startedAt: null,
    finishedAt: null,
    storage: "guest-memory",
    phase: "queued",
    requestContent: input.content,
    contextUrls: input.urls.slice(0, index + 1),
    contextImages: [],
    explorerTiming: null,
    plannerTiming: null,
    result: null
  }));
  jobs = [...jobs, ...created];
  publish();
  void processQueue();
  return created;
}

export function enqueueGuestPromptJob(input: {
  content: string;
}): GuestUrlImportJob {
  const createdAt = new Date().toISOString();
  const job: GuestUrlImportJob = {
    id: crypto.randomUUID(),
    chatId: "guest-memory",
    sourceType: "url",
    sourceLabel: "Yêu cầu chuyến đi",
    url: "",
    forceRefresh: false,
    status: "queued",
    queuePosition: null,
    attemptCount: 0,
    resultRevision: null,
    errorCode: null,
    errorMessage: null,
    createdAt,
    startedAt: null,
    finishedAt: null,
    storage: "guest-memory",
    phase: "queued",
    requestContent: input.content,
    contextUrls: [],
    contextImages: [],
    explorerTiming: null,
    plannerTiming: null,
    result: null
  };
  jobs = [...jobs, job];
  publish();
  void processQueue();
  return job;
}

export function retryGuestUrlJob(jobId: string): void {
  replace(jobId, {
    forceRefresh: true,
    status: "queued",
    phase: "queued",
    startedAt: null,
    finishedAt: null,
    errorCode: null,
    errorMessage: null,
    explorerTiming: null,
    plannerTiming: null,
    result: null
  });
  void processQueue();
}

export function reprocessGuestUrlJob(jobId: string): void {
  replace(jobId, {
    forceRefresh: true,
    status: "queued",
    phase: "queued",
    startedAt: null,
    finishedAt: null,
    errorCode: null,
    errorMessage: null,
    explorerTiming: null,
    plannerTiming: null,
    result: null
  });
  void processQueue();
}

export function deleteGuestUrlJob(jobId: string): void {
  controllers.get(jobId)?.abort();
  controllers.delete(jobId);
  jobs = jobs.filter((job) => job.id !== jobId);
  publish();
  void processQueue();
}
