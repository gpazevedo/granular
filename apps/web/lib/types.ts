// TypeScript types mirroring the backend Pydantic response models.

export type Level = "undergraduate" | "graduate" | "all";

export interface KULabel {
  ku_id: string;
  label: string;
  knowledge_area: string;
}

export interface CourseResult {
  course_id: string;
  course_number: string;
  subject_code: string;
  title: string;
  level: string;
  credits: string;
  description_excerpt: string;
  relevance_score: number;
  coverage_breadth: string;
  covered_ku_ids: string[];
  evidence_basis: "inferred";
  confidence: number;
  caveat: string;
}

export interface RedundancyNote {
  course_a_number: string;
  course_b_number: string;
  overlapping_ku_labels: string[];
}

export interface PrereqNote {
  take_first: string;
  then: string;
  declared: boolean;
  message?: string | null;
}

export interface CombinationResult {
  course_numbers: string[];
  course_titles: string[];
  combined_coverage_breadth: string;
  combined_ku_ids: string[];
  redundancies: RedundancyNote[];
  prerequisite_order: PrereqNote[];
  combined_relevance: number;
  evidence_basis: "inferred";
  caveat: string;
}

export interface ThinCoverageNote {
  ku_id: string;
  label: string;
}

export interface CourseConcept {
  ku_id: string;
  label: string;
  knowledge_area: string;
  confidence: number;
}

export interface CoursePrerequisite {
  course_id: string;
  title: string;
  verbatim: string;
}

export interface UnlockedCourse {
  course_id: string;
  title: string;
}

export interface CourseDetailResponse {
  course_id: string;
  course_number: string;
  subject_code: string;
  title: string;
  level: string;
  description: string;
  concepts: CourseConcept[];
  prerequisites: CoursePrerequisite[];
  unlocks: UnlockedCourse[];
  evidence_basis: "mixed";
  status: "ok" | "course_not_found";
  status_message?: string | null;
}

export type DiscoverStatus = "ok" | "no_concepts_resolved" | "no_courses_found";

export interface DiscoverResponse {
  resolved_kus: KULabel[];
  courses: CourseResult[];
  combinations: CombinationResult[];
  thin_coverage: ThinCoverageNote[];
  status: DiscoverStatus;
  status_message?: string | null;
}
