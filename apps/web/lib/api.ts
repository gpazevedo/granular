import type { CourseDetailResponse, DiscoverResponse, Level } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

// Forbidden entitlement patterns — mirror of the backend guard. Frontend acts
// as a second line of defence (REQ-AQ-03 / REQ-AQ-12).
const ENTITLEMENT_PATTERNS: RegExp[] = [
  /\bexempt\b/i,
  /\byou (?:will|can|should) master\b/i,
  /\bcovers everything\b/i,
  /\ball you need\b/i,
  /\bfully prepares?\b/i,
  /\byou can skip\b/i,
];

export function containsEntitlementLanguage(text: string): boolean {
  return ENTITLEMENT_PATTERNS.some((p) => p.test(text));
}

export async function discover(query: string, level: Level): Promise<DiscoverResponse> {
  const res = await fetch(`${API_BASE}/api/v1/discover`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, level }),
  });

  if (res.status === 400 || res.status === 422) {
    throw new Error("Please enter a learning interest.");
  }
  if (!res.ok) {
    throw new Error(`Request failed (${res.status})`);
  }

  return (await res.json()) as DiscoverResponse;
}

export async function fetchCourseDetail(courseId: string): Promise<CourseDetailResponse> {
  const res = await fetch(`${API_BASE}/api/v1/course/${encodeURIComponent(courseId)}`);
  if (!res.ok) {
    throw new Error(`Request failed (${res.status})`);
  }
  return (await res.json()) as CourseDetailResponse;
}
