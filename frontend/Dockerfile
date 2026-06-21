FROM nginx:1.27-alpine

# Remove default config
RUN rm /etc/nginx/conf.d/default.conf

COPY nginx.conf /etc/nginx/conf.d/chatbot.conf
COPY index.html /usr/share/nginx/html/index.html

EXPOSE 80
