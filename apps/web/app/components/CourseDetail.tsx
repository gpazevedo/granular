"use client";

import { useEffect, useState } from "react";
import { fetchCourseDetail, containsEntitlementLanguage } from "@/lib/api";
import type { CourseDetailResponse } from "@/lib/types";

function guard(text: string): string {
  if (containsEntitlementLanguage(text)) {
    if (process.env.NODE_ENV !== "production") {
      throw new Error(`Entitlement language in rendered text: ${text}`);
    }
    return "";
  }
  return text;
}

interface Props {
  courseId: string;
  /** KU ids the search query resolved to, used to highlight query-related atoms. */
  resolvedKuIds: string[];
  onClose: () => void;
}

export function CourseDetail({ courseId, resolvedKuIds, onClose }: Props) {
  const [detail, setDetail] = useState<CourseDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    fetchCourseDetail(courseId)
      .then((d) => {
        if (active) setDetail(d);
      })
      .catch((e) => {
        if (active) setError(e instanceof Error ? e.message : "Failed to load course.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [courseId]);

  const resolved = new Set(resolvedKuIds);

  return (
    <div className="detail-overlay" onClick={onClose}>
      <div className="detail-panel" onClick={(e) => e.stopPropagation()}>
        <button className="detail-close" onClick={onClose} aria-label="Close">
          ×
        </button>

        {loading && <p>Loading…</p>}
        {error && <p className="error">{error}</p>}

        {detail && detail.status === "course_not_found" && (
          <p className="caveat">{detail.status_message}</p>
        )}

        {detail && detail.status === "ok" && (
          <>
            <div className="card-header">
              <span className="course-number">
                {detail.subject_code} {detail.course_number}
              </span>
              <span className="level-badge">{detail.level}</span>
            </div>
            <h2 className="course-title">{guard(detail.title)}</h2>

            {detail.description && (
              <p className="detail-description">{guard(detail.description)}</p>
            )}

            <section className="detail-section">
              <h3 className="section-title">
                Knowledge atoms ({detail.concepts.length})
              </h3>
              <p className="caveat">
                CS2023 knowledge units inferred from the course description.
                Highlighted atoms relate to your search.
              </p>
              <ul className="atom-list">
                {detail.concepts.map((c) => (
                  <li
                    key={c.ku_id}
                    className={resolved.has(c.ku_id) ? "atom atom-matched" : "atom"}
                    title={`${c.knowledge_area} · confidence ${c.confidence.toFixed(2)}`}
                  >
                    <span className="atom-label">{c.label}</span>
                    <span className="atom-area">{c.knowledge_area}</span>
                    {resolved.has(c.ku_id) && <span className="atom-tag">matches search</span>}
                  </li>
                ))}
                {detail.concepts.length === 0 && (
                  <li className="caveat">No concepts were extracted for this course.</li>
                )}
              </ul>
            </section>

            <section className="detail-section">
              <h3 className="section-title">Prerequisites ({detail.prerequisites.length})</h3>
              {detail.prerequisites.length === 0 ? (
                <p className="caveat">No prerequisites are published for this course.</p>
              ) : (
                <ul className="prereq-list">
                  {detail.prerequisites.map((p) => (
                    <li key={p.course_id}>
                      <strong>{p.course_id}</strong>
                      {p.title ? ` — ${guard(p.title)}` : ""}
                      {p.verbatim ? <span className="verbatim"> ({guard(p.verbatim)})</span> : ""}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="detail-section">
              <h3 className="section-title">Unlocks ({detail.unlocks.length})</h3>
              {detail.unlocks.length === 0 ? (
                <p className="caveat">No courses declare this one as a prerequisite.</p>
              ) : (
                <ul className="unlock-list">
                  {detail.unlocks.slice(0, 20).map((u) => (
                    <li key={u.course_id}>
                      <strong>{u.course_id}</strong>
                      {u.title ? ` — ${guard(u.title)}` : ""}
                    </li>
                  ))}
                  {detail.unlocks.length > 20 && (
                    <li className="caveat">…and {detail.unlocks.length - 20} more</li>
                  )}
                </ul>
              )}
            </section>

            <p className="caveat">
              Evidence basis: {detail.evidence_basis} — description is published;
              knowledge atoms are inferred from it.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
