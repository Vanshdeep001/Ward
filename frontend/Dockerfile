# ── Stage 1: install dependencies ────────────────────────────────────────────
FROM node:20-alpine AS deps

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci


# ── Stage 2: build ────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build


# ── Stage 3: dev server (used by docker-compose) ──────────────────────────────
# For production swap this stage with a static server (e.g. nginx) serving /app/dist.
FROM node:20-alpine AS dev

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

EXPOSE 5173

# --host 0.0.0.0 makes Vite reachable outside the container.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

