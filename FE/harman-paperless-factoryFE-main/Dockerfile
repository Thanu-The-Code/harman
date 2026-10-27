# Paperless Factory frontend - production image
# Build the Vite app with Node, then serve the static files with nginx.

# Stage 1: Build
# Vite 8 needs Node ^20.19 or >=22.12.
FROM node:22-slim AS build
WORKDIR /build

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .

# Vite bakes VITE_* variables into the bundle at build time, so the API
# address is a build argument, not a runtime setting.
ARG VITE_API_URL=""
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

# Stage 2: Serve
FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /build/dist/ /usr/share/nginx/html/

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
