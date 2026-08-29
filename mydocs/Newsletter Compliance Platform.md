# Newsletter Compliance Platform
## Consolidated Implementation Blueprint
### Odoo 19 Community Edition

**Document Status:** Implementation Baseline  
**Target Platform:** Odoo 19 Community Edition  
**Custom Module:** `newsletter_compliance`  
**Primary Standard Dependency:** Odoo Email Marketing / `mass_mailing`  
**Architecture Principle:** Extend Odoo Email Marketing; do not replace the native mailing engine.

---

# 1. Purpose

This document is the single implementation specification for the Newsletter Compliance Platform built on Odoo 19 Community Edition.

It consolidates six build increments:

| Release | Scope |
|---|---|
| R1 | Consent & Suppression Foundation |
| R2 | Campaign Governance |
| R3 | Recipient Eligibility & Preflight |
| R4 | Campaign Execution, Send Ledger & Archive |
| R5 | Delivery Feedback, Reputation & Monitoring |
| R6 | Privacy, Retention, Legal Hold & Evidence |

The original specification assumed SharePoint, Power Automate, Apache Camel, SES/SNS/SQS and an external consent store. The business requirements, however, are technology-independent: campaign governance, recipient consent, suppression, safe sending, traceability, feedback processing and durable audit evidence.

The source specification requires filtering recipients against suppression controls, retaining exact campaign and send information, maintaining recipient-level consent/send history, supporting partial failures and resumability, and retaining data according to organizational retention policy. 
---

# 2. Target Architecture

```text
                                USERS
        ┌────────────────────────────────────────────────┐
        │ Author | Approver | Compliance | Operator      │
        │ Privacy | Auditor | Administrator              │
        └───────────────────────┬────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ODOO 19 COMMUNITY                            │
│                                                                 │
│  ┌──────────────── STANDARD ODOO ────────────────────────────┐  │
│  │ Contacts                                                  │  │
│  │ Mail / Chatter                                            │  │
│  │ Email Marketing (`mass_mailing`)                          │  │
│  │ `mailing.mailing`                                         │  │
│  │ `mailing.contact` / recipient models                      │  │
│  │ Native marketing blacklist                                │  │
│  │ Native outbound mail infrastructure                       │  │
│  └─────────────────────────┬─────────────────────────────────┘  │
│                            │                                    │
│  ┌────────── NEWSLETTER COMPLIANCE MODULE ──────────────────┐  │
│  │                                                          │  │
│  │ R1  Consent Register                                     │  │
│  │     Suppression Register                                 │  │
│  │                                                          │  │
│  │ R2  Campaign Governance                                  │  │
│  │     Content Approval                                     │  │
│  │     Compliance Approval                                  │  │
│  │                                                          │  │
│  │ R3  Recipient Resolver                                   │  │
│  │     Eligibility Engine                                   │  │
│  │     Preflight                                            │  │
│  │     Frozen Recipient Population                          │  │
│  │                                                          │  │
│  │ R4  Campaign Run                                         │  │
│  │     Dispatch Worker                                      │  │
│  │     Send Event Ledger                                    │  │
│  │     Immutable As-Sent Archive                            │  │
│  │                                                          │  │
│  │ R5  Provider Event Gateway                               │  │
│  │     Bounce / Complaint / Unsubscribe                     │  │
│  │     Reputation Engine                                    │  │
│  │     Campaign Outcome                                     │  │
│  │     Monitoring / Alerts                                  │  │
│  │                                                          │  │
│  │ R6  Retention Engine                                     │  │
│  │     Privacy Requests                                     │  │
│  │     Legal Hold                                           │  │
│  │     Pseudonymization                                     │  │
│  │     Audit Package / Integrity Verification               │  │
│  └──────────────────────────┬───────────────────────────────┘  │
└─────────────────────────────┼───────────────────────────────────┘
                              │
                              ▼
                  ┌─────────────────────────┐
                  │ Email Delivery Provider │
                  │ SMTP / SES / SendGrid / │
                  │ Mailgun / Other         │
                  └────────────┬────────────┘
                               │
                    Delivery / Bounce /
                    Complaint callbacks
                               │
                               ▼
                  Provider Event Gateway
```

Odoo 19's `mailing.mailing` remains the native campaign object. The standard form exposes recipients, mailing lists/domains, body HTML, sender, reply-to and attachments, so the custom implementation should inherit this model rather than duplicate it.

Odoo 19 also exposes `action_put_in_queue()`, `action_send_mail()` and `_get_recipients_domain()` as extensible mailing paths. These are appropriate enforcement points for compliance readiness and frozen-recipient selection.

---

# 3. Non-Negotiable Architecture Decisions

1. `mailing.mailing` remains the campaign definition.
2. Odoo's native `state` is never repurposed for compliance.
3. Compliance uses a separate `compliance_state`.
4. Approval does not mean permission to send.
5. Preflight must complete before Send/Schedule.
6. Preflight freezes the eligible recipient population.
7. Actual dispatch uses that frozen population, not a freshly recalculated audience.
8. Consent and suppression are rechecked immediately before dispatch.
9. Successfully submitted recipients are never automatically resent within the same run.
10. Recipient technical failure cannot block unrelated recipients.
11. Send events are append-only.
12. Campaign archive content is copied, hashed and application-level immutable.
13. Provider events are normalized into a provider-independent canonical model.
14. Global suppressions synchronize with Odoo's native marketing blacklist.
15. Purpose/list suppressions do not become global blacklist records.
16. Privacy erasure must not cause a previously opted-out recipient to become eligible again.
17. Legal Hold always overrides automated retention actions.
18. Public RPC/action methods must perform explicit authorization and state checks; UI button hiding is not security.

Odoo access rights are additive and record rules are default-allow when an ACL grants access but no applicable rule restricts it. Public model methods may also be callable by RPC, so workflow methods must validate groups/state explicitly.

---

# 4. Complete Module Structure

```text
newsletter_compliance/
│
├── __init__.py
├── __manifest__.py
├── README.md
│
├── models/
│   ├── __init__.py
│   │
│   ├── consent_purpose.py
│   ├── consent_record.py
│   ├── suppression_reason.py
│   ├── suppression_entry.py
│   │
│   ├── campaign_brand.py
│   ├── mailing_mailing.py
│   ├── campaign_approval.py
│   │
│   ├── campaign_run.py
│   ├── recipient_eligibility.py
│   │
│   ├── send_event.py
│   ├── campaign_archive.py
│   ├── campaign_archive_attachment.py
│   ├── campaign_outcome.py
│   ├── campaign_outcome_adjustment.py
│   │
│   ├── provider_event.py
│   ├── delivery_reputation.py
│   ├── compliance_alert.py
│   ├── provider_health.py
│   │
│   ├── retention_policy.py
│   ├── retention_action.py
│   ├── legal_hold.py
│   ├── privacy_request.py
│   ├── audit_export.py
│   │
│   └── res_partner.py
│
├── services/
│   ├── __init__.py
│   ├── email_normalization_service.py
│   ├── consent_service.py
│   ├── suppression_service.py
│   ├── recipient_resolver.py
│   ├── eligibility_service.py
│   ├── preflight_service.py
│   ├── dispatch_service.py
│   ├── retry_service.py
│   ├── reconciliation_service.py
│   ├── event_service.py
│   ├── reputation_service.py
│   ├── archive_service.py
│   ├── hashing_service.py
│   ├── integrity_service.py
│   ├── retention_service.py
│   ├── legal_hold_service.py
│   ├── privacy_discovery_service.py
│   ├── pseudonymization_service.py
│   ├── erasure_service.py
│   └── audit_export_service.py
│
├── services/providers/
│   ├── __init__.py
│   ├── base_provider.py
│   ├── smtp_provider.py
│   ├── ses_provider.py
│   ├── sendgrid_provider.py
│   └── mailgun_provider.py
│
├── controllers/
│   ├── __init__.py
│   ├── provider_event_controller.py
│   ├── unsubscribe_controller.py
│   └── privacy_controller.py
│
├── wizard/
│   ├── __init__.py
│   ├── withdraw_consent.py
│   ├── reinstate_suppression.py
│   ├── reject_campaign.py
│   ├── reset_campaign.py
│   ├── cancel_campaign.py
│   ├── retention_preview.py
│   ├── manual_retention.py
│   ├── legal_hold_release.py
│   ├── privacy_request_execute.py
│   └── audit_export.py
│
├── security/
│   ├── newsletter_compliance_groups.xml
│   ├── ir.model.access.csv
│   └── newsletter_compliance_rules.xml
│
├── data/
│   ├── sequences.xml
│   ├── suppression_reason_data.xml
│   ├── retention_policy_data.xml
│   ├── dispatch_cron.xml
│   ├── provider_event_cron.xml
│   ├── monitoring_cron.xml
│   ├── outcome_cron.xml
│   └── retention_cron.xml
│
├── views/
│   ├── consent_purpose_views.xml
│   ├── consent_record_views.xml
│   ├── suppression_reason_views.xml
│   ├── suppression_entry_views.xml
│   ├── campaign_brand_views.xml
│   ├── mailing_mailing_views.xml
│   ├── campaign_approval_views.xml
│   ├── campaign_run_views.xml
│   ├── recipient_eligibility_views.xml
│   ├── send_event_views.xml
│   ├── campaign_archive_views.xml
│   ├── campaign_outcome_views.xml
│   ├── provider_event_views.xml
│   ├── delivery_reputation_views.xml
│   ├── compliance_alert_views.xml
│   ├── provider_health_views.xml
│   ├── retention_policy_views.xml
│   ├── retention_action_views.xml
│   ├── legal_hold_views.xml
│   ├── privacy_request_views.xml
│   ├── audit_export_views.xml
│   ├── dashboard_views.xml
│   ├── res_partner_views.xml
│   └── menu_views.xml
│
├── static/
│   └── src/
│       ├── js/
│       ├── xml/
│       └── scss/
│
└── tests/
    ├── __init__.py
    ├── test_consent.py
    ├── test_suppression.py
    ├── test_campaign_governance.py
    ├── test_approval_invalidation.py
    ├── test_eligibility.py
    ├── test_preflight.py
    ├── test_dispatch.py
    ├── test_resumability.py
    ├── test_retry.py
    ├── test_reconciliation.py
    ├── test_send_event.py
    ├── test_archive.py
    ├── test_provider_events.py
    ├── test_bounce.py
    ├── test_complaint.py
    ├── test_unsubscribe.py
    ├── test_reputation.py
    ├── test_alerts.py
    ├── test_retention.py
    ├── test_legal_hold.py
    ├── test_erasure.py
    ├── test_pseudonymization.py
    ├── test_audit_export.py
    ├── test_security.py
    └── test_integrity.py
```

Odoo 19 XML list views use `<list>` rather than the historical `<tree>` root.

---

# 5. Manifest

```python
{
    "name": "Newsletter Compliance",
    "summary": "Governed compliant email marketing for Odoo 19",
    "version": "19.0.1.0.0",
    "category": "Marketing/Email Marketing",
    "license": "LGPL-3",
    "depends": [
        "base",
        "contacts",
        "mail",
        "mass_mailing",
    ],
    "data": [
        "security/newsletter_compliance_groups.xml",
        "security/ir.model.access.csv",
        "security/newsletter_compliance_rules.xml",

        "data/sequences.xml",
        "data/suppression_reason_data.xml",
        "data/retention_policy_data.xml",
        "data/dispatch_cron.xml",
        "data/provider_event_cron.xml",
        "data/monitoring_cron.xml",
        "data/outcome_cron.xml",
        "data/retention_cron.xml",

        "views/consent_purpose_views.xml",
        "views/consent_record_views.xml",
        "views/suppression_entry_views.xml",
        "views/campaign_brand_views.xml",
        "views/mailing_mailing_views.xml",
        "views/campaign_approval_views.xml",
        "views/campaign_run_views.xml",
        "views/recipient_eligibility_views.xml",
        "views/send_event_views.xml",
        "views/campaign_archive_views.xml",
        "views/campaign_outcome_views.xml",
        "views/provider_event_views.xml",
        "views/delivery_reputation_views.xml",
        "views/compliance_alert_views.xml",
        "views/provider_health_views.xml",
        "views/retention_policy_views.xml",
        "views/retention_action_views.xml",
        "views/legal_hold_views.xml",
        "views/privacy_request_views.xml",
        "views/audit_export_views.xml",
        "views/dashboard_views.xml",
        "views/res_partner_views.xml",
        "views/menu_views.xml",
    ],
    "installable": True,
}
```

---

# 6. Canonical Data Model

## 6.1 Entity Relationship Overview

```text
res.partner
    │
    ├──< newsletter.consent.record >── newsletter.consent.purpose
    │
    ├──< newsletter.suppression.entry >── suppression.reason
    │
    └──< newsletter.recipient.eligibility
                         │
                         ▼
mailing.mailing ──< newsletter.campaign.run
      │                    │
      │                    ├──< recipient.eligibility
      │                    │          │
      │                    │          └──< newsletter.send.event
      │                    │
      │                    ├──── newsletter.campaign.archive
      │                    │
      │                    └──── newsletter.campaign.outcome
      │
      └──< newsletter.campaign.approval

provider.event ───────────────> recipient.eligibility/send.event

delivery.reputation ──────────> normalized recipient identity

legal.hold ───────────────────> governed records

retention.policy ─────────────> retention-aware records
retention.action ─────────────> retention audit ledger

privacy.request ──────────────> recipient discovery/actions
audit.export ─────────────────> campaign/privacy evidence package
```

---

# 7. Model Specifications

## 7.1 `newsletter.consent.purpose`

Purpose-specific communication authorization.

Key fields:

| Field | Type |
|---|---|
| `name` | Char |
| `code` | Char |
| `description` | Text |
| `requires_explicit_consent` | Boolean |
| `privacy_notice_version` | Char |
| `retention_policy_id` | Many2one |
| `active` | Boolean |
| `company_id` | Many2one |

Constraint:

```text
unique(code, company_id)
```

Examples:

- Corporate Newsletter
- Healthcare Newsletter
- Product Updates
- Events & Webinars
- Promotional Offers

---

## 7.2 `newsletter.consent.record`

Fields:

```text
reference
partner_id
email_original
email_normalized
purpose_id
status
given_at
expires_at
withdrawn_at
source
channel
privacy_notice_version
source_reference
consent_text
evidence_attachment_id
withdrawal_reason
withdrawal_source
supersedes_id
company_id
retention_policy_id
retain_until
legal_hold
identity_state
active
```

Status:

```text
pending
active
withdrawn
expired
invalidated
superseded
```

Finalized consent records cannot be substantively rewritten or deleted.

Re-consent creates a new record.

---

## 7.3 `newsletter.suppression.reason`

Fields:

```text
name
code
category
default_scope
auto_suppress
allow_reinstatement
active
company_id
```

Standard reasons:

```text
UNSUBSCRIBE
GLOBAL_OPT_OUT
HARD_BOUNCE
SOFT_BOUNCE_LIMIT
COMPLAINT
INVALID_ADDRESS
LEGAL_HOLD
COMPLIANCE_HOLD
PURPOSE_OPT_OUT
MANUAL
DATA_QUALITY
```

---

## 7.4 `newsletter.suppression.entry`

Fields:

```text
reference
partner_id
email_normalized
email_token
scope
purpose_id
mailing_list_id
reason_id
effective_from
effective_until
active
source
details
evidence_attachment_id
source_event_id
reinstated_at
reinstated_by_id
reinstatement_reason
identity_state
company_id
retention_policy_id
retain_until
legal_hold
```

Scope:

```text
global
purpose
mailing_list
```

Precedence:

```text
GLOBAL > PURPOSE > MAILING LIST
```

---

## 7.5 `newsletter.campaign.brand`

Fields:

```text
name
code
company_id
email_from
reply_to
physical_address
website_url
default_consent_purpose_id
active
```

Provides independent business-domain configuration without duplicating sending logic, consistent with the original requirement for independently configurable business domains.

---

## 7.6 `mailing.mailing` extension

Add:

```text
compliance_campaign_id
brand_id
consent_purpose_id
business_owner_id
compliance_owner_id
compliance_state

governance_version
approval_version
approval_content_hash

content_review_requested_at
content_review_requested_by_id
content_approved_by_id
content_approved_at
compliance_approved_by_id
compliance_approved_at

approvals_valid

current_campaign_run_id
campaign_run_ids

preflight_status
preflight_targeted_count
preflight_eligible_count
preflight_excluded_count

physical_address
```

Controlled fields affecting approval/preflight:

```text
subject
body_arch
body_html
preview
email_from
reply_to
attachment_ids
brand_id
consent_purpose_id
mailing_model_id
mailing_domain
contact_list_ids
physical_address
```

A controlled-field change invalidates approval and any existing preflight.

---

## 7.7 `newsletter.campaign.approval`

Append-only structured approval history.

Fields:

```text
mailing_id
approval_version
governance_version
approval_type
decision
reviewer_id
reviewed_at
comments
content_hash
subject_snapshot
recipient_snapshot
consent_purpose_id
brand_id
company_id
```

Approval type:

```text
content
compliance
```

Decision:

```text
approved
rejected
invalidated
```

---

## 7.8 `newsletter.campaign.run`

Represents one execution/preflight instance.

Fields:

```text
reference
mailing_id
campaign_compliance_id
governance_version
approval_version

state

preflight_started_at
preflight_completed_at
preflight_started_by_id

targeted_count
eligible_count
excluded_count

duplicate_count
missing_consent_count
withdrawn_consent_count
expired_consent_count
global_blacklist_count
suppression_count
invalid_email_count
already_sent_count

input_hash
result_hash
ruleset_version

frozen
frozen_at

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
soft_bounce_count
hard_bounce_count
complaint_count
unsubscribe_count

archive_id
outcome_id

last_reconciled_at
company_id
retention_policy_id
retain_until
legal_hold
```

---

## 7.9 `newsletter.recipient.eligibility`

This is both the preflight decision and the frozen recipient execution record.

Fields:

```text
campaign_run_id
mailing_id

partner_id
mailing_contact_id
recipient_model
recipient_res_id

email_original
email_normalized

status
reason_code
reason_detail
secondary_reason_codes

consent_record_id
suppression_entry_id
mailing_list_id
duplicate_of_id

evaluated_at
ruleset_version
evaluation_sequence
decision_hash
frozen

dispatch_state
delivery_state

dispatch_attempt_count
first_queued_at
last_queued_at
first_sent_at
last_attempt_at
next_retry_at

provider
provider_message_id

last_error_code
last_error_message

correlation_id
dispatch_lock_token
dispatch_locked_at

company_id
retention_policy_id
retain_until
legal_hold
identity_state
recipient_token
```

Eligibility status:

```text
eligible
excluded
```

Dispatch state:

```text
not_queued
queued
processing
sent
retry_pending
failed
blocked
cancelled
```

Delivery state:

```text
unknown
accepted
delivered
delayed
soft_bounce
hard_bounce
complaint
```

---

## 7.10 `newsletter.send.event`

Append-only canonical event ledger.

Fields:

```text
reference
campaign_run_id
mailing_id
eligibility_id
partner_id
mailing_contact_id
email_normalized
recipient_token

event_type
event_timestamp
processing_timestamp
attempt_number

provider
provider_message_id
provider_event_id
correlation_id

error_code
error_message
source

payload_hash
previous_event_hash
event_hash

company_id
retention_policy_id
retain_until
legal_hold
identity_state
```

Event types include:

```text
eligibility_passed
eligibility_excluded
queued
dispatch_started
dispatch_recheck_passed
dispatch_recheck_blocked
send_attempted
send_accepted
send_failed
send_failed_final
retry_scheduled
retry_started
delivered
delivery_delayed
soft_bounce
hard_bounce
complaint
unsubscribed
suppression_created
campaign_completed
campaign_cancelled
late_delivery_event
```

---

## 7.11 `newsletter.campaign.archive`

Application-level immutable exact as-sent evidence.

Fields:

```text
reference
mailing_id
campaign_run_id
campaign_compliance_id

governance_version
approval_version
archive_version

brand_id
consent_purpose_id

campaign_name_snapshot
subject_snapshot
preview_snapshot
email_from_snapshot
reply_to_snapshot
body_html_snapshot
body_text_snapshot
physical_address_snapshot

recipient_model_snapshot
recipient_domain_snapshot
mailing_lists_snapshot

targeted_count
eligible_count
excluded_count
sent_count
blocked_count
failed_count

approval_hash
preflight_hash
content_hash
archive_hash

created_at
created_by_id
locked
locked_at

retention_policy_id
retain_until
legal_hold
```

The original requirements require a read-only archived newsletter with campaign metadata and statistics.

---

## 7.12 `newsletter.campaign.archive.attachment`

Fields:

```text
archive_id
filename
mimetype
size
content_hash
attachment_copy_id
```

The archive must retain an archival copy or equivalent protected attachment evidence, not only a pointer to an editable source attachment.

---

## 7.13 `newsletter.campaign.outcome`

Evolving delivery outcome, separated from immutable content archive.

Fields:

```text
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

delivery_rate
bounce_rate
complaint_rate
unsubscribe_rate

health_state

observation_started_at
observation_until

finalized
finalized_at
outcome_hash
```

---

## 7.14 `newsletter.provider.event`

Raw inbound provider callback.

Fields:

```text
reference
provider
provider_event_id
provider_message_id
received_at
event_timestamp
raw_payload
payload_hash
processing_state
processing_attempts
next_retry_at
error_message

send_event_id
campaign_run_id
eligibility_id

company_id
retention_policy_id
retain_until
legal_hold
```

States:

```text
received
validated
processing
processed
unmatched
retry_pending
failed
ignored_duplicate
```

---

## 7.15 `newsletter.delivery.reputation`

Recipient-level deliverability aggregate.

Fields:

```text
email_normalized
recipient_token
partner_id

soft_bounce_count
lifetime_soft_bounce_count
hard_bounce_count
complaint_count

last_soft_bounce_at
last_hard_bounce_at
last_delivery_at
last_complaint_at

reputation_state
company_id
```

---

## 7.16 `newsletter.compliance.alert`

Fields:

```text
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
```

---

## 7.17 `newsletter.retention.policy`

Fields:

```text
name
code
data_category
retention_period_days
retention_trigger
expiry_action
legal_hold_allowed
pseudonymize_before_delete
active
company_id
```

---

## 7.18 `newsletter.retention.action`

Append-only privacy/retention audit ledger.

Fields:

```text
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
```

---

## 7.19 `newsletter.legal.hold`

Fields:

```text
reference
name
reason
legal_reference
start_at
released_at
status
owner_id
approved_by_id
scope_type
company_id
```

Hold targets should be represented by explicit relation/detail records rather than arbitrary Python expressions.

---

## 7.20 `newsletter.privacy.request`

Fields:

```text
reference
request_type
partner_id
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

company_id
```

Request types:

```text
access
export
correction
erasure
restriction
objection
consent_history
marketing_opt_out
```

---

## 7.21 `newsletter.audit.export`

Fields:

```text
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
company_id
```

---

# 8. State Machines

## 8.1 Consent

```text
PENDING
   │
   ▼
ACTIVE
   │
   ├── WITHDRAWN
   ├── EXPIRED
   ├── INVALIDATED
   └── SUPERSEDED
```

No transition from Withdrawn back to Active. Re-consent creates a new record.

---

## 8.2 Campaign Governance

```text
DRAFT
  │
  ▼
CONTENT REVIEW
  │
  ├── Reject ───────> REJECTED
  │
  ▼
COMPLIANCE REVIEW
  │
  ├── Reject ───────> REJECTED
  │
  ▼
PREFLIGHT REQUIRED
  │
  ▼
READY TO SEND
  │
  ▼
SENDING
  │
  ▼
COMPLETED
  │
  ▼
ARCHIVED
```

Any governed modification after approval:

```text
APPROVAL/PREFLIGHT
       ↓
INVALIDATED
       ↓
DRAFT / REVIEW REQUIRED
```

---

## 8.3 Preflight Run

```text
DRAFT
  ↓
EVALUATING
  ├── FAILED
  └── PASSED
        ↓
      FROZEN
        ↓
      QUEUED
```

Passed does not imply zero exclusions. It means every targeted recipient has a valid decision and the result reconciles.

---

## 8.4 Recipient Execution

```text
NOT QUEUED
    ↓
QUEUED
    ↓
PROCESSING
   /   |    \
  /    |     \
SENT RETRY   BLOCKED
      ↓
  PROCESSING
   /     \
 SENT    FAILED
```

`SENT` is terminal for submission.

Delivery outcomes subsequently attach to a sent record.

---

## 8.5 Provider Event

```text
RECEIVED
   ↓
VALIDATED
   ↓
PROCESSING
  /   |    \
 /    |     \
PROCESSED  UNMATCHED
             |
        RETRY_PENDING
             |
          FAILED
```

Duplicates become `IGNORED_DUPLICATE`.

---

## 8.6 Campaign Outcome

```text
OPEN
  ↓
OBSERVING
  ↓
FINALIZED
  ↓
LATE EVENT
  ↓
OUTCOME ADJUSTMENT
```

Finalized outcome records are not silently rewritten.

---

## 8.7 Privacy Request

```text
RECEIVED
  ↓
IDENTITY VERIFICATION
  ↓
DISCOVERY
  ↓
POLICY / LEGAL REVIEW
  ↓
APPROVED / PARTIALLY APPROVED / REJECTED
  ↓
EXECUTION
  ↓
COMPLETED
```

---

# 9. Recipient Eligibility Rules

Eligibility is:

```text
VALID RECIPIENT
AND
VALID EMAIL
AND
NOT DUPLICATE
AND
COMPANY ACCESS VALID
AND
NOT ODOO GLOBAL BLACKLIST
AND
NOT GLOBAL CUSTOM SUPPRESSION
AND
NOT APPLICABLE PURPOSE SUPPRESSION
AND
NOT APPLICABLE LIST SUPPRESSION / OPT-OUT
AND
VALID ACTIVE CONSENT FOR CAMPAIGN PURPOSE
AND
CONSENT NOT EXPIRED
AND
NOT ALREADY SENT IN SAME RUN
```

Evaluation order:

```text
1. Resolve recipient
2. Extract email
3. Normalize
4. Validate syntax
5. Deduplicate
6. Validate company
7. Native blacklist
8. Global suppression
9. Purpose suppression
10. Mailing-list suppression/opt-out
11. Consent existence
12. Consent status
13. Consent expiry
14. Already-sent check
15. Eligible
```

Primary exclusion reason is deterministic. Secondary conditions may be retained separately.

Reconciliation invariant:

```text
TARGETED = ELIGIBLE + EXCLUDED
```

---

# 10. Campaign Approval Integrity

Approval hash must cover at least:

```text
subject
preview
email_from
reply_to
body_html
attachment hashes
brand
consent purpose
recipient model
recipient domain
mailing lists
physical address
```

On change to any governed field:

```text
content approval = invalid
compliance approval = invalid
preflight = invalid
ready-to-send = revoked
```

Approval history remains intact.

---

# 11. Frozen Recipient Population

After successful preflight:

```text
newsletter.recipient.eligibility
WHERE
campaign_run_id = current_run
AND
status = eligible
```

becomes the authoritative dispatch population.

Do not resolve a fresh Odoo recipient domain during final send.

Implementation should hook Odoo's recipient-resolution pathway. `_get_recipients_domain()` is an existing Odoo 19 extension point, but the development team must regression-test all sending paths—including Send Now, Schedule and automatic/native batch behavior—to prove no bypass exists.

---

# 12. Send Enforcement

Before queue/send:

```python
if mailing.compliance_state != "ready":
    raise UserError(...)

run = mailing.current_campaign_run_id

if not run:
    raise UserError(...)

if run.state != "passed":
    raise UserError(...)

if not run.frozen:
    raise UserError(...)
```

Enforce at server level around:

```text
action_put_in_queue()
action_send_mail()
```

and any other Odoo 19 entry points discovered during regression testing.

Odoo 19's own modules override these actions to enforce prerequisites, demonstrating that these are valid extension hooks.

---

# 13. Dispatch-Time Compliance Check

Immediately before each send attempt recheck volatile controls:

```text
Consent still active?
Consent not expired?
Native blacklist active?
Global suppression active?
Purpose suppression active?
Mailing-list opt-out active?
```

Do not rerun segmentation.

If the recipient became ineligible:

```text
dispatch_state = blocked
```

not `failed`.

The original source explicitly states that addresses on the suppression list must not be sent to at dispatch time.

---

# 14. Retry Model

Retry only technical transient failures.

```text
retryable:
- temporary SMTP failure
- network timeout
- provider unavailable
- provider throttling

non-retryable:
- invalid recipient
- permanent provider rejection
- invalid configuration

compliance:
- consent withdrawn
- suppression activated
- global opt-out
```

Default algorithm:

```text
delay =
min(
  base_delay × 2^(attempt-1),
  max_delay
)
```

Example:

```text
1 → 60 sec
2 → 120 sec
3 → 240 sec
4 → 480 sec
5 → 960 sec
```

The original requirement calls for retry with configurable exponential backoff.

---

# 15. Provider Canonical Event Contract

```json
{
  "provider": "ses",
  "provider_event_id": "event-123",
  "provider_message_id": "message-456",
  "event_type": "hard_bounce",
  "event_timestamp": "2026-08-28T14:30:00Z",
  "email": "recipient@example.com",
  "campaign_id": "CMP-2026-000128",
  "campaign_run_id": "RUN-2026-000414",
  "bounce_type": "permanent",
  "bounce_subtype": "general",
  "smtp_status": "550",
  "diagnostic_code": "mailbox does not exist"
}
```

Core event types:

```text
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
```

Provider-specific representations must be translated into this contract.

---

# 16. APIs / Controllers

## 16.1 Provider Event API

```text
POST /newsletter-compliance/v1/events/{provider}
```

Responsibilities:

```text
authenticate callback
validate request size/content
persist raw event
compute payload hash
perform idempotency check
return 2xx rapidly
```

Business processing occurs asynchronously through Odoo cron.

---

## 16.2 Unsubscribe API

```text
GET/POST /newsletter-compliance/unsubscribe/{token}
```

Support choices:

```text
newsletter only
communication purpose
all marketing
```

Effects:

| Choice | Effect |
|---|---|
| Newsletter only | Mailing-list opt-out |
| Purpose | Withdraw applicable consent + purpose suppression |
| All marketing | Global suppression + Odoo blacklist |

The original requirement requires functional one-click unsubscribe behavior.

---

## 16.3 Privacy Request API

External self-service is optional.

If implemented:

```text
POST /newsletter-compliance/v1/privacy/request
```

The API only creates a pending request. It must not execute erasure without identity verification and internal policy review.

---

## 16.4 Internal APIs

Prefer normal Odoo model/service calls for:

```text
campaign approval
preflight
send execution
retention
audit exports
legal hold
```

Do not add HTTP APIs unless another system genuinely needs them.

---

# 17. Provider Event Security

Every provider adapter must implement:

```text
validate_webhook()
normalize_event()
extract_message_id()
extract_event_id()
classify_bounce()
```

Controls:

```text
TLS
signature/HMAC/certificate verification where supported
request-size limit
schema validation
rate limiting
replay/idempotency protection
provider-message correlation
```

Do not suppress an address based solely on an uncorrelated email value supplied by a callback.

---

# 18. Bounce / Complaint Rules

## Hard Bounce

```text
HARD_BOUNCE
  ↓
delivery_state = hard_bounce
  ↓
global suppression
  ↓
native Odoo blacklist
```

## Complaint

```text
COMPLAINT
  ↓
global suppression
  ↓
native Odoo blacklist
  ↓
compliance alert
```

## Soft Bounce

Configuration:

```text
threshold = configurable
window = configurable
```

Example:

```text
3 soft bounces in 90 days
→ SOFT_BOUNCE_LIMIT suppression
```

Do not globally suppress a single soft bounce.

---

# 19. Native Blacklist Synchronization

Two-way synchronization:

```text
Compliance Global Suppression
        ↓
Odoo Native Marketing Blacklist
```

and:

```text
Odoo Native Global Blacklist
        ↓
Compliance Suppression Entry
```

Purpose/list suppressions remain scoped.

Use origin flags/context to prevent synchronization loops.

---

# 20. As-Sent Archive

Archive creation occurs only after execution reconciliation.

Capture:

```text
Campaign Compliance ID
Run ID
Governance Version
Approval Version
Brand
Consent Purpose

Campaign Name
Subject
Preview
From
Reply-To
Exact HTML
Text representation
Physical address
Attachments + hashes

Recipient definition
Targeted count
Eligible count
Excluded count

Sent count
Blocked count
Failed count

Approval evidence
Preflight hash
Content hash
Archive hash

Execution start/end
Operator
```

The archive is then locked.

Application-level protection:

```text
write() blocked when locked
unlink() always blocked
hash verification supported
```

Important limitation:

**Odoo/PostgreSQL application controls are not equivalent to physical or cryptographic WORM storage.**

If regulatory requirements later demand true immutable storage, archive packages can additionally be exported to an object-lock/WORM repository.

---

# 21. Campaign Outcome

Delivery feedback remains separate from archive content.

```text
Archive
= immutable evidence of what was sent

Outcome
= evolving provider result
```

Outcome observation window:

```text
configurable, e.g. 72 hours or 7 days
```

At completion:

```text
finalized = True
outcome_hash = SHA-256(...)
```

Late provider events create adjustment records rather than silently modifying finalized evidence.

---

# 22. Event Integrity

Send Events:

```text
write = prohibited
unlink = prohibited
```

Optional chaining:

```text
event[n].previous_event_hash
=
event[n-1].event_hash
```

Campaign archive:

```text
archive_hash
```

Campaign outcome:

```text
outcome_hash
```

Preflight:

```text
input_hash
result_hash
```

Approval:

```text
approval_content_hash
```

Integrity verification must never silently replace a mismatching stored hash.

---

# 23. Retention & Privacy

The source requires retention sufficient for audit purposes while avoiding longer-than-necessary retention.

Retention categories:

```text
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
```

Expiry actions:

```text
retain
review
pseudonymize
anonymize
purge_payload
delete
```

Every destructive/pseudonymization action must generate a `newsletter.retention.action`.

---

# 24. Suppression Preservation After Privacy Erasure

A privacy action must not reactivate future marketing.

For long-term opt-out preservation:

```text
normalized email
      ↓
HMAC-SHA256(secret, normalized_email)
      ↓
suppression token
```

After pseudonymization:

```text
name = removed
partner_id = removed
plain email = removed

recipient_token = HMAC(...)
reason = GLOBAL_OPT_OUT
scope = global
```

Future imported email:

```text
normalize
  ↓
HMAC
  ↓
matches token
  ↓
BLOCK
```

Use HMAC rather than an unsalted public SHA-256 of email addresses.

---

# 25. Legal Hold

Retention execution order:

```text
candidate expired
     ↓
active legal hold?
    / \
  YES  NO
   |    |
 RETAIN apply policy
```

Hold release:

```text
release hold
  ↓
audit release
  ↓
record re-enters next retention cycle
```

Do not delete immediately as part of hold-release transaction.

---

# 26. Cron / Scheduled Jobs

| Job | Frequency | Responsibility |
|---|---|---|
| `newsletter_dispatch_worker` | Every minute | Process queued/retry recipients |
| `newsletter_provider_event_processor` | Every minute | Normalize/process inbound provider events |
| `newsletter_provider_event_retry` | Every 5 min | Retry provider event failures |
| `newsletter_provider_event_monitor` | Every 10 min | Backlog/unmatched health alerts |
| `newsletter_campaign_reconciliation` | Every 5 min | Reconcile active runs |
| `newsletter_outcome_refresh` | Every 5 min | Refresh campaign outcome metrics |
| `newsletter_outcome_finalizer` | Hourly | Finalize expired outcome windows |
| `newsletter_reputation_maintenance` | Daily | Recalculate/decay policy as required |
| `newsletter_alert_evaluator` | Every 5 min | Bounce/complaint/technical thresholds |
| `newsletter_retention_processor` | Daily | Policy-driven retention actions |
| `newsletter_retention_exception_monitor` | Daily | Raise retention failures/exceptions |
| `newsletter_audit_export_cleanup` | Daily | Remove expired generated export files |
| `newsletter_integrity_verifier` | Daily/Weekly | Verify archive/outcome/event integrity |

The dispatch worker must process records in bounded batches.

For concurrency, use safe row locking; PostgreSQL `FOR UPDATE SKIP LOCKED` may be justified for worker acquisition if implemented carefully.

---

# 27. Configuration

Central settings should include:

### Preflight

```text
preflight_batch_size
max_preflight_age_minutes
minimum_eligible_recipient_count
dispatch_time_recheck
```

### Dispatch

```text
dispatch_batch_size
maximum_retry_count
base_retry_delay_seconds
maximum_retry_delay_seconds
```

### Reputation

```text
soft_bounce_threshold
soft_bounce_window_days
bounce_warning_rate
bounce_critical_rate
complaint_warning_rate
complaint_critical_rate
unsubscribe_warning_rate
auto_suspend_on_critical_bounce
auto_suspend_on_critical_complaint
```

### Provider

```text
provider_code
webhook authentication settings
event_processing_retry_limit
```

Secrets must not be stored as ordinary readable business fields.

### Retention

```text
retention_batch_size
retention_dry_run
audit_export_expiry_days
```

---

# 28. Security Roles

Canonical roles:

```text
Newsletter Author
Content Approver
Compliance Reviewer
Campaign Operator
Compliance Administrator
Operations Administrator
Privacy Officer
Legal Hold Administrator
Audit Reviewer
```

Do not imply Content Approver → Compliance Reviewer.

Separation of duties must remain explicit.

---

# 29. Security Matrix

| Capability | Author | Content Approver | Compliance Reviewer | Operator | Compliance Admin | Privacy | Legal Hold Admin | Auditor |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Create/edit Draft | ✅ | | | | ✅ | | | R |
| Submit Content Review | ✅ | | | | ✅ | | | R |
| Approve Content | | ✅ | | | Controlled | | | R |
| Approve Compliance | | | ✅ | | Controlled | | | R |
| Run Preflight | | | ✅ | ✅ | ✅ | | | R |
| View eligibility | Limited | ✅ | ✅ | ✅ | ✅ | | | ✅ |
| Modify eligibility | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Start send | | | | ✅ | Controlled | | | |
| Cancel send | | | | ✅ | ✅ | | | |
| Retry technical failures | | | | ✅ | ✅ | | | |
| View raw provider event | | | Limited | Limited | ✅ | Controlled | | ✅ |
| Configure provider | | | | | ✅ | | | |
| View consent/suppression | Limited | | ✅ | Limited | ✅ | ✅ | | ✅ |
| Reinstate suppression | | | | | ✅ controlled | | | |
| Manage retention policies | | | | | ✅ | ✅ | | R |
| Execute privacy request | | | | | | ✅ | | R |
| Create/release legal hold | | | | | | | ✅ | R |
| Audit package export | | | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Modify send events | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Modify locked archive | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Modify retention ledger | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

`R` = read-only.

---

# 30. Multi-Company Security

All custom business records should contain `company_id` unless truly global.

Global rule pattern:

```python
[
    "|",
    ("company_id", "=", False),
    ("company_id", "in", company_ids),
]
```

For company-mandatory models, simplify to:

```python
[("company_id", "in", company_ids)]
```

Odoo recommends global multi-company rules to ensure group rules cannot accidentally broaden access across companies.

---

# 31. Public Method Security

Every workflow/public method must:

```text
ensure_one()/validate recordset
check current state
check required group
check record/company access
validate separation of duties
validate input
avoid unnecessary sudo()
```

Examples:

```text
action_approve_content
action_approve_compliance
action_run_compliance_preflight
action_start_campaign_execution
action_retry_failed
action_reinstate_suppression
action_execute_privacy_request
action_release_legal_hold
```

Do not trust method invocation simply because the corresponding button is hidden.

---

# 32. Functional Requirement Traceability

## Recipient / Consent

| Requirement | Implementation |
|---|---|
| FR-01 recipient source | Odoo recipient resolver |
| FR-02 exclude suppression list | R3 suppression evaluation |
| FR-03 valid campaign-category consent | R1 Consent + R3 eligibility |
| FR-04 valid email syntax | R3 normalization/validation |

## Newsletter / Campaign Governance

| Requirement | Implementation |
|---|---|
| FR-05 campaign metadata | `mailing.mailing` governance extensions |
| FR-06 approval/schedule trigger | Compliance workflow + native Odoo scheduling |
| FR-07 validate required metadata | `_validate_compliance_metadata()` |
| FR-08 Camel initiation API | Replaced by internal Odoo campaign execution |

The original FR-05–FR-08 implementation is SharePoint/Power-Automate-specific, but its metadata and approval intent is preserved in Odoo.

## Content / Personalization

| Requirement | Implementation |
|---|---|
| FR-09 retrieve approved HTML | Odoo mailing body is governed source |
| FR-10 exact approved version | governance version + approval hash |
| FR-11 recipient merge fields | Native Odoo rendering |
| FR-12 unsubscribe | Native/custom unsubscribe + header validation |

## Queue / Dispatch

| Requirement | Implementation |
|---|---|
| FR-13 provider send rate | Provider/dispatch configuration |
| FR-14 preparation/dispatch buffering | DB-backed recipient queue |
| FR-15 campaign provider tagging | campaign/run/correlation metadata |
| FR-16 dead-letter behavior | permanent failed recipient/event state |
| FR-17 exponential retry | R4 Retry Service |

## Feedback / Suppression

| Requirement | Implementation |
|---|---|
| FR-18 delivery/bounce/complaint ingestion | Provider Event API |
| FR-19 hard bounce/complaint suppression | R5 reputation + global suppression |
| FR-20 unsubscribe suppression | near-real-time unsubscribe processing |
| FR-21 soft-bounce escalation | reputation threshold |

## Archive

| Requirement | Implementation |
|---|---|
| FR-22 completion callback/stats | run reconciliation/outcome |
| FR-23 archive newsletter | `newsletter.campaign.archive` |
| FR-24 archive counts/metadata | archive + outcome |
| FR-25 read-only archive | locked server-side archive |

## Reporting

| Requirement | Implementation |
|---|---|
| FR-26 campaign counts | run/outcome dashboards |
| FR-27 recipient consent/send reconstruction | eligibility + event + consent/suppression history |
| FR-28 bounce/complaint alert | Compliance Alert Engine |

The source specifically requires targeted, sent, suppressed, delivered, bounced, complained and unsubscribed campaign metrics, as well as recipient-level reconstruction.

---

# 33. Non-Functional Requirement Traceability

| NFR | Implementation |
|---|---|
| NFR-01 provider-limited throughput | Batch dispatch/provider throttling configuration |
| NFR-02 unsubscribe ≤24h / near real-time | Transactional unsubscribe suppression |
| NFR-03 partial failure isolation | recipient-level dispatch state |
| NFR-04 resume without resend | terminal `sent` state + campaign run |
| NFR-05 no static cloud keys | provider secret abstraction/external secret store |
| NFR-06 PII protected in transit/at rest | TLS + DB/storage controls |
| NFR-07 consent/suppression restricted/logged | groups, ACLs, record rules, audit |
| NFR-08 least-privilege external integration | provider-specific constrained credentials |
| NFR-09 end-to-end traceability | approval → preflight → run → event → archive |
| NFR-10 configurable business domains | `newsletter.campaign.brand` |
| NFR-11 simple operator workflow | Approve → Preflight → Send |

NFR-03/04 explicitly require partial failures not to block other recipients and execution to resume without resending already-dispatched recipients.

---

# 34. Regulatory Control Traceability

| Control | Implementation |
|---|---|
| RC-01 provider production configuration | deployment/provider readiness |
| RC-02 DKIM | external DNS/provider configuration |
| RC-03 SPF | external DNS/provider configuration |
| RC-04 DMARC | external DNS/provider configuration |
| RC-05 bounce reputation | R5 monitoring/alerts |
| RC-06 complaint reputation | R5 monitoring/alerts |
| RC-07 valid consent category | Consent Purpose + R3 eligibility |
| RC-08 consent timestamp/source/scope | Consent Record |
| RC-09 withdrawal affects future sends | withdrawal + suppression + dispatch recheck |
| RC-10 purpose limitation | purpose-specific eligibility |
| RC-11 retention/erasure | R6 |
| RC-12 physical mailing address | Brand/campaign validation |
| RC-13 compliant unsubscribe | unsubscribe workflow |
| RC-14 accurate From/Reply-To/Subject | approval-controlled fields |
| RC-15 exact as-sent content retained | Campaign Archive |
| RC-16 restricted archive | RBAC + locked archive |

Provider-specific RC controls remain deployment responsibilities rather than Odoo application logic.

---

# 35. Operational Reconciliation Rules

## Preflight

```text
Targeted
=
Eligible + Excluded
```

## Execution

```text
Eligible
=
Sent
+ Failed
+ Blocked at Dispatch
+ Cancelled
```

## Campaign Outcome

Outcome counts must derive from recipient/event records rather than manually entered totals.

A reconciliation mismatch prevents final campaign completion/archive finalization.

---

# 36. Monitoring

Dashboards:

### Campaign Operations

```text
Active Runs
Queued
Sending
Retry Pending
Suspended
Failed Recipients
Completed Today
```

### Deliverability

```text
Sent
Delivered
Delayed
Soft Bounce
Hard Bounce
Complaint
Unsubscribe
Delivery Rate
Bounce Rate
Complaint Rate
```

### Compliance

```text
Missing Consent
Global Suppression
Purpose Suppression
New Complaints
New Hard Bounces
Open Alerts
```

### Privacy / Retention

```text
Records Approaching Expiry
Expired Pending Action
Records on Legal Hold
Privacy Requests Open
Privacy Requests Overdue
Retention Failures
```

---

# 37. Alert Types

```text
bounce_threshold
complaint_threshold
unsubscribe_spike
technical_failure_threshold
provider_event_failure
provider_event_backlog
unmatched_provider_events
reputation_risk
archive_integrity_failure
retention_failure
privacy_request_overdue
```

Severity:

```text
info
warning
critical
```

Deduplicate using:

```text
campaign_run + alert_type
```

for campaign-specific alerts.

---

# 38. Audit Package

Campaign audit export structure:

```text
CMP-2026-000128/
│
├── manifest.json
├── campaign.json
├── approvals.json
├── preflight-summary.json
├── recipient-decisions.csv
├── execution-summary.json
├── send-events.csv
├── campaign-outcome.json
├── suppression-actions.csv
├── integrity-manifest.json
├── newsletter.html
└── attachments/
```

`manifest.json` contains hashes of all package components.

Support:

```text
Masked Export
Full Evidence Export
```

Full recipient evidence requires elevated permission.

---

# 39. Recipient Audit Reconstruction

For any recipient, the platform must be able to reconstruct:

```text
Consent granted
Consent source
Consent purpose
Consent notice version
Consent withdrawn/expired

Suppressions
Suppression scope
Suppression cause

Campaign targeted
Eligibility decision
Decision reason

Campaign/run
Send attempt
Send accepted/failed

Delivery
Bounce
Complaint
Unsubscribe

Retention/pseudonymization actions
```

This is the canonical implementation of FR-27.

---

# 40. Dependency / Build Order

Strict dependency order:

```text
Foundation
   ↓
R1 Consent + Suppression
   ↓
R2 Campaign Governance
   ↓
R3 Eligibility / Preflight
   ↓
R4 Execution / Audit
   ↓
R5 Provider Feedback
   ↓
R6 Privacy / Retention
```

Do not start R4 production execution before R3 enforcement exists.

Do not start R5 suppression automation before R1 suppression history is stable.

Do not enable destructive R6 retention actions before archive/event integrity is stable.

---

# 41. Recommended Sprint Plan

Assumption: two-week sprints, one cross-functional Odoo team.

## Sprint 0 — Engineering Foundation

**Goals**

```text
Module skeleton
Development environment
CI/CD
Test framework
Security-group baseline
Coding standards
Logging conventions
Sequences
Multi-company design
```

Exit criteria:

```text
module installs cleanly
automated test pipeline working
Odoo 19 upgrade/update command tested
```

---

## Sprint 1 — R1 Consent

Epics:

```text
Consent Purpose
Consent Record
Contact integration
Consent history
Consent withdrawal
```

Deliverables:

```text
Consent list/form
Withdraw wizard
immutability rules
contact smart button
security tests
```

---

## Sprint 2 — R1 Suppression

Epics:

```text
Suppression Reason
Suppression Entry
Global/Purpose/List scope
Reinstatement
Native blacklist synchronization foundation
```

Exit criterion:

For a Contact, user can reconstruct consent and suppression position.

---

## Sprint 3 — R2 Campaign Governance I

Epics:

```text
Campaign ID
Brand
Consent Purpose on mailing
Compliance state
Required metadata
Content Review
Content Approval
```

Deliverables:

```text
mailing form extension
approval queue
self-approval prevention
```

---

## Sprint 4 — R2 Campaign Governance II

Epics:

```text
Compliance Approval
Approval History
Governance Version
Approval Hash
Controlled-field invalidation
Campaign rejection/reset/cancel
```

Exit criterion:

Approved campaign becomes `Preflight Required`, never directly Send Ready.

---

## Sprint 5 — R3 Recipient Eligibility

Epics:

```text
Recipient Resolver
Email normalization
Duplicate detection
Consent Service
Suppression Service
Native blacklist lookup
List opt-out
Eligibility reasons
```

Performance requirement:

Avoid per-recipient N+1 lookups.

---

## Sprint 6 — R3 Preflight & Enforcement

Epics:

```text
Campaign Run
Batch preflight
Frozen population
Preflight counts/reconciliation
Preflight UI
Send/Schedule blocking
Recipient-resolution enforcement
```

Exit criterion:

No send path can bypass successful frozen preflight.

---

## Sprint 7 — R4 Dispatch Execution

Epics:

```text
Dispatch worker
Recipient execution states
Concurrency locking
Retry classification
Exponential retry
Dispatch-time compliance recheck
No-resend invariant
```

Test interruption/restart scenarios.

---

## Sprint 8 — R4 Ledger & Archive

Epics:

```text
Send Event Ledger
Event hashing
Campaign reconciliation
Completion logic
As-Sent Archive
Attachment copy/hash
Recipient history
Integrity verification
```

Exit criterion:

Completed campaign can be reconstructed without relying on application log files.

---

## Sprint 9 — R5 Provider Event Integration

Epics:

```text
Provider Event model
Webhook controller
Provider Adapter API
Authentication
Idempotency
Message correlation
Canonical event creation
```

Implement the first actual production provider adapter.

---

## Sprint 10 — R5 Reputation & Monitoring

Epics:

```text
Hard bounce
Soft bounce
Complaint
Unsubscribe
Reputation model
Native blacklist two-way sync
Campaign Outcome
Threshold alerts
Provider-health monitor
Dashboards
```

Exit criterion:

Delivery feedback changes future eligibility automatically.

---

## Sprint 11 — R6 Retention & Legal Hold

Epics:

```text
Retention Policy
retain_until
Retention Processor
Dry Run
Legal Hold
Retention Action Ledger
Provider raw-payload purge
```

Initial production retention execution should run in dry-run mode.

---

## Sprint 12 — R6 Privacy & Audit

Epics:

```text
Privacy Request
Privacy Discovery
Pseudonymization
Suppression token preservation
Campaign Audit Package
Recipient Evidence Package
Export expiry
Integrity reporting
```

---

## Sprint 13 — Hardening / Production Readiness

Activities:

```text
End-to-end performance tests
100k+ recipient campaign test
Concurrent worker test
Interrupted-send recovery
Provider callback storm
Security penetration testing
ACL/record-rule review
Multi-company test
Privacy/retention dry run
Backup/restore
Disaster recovery
Observability
Operational runbooks
```

---

# 42. Release Gates

## R1 Gate

Must prove:

```text
consent evidence immutable
withdrawal auditable
suppression history durable
scope semantics correct
```

## R2 Gate

Must prove:

```text
author cannot self-approve
compliance approval separate
controlled changes invalidate approval
```

## R3 Gate

Must prove:

```text
every recipient gets a decision
counts reconcile
population freezes
all Send/Schedule paths blocked unless Ready
```

## R4 Gate

Must prove:

```text
partial failure isolation
restart without resend
event ledger immutable
archive exact and locked
```

## R5 Gate

Must prove:

```text
provider webhook authenticated
events idempotent
hard bounce/complaint suppress future sends
unsubscribe effective immediately
```

## R6 Gate

Must prove:

```text
legal hold stops purge
privacy erasure does not reactivate opt-out
retention actions auditable
audit export hashes verify
```

---

# 43. Testing Strategy

Required layers:

```text
Unit Tests
ORM Model Tests
Security Tests
Workflow Tests
Integration Tests
Provider Adapter Tests
Concurrency Tests
Performance Tests
End-to-End Campaign Tests
Retention/Privacy Tests
```

Particularly critical automated tests:

```text
RPC approval bypass attempt
RPC send bypass attempt
Cross-company access attempt
Duplicate send attempt
Worker crash/resume
Double webhook delivery
Complaint duplicate
Post-preflight unsubscribe
Post-preflight suppression
Archive modification attempt
Legal-hold purge attempt
Erasure followed by email re-import
```

---

# 44. Performance Principles

Do not execute:

```python
for recipient in recipients:
    search_consent()
    search_suppression()
    search_blacklist()
```

Instead:

```text
batch normalized emails
     ↓
bulk fetch consent
bulk fetch suppression
bulk fetch blacklist
bulk fetch opt-outs
     ↓
dictionary/index lookup
```

Recommended configurable starting values:

```text
Preflight batch: 2,000
Dispatch batch: 500
Retention batch: 1,000
```

Tune after realistic load testing.

---

# 45. Database Indexes

At minimum index:

```text
consent_record.email_normalized
consent_record.purpose_id
consent_record.status

suppression_entry.email_normalized
suppression_entry.email_token
suppression_entry.scope
suppression_entry.active

campaign_run.reference
campaign_run.mailing_id
campaign_run.state

recipient_eligibility.campaign_run_id
recipient_eligibility.email_normalized
recipient_eligibility.status
recipient_eligibility.dispatch_state
recipient_eligibility.provider_message_id

send_event.campaign_run_id
send_event.eligibility_id
send_event.provider_message_id
send_event.provider_event_id
send_event.event_type

provider_event.provider_event_id
provider_event.provider_message_id
provider_event.processing_state

delivery_reputation.email_normalized
delivery_reputation.recipient_token

retention-related retain_until fields
```

Introduce composite indexes after examining production query plans.

---

# 46. Unique Constraints

Recommended:

```text
Consent Purpose:
(code, company_id)

Provider Event:
(provider, provider_event_id)

Campaign ID:
compliance_campaign_id

Campaign Run:
reference

Send Event:
reference

Suppression:
prevent exact duplicate active suppression where practical

Audit/Retention:
reference
```

Do not over-constrain consent history in ways that prevent legitimate superseding records.

---

# 47. Logging Standard

Every operational log should include where applicable:

```text
campaign_id
campaign_run_id
eligibility_id
correlation_id
provider
provider_message_id
event_type
attempt
```

Do not routinely log:

```text
full HTML
raw consent evidence
full webhook payload
unmasked sensitive data
```

---

# 48. Deployment Prerequisites

Before production:

```text
Odoo 19 Community deployment hardened
PostgreSQL backup/restore tested
TLS everywhere
Outbound mail provider configured
SPF/DKIM/DMARC configured
provider callback endpoint reachable
provider webhook authentication configured
secret-management strategy established
worker/cron capacity validated
application monitoring configured
database monitoring configured
backup retention defined
privacy/retention policies approved
```

Original AWS-specific infrastructure constraints are no longer mandatory unless AWS SES is selected as the delivery provider.

---

# 49. Operational Runbooks Required

Create runbooks for:

```text
Campaign stuck in Sending
Retry backlog
Provider unavailable
Provider callback failure
High bounce rate
Complaint spike
Campaign suspension
Unmatched provider event
Incorrect suppression
Consent dispute
Archive integrity failure
Retention processing failure
Privacy request
Legal hold
Audit package generation
Database restore
```

---

# 50. Definition of Done for the Platform

The platform is production-ready when an auditor can choose any campaign and reconstruct:

```text
Who created it?
What exact content was approved?
Who content-approved it?
Who compliance-approved it?
What consent purpose applied?
Who was targeted?
Who was excluded?
Why was each excluded?
Which consent supported each eligible recipient?
What suppressions were considered?
Who was actually sent?
Which sends failed?
Which retries occurred?
Who was delivered/bounced/complained?
Which suppressions resulted?
What exactly was sent?
Has the evidence been altered?
What retention policy applies?
Is anything on legal hold?
```

And, for any individual recipient:

```text
What did they consent to?
When and how?
What notice/version applied?
Did they withdraw?
Are they suppressed?
For what scope?
Which campaigns considered them?
Why were they eligible/excluded?
Which messages were submitted?
What happened to those messages?
What personal data remains?
Why is it retained?
```

---

# 51. Final Lifecycle

```text
                       CONSENT
                          │
                          ▼
                  SUPPRESSION CHECK
                          │
                          ▼
                 CAMPAIGN AUTHORING
                          │
                          ▼
                   CONTENT REVIEW
                          │
                          ▼
                 COMPLIANCE REVIEW
                          │
                          ▼
                       APPROVED
                          │
                          ▼
                       PREFLIGHT
                          │
             ┌────────────┴────────────┐
             │                         │
          EXCLUDED                 ELIGIBLE
                                       │
                                       ▼
                               FROZEN POPULATION
                                       │
                                       ▼
                              DISPATCH-TIME CHECK
                                       │
                            ┌──────────┴─────────┐
                            │                    │
                         BLOCKED               SEND
                                                 │
                                                 ▼
                                          PROVIDER EVENT
                                                 │
                    ┌─────────────┬──────────────┼──────────────┐
                    ▼             ▼              ▼              ▼
                DELIVERED     SOFT BOUNCE    HARD BOUNCE    COMPLAINT
                                   │              │              │
                                   ▼              └──────┬───────┘
                              REPUTATION                 ▼
                                   │               SUPPRESSION
                                   │                    │
                                   └───────────┬────────┘
                                               ▼
                                      FUTURE ELIGIBILITY

Campaign Execution
        │
        ▼
As-Sent Archive
        │
        ▼
Campaign Outcome
        │
        ▼
Retention / Privacy
        │
        ▼
Audit Evidence
```

---

# 52. Final Recommendation to Development Team

Treat the six releases as **one domain model delivered incrementally**, not six separate customizations.

The architectural backbone is:

```text
Consent
    +
Suppression
    +
Campaign Governance
    +
Frozen Eligibility
    +
Recipient-Level Execution
    +
Append-Only Events
    +
Immutable Campaign Evidence
    +
Provider Feedback
    +
Privacy Lifecycle
```

Do not weaken these boundaries to simplify short-term coding.

The two controls most important to overall correctness are:

```text
1. No recipient can reach dispatch without a frozen R3 eligibility record.

2. No campaign or recipient compliance history is reconstructed from mutable
   application state when an append-only historical record should exist.
```

Those principles should guide implementation decisions throughout the project.

---

# 53. Odoo 19 Implementation Notes

The design has been aligned to currently published Odoo 19 behavior:

- `mailing.mailing` is the appropriate Email Marketing extension model.
- The native mailing form contains mailing-list/domain recipient selection, body HTML, From, Reply-To and attachments.
- `action_put_in_queue()` and `action_send_mail()` are established Odoo 19 extension points for pre-send validation.
- `_get_recipients_domain()` exists as a recipient-selection extension point.
- Odoo 19 list views use `<list>`.
- ACLs are additive, record rules require careful composition, and public methods require explicit security validation.

Before coding the final send-path override, developers must inspect and test the exact installed Odoo 19 build to confirm every Send Now, Schedule, batch-processing and A/B-testing execution path reaches the compliance enforcement layer. This should be treated as an implementation verification step, not as a change to the architecture.