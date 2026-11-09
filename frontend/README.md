# IntentFlow SDN dashboard

The frontend is a demo-first SDN operations dashboard built with Next.js App Router, React, TypeScript, Tailwind CSS, shadcn-style reusable UI primitives, XYFlow, Recharts, and Lucide icons.

## Run locally

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Useful checks:

```bash
npx tsc --noEmit
npm run lint
npm run build
```

## Demo and backend boundary

The current UI uses explicit illustrative data from `src/lib/demo-data.ts`. Charts and topology are not live telemetry; intent previews are produced by a small local example parser and are not LLM output, canonical backend intent, or validation. Submitting an intent does not send a request or deploy configuration.

`src/lib/api-client.ts` is the typed integration boundary for a future HTTP API. Configure `NEXT_PUBLIC_API_BASE_URL` only after a compatible Python API exists. No backend endpoint or WebSocket contract is assumed. The API client reports missing configuration instead of returning demo-shaped responses.

## Application structure

- `src/app`: App Router entry, metadata, global styling.
- `src/components`: navigation shell and separate dashboard, topology, intent, planning, metrics, execution, settings, and shared UI components.
- `src/components/ui`: reusable Button, Card, Badge, and dashboard primitives.
- `src/lib`: typed API client and isolated demo data.
- `src/types`: shared domain and view types.

The topology uses the illustrative 5-switch/4-host diamond. Its capacities are configured sample values, not achieved-throughput measurements.
