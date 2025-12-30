FROM nginx:alpine

# Copy static files
COPY index.html /usr/share/nginx/html/
COPY styles.css /usr/share/nginx/html/
COPY app.js /usr/share/nginx/html/

# Custom nginx config with API and MinIO proxy
RUN echo 'server { \
    listen 80; \
    root /usr/share/nginx/html; \
    index index.html; \
    location / { \
    try_files $uri $uri/ /index.html; \
    } \
    location /api/ { \
    proxy_pass http://api:8000/; \
    proxy_set_header Host $host; \
    proxy_set_header X-Real-IP $remote_addr; \
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; \
    proxy_connect_timeout 30s; \
    proxy_read_timeout 300s; \
    } \
    location /minio/ { \
    proxy_pass http://minio:9000/; \
    proxy_set_header Host minio:9000; \
    proxy_set_header X-Real-IP $remote_addr; \
    proxy_connect_timeout 30s; \
    proxy_read_timeout 300s; \
    client_max_body_size 500M; \
    } \
    }' > /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

