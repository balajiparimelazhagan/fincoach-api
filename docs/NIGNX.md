Got it. Below is a **short, essential README** — only what you actually need, no extras.

---

README – Nginx + SSL Setup (Ubuntu)

Purpose
Serve a built SPA frontend with Nginx, proxy API requests, and enable HTTPS using Certbot.

Assumptions

* Ubuntu server
* Nginx on host
* Frontend is a SPA (React / Vite)
* Backend runs on localhost:8000
* Domain: app.roobai.fyi

---

1. Install Nginx

sudo apt update
sudo apt install -y nginx

---

2. DNS (mandatory)

Ensure:

* app.roobai.fyi points to this server (A or CNAME)
* Domain is reachable over HTTP

Check:
dig +short app.roobai.fyi

---

3. Nginx config (HTTP only)

File: /etc/nginx/sites-enabled/app.roobai.fyi

server {
listen 80;
server_name app.roobai.fyi;

```
root /usr/share/nginx/html;
index index.html;

location / {
    try_files $uri $uri/ /index.html;
}

location /api/ {
    proxy_pass http://localhost:8000/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

}

Test & reload:
sudo nginx -t
sudo systemctl reload nginx

---

4. Build & deploy frontend

cd ~/fincoach-ui
npm install
npm run build

Clear & copy:
sudo rm -rf /usr/share/nginx/html/*
sudo cp -r build/* /usr/share/nginx/html/   (or dist/* for Vite)

Permissions:
sudo chown -R www-data:www-data /usr/share/nginx/html

---

5. Install Certbot

sudo apt install -y certbot python3-certbot-nginx

---

6. Fetch SSL (HTTPS)

sudo certbot --nginx -d app.roobai.fyi

Choose: redirect HTTP → HTTPS

---

7. Verify

[https://app.roobai.fyi](https://app.roobai.fyi)
sudo certbot renew --dry-run

---

Rules to remember

* Do NOT use listen 443 ssl before Certbot
* Do NOT manually manage PEM files
* nginx -t must pass before certbot
* Frontend must call APIs using /api, not localhost

---

End
