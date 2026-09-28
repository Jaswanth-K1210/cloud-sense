FROM node:22-alpine
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_API_URL=http://localhost:8000
ARG VITE_READONLY_TEMPLATE_URL=
ENV VITE_API_URL=$VITE_API_URL VITE_READONLY_TEMPLATE_URL=$VITE_READONLY_TEMPLATE_URL
RUN npm run build
EXPOSE 4173
CMD ["npm", "run", "preview", "--", "--port", "4173"]
