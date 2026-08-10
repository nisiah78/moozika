# Image de développement (hot-reload). Une image de production multi-stage
# (next build + next start) sera ajoutée lors de la mise en prod.
FROM node:20-slim

WORKDIR /app
COPY package.json ./
RUN npm install

COPY . .

EXPOSE 3000
CMD ["npm", "run", "dev"]
