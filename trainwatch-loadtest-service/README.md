# TrainWatch Availability Load-Test Service

A deployable, production-hardened microservice designed for **Google Cloud Run**, triggered every 5 minutes by **Google Cloud Scheduler** via secure OIDC authentication.

---

## 1. Overview & Architecture

The **TrainWatch Load-Test Service** continuously verifies the performance, stability, and deduplication behavior of our live train availability API (`https://dreamdestiny.cloud.run/api/v1/trains/availability`) under concurrent load.

```
                           +--------------------------------------+
                           |   Google Cloud Scheduler (5 min)     |
                           |  cron: */5 * * * *                   |
                           +------------------+-------------------+
                                              | OIDC Bearer Token
                                              v
                           +--------------------------------------+
                           |    Google Cloud Run (Secured)        |
                           |  Service: trainwatch-loadtest-service|
                           |  POST /run (Lock-guarded, No overlap)|
                           +--------+--------------------+--------+
                                    |                    |
            Concurrent User Queries |                    | Persist Test Summaries
            (Singleflight Deduplicated)                  | & Latency Telemetry
                                    v                    v
         +----------------------------------+  +-------------------------------+
         | Live Train Availability Service |  | Google Cloud Firestore        |
         | https://dreamdestiny.cloud.run   |  | Collection:                   |
         | /api/v1/trains/availability      |  | trainwatch_load_test_runs     |
         +----------------------------------+  +-------------------------------+
```

### Key Capabilities
1. **Concurrent User Simulation:** Dispatches concurrent async requests across combinations of station pairs (23 stations, 253 forward pairs), upcoming valid Sundays, and classes (`SL`, `3A`, `2A`).
2. **IRCTC Blackout Window Protection:** Automatically suppresses all test traffic during high-risk IRCTC operational windows:
   * **IRCTC Server Maintenance:** `11:40 PM – 12:25 AM IST` (23:40 – 00:25)
   * **AC Tatkal Booking Opening:** `09:45 AM – 10:15 AM IST` (Extreme rate limits)
   * **Non-AC / Sleeper Tatkal Window:** `10:45 AM – 11:15 AM IST` (Extreme rate limits)
   * *Returns HTTP 200 with `{"skipped": true}` so Cloud Scheduler records clean executions without retrying.*
3. **Deduplication Verification:** Proves that identical canonical keys (`{trainNo}:{src}:{dst}:{date}:{class}:{quota}`) share upstream executions and benefit from in-flight singleflight coalescing and snapshot caching.
4. **Overlapping Run Protection:** In-process concurrency lock rejects concurrent runs with `409 Conflict`.
5. **Runaway Prevention & Safety Guardrails:** Strict server-side caps on concurrency (`max: 50`) and requests (`max: 200`) prevent accidental billing spikes or upstream flooding.
6. **Firestore Telemetry:** Automatically records test summaries, latency percentiles (min, avg, p50, p90, p95, p99, max), status codes, and deduplication efficiency ratios to collection `trainwatch_load_test_runs`.
7. **Zero Impact on Production Service:** Interacts strictly with the public API endpoint via standard HTTPS POST requests without altering production internals.

---

## 2. API Endpoints

| Endpoint | Method | Auth Required | Description |
| :--- | :--- | :--- | :--- |
| `/health` | `GET` | No | Liveness probe reporting service status, Firestore connectivity, and active run state. |
| `/run` | `POST` | Yes (OIDC / API Key) | Triggers a bounded load test run. Returns summary and persists to Firestore. |
| `/runs` | `GET` | Optional | Returns the 10 most recent test runs from Firestore. |
| `/runs/{run_id}` | `GET` | Optional | Fetches detailed metrics and canonical key breakdown for a specific run. |

### Example Request Body for `POST /run` (Optional)
```json
{
  "scenario": "balanced",
  "concurrency": 20,
  "total_requests": 60,
  "timeout_seconds": 10.0
}
```

*Supported Scenarios:*
* `balanced` (Default): 50% identical hot query, 50% diverse station/date/class queries.
* `burst_identical`: 100% identical canonical keys (audits pure Singleflight coalescing).
* `diverse_matrix`: 100% distinct forward routes across 23 stations and 5 upcoming Sundays.
* `custom`: Executes explicit payloads provided in `custom_payloads`.

---

## 3. End-to-End GCP Setup & Deployment Instructions

Set your shell variables before executing the commands below:

```bash
export PROJECT_ID="trainwatch"
export REGION="asia-south1"
export SERVICE_NAME="trainwatch-loadtest-service"
export TARGET_AVAILABILITY_URL="https://dreamdestiny.cloud.run/api/v1/trains/availability"
export RUNTIME_SA="trainwatch-loadtest-sa@${PROJECT_ID}.iam.gserviceaccount.com"
export SCHEDULER_SA="trainwatch-scheduler-sa@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud config set project $PROJECT_ID
```

---

### Step 1: Enable Required GCP APIs
Enable Cloud Run, Cloud Build, Artifact Registry, Firestore, IAM, and Cloud Scheduler:

```bash
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    firestore.googleapis.com \
    cloudscheduler.googleapis.com \
    iam.googleapis.com
```

---

### Step 2: Create Dedicated Service Accounts with Least-Privilege IAM

1. **Create the Cloud Run Runtime Service Account:**
   ```bash
   gcloud iam service-accounts create trainwatch-loadtest-sa \
       --display-name="TrainWatch Load-Test Service Runtime SA"
   ```

2. **Grant Firestore Read/Write Access (`roles/datastore.user`):**
   ```bash
   gcloud projects add-iam-policy-binding $PROJECT_ID \
       --member="serviceAccount:${RUNTIME_SA}" \
       --role="roles/datastore.user"
   ```

3. **Create the Cloud Scheduler Invoker Service Account:**
   ```bash
   gcloud iam service-accounts create trainwatch-scheduler-sa \
       --display-name="TrainWatch Scheduler Invoker SA"
   ```

---

### Step 3: Create Firestore Database
If you do not already have a Firestore database in your project:

```bash
gcloud firestore databases create \
    --location=$REGION \
    --type=firestore-native
```
> The service writes its audit logs to the `trainwatch_load_test_runs` collection automatically.

---

### Step 4: Build and Deploy the Service to Cloud Run

1. **Build Container Image with Cloud Build:**
   ```bash
   gcloud builds submit \
       --tag gcr.io/${PROJECT_ID}/${SERVICE_NAME}:latest \
       trainwatch-loadtest-service/
   ```

2. **Deploy to Cloud Run with Unauthenticated Access Disabled:**
   ```bash
   gcloud run deploy $SERVICE_NAME \
       --image gcr.io/${PROJECT_ID}/${SERVICE_NAME}:latest \
       --region $REGION \
       --platform managed \
       --no-allow-unauthenticated \
       --service-account $RUNTIME_SA \
       --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID},TARGET_AVAILABILITY_URL=${TARGET_AVAILABILITY_URL},ENABLE_FIRESTORE=true,DEFAULT_CONCURRENCY=20,DEFAULT_TOTAL_REQUESTS=60,MAX_ALLOWED_CONCURRENCY=50,MAX_ALLOWED_REQUESTS=200" \
       --concurrency 10 \
       --cpu 1 \
       --memory 512Mi \
       --timeout 180s \
       --min-instances 0 \
       --max-instances 2
   ```

3. **Retrieve the Deployed Cloud Run Service URL:**
   ```bash
   export SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
       --region $REGION \
       --format="value(status.url)")
   echo "Service deployed at: $SERVICE_URL"
   ```

4. **Grant Cloud Scheduler Permission to Invoke the Cloud Run Service (`roles/run.invoker`):**
   ```bash
   gcloud run services add-iam-policy-binding $SERVICE_NAME \
       --region $REGION \
       --member="serviceAccount:${SCHEDULER_SA}" \
       --role="roles/run.invoker"
   ```

---

### Step 5: Configure Google Cloud Scheduler (5-Minute Trigger)

Create a scheduled job targeting `POST /run` with OIDC authentication using the dedicated scheduler service account:

```bash
gcloud scheduler jobs create http trainwatch-5min-loadtest \
    --location=$REGION \
    --schedule="*/5 * * * *" \
    --time-zone="Asia/Kolkata" \
    --uri="${SERVICE_URL}/run" \
    --http-method=POST \
    --oidc-service-account-email=$SCHEDULER_SA \
    --oidc-token-audience=$SERVICE_URL \
    --headers="Content-Type=application/json" \
    --message-body='{"scenario":"balanced","concurrency":20,"total_requests":60}' \
    --attempt-deadline=180s \
    --description="Triggers TrainWatch availability deduplication load test every 5 minutes"
```

---

### Step 6: Trigger Manual Test & Verify Execution

1. **Trigger Cloud Scheduler Job Immediately:**
   ```bash
   gcloud scheduler jobs run trainwatch-5min-loadtest --location=$REGION
   ```

2. **Stream Live Cloud Run Logs:**
   ```bash
   gcloud logging tail "resource.type=cloud_run_revision AND resource.labels.service_name=${SERVICE_NAME}"
   ```

3. **Inspect Output via CLI (Using Your GCP User Token):**
   ```bash
   curl -X POST "${SERVICE_URL}/run" \
       -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
       -H "Content-Type: application/json" \
       -d '{"scenario":"burst_identical","concurrency":10,"total_requests":20}'
   ```

4. **Verify Firestore Persistence:**
   Open Google Cloud Console $\rightarrow$ **Firestore** $\rightarrow$ **Databases** $\rightarrow$ Collection: `trainwatch_load_test_runs`.
   Each document contains:
   * `run_id`: Unique identifier
   * `timestamp`: Run start time
   * `total_simulated_requests`: Number of simulated requests
   * `unique_canonical_keys`: Number of distinct query combinations
   * `deduplication_ratio`: Coalescing multiplier (e.g. `20.0`)
   * `latency`: `{ min_ms, avg_ms, p50_ms, p90_ms, p95_ms, p99_ms, max_ms }`
   * `key_breakdown`: Detailed per-route breakdown proving deduplication

---

### Step 7: Cost Management, Safety Caps & Disabling Schedule

1. **Safety Request Limits:**
   * Max concurrency is hard-capped in code at `50` (`MAX_ALLOWED_CONCURRENCY`).
   * Max requests per run is hard-capped at `200` (`MAX_ALLOWED_REQUESTS`).
   * Cloud Run max instances is constrained to `2` (`--max-instances 2`).
2. **Monthly Cost Estimate:**
   * Running 12 times per hour (every 5 minutes) = 8,640 runs/month.
   * With 60 requests per run, total simulated requests = ~518,400/month.
   * Total Firestore document writes = 8,640 writes/month (within free tier of 20,000 writes/day!).
   * Cloud Run compute time per run = ~2-4 seconds $\rightarrow$ comfortably within Google Cloud free tier (2 million requests/month, 360,000 vCPU-seconds).
3. **Pausing the Cloud Scheduler Job:**
   ```bash
   gcloud scheduler jobs pause trainwatch-5min-loadtest --location=$REGION
   ```
4. **Resuming the Cloud Scheduler Job:**
   ```bash
   gcloud scheduler jobs resume trainwatch-5min-loadtest --location=$REGION
   ```
5. **Completely Deleting the Schedule:**
   ```bash
   gcloud scheduler jobs delete trainwatch-5min-loadtest --location=$REGION --quiet
   ```

---

## 4. Local Testing & Verification

Run the test suite locally (runs offline with mock Firestore and target API):

```bash
# Navigate to the service folder
cd trainwatch-loadtest-service

# Install dependencies
pip install -r requirements-dev.txt

# Execute test suite
pytest tests -v
```

All 14 unit and integration tests will execute in under a second, verifying:
* Deduplication correctness for burst identical payloads
* Independent processing for diverse query matrices
* Overlapping run rejection (HTTP 409 Conflict)
* Dynamic upcoming Sunday calculation
* Authentication and Firestore fallback storage
