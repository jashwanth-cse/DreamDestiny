# Dream Destiny — AWS Free Tier Automated Deployment Guide

Deploy the entire Dream Destiny microservices suite into AWS behind a **single unified endpoint** at **$0.00 / month cost**, completely automated via the AWS CLI.

---

## 1. Architecture Highlights

- **Single Entry Point**: All microservices accessible via one host URL:
  - `http://<HOST>/health` $\rightarrow$ Gateway Health
  - `http://<HOST>/plan` $\rightarrow$ AI Planning Service (FastAPI :8000)
  - `http://<HOST>/tourism` $\rightarrow$ Tourism Service (FastAPI :8001)
  - `http://<HOST>/hotels` $\rightarrow$ Hotels Service (FastAPI :8002)
  - `http://<HOST>/route` $\rightarrow$ Route Service (FastAPI :8003)
  - `http://<HOST>/api/v1/buses` $\rightarrow$ Bus Transport Service (FastAPI :8004)
  - `http://<HOST>/api/v1/trains` $\rightarrow$ Train Transport Service (FastAPI :8005)
  - `http://<HOST>/flights` $\rightarrow$ Flight Transport Service (FastAPI :8006)
- **Hardened Security**:
  - Ports `8000–8006` are **isolated** inside an internal Docker bridge network (`dream-destiny-prod-net`) and never exposed to the public internet.
  - Only Port `80` (HTTP) and `443` (HTTPS) are exposed through NGINX.
  - SSH (Port 22) is automatically locked down to your public IP.
- **100% AWS Free Tier Compliant**:
  - **EC2 Instance**: `t3.micro` or `t2.micro` (750 free hours/month).
  - **EBS Storage**: 30 GB gp3 volume (30 GB free tier).
  - **Swap Configuration**: Automatically allocates a **3 GB swapfile** so 7 microservices run comfortably on 1 GB physical RAM without crashing or triggering OOM.

---

## 2. One-Command Autonomous Provisioning

Make sure your AWS CLI is configured (`aws configure` with an Access Key and Secret Key).

### On Windows (PowerShell):
```powershell
.\deploy\deploy_aws.ps1 -Region ap-south-1
```
*(Or specify any region like `us-east-1`, `eu-west-1`)*

### On Linux / macOS / Git Bash:
```bash
chmod +x deploy/deploy_aws.sh
./deploy/deploy_aws.sh ap-south-1
```

The script will automatically:
1. Verify credentials and target region.
2. Locate the default VPC and public subnet.
3. Create the `dream-destiny-sg` security group (restricted SSH, public HTTP/HTTPS).
4. Generate the `dream-destiny-key.pem` SSH key pair.
5. Find the latest official Ubuntu 24.04 LTS AMI.
6. Assemble the cloud-init bootstrap script with your `.env` secrets.
7. Launch the EC2 instance with 30GB gp3 storage.
8. Wait for boot, retrieve the public IP, and print the endpoint links.

---

## 3. Verifying the Deployment

Once the instance boots and Docker Compose finishes building (approx. 2–3 minutes after launch), verify all endpoints through the reverse proxy:

```bash
python deploy/verify_deployment.py http://<YOUR_EC2_PUBLIC_IP>
```

Sample output:
```text
================================================================================
  DREAM DESTINY — DEPLOYMENT VERIFICATION TEST SUITE
  Target Gateway URL: http://54.210.12.34
================================================================================
STATUS  | METH | CODE| LATENCY | SERVICE                | URL
--------------------------------------------------------------------------------
[PASS]  | GET  | 200 |    45ms | Gateway Health         -> http://54.210.12.34/health
[PASS]  | GET  | 200 |   180ms | Tourism Service        -> http://54.210.12.34/tourism?city=delhi&limit=3
[PASS]  | GET  | 200 |   410ms | Hotel Service          -> http://54.210.12.34/hotels?city=delhi...
[PASS]  | GET  | 200 |   120ms | Route Service          -> http://54.210.12.34/route?origin=delhi...
[PASS]  | GET  | 200 |    95ms | Bus Service (cities)   -> http://54.210.12.34/api/v1/buses/cities
[PASS]  | GET  | 200 |   150ms | Train Service          -> http://54.210.12.34/api/v1/trains/search...
[PASS]  | POST | 200 |   320ms | Flight Service         -> http://54.210.12.34/flights/search
[PASS]  | POST | 200 |   850ms | Planner Context        -> http://54.210.12.34/plan/context
--------------------------------------------------------------------------------
Results: 8/8 endpoints passed successfully.
================================================================================
[SUCCESS] All microservices are healthy, reachable, and correctly routed through NGINX!
```

---

## 4. SSH & Server Management

To connect to your server:
```bash
ssh -i deploy/dream-destiny-key.pem ubuntu@<YOUR_EC2_PUBLIC_IP>
```

Useful management commands on the server:
```bash
# Check running containers
docker compose -f /opt/dream-destiny/docker-compose.prod.yml ps

# View live gateway / microservice logs
docker compose -f /opt/dream-destiny/docker-compose.prod.yml logs -f gateway
docker compose -f /opt/dream-destiny/docker-compose.prod.yml logs -f planner-service

# Check memory and swap usage
free -h
```

---

## 5. Free HTTPS & Custom Domain (Cloudflare)

To give your deployment a professional domain with free SSL/TLS (HTTPS):
1. Sign up for [Cloudflare](https://www.cloudflare.com) (Free Tier).
2. Add your domain and create an **`A` record**:
   - **Type**: `A`
   - **Name**: `api` (e.g. `api.yourdomain.com`)
   - **IPv4 address**: `<YOUR_EC2_PUBLIC_IP>`
   - **Proxy status**: **Proxied (Orange Cloud)**
3. In Cloudflare **SSL/TLS settings**, choose **Flexible** or **Full**.
4. You now have an enterprise-grade `https://api.yourdomain.com` with free automated SSL, DDoS defense, and edge caching at **$0 cost**!
