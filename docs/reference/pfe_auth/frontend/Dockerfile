FROM node:20-alpine

WORKDIR /app

# Install deps first (layer cache)
COPY package.json package-lock.json* ./
RUN npm ci

# Copy source (overridden by volume mount in dev)
COPY . .

EXPOSE 5173

# host 0.0.0.0 required so Docker can forward the port out of the container
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
