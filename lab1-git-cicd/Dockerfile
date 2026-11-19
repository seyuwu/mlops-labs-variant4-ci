FROM node:22-alpine AS test
WORKDIR /app
COPY package.json ./
COPY src ./src
COPY tests ./tests
COPY scripts ./scripts
RUN npm test && npm run build

FROM node:22-alpine AS production
WORKDIR /app
ENV NODE_ENV=production
COPY --from=test --chown=node:node /app/dist ./src
COPY --chown=node:node package.json ./
RUN mkdir /app/logs && chown node:node /app/logs
USER node
CMD ["npm", "start"]
