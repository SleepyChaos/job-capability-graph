FROM node:22-alpine AS build

WORKDIR /srv/frontend

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN npm config set registry https://registry.npmmirror.com && \
    npm install -g pnpm@10.29.3 && \
    pnpm install --frozen-lockfile --registry https://registry.npmmirror.com

COPY . .
RUN pnpm build

# 预压静态产物，供 nginx 的 gzip_static 直接发送（见 nginx.conf 里的说明）。
# 保留未压缩原件：不支持 gzip 的客户端仍走原文件。-9 是构建期一次性开销，换取
# 运行期零 CPU；1024 字节以下压了反而更大，跳过。
RUN find dist -type f \( -name '*.js' -o -name '*.css' -o -name '*.json' -o -name '*.html' -o -name '*.svg' \) \
      -size +1k -exec sh -c 'gzip -9 -c "$1" > "$1.gz"' _ {} \;

FROM nginx:1.27-alpine

COPY --from=build /srv/frontend/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
