import type { CombinationResult } from "@/lib/types";
import { CoverageBar } from "./MetricBadge";

export function CombinationCard({ combo }: { combo: CombinationResult }) {
  const declaredOrder = combo.prerequisite_order.find((p) => p.declared);

  return (
    <div className="card">
      <div className="combo-courses">
        {combo.course_numbers.map((num, i) => (
          <span key={num} className="combo-courses">
            <span className="pill">
              {num}
              {combo.course_titles[i] ? ` — ${combo.course_titles[i]}` : ""}
            </span>
            {i < combo.course_numbers.length - 1 && <span className="arrow">+</span>}
          </span>
        ))}
      </div>

      <div className="metrics">
        <CoverageBar label={combo.combined_coverage_breadth} />
        <span className="metric-label">relevance {combo.combined_relevance.toFixed(2)}</span>
      </div>

      {declaredOrder ? (
        <p className="redundancy">
          Suggested order: take {declaredOrder.take_first} before {declaredOrder.then}.
        </p>
      ) : (
        <p className="redundancy">
          {combo.prerequisite_order[0]?.message ??
            "No ordering constraint is published between these courses."}
        </p>
      )}

      {combo.redundancies.length > 0 && (
        <p className="redundancy">
          Overlap:{" "}
          {combo.redundancies
            .map(
              (r) =>
                `${r.course_a_number} & ${r.course_b_number} share ${r.overlapping_ku_labels.length} concept(s)`
            )
            .join("; ")}
        </p>
      )}

      <p className="caveat">{combo.caveat}</p>
    </div>
  );
}
