# OPNXT Frontend (Next.js)

A minimal Next.js (TypeScript) frontend for OPNXT that calls the FastAPI backend.

## Prerequisites

- Node.js 18+
- FastAPI backend running locally at `http://localhost:8000`

## Configure

Create `.env.local` (or copy the example):

```
cp .env.local.example .env.local
```

Adjust `NEXT_PUBLIC_API_BASE_URL` if your backend runs elsewhere.

## Run

```
npm install
npm run dev
```

Open http://localhost:3000

## Build

```
npm run build
npm start
```
