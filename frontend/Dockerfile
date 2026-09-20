# The frontend.
#
# Three stages. Dependencies, then the build, then a runtime image that carries
# neither: no node_modules, no typescript, no test runner. Next's standalone
# output traces which files the server actually needs and copies only those.

# --- stage 1: dependencies ---------------------------------------------------

FROM node:22-alpine AS deps
WORKDIR /app

# The lockfile alone, so that editing a component does not reinstall the world.
COPY package.json package-lock.json ./
RUN npm ci

# --- stage 2: the build ------------------------------------------------------

FROM node:22-alpine AS build
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_* values are inlined into the browser bundle at BUILD time, not
# read at runtime. It is left unset on purpose: the app calls its own origin
# and this server proxies /api/* onward, so nothing in the client is tied to
# one machine's address. See next.config.ts.
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# --- stage 3: the application ------------------------------------------------

FROM node:22-alpine AS runtime
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 app && adduser --system --uid 1001 app

# `standalone` holds the server and its traced dependencies; `static` and
# `public` are not traced into it and have to come across separately, or every
# stylesheet and font 404s while the page itself renders perfectly.
COPY --from=build --chown=app:app /app/.next/standalone ./
COPY --from=build --chown=app:app /app/.next/static ./.next/static
COPY --from=build --chown=app:app /app/public ./public

USER app
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD node -e "fetch('http://127.0.0.1:3000/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "server.js"]
