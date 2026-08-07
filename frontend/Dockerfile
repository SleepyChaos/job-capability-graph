# 前端镜像：Next.js standalone 多阶段构建（阶段 6 容器化部署）
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# 浏览器访问宿主 8002 端口 → 后端（与 docker-compose 端口映射一致）
ARG NEXT_PUBLIC_API_BASE=http://localhost:8002
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
RUN corepack enable && pnpm build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
