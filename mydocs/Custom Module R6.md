Absolutely. **R6 — Privacy Lifecycle, Retention, Legal Hold, Evidence Export & Compliance Reporting** should be the final governance layer over R1–R5.

R6 is less about sending email and more about answering four questions reliably: **How long do we retain each class of data? What happens when retention expires or a privacy request is received? What evidence must remain because of audit/legal obligations? Can we produce a defensible compliance package without exposing more personal data than necessary?**

Your source already requires retention aligned to organizational policy, enough information to maintain the required audit trail, and no longer than necessary. It also requires end-to-end traceability of recipient, newsletter version, consent basis, timestamp, and outcome. R6 therefore has to balance **privacy minimization** with **evidence preservation**.

# R6 — Privacy Lifecycle & Compliance Evidence

## 1\. R6 scope

| Capability | R6 |
| --- | --- |
| Retention Policy master | ✅ |
| Policy by data category | ✅ |
| Retention calculation | ✅ |
| Expiry processing | ✅ |
| Legal Hold | ✅ |
| Legal Hold release | ✅ |
| Erasure workflow | ✅ |
| Pseudonymization | ✅ |
| Anonymization where feasible | ✅ |
| Consent-evidence retention | ✅ |
| Suppression preservation | ✅ |
| Archive preservation | ✅ |
| Raw provider-payload cleanup | ✅ |
| DSAR / recipient history export | ✅ |
| Campaign audit evidence export | ✅ |
| Integrity verification | ✅ |
| Compliance reporting | ✅ |
| Retention dashboard | ✅ |
| Privacy operations dashboard | ✅ |
| Controlled purge | ✅ |
| Purge audit ledger | ✅ |

* * *

# 2\. Core design principle

Do **not** apply one global rule such as:

    Delete newsletter data after 7 years

Different records have different purposes.

For example:

    Consent evidence
    ≠
    Suppression record
    ≠
    Provider raw event
    ≠
    Campaign archive
    ≠
    Recipient eligibility record

Each needs an independently governed lifecycle.

* * *

# 3\. R6 architecture

    R1 Consent / Suppression
              │
    R2 Campaign Governance
              │
    R3 Eligibility
              │
    R4 Execution / Archive
              │
    R5 Outcomes / Provider Events
              │
              ▼
    ┌──────────────────────────────────────┐
    │ R6 PRIVACY & RETENTION ENGINE        │
    │                                      │
    │ Retention Policies                   │
    │        ↓                             │
    │ Record Classification                │
    │        ↓                             │
    │ Retain Until                         │
    │        ↓                             │
    │ Legal Hold Check                     │
    │        ↓                             │
    │ Expiry Action                        │
    │   ├─ retain                          │
    │   ├─ pseudonymize                    │
    │   ├─ anonymize                       │
    │   ├─ delete raw payload              │
    │   └─ purge                           │
    │                                      │
    │ Evidence Export / Compliance Reports │
    └──────────────────────────────────────┘

* * *

# 4\. Retention Policy model

Create:

    newsletter.retention.policy

Fields:

| Field | Purpose |
| --- | --- |
| name | Policy name |
| code | Stable code |
| data_category | Data type governed |
| retention_period_days | Duration |
| retention_trigger | Starting event |
| expiry_action | What happens |
| legal_hold_allowed | Hold support |
| pseudonymize_before_delete | Optional |
| minimum_evidence_fields | Evidence policy |
| active | Active |
| company_id | Company |

* * *

# 5\. Data categories

Use controlled values such as:

    consent_evidence
    consent_history
    suppression_history
    recipient_eligibility
    campaign_run
    send_event
    provider_raw_event
    campaign_archive
    campaign_outcome
    recipient_reputation
    compliance_alert
    approval_history
    audit_export

That gives privacy administrators explicit control.

* * *

# 6\. Retention trigger

Not every retention period starts at record creation.

Possible triggers:

    record_created
    consent_given
    consent_withdrawn
    campaign_completed
    campaign_archived
    last_delivery_event
    suppression_reinstated
    outcome_finalized
    legal_hold_released

Example:

    Campaign Archive
    Retention Trigger:
    campaign_archived
    
    Retention:
    2555 days

while:

    Raw Provider Event
    Retention Trigger:
    provider_event_received
    
    Retention:
    90 days

* * *

# 7\. Expiry actions

Use:

    expiry_action = fields.Selection([
        ("retain", "Retain"),
        ("review", "Manual Review"),
        ("pseudonymize", "Pseudonymize"),
        ("anonymize", "Anonymize"),
        ("purge_payload", "Remove Raw Payload"),
        ("delete", "Delete"),
    ])

Avoid silently deleting compliance records as soon as a date is reached.

* * *

# 8\. `retain_until`

Add standardized fields to applicable R1–R5 models:

    retention_policy_id
    retention_start_at
    retain_until
    retention_state
    legal_hold

Suggested retention states:

    active
    approaching_expiry
    expired
    on_hold
    pseudonymized
    purged

* * *

# 9\. Retention calculation

Centralize in:

    services/retention_service.py

Concept:

    retain_until =
        retention_trigger_timestamp
        + timedelta(
            days=policy.retention_period_days
        )

Do not scatter date calculations throughout every model.

* * *

# 10\. Retention policy examples

These are **illustrative**, not legal defaults:

| Data | Example handling |
| --- | --- |
| Campaign Archive | Long-term regulated/business retention |
| Approval History | Same or longer than campaign archive |
| Consent Evidence | Retain sufficient evidence of consent/withdrawal |
| Suppression History | Retain enough to prove why future sends were blocked |
| Send Events | Policy-driven audit retention |
| Provider Raw Payload | Shorter retention after canonical event extracted |
| Recipient Eligibility | Align with campaign audit retention |
| Operational alerts | Medium-term operational/audit retention |

Your requirements intentionally leave exact periods to the organization's retention schedule rather than hard-coding them.

* * *

# 11\. Very important: suppression vs privacy deletion

Do **not** simply delete a recipient's suppression record in response to an erasure request.

Suppose:

    john@example.com
    Global Opt-Out

and you erase the opt-out evidence completely.

Later someone reimports:

    john@example.com

and the system may send marketing again.

That defeats the purpose of withdrawal.

Instead preserve the **minimum suppression token necessary to honor the opt-out**.

* * *

# 12\. Suppression pseudonymization

A strong design is:

    Plain email:
    john@example.com
    
            ↓ pseudonymization
    
    HMAC(email_normalized, compliance_secret)
    =
    7faa18...

Then future candidate emails can be transformed using the same controlled HMAC and checked against the suppression token.

Store:

    email_hash
    reason_category
    effective_from
    scope

rather than retaining unnecessary personal profile details indefinitely.

* * *

# 13\. Why HMAC instead of plain SHA-256

Plain:

    SHA256("john@example.com")

is vulnerable to dictionary guessing.

Prefer:

    HMAC-SHA256(
        controlled_secret,
        normalized_email
    )

for long-term suppression matching.

The secret should be managed outside ordinary business-user access.

* * *

# 14\. Add privacy identity fields

For records where personal identity may later be removed:

    identity_state
    pseudonymized_at
    pseudonymized_by_id
    pseudonymization_reference

States:

    identified
    pseudonymized
    anonymized

* * *

# 15\. Pseudonymization vs anonymization

Keep the distinction explicit.

### Pseudonymization

Identity can potentially be re-associated through controlled information.

Example:

    recipient email → HMAC token

Useful for:

    suppression
    deduplication
    audit references

### Anonymization

Re-identification should no longer reasonably be possible.

Example:

    Campaign total delivered = 21,220

with no individual identity.

Useful for long-term aggregated analytics.

* * *

# 16\. Legal Hold

Create:

    newsletter.legal.hold

Fields:

| Field | Purpose |
| --- | --- |
| reference | Hold ID |
| name | Case/hold title |
| reason | Reason |
| legal_reference | Case/reference |
| start_at | Hold start |
| released_at | Release |
| status | Active/Released |
| owner_id | Responsible person |
| approved_by_id | Approver |
| scope_type | Campaign/Recipient/Date range/etc. |
| company_id | Company |

* * *

# 17\. Legal Hold scope

Allow hold over:

    Campaign
    Campaign Run
    Recipient
    Consent records
    Suppression records
    Date range
    Entire company/business domain

Potentially:

    Campaign CMP-2026-000128

or:

    All communication records for recipient X

* * *

# 18\. Legal Hold rule

Before any retention action:

    Is record on active legal hold?
            │
           YES
            │
            ▼
    DO NOT PURGE / PSEUDONYMIZE

Even if:

    retain_until < today

* * *

# 19\. Hold release

Releasing a hold must not immediately delete records inside the same transaction.

Instead:

    Legal Hold Released
           ↓
    Records re-enter retention evaluation
           ↓
    Next retention job evaluates expiry

This gives a safer audit trail.

* * *

# 20\. Legal Hold audit

Record:

    Hold created by
    Approved by
    Reason
    Scope
    Created at
    Released by
    Release reason
    Released at

Never merely flip:

    legal_hold = False

without history.

* * *

# 21\. Privacy Request model

Create:

    newsletter.privacy.request

Types:

    access
    export
    correction
    erasure
    restriction
    objection
    consent_history
    marketing_opt_out

Fields:

    reference
    request_type
    requester
    recipient/partner
    email_normalized
    received_at
    due_at
    status
    identity_verified
    verification_method
    assigned_to
    decision
    decision_reason
    completed_at

* * *

# 22\. Privacy request workflow

    RECEIVED
       ↓
    IDENTITY VERIFICATION
       ↓
    DISCOVERY
       ↓
    LEGAL / RETENTION CHECK
       ↓
    DECISION
       │
       ├─ Fulfil
       ├─ Partially Fulfil
       └─ Reject With Reason
       ↓
    EXECUTION
       ↓
    EVIDENCE PACKAGE
       ↓
    COMPLETED

* * *

# 23\. Do not execute erasure immediately

An erasure request must first determine:

    What data exists?
    Why is it retained?
    Is there a legal hold?
    Is some minimal suppression evidence required?
    Can identity be removed while audit evidence remains?

So:

    Request → discovery → policy decision → action

not:

    Request → DELETE FROM ...

* * *

# 24\. Privacy discovery

Create:

    services/privacy_discovery_service.py

Given:

    partner
    or normalized email

find:

    Consent Records
    Suppressions
    Eligibility Decisions
    Send Events
    Provider Events
    Reputation
    Campaign History
    Alerts
    Attachments

Return a discovery manifest.

* * *

# 25\. Example discovery

    Privacy Request:
    PRIV-2026-000041
    
    Subject:
    john@example.com
    
    Records Found
    ----------------------------------
    Consent Records              4
    Suppression Records          1
    Campaign Decisions          18
    Send Events                 46
    Provider Events             12
    Campaign Archives            0*
    Reputation Record            1

`*` Archives are campaign-level rather than owned by the individual.

* * *

# 26\. Campaign archive and erasure

Do not modify an immutable campaign archive just because one recipient requests erasure.

The archive should generally contain:

    campaign content
    audience definition
    aggregate statistics
    approval evidence

—not a giant plaintext recipient roster embedded into immutable content.

Individual recipient evidence remains in linked records.

This architecture makes privacy handling much easier.

* * *

# 27\. Recipient-level event pseudonymization

Suppose retention policy says:

    individual send history no longer requires direct identity

Convert:

    email_normalized = john@example.com
    partner_id = 123

to:

    recipient_token = HMAC(...)
    email_normalized = False
    partner_id = False
    identity_state = pseudonymized

while retaining:

    Campaign
    Event Type
    Timestamp
    Outcome
    Consent-purpose category

where permitted by policy.

* * *

# 28\. Provider raw payload cleanup

This is particularly important.

R5 raw webhook payloads may contain:

    email
    SMTP diagnostic
    provider metadata
    IP information
    headers

Once:

    canonical Send Event

has been created and the troubleshooting retention period expires, you may no longer need the raw payload.

Use:

    expiry_action = purge_payload

Result:

    payload_hash remains
    provider event ID remains
    canonical event remains
    raw_payload = removed

This is a good example of data minimization without losing core auditability.

* * *

# 29\. Purge Event Ledger

Create:

    newsletter.retention.action

Every retention action must itself be auditable.

Fields:

    reference
    policy_id
    model_name
    record_reference
    action_type
    executed_at
    executed_by
    previous_identity_state
    new_identity_state
    legal_hold_checked
    result
    error_message
    evidence_hash_before
    evidence_hash_after

* * *

# 30\. Retention actions are append-only

Just like Send Events:

    newsletter.retention.action

should not be modified or deleted through normal application behavior.

It answers:

> “What happened to this record after its retention period expired?”

* * *

# 31\. Scheduled retention engine

Create:

    Newsletter Compliance Retention Processor

Run daily.

Concept:

    @api.model
    def _cron_process_retention(self):
        policies = self.search([("active", "=", True)])
    
        for policy in policies:
            retention_service.process_policy(policy)

* * *

# 32\. Retention batch processing

Never process millions of records in one transaction.

Use:

    Retention Batch Size = 1000

Process:

    Batch 1
    Commit
    
    Batch 2
    Commit
    
    ...

Failures should not stop unrelated records.

* * *

# 33\. Retention evaluation

Pseudocode:

    def evaluate_record(record):
    
        if record.legal_hold:
            return HOLD
    
        if not record.retain_until:
            return SKIP
    
        if record.retain_until > now:
            return RETAIN
    
        return policy.expiry_action

* * *

# 34\. Dry-run mode

Add:

    Retention Dry Run = Yes

This is essential before production activation.

Dry-run produces:

    1,280 records eligible for pseudonymization
    430 raw payloads eligible for purge
    17 records blocked by legal hold
    0 errors

without changing data.

* * *

# 35\. Retention preview

Before executing a new policy, Compliance Admin should be able to run:

    [Preview Impact]

Example:

    Policy:
    Provider Raw Events – 90 Days
    
    Eligible:
    38,412
    
    On Legal Hold:
    203
    
    Would Purge Raw Payload:
    38,209
    
    Estimated PII fields removed:
    114,627

* * *

# 36\. Destructive actions need two-person control

For broad actions such as:

    Delete
    Bulk anonymize
    Bulk pseudonymize

I recommend:

    Prepared By
    +
    Approved By

before execution.

Especially for:

    manual retention runs

outside standard scheduled policies.

* * *

# 37\. Evidence export — Campaign Audit Package

Create wizard:

    newsletter.audit.export.wizard

Input:

    Campaign
    Campaign Run
    Include recipient-level evidence? Yes/No
    Mask personal data? Yes/No

Output logical package:

    Campaign Identity
    Governance
    Approvals
    Consent Purpose
    Preflight Summary
    Eligibility Summary
    Execution Summary
    Outcome Summary
    Alerts
    Archive Hash
    Outcome Hash
    Integrity Verification

* * *

# 38\. Detailed audit package

For privileged audits, include:

    campaign.json
    approvals.json
    preflight-summary.json
    recipient-decisions.csv
    send-events.csv
    campaign-outcome.json
    suppression-actions.csv
    integrity-manifest.json
    newsletter.html
    attachments/

Later you can export this as a ZIP/PDF bundle if desired.

* * *

# 39\. Evidence manifest

Create:

    manifest.json

with:

    Package ID
    Generated At
    Generated By
    Campaign ID
    Run ID
    Files
    SHA-256 per file
    Archive Hash
    Outcome Hash
    Ruleset Version

This makes the package self-verifiable.

* * *

# 40\. Recipient audit package

For a privacy/audit request:

    Recipient:
    john@example.com

package can include:

    Consent Timeline
    Withdrawal Timeline
    Suppression Timeline
    Campaign Eligibility Decisions
    Send History
    Delivery Outcomes
    Complaint/Unsubscribe History
    Current Communication Status

This satisfies the underlying FR-27 intent to reconstruct consent basis and send history for a particular recipient.

* * *

# 41\. Masked vs unmasked exports

Support:

    Masked Export

Example:

    j***@example.com

and:

    Full Evidence Export

Full evidence export should require a more privileged role.

Do not expose unnecessary PII to routine campaign reviewers.

* * *

# 42\. Export logging

Every export creates:

    newsletter.audit.export

Fields:

    reference
    export_type
    campaign_run_id
    privacy_request_id
    generated_by
    generated_at
    masked
    record_count
    file_hash
    purpose
    download_count
    expires_at

Export activity itself is sensitive audit activity.

* * *

# 43\. Export expiration

Generated evidence files should not remain downloadable indefinitely.

Example:

    Audit Export Availability = 7 days

After expiry:

    file removed
    export metadata retained
    hash retained

* * *

# 44\. Integrity Verification service

Create:

    services/integrity_service.py

Operations:

    Verify Campaign Archive
    Verify Campaign Outcome
    Verify Send Event Chain
    Verify Audit Package

Result:

    VALID
    INVALID
    INCOMPLETE

* * *

# 45\. Integrity verification screen

Example:

    Campaign:
    CMP-2026-000128
    
    Archive:
    ARC-2026-000414
    
    Archive Hash:
    ✓ VALID
    
    Approval Hash:
    ✓ VALID
    
    Preflight Result Hash:
    ✓ VALID
    
    Outcome Hash:
    ✓ VALID
    
    Send Event Chain:
    ✓ 64,812 / 64,812 valid
    
    Last Verified:
    28-Aug-2026 15:21

* * *

# 46\. Integrity alert

If:

    stored archive hash
    !=
    calculated archive hash

immediately create:

    CRITICAL
    Archive Integrity Failure

Do not silently repair the stored hash.

The discrepancy itself is audit evidence.

* * *

# 47\. Compliance reporting

R6 should provide several standard reports.

### Consent Compliance

    Active consent by purpose
    Withdrawn consent
    Expired consent
    Consent source
    Privacy notice versions
    Consent evidence completeness

### Suppression Compliance

    Global suppression
    Purpose suppression
    Hard bounce suppression
    Complaint suppression
    Opt-out suppression
    Reinstatement activity

### Campaign Governance

    Campaigns approved
    Rejected
    Approval invalidations
    Self-approval attempts blocked
    Preflight failures

### Deliverability

    Delivery rate
    Bounce rate
    Complaint rate
    Unsubscribe rate

### Privacy

    Privacy requests
    Average completion time
    Erasure/pseudonymization actions
    Retention exceptions
    Legal holds

* * *

# 48\. Retention dashboard

Example:

    RETENTION & PRIVACY
    
    Records Approaching Expiry        8,412
    Expired / Pending Action          1,203
    On Legal Hold                       419
    
    Raw Payloads Pending Purge        6,701
    Records Pending Pseudonymization    782
    
    Failed Retention Actions             7
    
    Privacy Requests Open               14
    Privacy Requests Overdue             1
    
    Active Legal Holds                   4

* * *

# 49\. Retention exception queue

Provide:

    Email Marketing
    → Compliance
    → Privacy & Retention
    → Exceptions

Reasons:

    Missing policy
    Missing retention trigger
    Legal hold conflict
    Pseudonymization failure
    Attachment purge failure
    Integrity verification failure
    Policy configuration error

Never silently skip these.

* * *

# 50\. Legal Hold dashboard

    HOLD-2026-00017
    
    Reason:
    Litigation Preservation
    
    Scope:
    CMP-2026-000128
    CMP-2026-000129
    
    Start:
    01-Aug-2026
    
    Owner:
    Legal Department
    
    Records Protected:
    68,902
    
    Expired Records Prevented From Purge:
    8,218

* * *

# 51\. Compliance roles for R6

Add:

    Privacy Officer
    Legal Hold Administrator
    Compliance Auditor

Suggested permissions:

| Capability | Compliance Admin | Privacy Officer | Legal Hold Admin | Auditor |
| --- | --- | --- | --- | --- |
| View retention policy | ✅ | ✅ | ✅ | ✅ |
| Modify policy | ✅ | ✅ |  |  |
| Run retention preview | ✅ | ✅ |  |  |
| Execute manual purge | Controlled | Controlled |  |  |
| Create legal hold |  |  | ✅ |  |
| Release legal hold |  |  | ✅ |  |
| Privacy request management |  | ✅ |  | Read |
| Full recipient export | Controlled | ✅ |  | Controlled |
| Campaign audit export | ✅ | ✅ | ✅ | ✅ |
| Integrity verification | ✅ | ✅ | ✅ | ✅ |
| Modify purge ledger | ❌ | ❌ | ❌ | ❌ |

* * *

# 52\. Field-level restrictions

Highly restricted:

    raw provider payload
    IP address
    user agent
    consent evidence attachment
    full recipient export
    legal case references
    privacy verification details
    pseudonymization token

Do not give standard Campaign Operators access.

* * *

# 53\. Pseudonymization key handling

Do not store the HMAC secret in:

    campaign record
    system parameters readable by ordinary administrators
    source code

Use a controlled secret-management mechanism appropriate to your deployment.

Architecturally:

    Odoo
      │
      ▼
    Secret Provider
      │
      ▼
    HMAC operation

If you later deploy Vault/Kubernetes Secrets/cloud KMS, the service interface stays the same.

* * *

# 54\. Key rotation

If using HMAC-based suppression tokens, key rotation needs planning.

One pattern:

    token_version

Store:

    v1:<hash>
    v2:<hash>

During migration:

    check active token versions

Never rotate the key without preserving ability to match existing suppression tokens.

* * *

# 55\. Erasure strategy by record type

A recommended matrix:

| Record | Erasure strategy |
| --- | --- |
| Contact profile | Standard privacy process |
| Consent record | Pseudonymize after evidence retention, where allowed |
| Withdrawal record | Retain minimum evidence |
| Global suppression | Retain HMAC suppression token |
| Eligibility | Pseudonymize identity after retention |
| Send events | Pseudonymize identity after retention |
| Provider raw event | Purge raw payload early |
| Campaign archive | Keep aggregate/content evidence |
| Campaign outcome | Keep aggregate |
| Approval history | Keep |
| Compliance alerts | Remove unnecessary recipient PII |
| Reputation record | Delete/pseudonymize subject to active suppression |

* * *

# 56\. “Right to be forgotten” without forgetting opt-out

Conceptually:

    Before:
    John Smith
    john@example.com
    Suppressed = Global Opt-Out
    
    After privacy processing:
    
    Name = removed
    Partner link = removed
    Plain email = removed
    
    Suppression Token =
    HMAC(john@example.com)
    
    Reason =
    GLOBAL_OPT_OUT

If the email is imported later:

    HMAC(imported email)
          ↓
    matches existing suppression token
          ↓
    BLOCK

This is one of the most valuable R6 controls.

* * *

# 57\. Duplicate identities

Privacy discovery should search by:

    partner_id
    normalized email
    historical normalized email
    pseudonym token where permitted

because a recipient may exist as:

    res.partner
    mailing.contact
    multiple imported contacts

R3 already encountered the duplicate identity problem; R6 must solve it for privacy requests too.

* * *

# 58\. Retention precedence

When multiple policies apply, define:

    LEGAL HOLD
          ↓ highest
    
    Statutory/required minimum
          ↓
    
    Contractual/business retention
          ↓
    
    Normal policy
          ↓
    
    Erasure request

More precisely, an erasure request triggers an evaluation; it does not automatically supersede legitimate preservation requirements.

* * *

# 59\. Retention reason

Every retained record should be explainable.

Add:

    retention_basis

Examples:

    active_service
    consent_evidence
    opt_out_enforcement
    regulatory_audit
    legal_hold
    security_investigation
    campaign_audit

This is useful for privacy review.

* * *

# 60\. Data minimization check

R6 should also examine **what we are collecting**, not merely when we delete it.

For example:

    provider raw payload contains 40 fields
    canonical event needs 9

Keep only the 9 canonical fields long-term.

Likewise avoid duplicating:

    full recipient profile

into:

    eligibility
    send event
    archive
    provider event

Use stable references wherever direct duplication isn't needed.

* * *

# 61\. R6 menu

    Email Marketing
    └── Compliance
        │
        ├── Campaign Governance
        ├── Execution
        ├── Deliverability
        ├── Suppression
        ├── Audit
        │   ├── Campaign Archives
        │   ├── Send Events
        │   ├── Recipient History
        │   ├── Audit Exports
        │   └── Integrity Verification
        │
        ├── Privacy & Retention
        │   ├── Dashboard
        │   ├── Privacy Requests
        │   ├── Records Approaching Expiry
        │   ├── Pending Retention Actions
        │   ├── Retention Exceptions
        │   ├── Legal Holds
        │   └── Retention Action Ledger
        │
        └── Configuration
            ├── Retention Policies
            ├── Privacy Settings
            └── Export Policies

* * *

# 62\. Module additions

    newsletter_compliance/
    ├── models/
    │   ├── retention_policy.py
    │   ├── retention_action.py
    │   ├── legal_hold.py
    │   ├── privacy_request.py
    │   ├── audit_export.py
    │   └── privacy_extensions.py
    │
    ├── services/
    │   ├── retention_service.py
    │   ├── privacy_discovery_service.py
    │   ├── pseudonymization_service.py
    │   ├── erasure_service.py
    │   ├── audit_export_service.py
    │   └── integrity_service.py
    │
    ├── wizard/
    │   ├── retention_preview_wizard.py
    │   ├── manual_retention_wizard.py
    │   ├── legal_hold_release_wizard.py
    │   ├── privacy_request_execute_wizard.py
    │   └── audit_export_wizard.py
    │
    ├── data/
    │   ├── retention_policy_data.xml
    │   └── retention_cron.xml
    │
    ├── views/
    │   ├── retention_policy_views.xml
    │   ├── retention_action_views.xml
    │   ├── legal_hold_views.xml
    │   ├── privacy_request_views.xml
    │   ├── audit_export_views.xml
    │   └── privacy_dashboard_views.xml
    │
    └── tests/
        ├── test_retention.py
        ├── test_legal_hold.py
        ├── test_pseudonymization.py
        ├── test_erasure.py
        ├── test_suppression_privacy.py
        ├── test_audit_export.py
        └── test_integrity.py

* * *

# 63\. Retention processor pseudocode

    def process_policy(policy):
    
        candidates = policy._find_expired_records(
            limit=policy.batch_size
        )
    
        for record in candidates:
    
            try:
                if legal_hold_service.is_held(record):
                    retention_log.record_hold(record)
                    continue
    
                action = retention_service.determine_action(
                    policy,
                    record,
                )
    
                before_hash = integrity_service.hash_record(
                    record
                )
    
                retention_service.execute(
                    action,
                    record,
                )
    
                after_hash = (
                    integrity_service.hash_record(record)
                    if record.exists()
                    else None
                )
    
                retention_log.record_success(
                    record=record,
                    action=action,
                    before_hash=before_hash,
                    after_hash=after_hash,
                )
    
            except Exception as exc:
    
                retention_log.record_failure(
                    record=record,
                    error=str(exc),
                )

* * *

# 64\. Privacy erasure pseudocode

    def execute_erasure_request(request):
    
        request.ensure_identity_verified()
    
        discovery = privacy_discovery_service.discover(
            request
        )
    
        for item in discovery.items:
    
            policy = retention_service.get_policy(
                item.record
            )
    
            if legal_hold_service.is_held(item.record):
                item.mark_retained("legal_hold")
                continue
    
            decision = erasure_service.determine_action(
                item.record,
                policy,
            )
    
            erasure_service.execute(
                item.record,
                decision,
            )
    
        request.mark_completed()

* * *

# 65\. Campaign audit export pseudocode

    def generate_campaign_package(run):
    
        archive = run.archive_id
        outcome = run.outcome_id
    
        integrity_service.verify_archive(archive)
    
        package = {
            "campaign": build_campaign_metadata(run),
            "approvals": build_approval_history(run),
            "preflight": build_preflight_summary(run),
            "execution": build_execution_summary(run),
            "outcome": build_outcome_summary(outcome),
            "integrity": build_integrity_manifest(run),
        }
    
        return export_service.create_package(package)

* * *

# 66\. R6 business rules

| Rule | Requirement |
| --- | --- |
| R6-BR-01 | Every retained compliance dataset must have a policy |
| R6-BR-02 | Retention trigger must be explicit |
| R6-BR-03 | Legal hold overrides automated expiry |
| R6-BR-04 | Hold creation/release must be auditable |
| R6-BR-05 | Erasure requests do not automatically delete regulatory/audit evidence |
| R6-BR-06 | Minimum opt-out evidence must survive privacy cleanup where needed to prevent future marketing |
| R6-BR-07 | Raw provider payload should not be retained longer than necessary |
| R6-BR-08 | Purge/pseudonymization actions must be logged |
| R6-BR-09 | Retention ledger is append-only |
| R6-BR-10 | Immutable campaign archive cannot be rewritten by privacy jobs |
| R6-BR-11 | Recipient-level identity may be pseudonymized independently of aggregate campaign evidence |
| R6-BR-12 | Destructive bulk action requires privileged authorization |
| R6-BR-13 | Audit exports must be logged |
| R6-BR-14 | Audit exports should expire |
| R6-BR-15 | Integrity failures must create alerts |
| R6-BR-16 | Dry-run must be available before activating new retention policy |
| R6-BR-17 | Failed retention actions remain visible for remediation |
| R6-BR-18 | Privacy request completion must retain evidence of what actions were taken |

* * *

# 67\. R6 acceptance tests

### Retention policies

1.  Create policy for Provider Events.
    
2.  Correct `retain_until` calculated.
    
3.  Change policy only affects appropriate future/recalculated records according to defined behavior.
    
4.  Expired record enters retention queue.
    
5.  Non-expired record remains untouched.
    

### Legal hold

6.  Place expired record on legal hold.
    
7.  Retention processor does not purge.
    
8.  Hold action logged.
    
9.  Release hold.
    
10.  Record returns to retention evaluation.
    
11.  Hold release itself logged.
    

### Raw provider events

12.  Expired raw payload removed.
    
13.  Provider event metadata remains.
    
14.  Payload hash remains.
    
15.  Canonical Send Event remains.
    
16.  Campaign counts remain unchanged.
    

### Pseudonymization

17.  Recipient identity replaced with token.
    
18.  Partner relationship removed where policy requires.
    
19.  Campaign/event linkage remains.
    
20.  Aggregate reports remain correct.
    

### Suppression

21.  Global opt-out survives privacy cleanup as protected token.
    
22.  Re-importing same normalized email still matches suppression.
    
23.  Purpose-specific suppression remains scoped correctly.
    
24.  Deleted contact does not accidentally reactivate marketing eligibility.
    

### Privacy requests

25.  Access request finds all related compliance records.
    
26.  Erasure request requires identity verification.
    
27.  Active legal hold blocks applicable erasure.
    
28.  Erasure actions logged.
    
29.  Minimum opt-out evidence retained.
    
30.  Request cannot be marked complete until required actions reconcile.
    

### Audit export

31.  Campaign package contains campaign identity.
    
32.  Approval evidence included.
    
33.  Preflight evidence included.
    
34.  Execution summary included.
    
35.  Outcome included.
    
36.  Integrity manifest included.
    
37.  File hashes validate.
    
38.  Export action logged.
    
39.  Masked export masks PII.
    
40.  Export expires according to policy.
    

### Integrity

41.  Valid archive verifies successfully.
    
42.  Modify archived data in test DB → integrity validation fails.
    
43.  Critical alert generated.
    
44.  System does not silently recalculate and overwrite the old hash.
    

### Retention safety

45.  Dry-run performs no mutation.
    
46.  Dry-run counts match actual run.
    
47.  Failed record does not abort entire batch.
    
48.  Batch can resume safely.
    
49.  Retention ledger cannot be edited.
    
50.  Multi-company isolation applies to privacy and retention operations.
    

* * *

# 68\. Requirement traceability

R6 maps mainly to the audit/privacy aspects of the original requirements:

| Requirement | R6 capability |
| --- | --- |
| FR-27 recipient reconstruction | Recipient audit package |
| NFR-07 restricted compliance data | Privacy/security roles |
| NFR-09 retained auditability | Retention + evidence preservation |
| RC-08 consent evidence | Consent retention |
| RC-09 withdrawal evidence | Withdrawal/suppression preservation |
| RC-11 retention and erasure | Retention/erasure engine |
| RC-15 as-sent evidence | Protected campaign archive |
| RC-16 restricted archive access | RBAC + audit export controls |

The source explicitly requires retention sufficient for audit while also avoiding retention beyond what is necessary. That is precisely the design tension R6 resolves.

# 69\. End state after R6

With R6 complete, the complete lifecycle is:

    R1
    Consent & Suppression
            ↓
    R2
    Campaign Governance
            ↓
    R3
    Eligibility & Preflight
            ↓
    R4
    Safe Execution & Archive
            ↓
    R5
    Delivery Feedback & Reputation
            ↓
    R6
    Privacy / Retention / Evidence
            ↓
    ┌───────────────────────────────┐
    │ COMPLETE COMPLIANCE LIFECYCLE │
    └───────────────────────────────┘

A single recipient can now be traced across the complete lifecycle:

    Consent Granted
          ↓
    Campaign Selected
          ↓
    Eligibility Decision
          ↓
    Email Sent
          ↓
    Delivered / Bounced / Complaint
          ↓
    Suppression / Withdrawal
          ↓
    Retention Period
          ↓
    Pseudonymization / Retention
          ↓
    Audit Evidence

And a campaign can be reconstructed as:

    Campaign
       ↓
    Governance Version
       ↓
    Content Approval
       ↓
    Compliance Approval
       ↓
    Preflight Run
       ↓
    Frozen Population
       ↓
    Recipient Dispatch Events
       ↓
    Delivery Outcome
       ↓
    As-Sent Archive
       ↓
    Integrity Hash
       ↓
    Retention Policy
       ↓
    Audit Package

## R1–R6 completion picture

| Capability | Release |
| --- | --- |
| Consent Register | R1 |
| Suppression Register | R1 |
| Campaign Governance | R2 |
| Content/Compliance Approval | R2 |
| Recipient Eligibility | R3 |
| Preflight | R3 |
| Send Enforcement | R3 |
| Safe/Resumable Execution | R4 |
| Send Event Ledger | R4 |
| As-Sent Archive | R4 |
| Delivery Feedback | R5 |
| Bounce/Complaint Management | R5 |
| Unsubscribe Feedback | R5 |
| Reputation Management | R5 |
| Operational Alerts | R5 |
| Retention Policies | R6 |
| Privacy Requests | R6 |
| Pseudonymization/Erasure | R6 |
| Legal Hold | R6 |
| Evidence Export | R6 |
| Integrity Verification | R6 |

At this stage, **R1–R6 form a coherent Odoo 19 Community newsletter compliance platform rather than just an Email Marketing customization**.

The most useful next step would be to stop adding conceptual releases and turn the six increments into a **single consolidated implementation blueprint**: final architecture, complete module/file structure, final canonical data model, state machines, APIs, cron jobs, security matrix, requirement traceability, dependency/build order, and sprint-level implementation backlog. That would give a development team one authoritative specification from which to start building.