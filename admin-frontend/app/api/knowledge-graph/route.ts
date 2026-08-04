import { promises as fs } from "node:fs";
import path from "node:path";
import { NextRequest, NextResponse } from "next/server";

const ALLOWED_FILES = [
  "aliases.csv",
  "entities.csv",
  "ontology.yaml",
  "properties.csv",
  "relationships.csv",
  "schema.yaml"
] as const;

type AllowedFile = (typeof ALLOWED_FILES)[number];

const DATASET_DIRECTORY = path.resolve(
  process.cwd(),
  "..",
  "knowledge-graph-real-v2"
);

const BACKEND_API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

function isAllowedFile(value: unknown): value is AllowedFile {
  return typeof value === "string" && ALLOWED_FILES.includes(value as AllowedFile);
}

async function hasAdminSession(request: NextRequest): Promise<boolean> {
  try {
    const response = await fetch(
      `${BACKEND_API_BASE}/admin/planning-runs?limit=1`,
      {
        cache: "no-store",
        headers: { cookie: request.headers.get("cookie") ?? "" }
      }
    );
    return response.ok;
  } catch {
    return false;
  }
}

function hasValidCsrf(request: NextRequest): boolean {
  const cookieValue = request.cookies.get("vsf_csrf")?.value;
  const headerValue = request.headers.get("x-csrf-token");
  if (!cookieValue || !headerValue) return false;
  try {
    return decodeURIComponent(cookieValue) === decodeURIComponent(headerValue);
  } catch {
    return false;
  }
}

export async function GET(request: NextRequest) {
  if (!(await hasAdminSession(request))) {
    return NextResponse.json({ message: "Admin session required." }, { status: 401 });
  }

  const entries = await Promise.all(
    ALLOWED_FILES.map(async (fileName) => {
      const content = await fs.readFile(path.join(DATASET_DIRECTORY, fileName), "utf8");
      return [fileName, content] as const;
    })
  );

  return NextResponse.json({ files: Object.fromEntries(entries) });
}

export async function PUT(request: NextRequest) {
  if (!(await hasAdminSession(request))) {
    return NextResponse.json({ message: "Admin session required." }, { status: 401 });
  }
  if (!hasValidCsrf(request)) {
    return NextResponse.json({ message: "CSRF validation failed." }, { status: 403 });
  }

  const body = (await request.json()) as {
    fileName?: unknown;
    content?: unknown;
    files?: Record<string, unknown>;
  };
  const updates = body.files
    ? Object.entries(body.files)
    : [[body.fileName, body.content]];
  if (
    updates.length === 0 ||
    updates.some(([fileName, content]) => !isAllowedFile(fileName) || typeof content !== "string")
  ) {
    return NextResponse.json({ message: "Invalid knowledge graph file payload." }, { status: 422 });
  }
  if (updates.some(([, content]) => Buffer.byteLength(content as string, "utf8") > 1_000_000)) {
    return NextResponse.json({ message: "Knowledge graph file exceeds 1 MB." }, { status: 413 });
  }

  const targets = updates.map(([fileName, content]) => {
    const target = path.join(DATASET_DIRECTORY, fileName as AllowedFile);
    return { fileName: fileName as AllowedFile, content: content as string, target, temporary: `${target}.tmp` };
  });
  await Promise.all(targets.map((item) => fs.writeFile(item.temporary, item.content, "utf8")));
  await Promise.all(targets.map((item) => fs.rename(item.temporary, item.target)));

  return NextResponse.json({ files: targets.map((item) => item.fileName), saved: true });
}
