Absolutely. **R5 — Delivery Feedback, Bounce/Complaint/Unsubscribe Processing, Provider Integration & Operational Monitoring** closes the loop that began in R1.

Up through R4, the platform can decide who is eligible, send safely, retry individual failures, reconcile campaign execution, and create an immutable as-sent archive. R5 adds the downstream truth: **Was the email delivered? Did it bounce? Did the recipient complain? Did they unsubscribe? Should we suppress them immediately?**

Your original requirements explicitly require ingestion of delivery/bounce/complaint events, hard-bounce/complaint suppression, unsubscribe processing, soft-bounce escalation, and operator alerts when bounce or complaint rates exceed configured thresholds.

Odoo 19 already has useful native foundations here: it supports mailing-list unsubscribe, global marketing blacklist, opt-out reasons, and timestamped blacklist history; global-blacklisted addresses are excluded from marketing mailings while transactional mail can still be delivered. ([Odoo](https://www.odoo.com/documentation/saas-19.1/fr/applications/marketing/email_marketing/unsubscriptions.html?utm_source=chatgpt.com "Manage unsubscriptions (blacklist) — Documentation Odoo saas-19.1")) Odoo also has a bounce return-path mechanism and displays delivery failures, but our R5 layer should remain the compliance authority for classification, suppression, provider callbacks, thresholds, and audit evidence. ([Odoo](https://www.odoo.com/documentation/19.0/applications/general/email_communication/email_servers_inbound.html?msockid=170e05a3d0ec68d110571356d1b86952&utm_source=chatgpt.com "Manage inbound messages — Odoo 19.0 documentation"))

# R5 — Delivery Feedback & Operational Monitoring

## 1\. R5 scope

| Capability | R5 |
| --- | --- |
| Provider-neutral delivery integration | ✅ |
| Delivery event webhook/API | ✅ |
| Event authentication | ✅ |
| Event idempotency | ✅ |
| Provider message correlation | ✅ |
| Delivered event processing | ✅ |
| Delayed/deferred event processing | ✅ |
| Hard-bounce classification | ✅ |
| Soft-bounce classification | ✅ |
| Soft-bounce counter | ✅ |
| Soft-bounce threshold suppression | ✅ |
| Complaint processing | ✅ |
| Automatic suppression | ✅ |
| Native Odoo blacklist synchronization | ✅ |
| Odoo unsubscribe synchronization | ✅ |
| Purpose-specific unsubscribe | ✅ |
| Global opt-out | ✅ |
| Recipient consent withdrawal linkage | ✅ |
| Campaign outcome reconciliation | ✅ |
| Bounce/complaint warning thresholds | ✅ |
| Operational dashboards | ✅ |
| Alerting | ✅ |
| Provider health monitoring | ✅ |
| Retention/privacy lifecycle | R6 |

* * *

# 2\. R5 architecture

The architecture becomes:

                              ODOO 19 COMMUNITY
    ┌─────────────────────────────────────────────────────────────┐
    │                                                             │
    │ Campaign Governance                                         │
    │        │                                                    │
    │        ▼                                                    │
    │ Eligibility / Preflight                                     │
    │        │                                                    │
    │        ▼                                                    │
    │ Campaign Execution                                          │
    │        │                                                    │
    │        ▼                                                    │
    │ Odoo SMTP / External Provider                               │
    │                                                             │
    └─────────────────────────┬───────────────────────────────────┘
                              │
                              │ outbound email
                              ▼
                  ┌──────────────────────────┐
                  │     EMAIL PROVIDER       │
                  │                          │
                  │ SMTP / SES / SendGrid / │
                  │ Mailgun / Other         │
                  └───────────┬──────────────┘
                              │
                 Delivery / Bounce / Complaint
                              │
                              ▼
    ┌─────────────────────────────────────────────────────────────┐
    │                  R5 EVENT INGESTION                         │
    │                                                             │
    │ Authenticate                                                │
    │      ↓                                                      │
    │ Normalize Provider Event                                    │
    │      ↓                                                      │
    │ Idempotency                                                 │
    │      ↓                                                      │
    │ Correlate Message                                           │
    │      ↓                                                      │
    │ Classify Outcome                                            │
    │      ↓                                                      │
    │ Send Event Ledger                                           │
    │      ↓                                                      │
    │ Suppression Engine                                          │
    │      ↓                                                      │
    │ Campaign Outcome                                            │
    │      ↓                                                      │
    │ Monitoring / Alerts                                         │
    └─────────────────────────────────────────────────────────────┘

The important architecture decision is that **Odoo should understand a canonical internal delivery-event format**, not AWS SES, SendGrid, or Mailgun directly.

* * *

# 3\. Provider-neutral integration

Create an abstraction:

    newsletter.provider.adapter

or, preferably initially, Python service adapters:

    services/providers/
    ├── base_provider.py
    ├── smtp_provider.py
    ├── ses_provider.py
    ├── sendgrid_provider.py
    └── mailgun_provider.py

The compliance layer operates only on:

    Canonical Delivery Event

regardless of the underlying provider.

* * *

# 4\. Canonical provider event

Define:

    {
        "provider": "ses",
        "provider_event_id": "...",
        "provider_message_id": "...",
    
        "event_type": "hard_bounce",
    
        "event_timestamp": "...",
    
        "email": "john@example.com",
    
        "campaign_id": "CMP-2026-000128",
        "campaign_run_id": "RUN-2026-000414",
    
        "bounce_type": "permanent",
        "bounce_subtype": "general",
    
        "smtp_status": "550",
        "diagnostic_code": "...",
    
        "raw_payload": {...},
    }

Then all downstream logic operates on this format.

* * *

# 5\. Canonical event types

Use controlled values:

    accepted
    delivered
    delivery_delayed
    soft_bounce
    hard_bounce
    complaint
    unsubscribe
    provider_rejected
    provider_dropped
    unknown

Do not create provider-specific event types such as:

    SES_BOUNCE_PERMANENT
    SENDGRID_DROPPED
    MAILGUN_FAILED

inside the core data model.

Adapters translate those into canonical values.

* * *

# 6\. Delivery event API

Create an endpoint such as:

    POST /newsletter-compliance/v1/events/{provider}

Examples:

    /newsletter-compliance/v1/events/ses
    /newsletter-compliance/v1/events/sendgrid
    /newsletter-compliance/v1/events/mailgun

Controller:

    controllers/event_webhook_controller.py

* * *

# 7\. Event processing pipeline

Never perform all downstream logic directly inside the webhook HTTP request.

Use:

    Provider
       │
       ▼
    Webhook
       │
       ▼
    Validate
       │
       ▼
    Persist Raw Incoming Event
       │
       ▼
    Return HTTP 2xx
       │
       ▼
    Background Processor
       │
       ▼
    Normalize
    Correlate
    Classify
    Apply Suppression
    Update Outcome
    Alert

This provides reliability and keeps provider callbacks fast.

* * *

# 8\. Incoming Event model

Create:

    newsletter.provider.event

This is different from:

    newsletter.send.event

The distinction is:

### Provider Event

Raw inbound technical message.

### Send Event

Canonical business/audit event.

* * *

# 9\. Provider Event fields

| Field | Purpose |
| --- | --- |
| reference | Internal inbound ID |
| provider | Provider |
| provider_event_id | Provider ID |
| provider_message_id | Provider message |
| received_at | Odoo receipt time |
| event_timestamp | Provider event time |
| raw_payload | Original payload |
| payload_hash | Integrity |
| processing_state | New/Processed/Failed |
| processing_attempts | Retry count |
| next_retry_at | Retry |
| error_message | Error |
| send_event_id | Canonical event generated |
| campaign_run_id | Correlated run |
| eligibility_id | Correlated recipient |
| company_id | Company |

* * *

# 10\. Provider-event states

    received
    validated
    processing
    processed
    unmatched
    retry_pending
    failed
    ignored_duplicate

Do not discard unmatched events.

An event might arrive before another database transaction becomes visible, or correlation metadata might have been temporarily unavailable.

* * *

# 11\. Event authentication

Each provider adapter should implement:

    validate_request(headers, body)

Do not expose an anonymous endpoint that trusts arbitrary bounce/complaint JSON.

Depending on provider, validate:

    Webhook signature
    Shared secret
    HMAC
    Signed notification
    Certificate/signature
    Source token

Also enforce:

    TLS
    Request-size limits
    JSON validation
    Rate limiting
    Replay protection

* * *

# 12\. Never trust campaign/email fields from callback alone

Suppose someone sends:

    {
      "email": "ceo@example.com",
      "event": "complaint"
    }

That should not immediately globally suppress the CEO.

Require event correlation through:

    provider_message_id

plus known execution history where available.

Preferred correlation:

    provider_message_id
          ↓
    newsletter.recipient.eligibility
          ↓
    Campaign Run
          ↓
    Recipient

* * *

# 13\. Provider Message ID

R4 already added:

    provider_message_id

to dispatch records.

Make it:

    indexed

and ideally unique in combination with provider:

    (provider, provider_message_id)

because this becomes the primary R5 correlation key.

* * *

# 14\. Idempotency

Providers may retry webhooks.

Therefore:

    Provider Event #ABC123

received five times must result in:

    one business event
    one suppression action

not five.

Add SQL uniqueness:

    unique(provider, provider_event_id)

where provider IDs are reliable.

Fallback idempotency key:

    SHA256(
        provider
        + provider_message_id
        + event_type
        + timestamp
        + email
    )

* * *

# 15\. Event normalization service

Create:

    services/event_normalization_service.py

Flow:

    adapter = get_provider_adapter(provider)
    
    canonical_event = adapter.normalize_event(
        raw_event
    )

Expected result:

    CanonicalDeliveryEvent(...)

* * *

# 16\. Delivery processing

For:

    DELIVERED

update:

    eligibility.delivery_state = delivered

create:

    newsletter.send.event
    event_type = delivered

and update:

    newsletter.campaign.outcome

No suppression action.

* * *

# 17\. Delivery delayed

For temporary provider delays:

    delivery_state = delayed

and:

    SEND EVENT:
    delivery_delayed

Do not treat provider delay automatically as a soft bounce unless the provider's event semantics indicate a delivery failure.

This distinction is important.

* * *

# 18\. Bounce classification

Create:

    newsletter.bounce.classification

or initially implement a controlled classifier service.

Categories:

    hard
    soft
    unknown

Subcategories:

    invalid_recipient
    mailbox_not_found
    domain_not_found
    mailbox_full
    temporary_server_error
    greylisted
    policy_rejection
    spam_rejection
    message_too_large
    dns_failure
    connection_failure
    other

* * *

# 19\. Hard bounce

Examples commonly include permanent mailbox/address failures.

Flow:

    Provider Hard Bounce
            │
            ▼
    Provider Event
            │
            ▼
    Canonical HARD_BOUNCE
            │
            ▼
    Send Event
            │
            ▼
    Recipient delivery_state = hard_bounce
            │
            ▼
    Create Global Suppression
            │
            ▼
    Synchronize Odoo Blacklist

This implements the original FR-19 behavior.

* * *

# 20\. Hard bounce suppression

Create:

    newsletter.suppression.entry

with:

    scope = global
    reason = HARD_BOUNCE
    source = provider
    effective_from = event_timestamp

Link:

    source_event_id
    provider_event_id
    campaign_run_id

If an equivalent active suppression already exists:

    do not create duplicate suppression

but still retain the new send event.

* * *

# 21\. Complaint

Complaint should normally be treated even more strictly.

Flow:

    Provider Complaint
           │
           ▼
    Canonical COMPLAINT
           │
           ▼
    Send Event
           │
           ▼
    Global Suppression
           │
           ▼
    Native Odoo Blacklist
           │
           ▼
    Alert Compliance

The source requires complained recipients to be suppressed from future sends.

* * *

# 22\. Complaint reason

Suppression:

    reason = COMPLAINT
    scope = global

Do not permit ordinary users to reinstate complaint suppressions.

I recommend:

    allow_reinstatement = False

by default.

Any extraordinary reversal should require a Compliance Administrator and evidence.

* * *

# 23\. Soft bounce

Soft bounces require a different policy.

Example:

    RUN 1 → soft bounce
    Count = 1
    
    RUN 2 → delivered
    Count resets / decays depending policy
    
    or
    
    RUN 2 → soft bounce
    Count = 2
    
    RUN 3 → soft bounce
    Count = 3
    → suppression

Your original requirement explicitly calls for soft-bounce counting and suppression after a configurable threshold.

* * *

# 24\. Soft Bounce Counter

Create:

    newsletter.delivery.reputation

per normalized email.

Fields:

| Field | Purpose |
| --- | --- |
| email_normalized | Address |
| partner_id | Contact |
| soft_bounce_count | Consecutive/current count |
| lifetime_soft_bounce_count | Historical count |
| hard_bounce_count | Historical |
| complaint_count | Historical |
| last_soft_bounce_at | Date |
| last_hard_bounce_at | Date |
| last_delivery_at | Date |
| last_complaint_at | Date |
| reputation_state | Good/Warning/Suppressed |
| company_id | Company |

* * *

# 25\. Why a separate reputation model

Do not count soft bounces by querying every historical send event each time.

Maintain:

    recipient reputation aggregate

while preserving the events as the source audit trail.

This gives fast preflight checks.

* * *

# 26\. Soft-bounce policy

Configuration:

    Soft Bounce Threshold = 3
    Soft Bounce Window = 90 days
    Reset on Successful Delivery = Yes

Recommended initial policy:

    consecutive soft bounces >= 3
    → global suppression

But keep it configurable.

* * *

# 27\. Successful delivery and bounce count

Two possible policies:

### Policy A — consecutive bounces

    soft bounce
    soft bounce
    delivered
    → counter resets to 0

### Policy B — rolling window

    3 soft bounces within 90 days
    → suppress

I recommend **rolling window or consecutive-with-window**, because a single successful delivery should not necessarily erase persistent quality problems forever.

Initial implementation:

    threshold = 3
    window = 90 days

* * *

# 28\. Soft-bounce threshold flow

    SOFT BOUNCE
        │
        ▼
    Increment Reputation
        │
        ▼
    threshold reached?
       / \
     NO   YES
     │     │
     ▼     ▼
    Log   Create suppression
          reason =
          SOFT_BOUNCE_LIMIT

* * *

# 29\. Unknown bounce

If provider says only:

    failed

and classification is uncertain:

    event_type = unknown_bounce

Do not automatically create global suppression unless policy says otherwise.

Instead:

    delivery_state = unknown_failure

and flag for review.

Conservative classification is safer than incorrectly suppressing valid recipients.

* * *

# 30\. Odoo native blacklist synchronization

Odoo 19 supports a global marketing blacklist and excludes blacklisted addresses from marketing mailings. ([Odoo](https://www.odoo.com/documentation/saas-19.1/fr/applications/marketing/email_marketing/unsubscriptions.html?utm_source=chatgpt.com "Manage unsubscriptions (blacklist) — Documentation Odoo saas-19.1"))

Therefore R5 should synchronize **global** compliance suppression into Odoo's blacklist mechanism.

Examples:

    HARD_BOUNCE       → Odoo blacklist
    COMPLAINT         → Odoo blacklist
    GLOBAL_OPT_OUT    → Odoo blacklist
    SOFT_BOUNCE_LIMIT → Odoo blacklist

Do not synchronize:

    PURPOSE_OPT_OUT
    MAILING_LIST_OPT_OUT

to the global blacklist.

* * *

# 31\. Two-way blacklist synchronization

We also need the reverse path.

If an authorized Odoo user or recipient creates a native global blacklist entry:

    Odoo Blacklist
         ↓
    newsletter.suppression.entry

Create:

    reason = GLOBAL_OPT_OUT
    source = odoo_blacklist

This keeps R1 suppression history complete.

* * *

# 32\. Avoid synchronization loops

Add:

    source_system
    external_reference
    sync_origin

and context flags such as:

    with_context(
        newsletter_skip_blacklist_sync=True
    )

Otherwise:

    Compliance creates blacklist
    → native blacklist hook
    → creates compliance suppression
    → compliance hook
    → creates blacklist
    → ...

* * *

# 33\. Native unsubscribe

Odoo 19 supports unsubscribing from specific mailing lists, and recipients can optionally globally blacklist themselves from all marketing emails. Odoo also records opt-out reasons. ([Odoo](https://www.odoo.com/documentation/saas-19.1/fr/applications/marketing/email_marketing/unsubscriptions.html?utm_source=chatgpt.com "Manage unsubscriptions (blacklist) — Documentation Odoo saas-19.1"))

We should preserve that UX but extend its compliance consequences.

* * *

# 34\. Purpose-specific unsubscribe

This requires careful semantics.

Suppose:

    Mailing List:
    Healthcare Monthly
    
    Consent Purpose:
    Healthcare Updates

Recipient clicks Unsubscribe.

We should create:

    mailing-list opt-out

and potentially:

    purpose suppression

depending on the unsubscribe choice.

Do not automatically withdraw every marketing consent.

* * *

# 35\. Recommended unsubscribe choices

Present:

    ○ Stop this newsletter only
    ○ Stop all Healthcare Updates
    ○ Stop all marketing communications

Result:

### Newsletter only

    Mailing List Opt-Out

### Purpose

    Suppression scope = PURPOSE
    Purpose = Healthcare Updates

Potentially also withdraw the applicable consent.

### All Marketing

    Suppression scope = GLOBAL
    Odoo blacklist = True

* * *

# 36\. Consent withdrawal linkage

If the recipient explicitly chooses:

    Stop all Healthcare Updates

then:

    Active Healthcare consent
           ↓
    Withdraw Consent
           ↓
    Create PURPOSE suppression

This gives a coherent history:

    Consent withdrawal
    +
    Suppression
    +
    Send Event

* * *

# 37\. Unsubscribe SLA

The original NFR requires unsubscribe to be reflected in suppression within 24 hours, with near-real-time as the target.

Our Odoo design should make this:

    near real-time

because unsubscribe processing occurs transactionally.

If the recipient clicks unsubscribe:

    request
      ↓
    Odoo updates opt-out
      ↓
    Compliance suppression created
      ↓
    future dispatch-time check sees it immediately

* * *

# 38\. One-click unsubscribe / headers

Your original FR-12 expects a working one-click unsubscribe link and recipient-specific `List-Unsubscribe` behavior.

Odoo provides native unsubscribe facilities, but R5 should test the actual outbound headers and rendered links in your deployed environment.

Do not simply assume that because the template has a visual unsubscribe link, all required headers are present exactly as desired.

Add an automated integration test for:

    unsubscribe link
    List-Unsubscribe
    List-Unsubscribe-Post where configured/supported

* * *

# 39\. Campaign Outcome model

R4 introduced:

    newsletter.campaign.outcome

R5 now fully implements it.

Fields:

    campaign_run_id
    sent_count
    accepted_count
    delivered_count
    
    delivery_delayed_count
    
    soft_bounce_count
    hard_bounce_count
    unknown_bounce_count
    
    complaint_count
    unsubscribe_count
    
    provider_rejected_count
    
    outcome_observation_started_at
    outcome_observation_until
    
    finalized
    finalized_at
    
    outcome_hash

* * *

# 40\. Why outcome is separate from archive

Recall our R4 rule:

    Campaign Archive
    = immutable exact as-sent evidence
    
    Campaign Outcome
    = evolving downstream result

This remains the right design.

For example:

    28-Aug 15:48
    Dispatch complete
    Archive locked
    
    28-Aug 15:49
    12,000 delivered
    
    28-Aug 18:00
    21,000 delivered
    
    29-Aug
    15 bounces
    2 complaints

The content archive should not be repeatedly edited.

The Outcome object may evolve until finalized.

* * *

# 41\. Outcome observation window

Configuration:

    Outcome Finalization Window = 72 hours

or:

    7 days

depending on your audit requirement.

Do not prematurely assume all delivery feedback is final immediately after dispatch.

When window expires:

    Outcome → FINALIZED

and calculate:

    outcome_hash

* * *

# 42\. Late events

A provider event may arrive after outcome finalization.

Do not modify a locked finalized outcome silently.

Create:

    newsletter.campaign.outcome.adjustment

or:

    LATE_DELIVERY_EVENT

linked to the finalized outcome.

Then reports can show:

    Finalized counts
    +
    Late adjustments

This preserves evidence integrity.

* * *

# 43\. Campaign metrics

R5 should provide:

    Targeted
    Eligible
    Excluded
    Sent
    Accepted
    Delivered
    Delivery Delayed
    Soft Bounce
    Hard Bounce
    Complaint
    Unsubscribe
    Technical Failed
    Dispatch Blocked

Your original FR-26 explicitly requires campaign-level targeted, sent, suppressed, delivered, bounced, complained, and unsubscribed counts.

* * *

# 44\. Rate calculations

Add:

    Delivery Rate
    Bounce Rate
    Hard Bounce Rate
    Complaint Rate
    Unsubscribe Rate
    Failure Rate
    Suppression Rate

Example definitions:

    Delivery Rate =
    Delivered / Sent

    Bounce Rate =
    (Soft Bounce + Hard Bounce) / Sent

    Complaint Rate =
    Complaints / Delivered

or `/ Sent`, depending on your policy/reporting definition.

Pick one denominator and document it.

Do not let dashboards calculate differently from alerts.

* * *

# 45\. Warning thresholds

Configuration:

    Bounce Warning Threshold
    Complaint Warning Threshold
    Unsubscribe Warning Threshold
    Technical Failure Warning Threshold

Your original requirement explicitly calls for bounce and complaint warning thresholds during an in-progress campaign.

* * *

# 46\. Example defaults

Do not hard-code regulatory/provider thresholds as universal facts.

Provide configurable defaults such as:

    Bounce warning: 2%
    Complaint warning: 0.05%

and allow administrators to change them based on provider and policy.

The original document includes provider/reputation expectations, but because we have moved away from an SES-only architecture, the threshold mechanism should be provider-neutral.

* * *

# 47\. Threshold states

Campaign Outcome:

    healthy
    warning
    critical

Example:

    Bounce rate < warning
    → HEALTHY
    
    Bounce rate >= warning
    → WARNING
    
    Bounce rate >= critical
    → CRITICAL

* * *

# 48\. Operational alerts

Create:

    newsletter.compliance.alert

Types:

    bounce_threshold
    complaint_threshold
    unsubscribe_spike
    technical_failure_threshold
    provider_event_failure
    provider_event_backlog
    unmatched_provider_events
    reputation_risk
    archive_integrity_failure

Fields:

    reference
    alert_type
    severity
    campaign_run_id
    provider
    raised_at
    metric_name
    metric_value
    threshold_value
    status
    assigned_to
    acknowledged_at
    resolved_at
    resolution_notes
    company_id

* * *

# 49\. Alert severity

Use:

    info
    warning
    critical

No need for an excessive severity taxonomy.

* * *

# 50\. Alert deduplication

Do not create:

    500 complaint threshold alerts

while a campaign remains above threshold.

Use an active alert key:

    campaign_run
    +
    alert_type

Only create another after:

    previous alert resolved

or escalation threshold changes materially.

* * *

# 51\. Alert actions

On threshold breach:

    Create Compliance Alert
          │
          ├── Odoo activity for Campaign Operator
          ├── activity for Compliance Reviewer
          ├── chatter notification
          └── optional email/webhook

For critical conditions, optionally:

    Suspend campaign

if sending is still in progress.

* * *

# 52\. Automatic campaign suspension

Make configurable:

    Auto Suspend on Complaint Threshold = Yes/No
    Auto Suspend on Bounce Threshold = Yes/No

If enabled:

    threshold exceeded
           ↓
    Campaign Run = suspended
           ↓
    worker stops acquiring new recipients
           ↓
    already-sent recipients unaffected

Add R5 state:

    suspended

to Campaign Run.

* * *

# 53\. Suspended campaign behavior

When suspended:

    processing recipients
    → allowed to finish safely
    
    queued/not-started recipients
    → remain pending

Operator can:

    Resume
    Cancel

but resume should require:

    reason

and possibly Compliance Reviewer authorization for critical reputation alerts.

* * *

# 54\. Provider-health monitoring

Create:

    newsletter.provider.health

Track:

    Provider
    Last event received
    Last successful send
    Webhook backlog
    Event processing failures
    Unmatched events
    Average callback latency
    Current health

States:

    healthy
    degraded
    unavailable
    unknown

* * *

# 55\. Why provider health matters

Imagine:

    100,000 emails sent
    0 delivery events for 4 hours

That is not necessarily:

    100% delivery failure

It may mean:

    provider callback integration broken

Operational dashboards must distinguish those cases.

* * *

# 56\. Event backlog monitoring

Scheduled action:

    Newsletter Provider Event Monitor

Checks:

    provider events in received/retry_pending
    older than threshold

Example:

    Event Backlog Warning:
    > 100 events older than 10 minutes

Raise alert.

* * *

# 57\. Unmatched event monitoring

If:

    provider_message_id

cannot correlate to a campaign recipient:

    provider_event.state = unmatched

Do not discard.

Dashboard:

    Unmatched Provider Events: 7

Compliance/operations can investigate.

* * *

# 58\. Event retry processing

Provider-event processing should itself have retry behavior:

    received
      ↓
    processing
      ↓
    failure
      ↓
    retry_pending

Example:

    Attempt 1 → +1 min
    Attempt 2 → +5 min
    Attempt 3 → +15 min
    Attempt 4 → +1 hr

Different from email send retries.

* * *

# 59\. Raw payload retention

Store provider raw event payload for audit/troubleshooting, but:

*   restrict access;
    
*   avoid displaying it to ordinary marketing users;
    
*   apply retention;
    
*   hash it;
    
*   avoid unnecessary duplicate PII.
    

Add field-level/group restrictions where possible.

* * *

# 60\. Logging sensitive information

Do not log:

    full email body
    consent evidence
    raw webhook with all PII

in normal application logs.

Structured logs should use:

    campaign_run_id
    event ID
    provider_message_id
    recipient internal ID
    hashed or masked email

where practical.

* * *

# 61\. R5 dashboards

Create three dashboards.

## Campaign Operations

    In Progress
    Suspended
    Completed Today
    Retry Pending
    Provider Failures

## Deliverability

    Delivery Rate
    Bounce Rate
    Hard Bounce Rate
    Complaint Rate
    Unsubscribe Rate
    Top Problem Campaigns

## Compliance

    Active Suppressions
    New Hard Bounces
    New Complaints
    Unsubscribes
    Soft-Bounce Threshold Suppressions
    Open Alerts

* * *

# 62\. Example campaign dashboard

    Healthcare Monthly Newsletter
    CMP-2026-000128
    RUN-2026-000414
    
    STATUS: COMPLETED
    
    Targeted                  25,000
    Eligible                  21,620
    Sent                      21,580
    
    Delivered                 21,220
    Delayed                       90
    
    Soft Bounce                  190
    Hard Bounce                   70
    Complaint                      3
    Unsubscribed                  42
    
    Delivery Rate              98.3%
    Bounce Rate                 1.20%
    Complaint Rate              0.01%
    
    Reputation Status:
    ✓ HEALTHY

* * *

# 63\. Recipient reputation screen

On Contact:

    Newsletter Deliverability
    
    Current State:
    GOOD
    
    Soft Bounces:
    1
    
    Hard Bounces:
    0
    
    Complaints:
    0
    
    Last Delivered:
    27-Aug-2026
    
    Active Suppression:
    None

For a problem recipient:

    Current State:
    SUPPRESSED
    
    Reason:
    Repeated Soft Bounce
    
    Count:
    3
    
    Suppression:
    SUP-2026-001232

* * *

# 64\. Contact timeline after R5

A single recipient can now show:

    15-Jan-2026
    Consent Granted
    Healthcare Updates
    
    28-Aug-2026 15:38
    Campaign Preflight
    Eligible
    
    28-Aug-2026 15:42
    Message Accepted
    MSG-889301
    
    28-Aug-2026 15:43
    Delivered
    
    02-Sep-2026
    Campaign Accepted
    
    02-Sep-2026
    Soft Bounce
    Mailbox Full
    Count = 1
    
    02-Oct-2026
    Soft Bounce
    Count = 2
    
    02-Nov-2026
    Soft Bounce
    Count = 3
    
    02-Nov-2026
    Global Suppression Created
    Repeated Soft Bounce

That is a very strong FR-27 audit trail.

* * *

# 65\. Provider adapter contract

Base:

    class NewsletterProviderAdapter:
    
        provider_code = None
    
        def validate_webhook(self, request):
            raise NotImplementedError
    
        def normalize_event(self, payload):
            raise NotImplementedError
    
        def classify_bounce(self, event):
            raise NotImplementedError
    
        def extract_message_id(self, event):
            raise NotImplementedError
    
        def extract_event_id(self, event):
            raise NotImplementedError

This keeps the platform extensible.

* * *

# 66\. SMTP-only deployments

If using only generic SMTP and no provider webhook API, you can still use:

    Odoo bounce alias / inbound mail

as one source of delivery failures.

Odoo documents its bounce alias as the return-path for failed messages, with errors surfaced back into the application. ([Odoo](https://www.odoo.com/documentation/19.0/applications/general/email_communication/email_servers_inbound.html?msockid=170e05a3d0ec68d110571356d1b86952&utm_source=chatgpt.com "Manage inbound messages — Odoo 19.0 documentation"))

However, generic SMTP typically gives less complete outcome telemetry than providers offering explicit delivery-event webhooks.

Therefore support two modes:

    Mode A:
    SMTP + Odoo Bounce Processing
    
    Mode B:
    Provider Event API/Webhook

Mode B is preferred for full R5 capability.

* * *

# 67\. Event source priority

If both native Odoo and provider events exist:

    Provider-specific event

should generally be the richer source for delivery/bounce classification.

But use idempotency/correlation so that:

    Odoo bounce
    +
    Provider bounce

does not create two suppressions for the same incident.

* * *

# 68\. Delivery-event processing pseudocode

    def process_provider_event(self):
    
        self.ensure_one()
    
        if self.processing_state == "processed":
            return
    
        adapter = provider_registry.get(
            self.provider
        )
    
        event = adapter.normalize_event(
            self.raw_payload
        )
    
        eligibility = (
            self._find_correlated_recipient(
                event.provider_message_id
            )
        )
    
        if not eligibility:
            self.processing_state = "unmatched"
            return
    
        send_event = self._create_canonical_send_event(
            eligibility,
            event,
        )
    
        self._apply_delivery_state(
            eligibility,
            event,
        )
    
        self._apply_reputation_rules(
            eligibility,
            event,
            send_event,
        )
    
        self._update_campaign_outcome(
            eligibility.campaign_run_id
        )
    
        self._evaluate_campaign_alerts(
            eligibility.campaign_run_id
        )
    
        self.write({
            "processing_state": "processed",
            "send_event_id": send_event.id,
        })

* * *

# 69\. Reputation-processing pseudocode

    def process_reputation_event(
        eligibility,
        event,
    ):
    
        reputation = get_or_create_reputation(
            eligibility.email_normalized
        )
    
        if event.type == "delivered":
    
            reputation.last_delivery_at = (
                event.event_timestamp
            )
    
            apply_delivery_recovery_policy(
                reputation
            )
    
        elif event.type == "soft_bounce":
    
            reputation.soft_bounce_count += 1
            reputation.lifetime_soft_bounce_count += 1
    
            if soft_bounce_threshold_reached(
                reputation
            ):
                create_global_suppression(
                    eligibility,
                    reason="SOFT_BOUNCE_LIMIT",
                )
    
        elif event.type == "hard_bounce":
    
            reputation.hard_bounce_count += 1
    
            create_global_suppression(
                eligibility,
                reason="HARD_BOUNCE",
            )
    
        elif event.type == "complaint":
    
            reputation.complaint_count += 1
    
            create_global_suppression(
                eligibility,
                reason="COMPLAINT",
            )

* * *

# 70\. Alert evaluation pseudocode

    def evaluate_alerts(run):
    
        outcome = run.outcome_id
    
        bounce_rate = safe_ratio(
            outcome.soft_bounce_count
            + outcome.hard_bounce_count,
            outcome.sent_count,
        )
    
        complaint_rate = safe_ratio(
            outcome.complaint_count,
            outcome.sent_count,
        )
    
        if bounce_rate >= settings.bounce_warning_rate:
            create_or_update_alert(
                run,
                "bounce_threshold",
                bounce_rate,
            )
    
        if (
            complaint_rate
            >= settings.complaint_warning_rate
        ):
            create_or_update_alert(
                run,
                "complaint_threshold",
                complaint_rate,
            )

* * *

# 71\. Configuration

Add:

    Email Marketing
    → Compliance
    → Configuration
    → Delivery & Reputation

Settings:

| Setting | Example |
| --- | --- |
| Provider | SMTP |
| Soft Bounce Threshold | 3 |
| Soft Bounce Window | 90 days |
| Bounce Warning Rate | Configurable |
| Bounce Critical Rate | Configurable |
| Complaint Warning Rate | Configurable |
| Complaint Critical Rate | Configurable |
| Unsubscribe Warning Rate | Configurable |
| Auto-suppress hard bounce | Yes |
| Auto-suppress complaint | Yes |
| Sync global suppression to Odoo blacklist | Yes |
| Auto-suspend on critical complaint rate | Yes |
| Outcome finalization window | 72 hours |
| Provider event retention | policy-driven |
| Event-processing retry limit | 5 |

* * *

# 72\. New R5 menu structure

    Email Marketing
    └── Compliance
        │
        ├── Campaign Governance
        ├── Execution
        │
        ├── Deliverability
        │   ├── Campaign Outcomes
        │   ├── Delivery Events
        │   ├── Soft Bounces
        │   ├── Hard Bounces
        │   ├── Complaints
        │   ├── Recipient Reputation
        │   └── Provider Health
        │
        ├── Suppression
        │   ├── Active Suppressions
        │   ├── Hard Bounce Suppressions
        │   ├── Complaint Suppressions
        │   ├── Unsubscribes
        │   └── Reinstatements
        │
        ├── Monitoring
        │   ├── Active Alerts
        │   ├── Provider Event Backlog
        │   └── Unmatched Events
        │
        └── Configuration
            ├── Delivery Provider
            ├── Reputation Policy
            └── Alert Thresholds

* * *

# 73\. R5 security

Add role:

    Newsletter Operations Administrator

if desired.

Access matrix:

| Capability | Author | Reviewer | Operator | Compliance Admin | Auditor |
| --- | --- | --- | --- | --- | --- |
| Campaign outcome | ✅ | ✅ | ✅ | ✅ | ✅ |
| Raw provider events |  | Limited | ✅ | ✅ | ✅ |
| Provider configuration |  |  |  | ✅ |  |
| Suppression creation |  | ✅ | System | ✅ |  |
| Manual suppression |  | ✅ |  | ✅ |  |
| Reinstate hard bounce |  |  |  | Controlled |  |
| Reinstate complaint |  |  |  | Exceptional |  |
| Alert acknowledge |  | ✅ | ✅ | ✅ |  |
| Alert resolve |  | ✅ | ✅ | ✅ |  |
| Modify send events | ❌ | ❌ | ❌ | ❌ | ❌ |

* * *

# 74\. R5 formal business rules

| Rule | Requirement |
| --- | --- |
| R5-BR-01 | Every provider event must be authenticated where supported |
| R5-BR-02 | Duplicate provider events must be idempotent |
| R5-BR-03 | Provider event must correlate to a known dispatched recipient before compliance action |
| R5-BR-04 | Hard bounce creates global suppression |
| R5-BR-05 | Complaint creates global suppression |
| R5-BR-06 | Soft bounce does not immediately suppress unless threshold reached |
| R5-BR-07 | Soft-bounce threshold is configurable |
| R5-BR-08 | Global compliance suppression synchronizes with Odoo blacklist |
| R5-BR-09 | Purpose suppression must not create global Odoo blacklist |
| R5-BR-10 | Unsubscribe is reflected in suppression near-real-time |
| R5-BR-11 | Explicit purpose unsubscribe withdraws/restricts applicable communication purpose |
| R5-BR-12 | Global opt-out blocks all marketing communication |
| R5-BR-13 | Delivery events remain append-only |
| R5-BR-14 | Campaign outcome is derived from recipient events |
| R5-BR-15 | Threshold breaches create one active alert per campaign/type |
| R5-BR-16 | Critical threshold may suspend campaign when configured |
| R5-BR-17 | Suspended campaign sends no new recipients |
| R5-BR-18 | Provider processing failures never discard raw events |
| R5-BR-19 | Unmatched provider events are retained for investigation |
| R5-BR-20 | Finalized outcome remains immutable; late events become adjustments |

* * *

# 75\. R5 acceptance tests

Before declaring R5 complete, I would require these.

### Provider ingestion

1.  Valid signed provider event accepted.
    
2.  Invalid signature rejected.
    
3.  Malformed payload rejected safely.
    
4.  Raw event stored.
    
5.  Duplicate event detected.
    
6.  Duplicate does not create duplicate business event.
    
7.  Event correlates by provider message ID.
    
8.  Unmatched event retained.
    

### Delivery

9.  Delivered event updates recipient.
    
10.  Delivered send event created.
    
11.  Campaign delivered count increments correctly.
    
12.  Duplicate delivered event does not double count.
    

### Hard bounce

13.  Hard bounce classified.
    
14.  Recipient marked hard bounce.
    
15.  Global suppression created.
    
16.  Native Odoo blacklist synchronized.
    
17.  Preflight excludes recipient in future campaign.
    
18.  Dispatch recheck excludes recipient immediately.
    

### Complaint

19.  Complaint event processed.
    
20.  Global complaint suppression created.
    
21.  Native blacklist synchronized.
    
22.  Compliance event retained.
    
23.  Complaint rate updates.
    
24.  Complaint alert raised if threshold exceeded.
    

### Soft bounce

25.  First soft bounce increments counter.
    
26.  Threshold not reached → no suppression.
    
27.  Subsequent soft bounces counted.
    
28.  Threshold reached → suppression.
    
29.  Window policy applied correctly.
    
30.  Delivery recovery/reset policy applied correctly.
    

### Unsubscribe

31.  Mailing-list unsubscribe processed.
    
32.  List-specific opt-out doesn't cause global blacklist.
    
33.  Purpose unsubscribe creates purpose suppression.
    
34.  Purpose consent withdrawal logged where applicable.
    
35.  Global opt-out creates global suppression.
    
36.  Global opt-out synchronizes to native blacklist.
    
37.  Subsequent dispatch blocked immediately.
    

### Outcome

38.  Delivered/bounce/complaint counts reconcile.
    
39.  Outcome rates calculate correctly.
    
40.  Finalization occurs after configured window.
    
41.  Outcome hash generated.
    
42.  Late event creates adjustment rather than rewriting finalized evidence.
    

### Alerts

43.  Bounce threshold generates alert.
    
44.  Complaint threshold generates alert.
    
45.  Duplicate alert not created repeatedly.
    
46.  Alert can be acknowledged.
    
47.  Alert resolution retains history.
    
48.  Auto-suspend works when configured.
    
49.  Resume requires authorization/reason.
    

### Operations

50.  Provider event backlog raises alert.
    
51.  Unmatched-event threshold raises alert.
    
52.  Failed processor retries.
    
53.  Failed event remains available after max retries.
    
54.  Raw payload access is restricted.
    
55.  Audit Reviewer can reconstruct provider → event → suppression → campaign history.
    

* * *

# 76\. Requirement traceability

| Original requirement | R5 implementation |
| --- | --- |
| FR-18 delivery/bounce/complaint ingestion | Provider Event API |
| FR-19 hard bounce/complaint suppression | Reputation + Suppression Engine |
| FR-20 unsubscribe suppression | Odoo unsubscribe + compliance sync |
| FR-21 soft-bounce escalation | Reputation counter |
| FR-22 completion statistics | Campaign Outcome |
| FR-24 archive statistics | Outcome linked to archive |
| FR-26 reporting | Deliverability dashboard |
| FR-27 recipient reconstruction | Provider + Send Event history |
| FR-28 threshold alerts | Compliance Alert Engine |
| NFR-02 unsubscribe SLA | Near-real-time processing |
| NFR-03 partial failure | Per-event processing |
| NFR-09 auditability | Canonical append-only events |
| RC-09 withdrawal | Consent/suppression linkage |
| RC-13 unsubscribe | Native/custom unsubscribe workflow |

* * *

# 77\. End state after R5

At this point the complete lifecycle looks like:

    R1
    CONSENT + SUPPRESSION
            │
            ▼
    R2
    CAMPAIGN GOVERNANCE
            │
            ▼
    R3
    ELIGIBILITY / PREFLIGHT
            │
            ▼
    R4
    SAFE EXECUTION
            │
            ▼
    EMAIL PROVIDER
            │
            ▼
    R5
    DELIVERY FEEDBACK
            │
            ├── Delivered
            ├── Soft Bounce
            ├── Hard Bounce
            ├── Complaint
            └── Unsubscribe
            │
            ▼
    REPUTATION + SUPPRESSION
            │
            ▼
    FUTURE PREFLIGHT / DISPATCH

So the feedback loop is genuinely closed:

    SEND
      ↓
    OUTCOME
      ↓
    LEARN
      ↓
    SUPPRESS / UPDATE CONSENT
      ↓
    PROTECT NEXT SEND

## R1–R5 capability picture

| Area | Status |
| --- | --- |
| Consent evidence | ✅ R1 |
| Suppression foundation | ✅ R1 |
| Campaign approval/governance | ✅ R2 |
| Recipient eligibility | ✅ R3 |
| Send blocking | ✅ R3 |
| Frozen recipient population | ✅ R3 |
| Safe resumable execution | ✅ R4 |
| Recipient event ledger | ✅ R4 |
| Immutable as-sent archive | ✅ R4 |
| Delivery feedback | ✅ R5 |
| Hard/soft bounce management | ✅ R5 |
| Complaint suppression | ✅ R5 |
| Unsubscribe synchronization | ✅ R5 |
| Operational alerts | ✅ R5 |
| Provider-independent architecture | ✅ R5 |
| Retention/erasure/legal hold | Next: R6 |

The next logical increment should therefore be **R6 — Privacy Lifecycle, Data Retention, Erasure/Pseudonymization, Legal Hold, Evidence Export & Compliance Reporting**. That would complete the regulatory lifecycle around the data R1–R5 now generate rather than adding more campaign functionality.