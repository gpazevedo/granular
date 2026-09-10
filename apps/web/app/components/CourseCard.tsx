import type { CourseResult } from "@/lib/types";
import { containsEntitlementLanguage } from "@/lib/api";
import { CoverageBar, RelevanceBadge } from "./MetricBadge";

function guard(text: string): string {
  // Frontend rendering-level entitlement-language check (REQ-AQ-12).
  if (containsEntitlementLanguage(text)) {
    if (process.env.NODE_ENV !== "production") {
      throw new Error(`Entitlement language in rendered text: ${text}`);
    }
    return "";
  }
  return text;
}

export function CourseCard({
  course,
  onSelect,
}: {
  course: CourseResult;
  onSelect?: (courseId: string) => void;
}) {
  return (
    <div
      className="card card-clickable"
      role="button"
      tabIndex={0}
      onClick={() => onSelect?.(course.course_id)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect?.(course.course_id);
        }
      }}
    >
      <div className="card-header">
        <span className="course-number">
          {course.subject_code} {course.course_number}
        </span>
        <span className="level-badge">{course.level}</span>
      </div>
      <h3 className="course-title">{guard(course.title)}</h3>
      <p className="excerpt">{guard(course.description_excerpt)}</p>
      <div className="metrics">
        <RelevanceBadge score={course.relevance_score} />
        <CoverageBar label={course.coverage_breadth} />
      </div>
      <div className="metrics">
        <span className="evidence">{course.evidence_basis}</span>
        <span className="metric-label">{course.credits ? `${course.credits} cr` : ""}</span>
      </div>
      <p className="caveat">{guard(course.caveat)}</p>
    </div>
  );
}
