# Etapa 1: Compilación de la aplicación React con Vite
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

ARG VITE_API_URL=/api/v1
ENV VITE_API_URL=$VITE_API_URL
ENV NODE_OPTIONS="--max-old-space-size=4096"

RUN npm run build

# Etapa 2: Servidor web de producción Nginx
FROM nginx:alpine

RUN apk add --no-cache openssl

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY entrypoint-nginx.sh /entrypoint-nginx.sh
RUN chmod +x /entrypoint-nginx.sh

EXPOSE 80 443

ENTRYPOINT ["/entrypoint-nginx.sh"]
CMD ["nginx", "-g", "daemon off;"]
