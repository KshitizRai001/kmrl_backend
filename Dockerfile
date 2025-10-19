FROM node:18-bullseye

# Install system deps for Python and build tools
RUN apt-get update && apt-get install -y python3 python3-pip build-essential ca-certificates --no-install-recommends && rm -rf /var/lib/apt/lists/*

# Use corepack to manage pnpm
RUN corepack enable && corepack prepare pnpm@10.14.0 --activate || true

WORKDIR /app

# Copy package manifests first for caching
COPY package.json pnpm-lock.yaml ./
COPY backend/package.json backend/pnpm-lock.yaml backend/

# Copy the full repo
COPY . .

# Install python requirements for the advanced model (optional; failure won't break JS build)
RUN if [ -f backend/advanced_model/requirements.txt ]; then pip3 install --no-cache-dir -r backend/advanced_model/requirements.txt || true; fi

# Install JS deps
RUN pnpm install --frozen-lockfile --prefer-offline || pnpm install

# Build the backend (TypeScript -> dist)
RUN pnpm --filter backend build

EXPOSE 3000

# Start the backend server
CMD ["pnpm", "--filter", "backend", "start"]
