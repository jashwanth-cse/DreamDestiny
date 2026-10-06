# Travel Planner — Amazon SQS Scalability Implementation Plan

## Objective

Introduce Amazon SQS between the WhatsApp bot and the long-running itinerary-generation workload.

**Do not rewrite the existing Travel Planner.** This phase only changes workload execution from synchronous/long-lived HTTP to asynchronous job processing.

### Current

```text
WhatsApp
  ↓
Webhook
  ↓
Bot
  ↓
Long-running planner request
  ↓
Itinerary
  ↓
WhatsApp
```

### Target

```text
WhatsApp
  ↓
Webhook
  ↓
Bot
  ↓
Create durable job
  ↓
Amazon SQS
  ↓
Planner Worker
  ↓
Existing Backend Gateway
  ↓
Existing Travel Planner
  ↓
Persist result
  ↓
WhatsApp Cloud API
```

The webhook must acknowledge the incoming event quickly. It must never remain open waiting for itinerary generation.

---

## 1. Target Architecture

```text
                         WhatsApp User
                              |
                              v
                    WhatsApp Cloud API
                              |
                           Webhook
                              |
                              v
                           Nginx
                              |
                              v
                  +-------------------------+
                  |   WhatsApp Bot Service  |
                  |                         |
                  | Webhook                 |
                  | Conversation Manager    |
                  | Redis                   |
                  | Firestore               |
                  +-----------+-------------+
                              |
                         Create Job
                              |
                              v
                       +-------------+
                       | Amazon SQS  |
                       | Main Queue  |
                       +------+------+ 
                              |
                     Message consumed
                              |
                              v
                  +-------------------------+
                  |    Planner Worker       |
                  |                         |
                  | SQS Consumer            |
                  | Job Processor            |
                  +-----------+-------------+
                              |
                              v
                    Existing Backend Gateway
                              |
               +--------------+--------------+
               |              |              |
               v              v              v
           Tourism        Transport        Hotels
               |              |              |
               +--------------+--------------+
                              |
                              v
                         AI Planner
                              |
                              v
                          Validator
                              |
                              v
                         Firestore
                              |
                              v
                   WhatsApp Cloud API
                              |
                              v
                            User
```

---

## 2. Non-Negotiable Compatibility Rules

Do not modify the core business logic.

Do not rewrite:

- Tourism service
- Transport service
- Hotel service
- Route service
- railway station resolver
- train fallback logic
- hotel caching
- planning agent
- validator
- cost engine
- TripContext
- existing gateway contracts

unless a minimal compatibility change is required.

The purpose of this phase is only:

```text
long-running synchronous workload
              ↓
asynchronous SQS workload
```

---

## 3. Responsibility Boundaries

### WhatsApp Bot Service

Responsible for:

- WhatsApp webhook
- conversation state
- Redis session
- Firestore persistence
- determining when a TripRequest is ready
- creating the job
- publishing the job to SQS
- sending an immediate acknowledgement

It must **not** generate the itinerary.

### Planner Worker

Responsible for:

- consuming SQS jobs
- loading the authoritative job from Firestore
- claiming the job
- calling the existing backend gateway
- retry/failure handling
- storing the itinerary
- sending the final WhatsApp response

### Existing Backend Gateway

Remains responsible for:

- orchestration
- Tourism
- Transport
- Hotels
- Routes
- AI planning
- validation
- all existing travel business logic

---

## 4. Job Lifecycle

Use:

```text
QUEUED
  ↓
PROCESSING
  ↓
COMPLETED
```

Failure:

```text
QUEUED
  ↓
PROCESSING
  ↓
FAILED
```

Retryable failure:

```text
PROCESSING
  ↓
retry
  ↓
PROCESSING
```

A job must not be considered completed until the result has been durably persisted and the outbound delivery workflow has been handled according to the application's idempotency policy.

---

## 5. SQS Message Contract

Keep the SQS message small.

Do not put the full conversation history into SQS.

```json
{
  "job_id": "job_01H...",
  "job_type": "GENERATE_ITINERARY",
  "user_id": "919876543210",
  "conversation_id": "conv_01H...",
  "request_id": "req_01H...",
  "created_at": "2026-10-06T12:00:00Z",
  "schema_version": 1
}
```

The worker uses `job_id` to retrieve the authoritative job/context from Firestore.

Use the existing TripRequest schema. Do not create an incompatible WhatsApp-only version.

---

## 6. Firestore Job Record

Create a durable job record:

```text
users/{wa_id}/jobs/{job_id}
```

Example:

```json
{
  "job_id": "job_01H...",
  "job_type": "GENERATE_ITINERARY",
  "user_id": "919876543210",
  "conversation_id": "conv_01H...",
  "request_id": "req_01H...",
  "status": "QUEUED",
  "attempt": 0,
  "trip_request": {},
  "created_at": "...",
  "updated_at": "...",
  "started_at": null,
  "completed_at": null,
  "error": null
}
```

The actual `trip_request` must use the existing project schema.

---

## 7. WhatsApp Request Flow

When the conversation is ready to generate:

```text
User
 ↓
WhatsApp webhook
 ↓
Conversation Manager
 ↓
TripRequest complete
 ↓
Create Firestore job
 ↓
Publish SQS message
 ↓
Return webhook success
```

Then immediately send:

> ✨ Got it! I'm building your itinerary now. I'll check transport, hotels, places and create your plan.

Do not wait for the planner.

---

## 8. Worker Flow

```text
SQS
 ↓
ReceiveMessage
 ↓
Read job_id
 ↓
Load Firestore job
 ↓
Atomically claim job
 ↓
Set PROCESSING
 ↓
Call existing Backend Gateway
 ↓
Receive itinerary
 ↓
Persist itinerary
 ↓
Send WhatsApp result
 ↓
Mark COMPLETED
 ↓
Delete SQS message
```

Make persistence and outbound delivery idempotent so worker crashes cannot cause duplicate itinerary generation.

---

## 9. At-Least-Once Delivery

Assume SQS delivers messages **at least once**.

The same job can be delivered more than once.

Therefore:

```text
SQS delivery
   ↓
job_id
   ↓
Firestore job state
   ↓
idempotent processing
```

If already completed, do not regenerate.

If already being processed, another worker must not process it concurrently.

---

## 10. Job Claiming / Locking

Use an atomic Firestore transaction/conditional update:

```text
QUEUED → PROCESSING
```

Only one worker may successfully claim a job.

Redis may be used for short-lived coordination, but Firestore job state is the authoritative job state.

Never depend only on a process-local lock.

---

## 11. Worker Concurrency

Support configurable concurrent processing:

```env
WORKER_CONCURRENCY=4
```

Do not blindly increase concurrency.

Consider:

- EC2 CPU
- EC2 memory
- backend gateway capacity
- Google API limits
- SerpAPI quota
- Gemini/API limits
- downstream service latency

---

## 12. Horizontal Scaling

The worker must be stateless:

```text
SQS
 |
 +--> Worker 1
 +--> Worker 2
 +--> Worker 3
```

Future worker instances can process independent jobs.

All shared state remains in Redis/Firestore/SQS.

---

## 13. SQS Visibility Timeout

Configure visibility timeout longer than the expected maximum processing duration, including:

```text
service calls
+ AI generation
+ validation
+ persistence
+ WhatsApp delivery
```

Use a safety margin.

If jobs can exceed the initial timeout, implement visibility-timeout extension/heartbeat while processing.

Never allow a long-running job to become visible to another worker while the original worker is still processing it.

---

## 14. Dead Letter Queue

Create:

```text
travel-planner-jobs
travel-planner-jobs-dlq
```

Configure a redrive policy.

Example:

```text
maxReceiveCount = 3
```

Keep it configurable.

Flow:

```text
Main Queue
  ↓
failure
  ↓
retry
  ↓
failure
  ↓
retry
  ↓
failure
  ↓
DLQ
```

Do not retry permanently invalid jobs forever.

---

## 15. Retry Classification

### Retryable

- network timeout
- temporary gateway failure
- transient upstream 5xx
- temporary WhatsApp API failure
- temporary Firestore failure

### Non-retryable

- invalid TripRequest
- malformed job
- unsupported job type
- permanent configuration failure
- permanently invalid payload

Do not create retry storms.

---

## 16. Idempotency

Implement idempotency at all important boundaries.

### Incoming WhatsApp message

Use WhatsApp `message_id`.

### Job

Use `job_id`.

### Itinerary

Before generation, check whether the job already has a completed result.

### Outbound WhatsApp

Persist delivery status where required.

The worker must safely recover from:

```text
generate
 ↓
persist
 ↓
worker crashes
```

without generating another itinerary on retry.

---

## 17. WhatsApp Processing During Generation

When a job is queued:

```text
conversation state = GENERATING
```

If the same user sends another modification while generation is running, do not create competing generations blindly.

For the initial implementation:

- prevent duplicate generation
- recognize the conversation is `GENERATING`
- either ask the user to wait or safely queue a modification
- never race multiple itinerary generations for the same active trip unless explicitly implemented

---

## 18. Backend Gateway Integration

The worker calls the existing gateway only.

For example:

```text
POST /plan
```

Use the actual existing endpoint.

The worker should send the existing `TripRequest`.

The worker must not call Tourism/Transport/Hotel/Route services directly.

Use:

- HTTP connection pooling
- explicit timeouts
- limited safe retries
- correlation IDs
- structured error handling

---

## 19. Result Delivery

After successful generation:

```text
Worker
 ↓
Itinerary
 ↓
Firestore
 ↓
WhatsApp Cloud API
 ↓
User
```

Always address the exact user from the job:

```python
send_message(
    recipient=job.user_id,
    message=formatted_itinerary
)
```

Never use a global/current-user variable.

---

## 20. User Experience

Immediately after queuing:

```text
✨ Your trip request is received.

I'm checking transport, hotels and places and building your itinerary now.
```

After completion:

```text
🎉 Your itinerary is ready!
```

If processing permanently fails:

```text
Sorry, I couldn't generate the itinerary right now.

Please try again in a moment.
```

Never expose internal errors.

---

## 21. Queue Backpressure

SQS is the workload buffer.

If traffic spikes:

```text
Users
 ↓
SQS queue depth increases
 ↓
Workers process at controlled capacity
```

Do not increase worker concurrency without considering downstream provider quotas.

Monitor queue depth and worker utilization.

---

## 22. Monitoring

Track at minimum:

```text
sqs_messages_sent_total
sqs_messages_received_total
sqs_jobs_completed_total
sqs_jobs_retried_total
sqs_jobs_dlq_total

job_queue_wait_time
job_processing_latency
job_success_rate
job_failure_rate

planner_gateway_latency
planner_gateway_errors

whatsapp_send_success_total
whatsapp_send_failure_total
```

Monitor SQS:

```text
ApproximateNumberOfMessagesVisible
ApproximateNumberOfMessagesNotVisible
```

The most important scalability indicators are queue depth, queue wait time, worker throughput and downstream error/rate-limit behavior.

---

## 23. Correlation IDs

Every job must contain:

```text
job_id
request_id
conversation_id
user_id
```

Propagate them through:

```text
WhatsApp
 ↓
Bot
 ↓
SQS
 ↓
Worker
 ↓
Gateway
 ↓
Travel services
```

A single itinerary request must be traceable across the entire system.

---

## 24. AWS Security

Use an EC2 IAM role or dedicated least-privilege IAM role rather than hard-coded AWS access keys.

Bot service requires only the necessary SQS publish permissions.

Worker requires only:

```text
ReceiveMessage
DeleteMessage
ChangeMessageVisibility
GetQueueAttributes
```

plus any required queue-send permission if recovery/outbox publishing is performed by the worker.

Do not grant unrestricted AWS permissions.

---

## 25. Environment Configuration

Add to `.env.example`:

```env
AWS_REGION=ap-south-1

SQS_ITINERARY_QUEUE_URL=
SQS_ITINERARY_DLQ_URL=

SQS_VISIBILITY_TIMEOUT_SECONDS=600
SQS_WAIT_TIME_SECONDS=20
SQS_MAX_MESSAGES=10
SQS_MAX_RECEIVE_COUNT=3

WORKER_CONCURRENCY=4

PLANNER_GATEWAY_URL=
```

Use actual existing configuration conventions where present.

Do not hard-code queue URLs or credentials.

---

## 26. SQS Long Polling

The worker must use long polling.

Use a configurable `WaitTimeSeconds`, e.g.:

```text
20 seconds
```

This avoids constant empty polling and reduces unnecessary SQS requests.

---

## 27. Worker Structure

Create a separate worker process/service:

```text
planner-worker/
├── app/
│   ├── main.py
│   ├── worker.py
│   ├── sqs/
│   │   ├── client.py
│   │   └── consumer.py
│   ├── jobs/
│   │   ├── processor.py
│   │   └── itinerary_job.py
│   ├── storage/
│   │   └── firestore.py
│   ├── clients/
│   │   ├── planner_gateway.py
│   │   └── whatsapp.py
│   ├── schemas/
│   │   └── job.py
│   └── config.py
├── tests/
├── Dockerfile
└── README.md
```

Reuse shared schemas/utilities where appropriate, but do not tightly couple the worker to the WhatsApp process.

---

## 28. Queue Schema Versioning

Every SQS message must contain:

```json
{
  "schema_version": 1
}
```

Future job-contract changes must preserve backward compatibility with already queued messages.

---

## 29. Graceful Shutdown

Worker must handle SIGTERM/SIGINT.

On shutdown:

1. Stop receiving new messages.
2. Finish active jobs where possible.
3. Never delete an SQS message before successful processing.
4. If processing cannot finish, allow visibility timeout/release behavior to make the message available again.
5. Close Redis/Firestore/HTTP clients.

This is required for EC2/service restarts and future autoscaling.

---

## 30. Failure Scenarios

Test:

### Worker crashes before processing

Message becomes visible again after visibility timeout.

### Worker crashes during planner call

Message becomes available again; job state must recover safely.

### Worker crashes after itinerary persistence

Retry detects the existing completed result and does not regenerate.

### WhatsApp send fails

Retry outbound delivery without regenerating the itinerary.

### Gateway timeout

Retry only according to retry policy.

### SQS unavailable

Do not tell the user generation has started unless the job was successfully queued. Use a recoverable queue-pending state.

### Firestore unavailable

Do not acknowledge durable job creation if the authoritative job cannot be stored.

---

## 31. Queue-Pending / Outbox Recovery

Avoid:

```text
Firestore job created
 ↓
SQS publish fails
 ↓
job permanently stranded
```

Use:

```text
Create Firestore job
status = QUEUE_PENDING
 ↓
Publish SQS
 ↓
success
 ↓
status = QUEUED
```

If publish fails:

```text
QUEUE_PENDING
```

must remain recoverable.

Implement a lightweight recovery process that finds stale `QUEUE_PENDING` jobs and republishes them safely.

Use `job_id` for idempotency.

Do not add a complex distributed transaction system unless actual workload requirements justify it.

---

## 32. Deployment

EC2 should contain separate processes/services:

```text
EC2
├── Nginx
├── Backend Gateway
├── Existing Travel Services
├── WhatsApp Bot Service
└── Planner Worker
```

Only the WhatsApp webhook needs public inbound access through Nginx.

The worker does not need a public HTTP endpoint.

Run both new services under systemd or Docker Compose with automatic restart.

---

## 33. Testing

### Unit tests

Test:

- SQS message creation
- message parsing
- job state transitions
- retry classification
- idempotency
- job claiming
- worker processing
- result persistence
- WhatsApp delivery

### Integration tests

Test:

```text
WhatsApp webhook
 -> Firestore
 -> SQS
 -> Worker
 -> Existing Gateway
 -> Firestore
 -> WhatsApp
```

Mock external Meta/AWS APIs where appropriate.

### Failure tests

Simulate:

- SQS unavailable
- Firestore unavailable
- gateway timeout
- gateway 500
- WhatsApp send failure
- worker crash
- duplicate SQS delivery
- duplicate WhatsApp message
- two workers receiving the same job

### Load tests

Simulate:

```text
10 concurrent jobs
50 concurrent jobs
100 concurrent jobs
500 queued jobs
```

Measure:

- queue wait time
- processing time
- throughput
- failure rate
- EC2 CPU
- EC2 memory
- downstream API usage

---

## 34. Implementation Order

### Phase 1 — Inspect Existing System

Before modifying code:

- inspect the WhatsApp bot service
- inspect Redis integration
- inspect Firestore integration
- inspect current synchronous itinerary generation
- inspect the existing backend gateway endpoint
- identify the exact call that currently waits for the itinerary
- identify current response handling

Do not change unrelated code.

### Phase 2 — AWS SQS Infrastructure

Create:

- main SQS queue
- DLQ
- redrive policy
- IAM permissions
- queue configuration

Verify connectivity independently.

### Phase 3 — Job Model

Create:

- job schema
- Firestore job document
- job states
- attempt tracking
- idempotency fields

### Phase 4 — Publisher

Change only:

```text
current:
Bot -> planner directly

new:
Bot -> create job -> SQS
```

Everything before job creation remains unchanged.

### Phase 5 — Planner Worker

Create:

```text
SQS -> job processor -> existing gateway
```

### Phase 6 — Result Handling

Implement:

```text
result -> Firestore -> WhatsApp
```

with idempotency.

### Phase 7 — Retry / DLQ

Implement:

- visibility timeout
- retry classification
- DLQ
- failure states

### Phase 8 — Concurrency

Implement:

- worker concurrency
- atomic job claiming
- duplicate protection
- graceful shutdown

### Phase 9 — Observability

Add:

- structured logs
- metrics
- correlation IDs
- queue monitoring

### Phase 10 — Testing

Run:

- unit tests
- integration tests
- failure tests
- concurrency tests
- load tests

### Phase 11 — Production Deployment

Verify:

- EC2 restart
- service restart
- worker restart
- duplicate webhook
- duplicate SQS delivery
- queue backlog
- DLQ
- planner failure
- WhatsApp delivery failure

---

## 35. Acceptance Criteria

The implementation is complete only when:

- WhatsApp webhook returns quickly without waiting for itinerary generation.
- Every accepted itinerary request creates a durable job.
- Jobs are published successfully to SQS.
- Worker consumes jobs.
- Existing backend gateway is reused.
- Existing travel services continue unchanged.
- Generated itineraries reach the correct WhatsApp user.
- Multiple users can generate itineraries concurrently.
- Duplicate SQS deliveries do not regenerate itineraries.
- Worker crashes do not permanently lose jobs.
- Failed jobs retry correctly.
- Poison jobs reach the DLQ.
- Queue depth is observable.
- Job queue wait time and processing latency are measurable.
- Redis conversation state continues to work.
- Firestore history continues to work.
- Returning users continue to work.
- Existing functionality remains unchanged.
- EC2/service restarts do not permanently lose queued work.
- Tests pass.
- Load tests pass.

---

## 36. Critical Rules for the Implementation Agent

1. Do not rewrite existing travel services.
2. Do not move travel business logic into the WhatsApp layer.
3. Do not maintain long-lived HTTP connections while generating itineraries.
4. Do not use Python process memory as shared state.
5. Do not use Redis as permanent job storage.
6. Do not duplicate the existing TripRequest/business schemas.
7. Do not call individual travel services directly from the worker.
8. Always use the existing backend gateway.
9. Assume SQS at-least-once delivery.
10. Make job processing idempotent.
11. Atomically claim jobs before processing.
12. Never generate duplicate itineraries because of an SQS retry.
13. Do not acknowledge a job as queued until SQS publish succeeds.
14. Make QUEUE_PENDING jobs recoverable.
15. Use a DLQ for poison jobs.
16. Use timeouts and bounded retries.
17. Do not create retry storms.
18. Use least-privilege IAM.
19. Do not hard-code AWS credentials or queue URLs.
20. Keep the worker independently deployable and horizontally scalable.
21. Preserve existing WhatsApp conversation behavior.
22. Preserve Redis and Firestore semantics.
23. Do not make unrelated changes.
24. Run existing tests before and after the change.
25. Run failure and concurrency tests before declaring completion.

---

## 37. Final Architecture

```text
                         WhatsApp
                            |
                            v
                    WhatsApp Cloud API
                            |
                         Webhook
                            |
                            v
                         Nginx
                            |
                            v
                  WhatsApp Bot Service
                    /                                /                                 v                 v
               Redis            Firestore
            session/state     durable state
                  |
                  v
             Create Job
                  |
                  v
             Amazon SQS
                  |
          +-------+-------+
          |       |       |
          v       v       v
       Worker  Worker  Worker
          |       |       |
          +-------+-------+
                  |
                  v
          Existing Gateway
                  |
       +----------+----------+
       |          |          |
       v          v          v
   Tourism    Transport    Hotels
       |          |          |
       +----------+----------+
                  |
                  v
             AI Planner
                  |
                  v
              Validator
                  |
                  v
             Firestore
                  |
                  v
         WhatsApp Cloud API
                  |
                  v
                User
```

**System-design principle:**

> Use HTTP for short request/event handling. Use Amazon SQS for long-running workload execution. Keep the existing internal travel services and business logic unchanged.

This change is intended to improve concurrency, backpressure, failure isolation and horizontal scalability without changing the core Travel Planner.
