import type { ThinCoverageNote } from "@/lib/types";

export function ThinCoverageAlert({ notes }: { notes: ThinCoverageNote[] }) {
  if (notes.length === 0) return null;
  return (
    <div className="thin-alert">
      Limited course coverage in the extracted map for:{" "}
      {notes.map((n) => n.label).join(", ")}. Results for these topics may be
      sparse.
    </div>
  );
}
