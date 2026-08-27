FROM node:22-alpine AS build

WORKDIR /srv/frontend

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN npm config set registry https://registry.npmmirror.com && \
    npm install -g pnpm@10.29.3 && \
    pnpm install --frozen-lockfile --registry https://registry.npmmirror.com

COPY . .
RUN pnpm build

FROM nginx:1.27-alpine

COPY --from=build /srv/frontend/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
