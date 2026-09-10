"use client";

import { useState } from "react";
import { discover } from "@/lib/api";
import type { DiscoverResponse, Level } from "@/lib/types";
import { CourseCard } from "./components/CourseCard";
import { CourseDetail } from "./components/CourseDetail";
import { CombinationCard } from "./components/CombinationCard";
import { ThinCoverageAlert } from "./components/ThinCoverageAlert";
import { NoResultsMessage } from "./components/NoResultsMessage";

const LEVELS: Level[] = ["all", "undergraduate", "graduate"];

export default function DiscoverPage() {
  const [query, setQuery] = useState("");
  const [level, setLevel] = useState<Level>("all");
  const [response, setResponse] = useState<DiscoverResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedCourseId, setSelectedCourseId] = useState<string | null>(null);

  async function onSearch() {
    if (!query.trim()) {
      setError("Please enter a learning interest.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await discover(query, level);
      setResponse(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
      setResponse(null);
    } finally {
      setLoading(false);
    }
  }

  const showResults = response && response.status === "ok";
  const showNoResults =
    response &&
    (response.status === "no_concepts_resolved" || response.status === "no_courses_found");

  return (
    <div className="container">
      <h1>Granular</h1>
      <p className="subtitle">
        Describe what you want to learn. We map it to Purdue CS courses.
      </p>

      <div className="search-row">
        <input
          className="search-input"
          placeholder="e.g. machine learning for computer vision"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onSearch()}
        />
        <button className="search-button" onClick={onSearch} disabled={loading}>
          {loading ? "Searching…" : "Discover"}
        </button>
      </div>

      <div className="level-filter">
        {LEVELS.map((l) => (
          <button
            key={l}
            className={level === l ? "active" : ""}
            onClick={() => setLevel(l)}
          >
            {l}
          </button>
        ))}
      </div>

      {error && <p className="error">{error}</p>}

      {response && <ThinCoverageAlert notes={response.thin_coverage} />}

      {showNoResults && <NoResultsMessage response={response!} />}

      {showResults && (
        <div className="columns">
          <div>
            <h2 className="section-title">Courses</h2>
            {response!.courses.map((c) => (
              <CourseCard key={c.course_id} course={c} onSelect={setSelectedCourseId} />
            ))}
          </div>
          <div>
            <h2 className="section-title">Course Combinations</h2>
            {response!.combinations.length === 0 ? (
              <p className="caveat">
                No combination improves on the individual courses above.
              </p>
            ) : (
              response!.combinations.map((combo, i) => (
                <CombinationCard key={i} combo={combo} />
              ))
            )}
          </div>
        </div>
      )}

      {selectedCourseId && (
        <CourseDetail
          courseId={selectedCourseId}
          resolvedKuIds={response?.resolved_kus.map((k) => k.ku_id) ?? []}
          onClose={() => setSelectedCourseId(null)}
        />
      )}
    </div>
  );
}
