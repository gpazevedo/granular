# Granular Web (Next.js frontend)

Student-facing interface for interest-driven course discovery.

## Development

```bash
cd apps/web
npm install
npm run dev        # http://localhost:3000
```

The backend must be running (see repo root):

```bash
uvicorn granular.api.main:app --reload --port 8000
```

Set `NEXT_PUBLIC_API_BASE` if the backend is not on `http://localhost:8000`.

## Structure

- `app/page.tsx` — the discover page (search + results + combinations)
- `app/components/` — CourseCard, CombinationCard, ThinCoverageAlert, NoResultsMessage, MetricBadge
- `lib/api.ts` — typed API client + frontend entitlement-language guard
- `lib/types.ts` — TypeScript types mirroring the backend response models
