FROM node:22.18.0-alpine AS build

WORKDIR /app
COPY RainN0Coding-frontend/package*.json ./
RUN npm ci
COPY RainN0Coding-frontend/ ./
ENV VITE_BUILD_TARGET=standalone \
    VITE_API_BASE=/api
RUN npm run build

FROM nginx:1.28.0-alpine
COPY deploy/docker/frontend.nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --retries=6 \
  CMD wget -qO- http://127.0.0.1/healthz || exit 1
