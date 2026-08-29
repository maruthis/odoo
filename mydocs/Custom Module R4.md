Absolutely. R4 should be **Campaign Execution, Send Event Ledger & Immutable Archive**.

This is the release where the system stops being only a compliance gate and becomes a reliable execution/audit platform.

The original requirements explicitly call for partial-failure isolation, resumability without resending successful recipients, campaign-level counts, recipient-level traceability, and a durable read-only “as-sent” record.

Odoo 19 already tracks native mailing progress and exposes counts for scheduled, processing, sent, failed, delivered, bounced, opened, etc. We should reuse those where helpful, but build our own compliance execution ledger because we need immutable recipient/run-level evidence and retry state beyond the normal campaign statistics. ([GitHub](https://github.com/odoo/odoo/blob/19.0/addons/mass_mailing/views/mailing_mailing_views.xml?utm_source=chatgpt.com "odoo/addons/mass_mailing/views/mailing_mailing_views.xml at 19.0 · odoo/odoo · GitHub"))

# R4 — Campaign Execution, Event Ledger & Immutable Archive

## 1\. R4 scope

| Capability | R4 |
| --- | --- |
| Execute only frozen eligible population | ✅ |
| Recipient-level dispatch state | ✅ |
| Batch dispatch control | ✅ |
| Retry-safe processing | ✅ |
| No duplicate resend | ✅ |
| Partial failure isolation | ✅ |
| Campaign execution progress | ✅ |
| Send Event Ledger | ✅ |
| Recipient communication history | ✅ |
| Campaign reconciliation | ✅ |
| Completion determination | ✅ |
| Exact as-sent content snapshot | ✅ |
| Immutable campaign archive | ✅ |
| Archive hashing | ✅ |
| Approval/preflight evidence linkage | ✅ |
| Audit package foundation | ✅ |
| Provider delivery/bounce callbacks | R5 |
| Complaint processing | R5 |
| Throttling sophistication | R5 |
| Real-time operational alerting | R5 |

* * *

# 2\. R4 architecture

After R3:

    APPROVED CAMPAIGN
           │
           ▼
    PREFLIGHT PASSED
           │
           ▼
    FROZEN ELIGIBLE POPULATION
           │
           ▼
    R4 CAMPAIGN EXECUTION
           │
           ├── Prepare recipient
           ├── Dispatch-time eligibility recheck
           ├── Queue
           ├── Send
           ├── Record result
           ├── Retry individual failures
           └── Never resend successful recipient
           │
           ▼
    SEND EVENT LEDGER
           │
           ▼
    CAMPAIGN RECONCILIATION
           │
           ▼
    COMPLETED
           │
           ▼
    IMMUTABLE AS-SENT ARCHIVE

The central principle is:

> **Campaign execution is recipient-oriented, not batch-oriented.**

A problem sending to recipient 417 must not affect recipients 418–25,000.

* * *

# 3\. Extend the Campaign Run model

R3 already created:

    newsletter.campaign.run

R4 now makes it the authoritative execution object.

Add:

    execution_started_at
    execution_completed_at
    execution_started_by_id
    
    queued_count
    processing_count
    sent_count
    failed_count
    blocked_at_dispatch_count
    retry_pending_count
    cancelled_count
    
    delivered_count
    bounced_count
    complained_count
    unsubscribed_count
    
    next_retry_at
    
    execution_batch_size
    maximum_retry_count
    
    archive_id
    completion_status
    
    last_reconciled_at

The delivery/bounce/complaint fields can initially be zero or synchronized from Odoo/native traces; R5 will make provider events authoritative.

* * *

# 4\. Campaign Run states

Expand the R3 state model:

    state = fields.Selection([
        ("draft", "Draft"),
        ("evaluating", "Evaluating"),
        ("passed", "Preflight Passed"),
        ("failed", "Preflight Failed"),
        ("invalidated", "Invalidated"),
        ("queued", "Queued"),
        ("sending", "Sending"),
        ("partially_completed", "Partially Completed"),
        ("completed", "Completed"),
        ("completed_with_errors", "Completed With Errors"),
        ("cancelled", "Cancelled"),
        ("archived", "Archived"),
    ])

Lifecycle:

    PASSED
       │
       ▼
    QUEUED
       │
       ▼
    SENDING
       │
       ├─────────────┐
       │             │
       ▼             ▼
    COMPLETED   COMPLETED WITH ERRORS
       │             │
       └──────┬──────┘
              ▼
           ARCHIVED

* * *

# 5\. Extend Recipient Eligibility into dispatch record

R3's:

    newsletter.recipient.eligibility

already contains the frozen eligible population.

Do **not** create another redundant recipient table unless necessary.

Extend it with execution state:

    dispatch_state = fields.Selection([
        ("not_queued", "Not Queued"),
        ("queued", "Queued"),
        ("processing", "Processing"),
        ("sent", "Sent"),
        ("retry_pending", "Retry Pending"),
        ("failed", "Failed"),
        ("blocked", "Blocked at Dispatch"),
        ("cancelled", "Cancelled"),
    ], default="not_queued")

Add:

    dispatch_attempt_count
    first_queued_at
    last_queued_at
    first_sent_at
    last_attempt_at
    next_retry_at
    
    provider_message_id
    last_error_code
    last_error_message
    
    dispatch_lock_token
    dispatch_locked_at

Only:

    status = eligible

records are eligible for dispatch.

* * *

# 6\. Strong no-resend invariant

The most important execution rule:

    dispatch_state = sent

means that record can **never automatically return to queued**.

This directly supports the original NFR requiring resumability without resending recipients already successfully dispatched.

Formal invariant:

    SENT is terminal for dispatch.

Later:

    Delivered
    Bounced
    Complaint

are delivery outcomes, but the dispatch itself remains:

    sent

because the provider accepted the message.

* * *

# 7\. Separate dispatch state from delivery state

This distinction is critical.

Use:

    dispatch_state

for your system's sending activity.

Use:

    delivery_state

for downstream provider outcome.

Example:

    dispatch_state = sent
    delivery_state = delivered

or:

    dispatch_state = sent
    delivery_state = hard_bounce

Add:

    delivery_state = fields.Selection([
        ("unknown", "Unknown"),
        ("accepted", "Accepted"),
        ("delivered", "Delivered"),
        ("delayed", "Delayed"),
        ("soft_bounce", "Soft Bounce"),
        ("hard_bounce", "Hard Bounce"),
        ("complaint", "Complaint"),
    ], default="unknown")

R5 updates this from provider feedback.

* * *

# 8\. Send Event Ledger

Create:

    newsletter.send.event

This becomes one of the most important audit models.

Each event is append-only.

Examples:

    RECIPIENT_TARGETED
    ELIGIBILITY_PASSED
    ELIGIBILITY_EXCLUDED
    QUEUED
    DISPATCH_STARTED
    DISPATCH_RECHECK_PASSED
    DISPATCH_RECHECK_BLOCKED
    SEND_ATTEMPTED
    SEND_ACCEPTED
    SEND_FAILED
    RETRY_SCHEDULED
    RETRY_STARTED
    DELIVERED
    DELAYED
    SOFT_BOUNCE
    HARD_BOUNCE
    COMPLAINT
    UNSUBSCRIBED
    SUPPRESSION_CREATED
    CAMPAIGN_COMPLETED

* * *

# 9\. Send Event model

Recommended fields:

| Field | Purpose |
| --- | --- |
| reference | Event ID |
| campaign_run_id | Run |
| mailing_id | Campaign |
| eligibility_id | Recipient decision |
| partner_id | Partner |
| mailing_contact_id | Mailing contact |
| email_normalized | Email |
| event_type | Event |
| event_timestamp | Business timestamp |
| processing_timestamp | System timestamp |
| attempt_number | Attempt |
| provider_message_id | Provider reference |
| provider_event_id | Provider event |
| correlation_id | Correlation |
| error_code | Error |
| error_message | Error |
| source | Odoo / Provider / User |
| raw_payload | Provider/event detail |
| payload_hash | Integrity |
| previous_event_hash | Optional chain |
| event_hash | Integrity hash |
| company_id | Company |

* * *

# 10\. Event reference

Example:

    EVT-2026-000000001

Sequence:

    <record id="seq_newsletter_send_event" model="ir.sequence">
        <field name="name">Newsletter Send Event</field>
        <field name="code">newsletter.send.event</field>
        <field name="prefix">EVT-%(year)s-</field>
        <field name="padding">9</field>
    </record>

Use a larger padding because recipient events grow quickly.

* * *

# 11\. Event immutability

Send events should be append-only.

Override:

    def write(self, vals):
        raise UserError(
            _("Send events are immutable and cannot be modified.")
        )
    
    def unlink(self):
        raise UserError(
            _("Send events cannot be deleted.")
        )

If a correction is required, create another event:

    EVENT_CORRECTION

rather than modify history.

* * *

# 12\. Event hashing

Canonical event payload:

    payload = {
        "reference": event.reference,
        "campaign_run": event.campaign_run_id.reference,
        "email": event.email_normalized,
        "event_type": event.event_type,
        "event_timestamp": event.event_timestamp.isoformat(),
        "attempt": event.attempt_number,
        "provider_message_id": event.provider_message_id or "",
        "previous_event_hash": event.previous_event_hash or "",
    }

Hash:

    sha256(
        json.dumps(payload, sort_keys=True).encode()
    ).hexdigest()

Optional chaining:

    Event 1 hash
        ↓
    Event 2.previous_event_hash
        ↓
    Event 2 hash

This doesn't make PostgreSQL a WORM appliance, but it materially improves integrity verification.

* * *

# 13\. Campaign-level event chain

Do **not** create one giant global hash chain across every campaign.

Prefer:

    Campaign Run
        │
        ├── recipient/event chain
        └── campaign-level chain

This keeps integrity verification localized and operationally manageable.

* * *

# 14\. Execution start

The operator sees:

    [Send]

only when:

    compliance_state = ready
    current run.state = passed
    current run.frozen = True

When Send is invoked:

    Run.state = queued
    Run.execution_started_at = now
    Campaign.compliance_state = sending

Then queue the frozen eligible recipients.

* * *

# 15\. Do not send synchronously in the UI request

Do not do:

    for 25_000 recipients:
        send()

inside one browser request.

Instead:

    User clicks Send
          │
          ▼
    Campaign Run → QUEUED
          │
          ▼
    Scheduled worker / cron
          │
          ▼
    Process batch
          │
          ▼
    Next batch

This makes execution resumable and less fragile.

* * *

# 16\. Community Edition queue strategy

You do not need Celery/Kafka/RabbitMQ just to meet this use case.

For R4 Community Edition, use:

    Odoo ir.cron
    +
    recipient dispatch states
    +
    database row locking

This gives a reasonable first implementation.

Later, for very high volume, you can plug in a dedicated queue service without changing the domain model.

* * *

# 17\. Scheduled action

Create:

    Newsletter Campaign Dispatch Worker

For example:

    <record id="ir_cron_newsletter_dispatch_worker" model="ir.cron">
        <field name="name">Newsletter Campaign Dispatch Worker</field>
        <field name="model_id"
               ref="model_newsletter_campaign_run"/>
        <field name="state">code</field>
        <field name="code">
            model._cron_process_campaign_dispatch()
        </field>
        <field name="interval_number">1</field>
        <field name="interval_type">minutes</field>
        <field name="active">True</field>
    </record>

* * *

# 18\. Worker selection

Worker should select:

    Campaign Run state in:
    queued
    sending
    partially_completed

then fetch:

    status = eligible
    AND dispatch_state in:
    not_queued
    queued
    retry_pending

subject to:

    next_retry_at <= now

* * *

# 19\. Batch size

Configuration:

    Dispatch Batch Size = 500

Start conservatively.

Example:

    21,620 eligible
    
    Batch 1: 500
    Batch 2: 500
    ...

The batch size is not the SMTP-provider send rate. R5 will introduce explicit provider throttling.

* * *

# 20\. Concurrency locking

You must prevent two workers from picking the same recipient simultaneously.

Conceptually use PostgreSQL row-level selection such as:

    FOR UPDATE SKIP LOCKED

or equivalent safe Odoo/database locking.

This is one area where custom SQL may be justified because execution correctness matters more than ORM purity.

The goal:

    Worker A gets recipients 1–500
    Worker B skips those locks and gets 501–1000

Never:

    Worker A sends John
    Worker B also sends John

* * *

# 21\. Recipient execution lifecycle

    NOT QUEUED
        │
        ▼
    QUEUED
        │
        ▼
    PROCESSING
        │
        ├───────────────┐
        │               │
        ▼               ▼
    SENT          RETRY PENDING
                        │
                        ▼
                     PROCESSING
                        │
                  ┌─────┴─────┐
                  ▼           ▼
                 SENT        FAILED

At any time before provider submission:

    dispatch-time compliance recheck

can lead to:

    BLOCKED

* * *

# 22\. Dispatch-time eligibility recheck

Before every send attempt check only volatile conditions:

    Active consent still valid?
    Global blacklist?
    Active global suppression?
    Active purpose suppression?
    Mailing-list opt-out?

Do not rerun segmentation.

If John withdrew consent after preflight:

    Preflight:
    Eligible
    
    Dispatch:
    BLOCKED
    
    Reason:
    Consent withdrawn after preflight

Create events:

    DISPATCH_RECHECK_BLOCKED
    SUPPRESSION/CONSENT REFERENCE

* * *

# 23\. Dispatch-time block is not failure

Do not classify:

    recipient withdrawn after preflight

as:

    FAILED

It should be:

    BLOCKED

because the system behaved correctly.

Campaign summary should therefore distinguish:

    Eligible at preflight
    Sent
    Blocked at dispatch
    Failed technically

* * *

# 24\. Send-event flow

For one recipient:

    ELIGIBILITY_PASSED
            │
            ▼
    QUEUED
            │
            ▼
    DISPATCH_RECHECK_PASSED
            │
            ▼
    SEND_ATTEMPTED
            │
            ├──────────────┐
            │              │
            ▼              ▼
    SEND_ACCEPTED      SEND_FAILED
                           │
                      retryable?
                       │      │
                      YES     NO
                       │      │
                       ▼      ▼
               RETRY_SCHEDULED FAILED

* * *

# 25\. Retry classification

Create a helper:

    newsletter.dispatch.error.classifier

or plain Python service.

Categories:

    retryable
    non_retryable
    compliance_block

Examples:

### Retryable

    SMTP temporary error
    Connection timeout
    Provider temporarily unavailable
    Rate/throttle error

### Non-retryable

    Malformed recipient
    Permanent provider rejection
    Invalid configuration

### Compliance block

    Consent withdrawn
    Suppression activated
    Global blacklist

* * *

# 26\. Retry configuration

Settings:

    Maximum Retry Count = 5
    Base Retry Delay = 60 seconds
    Maximum Retry Delay = 3600 seconds

Backoff:

    attempt 1 → 60 seconds
    attempt 2 → 120 seconds
    attempt 3 → 240 seconds
    attempt 4 → 480 seconds
    attempt 5 → 960 seconds

Formula:

    delay = min(
        base_delay * (2 ** (attempt - 1)),
        maximum_delay
    )

This aligns with the original requirement for exponential backoff and configurable retry limits.

* * *

# 27\. Exactly-once vs at-least-once

Email delivery cannot generally guarantee true global exactly-once behavior.

Your application should aim for:

> **at-most-once application submission per recipient after a confirmed provider acceptance**

Before retrying, always check:

    dispatch_state != sent

If a provider timeout occurs after submission but before response, you may not know if the message was accepted.

Record:

    delivery uncertainty

rather than blindly retrying in some providers.

R5 can improve this with provider message IDs/idempotency where supported.

* * *

# 28\. Odoo native mailing integration

Odoo already exposes native mailing statistics and trace-oriented views such as scheduled, processing, sent, failed and delivered ratios. ([GitHub](https://github.com/odoo/odoo/blob/19.0/addons/mass_mailing/views/mailing_mailing_views.xml?utm_source=chatgpt.com "odoo/addons/mass_mailing/views/mailing_mailing_views.xml at 19.0 · odoo/odoo · GitHub"))

Therefore I recommend:

    Odoo native mailing = presentation/delivery mechanism
    Newsletter Compliance = audit/execution authority

Do not delete or fight Odoo's standard records.

Where possible:

    native result
          ↓
    translate/synchronize
          ↓
    newsletter.send.event

But do not make your compliance history dependent solely on native trace retention.

* * *

# 29\. Provider abstraction

Create:

    services/mail_dispatch_service.py

Interface conceptually:

    class MailDispatchService:
    
        def send_recipient(
            self,
            campaign,
            run,
            eligibility,
        ):
            """
            Returns:
            {
                "accepted": True/False,
                "provider_message_id": "...",
                "error_code": None,
                "error_message": None,
                "retryable": False,
            }
            """

Initially the implementation can call Odoo's normal outbound email infrastructure.

Later:

    Odoo SMTP
    AWS SES
    SendGrid
    Mailgun

can implement the same contract.

* * *

# 30\. Correlation ID

Every recipient dispatch should have:

    correlation_id

Example:

    CMP-2026-000128
    RUN-2026-000414
    recipient 21871
    
    Correlation:
    CMP-2026-000128:RUN-2026-000414:21871

Carry it through:

    eligibility
    send event
    provider metadata
    logs
    archive

This makes troubleshooting much easier.

* * *

# 31\. Campaign completion

A run is not completed just because there are no `not_queued` recipients.

Completion condition:

    every eligible recipient is one of:
    
    sent
    failed
    blocked
    cancelled

No recipient may remain:

    queued
    processing
    retry_pending

Then reconcile.

* * *

# 32\. Reconciliation

Require:

    Eligible at preflight
    =
    Sent
    + Failed
    + Blocked at dispatch
    + Cancelled

Example:

    Eligible              21,620
    Sent                  21,580
    Blocked                   25
    Failed                    15
    --------------------------------
    Total                  21,620

If not equal:

    Run cannot be completed.

* * *

# 33\. Campaign completion classifications

Use:

### Completed

    failed_count = 0

although blocked recipients may exist legitimately.

### Completed with Errors

    failed_count > 0
    AND no retry_pending

### Partially Completed

    some terminal
    some retry_pending/processing

* * *

# 34\. Campaign completion event

Create event:

    CAMPAIGN_COMPLETED

containing:

    Targeted
    Eligible
    Excluded
    Sent
    Blocked at Dispatch
    Failed
    Retries
    Start Time
    Completion Time

This event forms part of the archive evidence.

* * *

# 35\. Immutable Campaign Archive

Create:

    newsletter.campaign.archive

This replaces the original SharePoint archive functionally.

The source requires retention of the exact newsletter as sent, along with campaign ID, send date/time, recipient/delivery/bounce/complaint counts and a read-only/archive characteristic.

* * *

# 36\. Archive identity fields

    reference
    mailing_id
    campaign_run_id
    campaign_compliance_id
    governance_version
    approval_version
    archive_version
    
    brand_id
    consent_purpose_id
    
    created_at
    created_by_id
    
    locked
    locked_at
    archive_hash

* * *

# 37\. Content snapshot

Capture:

    campaign_name
    subject
    preview_text
    email_from
    reply_to
    
    body_html
    body_text
    
    physical_address
    unsubscribe_configuration
    
    attachments_manifest

Do not rely on:

    mailing_id.body_html

after archive creation.

Copy the value into the archive.

* * *

# 38\. Attachment snapshot

Do not merely store:

    attachment_ids = mailing.attachment_ids

because the underlying attachment might later change or disappear.

For each attachment capture:

    filename
    mimetype
    size
    SHA-256

and ideally make an archival copy.

Create:

    newsletter.campaign.archive.attachment

or copy into protected `ir.attachment` records linked to the archive.

* * *

# 39\. Recipient-definition snapshot

Store:

    mailing_model
    mailing_domain
    selected mailing lists
    segment description
    
    targeted count
    eligible count
    excluded count

This lets an auditor understand what audience was intended.

* * *

# 40\. Approval snapshot

Store:

    Campaign Owner
    Content Approver
    Content Approval Time
    Compliance Approver
    Compliance Approval Time
    Approval Version
    Approval Hash
    Preflight Run
    Preflight Result Hash
    Ruleset Version

This connects R2/R3 evidence to the actual send.

* * *

# 41\. Execution snapshot

Store:

    run reference
    started at
    completed at
    started by
    
    eligible
    sent
    blocked
    failed
    retry count

Later R5 updates:

    delivered
    soft bounced
    hard bounced
    complained
    unsubscribed

* * *

# 42\. Archive before or after delivery events?

Create the archive in two stages.

### Stage 1 — Send Archive

Immediately after dispatch completes:

    Dispatch Archive

contains:

    exact content
    audience
    approvals
    preflight
    send results

### Stage 2 — Outcome Finalization

As downstream delivery/bounce/complaint events arrive:

    final campaign statistics

need to be associated with the run.

Do **not** modify the original content snapshot.

You can either:

1.  add outcome fields to archive that are updateable until a finalization deadline, or
    
2.  create a second `Campaign Outcome Summary`.
    

I prefer **option 2** for stronger immutability.

* * *

# 43\. Two-record archive model

Recommended:

    newsletter.campaign.archive

Immutable immediately.

And:

    newsletter.campaign.outcome

tracks provider outcomes.

Then:

    Archive
     ├── exact as-sent content
     ├── approvals
     ├── audience
     └── dispatch facts
    
    Outcome
     ├── delivered
     ├── bounce
     ├── complaint
     └── unsubscribe

Later, when the outcome observation window closes:

    Outcome → finalized/locked

This is cleaner than modifying the archive repeatedly.

* * *

# 44\. Archive hash

Canonical archive hash should include:

    Campaign ID
    Run ID
    Subject
    From
    Reply-To
    HTML hash
    Attachment hashes
    Consent Purpose
    Governance Version
    Approval Hash
    Preflight Hash
    Target Count
    Eligible Count
    Sent Count
    Completion Timestamp

Then:

    archive_hash = SHA256(canonical_payload)

* * *

# 45\. Archive locking

After creation:

    locked = True

Override:

    def write(self, vals):
        if self.filtered("locked"):
            raise UserError(
                _("Archived campaign evidence cannot be modified.")
            )
        return super().write(vals)
    
    def unlink(self):
        raise UserError(
            _("Campaign archives cannot be deleted.")
        )

No ordinary user, including Compliance Administrator, should casually unlock it.

* * *

# 46\. Technical administrator caveat

An Odoo database superuser or PostgreSQL administrator can ultimately alter database data.

Therefore describe the control accurately as:

> **Application-level immutable archive with hash-based integrity verification.**

Do not describe ordinary PostgreSQL/Odoo records as cryptographically or physically WORM unless you actually introduce external immutable storage.

If stronger retention is needed later, export archive packages to:

    S3 Object Lock
    WORM storage
    immutable backup repository

without changing the Odoo business design.

* * *

# 47\. Recipient communication history

Extend `res.partner` smart buttons:

    [Consents]
    [Suppressions]
    [Campaign Decisions]
    [Send History]

Send History should combine:

    campaign
    purpose
    decision
    send date
    dispatch outcome
    delivery outcome
    consent record used
    suppression if any

* * *

# 48\. Recipient audit screen

Example:

    John Smith
    john@example.com
    
    ---------------------------------------------------------
    28-Aug-2026
    Healthcare Monthly Newsletter
    CMP-2026-000128
    RUN-2026-000414
    
    Consent:
    CONS-000532
    Healthcare Updates
    Active
    
    Preflight:
    Eligible
    
    Dispatch:
    Sent
    
    Provider:
    Accepted
    
    Delivery:
    Pending
    ---------------------------------------------------------
    
    01-Jul-2026
    Product Promotions
    
    Preflight:
    Excluded
    
    Reason:
    Purpose Suppression
    
    Suppression:
    SUP-000212
    ---------------------------------------------------------

This directly supports FR-27's requirement to reconstruct a recipient's consent basis and send history.

* * *

# 49\. Recipient history should be derived

Do not create another manually maintained history table.

Generate it from:

    Consent Record
    Suppression Entry
    Recipient Eligibility
    Send Event
    Campaign Run

That prevents divergence.

* * *

# 50\. R4 menu additions

Extend:

    Email Marketing
    └── Compliance
        ├── Campaign Governance
        │
        ├── Execution
        │   ├── Active Runs
        │   ├── Retry Pending
        │   ├── Failed Recipients
        │   ├── Dispatch Blocked
        │   └── Completed Runs
        │
        ├── Audit
        │   ├── Send Events
        │   ├── Campaign Archives
        │   ├── Recipient History
        │   └── Integrity Verification

* * *

# 51\. Campaign execution dashboard

For an in-progress run:

    Healthcare Monthly Newsletter
    RUN-2026-000414
    
    Status: SENDING
    
    Eligible               21,620
    
    Sent                    12,400
    Queued                   8,600
    Processing                 100
    Retry Pending              480
    Failed                      15
    Blocked                     25
    
    Progress                  57.4%

Odoo itself already exposes mailing counts such as scheduled, processing, sent and failed, so the UI pattern is familiar. ([GitHub](https://github.com/odoo/odoo/blob/19.0/addons/mass_mailing/views/mailing_mailing_views.xml?utm_source=chatgpt.com "odoo/addons/mass_mailing/views/mailing_mailing_views.xml at 19.0 · odoo/odoo · GitHub"))

* * *

# 52\. Retry queue

List:

    Recipient
    Campaign Run
    Attempt
    Last Error
    Next Retry

Example:

    alice@example.com
    RUN-2026-000414
    Attempt 2/5
    SMTP 451 temporary failure
    Next retry 15:46

No user should need to manually reconstruct failures.

* * *

# 53\. Manual retry

Allow Campaign Operator:

    Retry Failed

only where:

    failure.retryable = True
    AND attempts < max

Before retry, still perform:

    dispatch-time compliance recheck

A technical retry must never override a new unsubscribe.

* * *

# 54\. Permanent failure

When attempts exceed maximum:

    dispatch_state = failed

Create event:

    SEND_FAILED_FINAL

Then campaign can complete with errors.

Do not keep retrying indefinitely.

* * *

# 55\. Cancellation

If campaign execution is cancelled:

    already sent → remain sent
    not yet sent → cancelled
    processing → finish safely / reconcile

Never try to “undo” already-sent emails.

Create:

    CAMPAIGN_CANCELLED

event with:

    user
    timestamp
    reason
    sent count at cancellation
    pending count

* * *

# 56\. Idempotent event creation

If the same provider/native callback is processed twice, do not create duplicate outcome effects.

Add unique key where applicable:

    source
    provider_event_id

or:

    campaign_run
    provider_message_id
    event_type
    provider_event_timestamp

R5 will depend heavily on this.

* * *

# 57\. Logging

Application logs should carry:

    campaign_id
    run_id
    recipient eligibility ID
    correlation ID
    attempt
    event type

Never rely only on:

    "Error sending email"

Use structured context.

* * *

# 58\. Data-retention design

The source requires send-event and suppression data to follow the organization's retention schedule and remain sufficient for audit trail purposes.

R4 should therefore add:

    retention_policy_id
    retain_until
    legal_hold

to:

    campaign archive
    send events
    campaign run

Actual retention automation can be completed in R5/R6.

* * *

# 59\. Security roles

R4 access:

| Capability | Author | Reviewer | Operator | Admin | Auditor |
| --- | --- | --- | --- | --- | --- |
| View execution status | ✅ | ✅ | ✅ | ✅ | ✅ |
| Start approved send |  |  | ✅ | ✅ |  |
| Cancel execution |  |  | ✅ | ✅ |  |
| Retry retryable recipients |  |  | ✅ | ✅ |  |
| Modify event ledger |  |  |  | ❌ | ❌ |
| View event ledger | Limited | ✅ | ✅ | ✅ | ✅ |
| View archive | ✅ | ✅ | ✅ | ✅ | ✅ |
| Modify archive | ❌ | ❌ | ❌ | ❌ normal UI | ❌ |
| Integrity verification |  | ✅ | ✅ | ✅ | ✅ |

* * *

# 60\. R4 module additions

    newsletter_compliance/
    ├── models/
    │   ├── campaign_run.py
    │   ├── recipient_eligibility.py
    │   ├── send_event.py
    │   ├── campaign_archive.py
    │   ├── campaign_outcome.py
    │   └── res_partner.py
    │
    ├── services/
    │   ├── dispatch_service.py
    │   ├── retry_service.py
    │   ├── reconciliation_service.py
    │   ├── archive_service.py
    │   └── integrity_service.py
    │
    ├── data/
    │   ├── execution_sequences.xml
    │   └── dispatch_cron.xml
    │
    ├── views/
    │   ├── campaign_run_views.xml
    │   ├── send_event_views.xml
    │   ├── campaign_archive_views.xml
    │   ├── campaign_outcome_views.xml
    │   └── recipient_history_views.xml
    │
    └── tests/
        ├── test_dispatch.py
        ├── test_retry.py
        ├── test_resumability.py
        ├── test_reconciliation.py
        ├── test_event_immutability.py
        └── test_archive.py

* * *

# 61\. Suggested dispatch worker pseudocode

    @api.model
    def _cron_process_campaign_dispatch(self):
    
        runs = self.search([
            ("state", "in", [
                "queued",
                "sending",
                "partially_completed",
            ])
        ], limit=10)
    
        for run in runs:
            try:
                run._process_next_dispatch_batch()
            except Exception:
                _logger.exception(
                    "Campaign dispatch failed for run %s",
                    run.reference,
                )

* * *

# 62\. Batch worker pseudocode

    def _process_next_dispatch_batch(self):
        self.ensure_one()
    
        if self.state == "queued":
            self.state = "sending"
    
        recipients = self._lock_next_dispatch_batch()
    
        if not recipients:
            self._reconcile_and_finalize_if_complete()
            return
    
        for eligibility in recipients:
            self._dispatch_recipient(eligibility)
    
        self._recompute_execution_counts()
        self._reconcile_and_finalize_if_complete()

* * *

# 63\. Recipient dispatch pseudocode

    def _dispatch_recipient(self, eligibility):
    
        if eligibility.dispatch_state == "sent":
            return
    
        eligibility.dispatch_state = "processing"
        eligibility.last_attempt_at = fields.Datetime.now()
        eligibility.dispatch_attempt_count += 1
    
        self._create_event(
            eligibility,
            "dispatch_started",
        )
    
        compliance_result = (
            self._dispatch_time_compliance_check(
                eligibility
            )
        )
    
        if not compliance_result.allowed:
    
            eligibility.dispatch_state = "blocked"
    
            self._create_event(
                eligibility,
                "dispatch_recheck_blocked",
                details=compliance_result.reason,
            )
    
            return
    
        result = self._dispatch_service_send(
            eligibility
        )
    
        if result.accepted:
    
            eligibility.write({
                "dispatch_state": "sent",
                "first_sent_at":
                    eligibility.first_sent_at
                    or fields.Datetime.now(),
                "provider_message_id":
                    result.provider_message_id,
            })
    
            self._create_event(
                eligibility,
                "send_accepted",
                provider_message_id=
                    result.provider_message_id,
            )
    
        elif result.retryable:
    
            eligibility.write({
                "dispatch_state": "retry_pending",
                "next_retry_at":
                    self._calculate_next_retry(
                        eligibility
                    ),
            })
    
            self._create_event(
                eligibility,
                "retry_scheduled",
            )
    
        else:
    
            eligibility.dispatch_state = "failed"
    
            self._create_event(
                eligibility,
                "send_failed_final",
                error_code=result.error_code,
                error_message=result.error_message,
            )

* * *

# 64\. Archive generation pseudocode

    def _create_campaign_archive(self):
        self.ensure_one()
    
        if self.archive_id:
            return self.archive_id
    
        if self.state not in (
            "completed",
            "completed_with_errors",
        ):
            raise UserError(
                _("Only completed runs can be archived.")
            )
    
        archive_vals = {
            "campaign_run_id": self.id,
            "mailing_id": self.mailing_id.id,
            "campaign_compliance_id":
                self.mailing_id.compliance_campaign_id,
            "subject_snapshot":
                self.mailing_id.subject,
            "body_html_snapshot":
                self.mailing_id.body_html,
            "email_from_snapshot":
                self.mailing_id.email_from,
            "consent_purpose_id":
                self.mailing_id.consent_purpose_id.id,
            "targeted_count":
                self.targeted_count,
            "eligible_count":
                self.eligible_count,
            "sent_count":
                self.sent_count,
            "failed_count":
                self.failed_count,
        }
    
        archive = self.env[
            "newsletter.campaign.archive"
        ].create(archive_vals)
    
        archive._calculate_and_lock()
    
        self.archive_id = archive.id
        self.state = "archived"
    
        return archive

* * *

# 65\. R4 business rules

| Rule | Requirement |
| --- | --- |
| R4-BR-01 | Only frozen eligible recipients may enter dispatch |
| R4-BR-02 | Sent recipients must never be automatically resent |
| R4-BR-03 | Every dispatch attempt creates an event |
| R4-BR-04 | Recipient failures must not block unrelated recipients |
| R4-BR-05 | Retry is recipient-specific |
| R4-BR-06 | Retry uses exponential backoff |
| R4-BR-07 | Dispatch-time compliance check precedes every attempt |
| R4-BR-08 | Compliance-blocked recipient is not a technical failure |
| R4-BR-09 | Event records are append-only |
| R4-BR-10 | Campaign completion requires reconciliation |
| R4-BR-11 | Eligible = Sent + Failed + Blocked + Cancelled |
| R4-BR-12 | Exact send content is snapshotted |
| R4-BR-13 | Archive is application-level immutable |
| R4-BR-14 | Archive contains approval/preflight evidence |
| R4-BR-15 | Campaign Run history is never overwritten |
| R4-BR-16 | Duplicate provider/events must be idempotent |
| R4-BR-17 | Every recipient interaction carries a correlation ID |
| R4-BR-18 | Cancellation never alters already-sent records |

* * *

# 66\. Acceptance tests

I would require at least the following before R4 is complete.

### Execution

1.  Passed/frozen run can enter queue.
    
2.  Failed preflight cannot execute.
    
3.  Unfrozen run cannot execute.
    
4.  Only eligible recipients are dispatched.
    
5.  Excluded recipients never dispatch.
    
6.  Worker processes recipients in batches.
    
7.  Two workers cannot process the same recipient.
    

### Resumability

8.  Simulate interruption after 500 recipients.
    
9.  Restart worker.
    
10.  First 500 are not resent.
    
11.  Remaining recipients continue.
    
12.  Run eventually reconciles.
    

### Compliance recheck

13.  Withdraw consent after preflight.
    
14.  Recipient becomes dispatch-blocked.
    
15.  Global suppression after preflight blocks.
    
16.  Purpose suppression after preflight blocks.
    
17.  Other-purpose suppression does not incorrectly block.
    

### Retry

18.  Temporary error → retry pending.
    
19.  Retry count increments.
    
20.  Backoff increases correctly.
    
21.  Eventually successful retry → sent.
    
22.  Maximum retries exceeded → failed.
    
23.  Permanent failure → no retry.
    

### Events

24.  Every queue/send/retry/failure creates an event.
    
25.  Events cannot be edited.
    
26.  Events cannot be deleted.
    
27.  Event hashes validate.
    
28.  Duplicate external event is ignored/idempotent.
    

### Reconciliation

29.  Eligible = terminal execution states.
    
30.  Reconciliation mismatch prevents completion.
    
31.  All successful → Completed.
    
32.  Final failures → Completed With Errors.
    

### Archive

33.  Completion creates archive.
    
34.  Subject matches exact sent subject.
    
35.  HTML matches exact send content.
    
36.  From/Reply-To captured.
    
37.  Approval data captured.
    
38.  Preflight run captured.
    
39.  Counts captured.
    
40.  Attachments captured/hash recorded.
    
41.  Archive hash generated.
    
42.  Locked archive cannot be changed.
    
43.  Locked archive cannot be deleted.
    

### Recipient audit

44.  Contact shows campaign decision.
    
45.  Contact shows dispatch outcome.
    
46.  Consent basis is visible.
    
47.  Suppression basis is visible where applicable.
    
48.  Recipient history can be reconstructed without reading application logs.
    

* * *

# 67\. Requirement traceability

| Original requirement | R4 implementation |
| --- | --- |
| FR-14 queued execution | Database-backed dispatch worker |
| FR-16 failure isolation | Recipient-level failure state |
| FR-17 exponential retry | Retry service |
| FR-22 completion statistics | Campaign reconciliation |
| FR-23 archival | Odoo Campaign Archive |
| FR-24 archive metadata | Archive snapshot |
| FR-25 read-only archive | Server-side immutable archive |
| FR-26 campaign counts | Run counters |
| FR-27 recipient reconstruction | Event ledger/history |
| NFR-03 partial failure isolation | Recipient-level processing |
| NFR-04 resumability/no resend | Terminal sent state |
| NFR-09 end-to-end traceability | Eligibility + event + archive |
| RC-15 as-sent record | Immutable content archive |
| RC-16 restricted archive | ACL/record rules |

The source specifically expects campaign statistics and recipient-level reconstruction, and requires resumability without resending successfully dispatched recipients.

# 68\. End state after R4

The operator should now see:

    Healthcare Monthly Newsletter
    CMP-2026-000128
    
    Run:
    RUN-2026-000414
    
    Status:
    ARCHIVED
    
    Targeted                 25,000
    Excluded                  3,380
    Eligible                 21,620
    
    Sent                     21,580
    Blocked at Dispatch          25
    Failed                       15
    
    Retries                      87
    
    Execution Started:
    28-Aug-2026 15:31
    
    Execution Completed:
    28-Aug-2026 15:48
    
    Archive:
    ARC-2026-000414
    
    Archive Integrity:
    ✓ VERIFIED
    
    [View Send Events]
    [View Recipient History]
    [View Campaign Archive]
    [Verify Integrity]

At this point, the Odoo 19 Community solution covers the **campaign governance, compliance gating, safe execution, resumability, traceability, and as-sent archival** portions of the original requirement.

The logical next increment is **R5 — Delivery Feedback, Bounce/Complaint/Unsubscribe Processing, Provider Integration & Operational Monitoring**. That is where we should integrate the actual SMTP/provider feedback path, classify hard/soft bounces, automatically update suppressions, enforce complaint thresholds, reconcile delivered/bounced/complained counts, and add health/alert dashboards.