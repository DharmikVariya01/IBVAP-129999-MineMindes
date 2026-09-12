# IBVAP Frontend

Frontend for the Intelligent Border Video Analysis Platform (IBVAP — SIH26187).

## Foundation Architecture (M18)
- **Framework:** React 18.3.1
- **Tooling & Bundler:** Vite 5.4.14
- **Language:** TypeScript 5.6.3
- **Styling:** Tailwind CSS 3.4.17 (tactical dark-mode surveillance theme)
- **Icons:** Lucide React
- **Testing:** Vitest 2.1.8 with jsdom and Testing Library

## Directory Structure
```
frontend/
├── public/              # Static public assets (favicon, icons)
├── src/
│   ├── components/
│   │   ├── common/      # Reusable generic UI components (Button, Card, Badge, Panel, etc.)
│   │   └── layout/      # Application Shell and Header
│   ├── config/          # Environment configuration service
│   ├── hooks/           # Custom React hooks (useWebSocket)
│   ├── pages/           # Foundation showcase and page placeholders
│   ├── services/
│   │   ├── api/         # REST API client (M16 resources)
│   │   └── websocket/   # Real-time WebSocket streaming client (M17 endpoint)
│   ├── tests/           # Vitest unit and integration test suites
│   ├── types/           # TypeScript interfaces for M16 REST and M17 WebSocket
│   ├── utils/           # Utility functions (cn styling helper)
│   ├── App.tsx          # Application root component
│   ├── main.tsx         # DOM mount entrypoint
│   └── index.css        # Tailwind directives and dark surveillance base styling
├── .env.example         # Environment variables template
├── package.json
├── tsconfig.json
├── tailwind.config.js
└── vite.config.ts
```

## Available Scripts
- `npm run dev`: Start local development server on http://127.0.0.1:5173
- `npm run build`: Typecheck and produce optimized production bundle in `dist/`
- `npm test`: Run full Vitest unit and integration test suite

