import type { DiscoverResponse } from "@/lib/types";

export function NoResultsMessage({ response }: { response: DiscoverResponse }) {
  return (
    <div className="no-results">
      <p>{response.status_message}</p>
      {response.resolved_kus.length > 0 && (
        <p>
          Your interest resolved to:{" "}
          {response.resolved_kus.map((k) => k.label).join(", ")}.
        </p>
      )}
    </div>
  );
}
