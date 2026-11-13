FROM node:24.22.1-bookworm-slim

WORKDIR /app

# Install pnpm
RUN corepack enable && corepack prepare pnpm@11.2.2 --activate

# Copy package files
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

# Copy source and build
COPY . .
ARG VITE_CLERK_PUBLISHABLE_KEY
ARG VITE_API_URL=http://localhost:8000
ENV VITE_CLERK_PUBLISHABLE_KEY=$VITE_CLERK_PUBLISHABLE_KEY
ENV VITE_API_URL=$VITE_API_URL
RUN test -n "$VITE_CLERK_PUBLISHABLE_KEY" && pnpm build

# Serve with a static file server
RUN npm install --global serve@14.2.6
EXPOSE 5173
CMD ["serve", "-s", "dist", "-l", "5173"]
