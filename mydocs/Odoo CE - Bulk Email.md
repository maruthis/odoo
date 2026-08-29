# Odoo 19 Community Edition – Bulk Email

Redesign the solution around what Community already gives you, then add a **small custom Community add-on** for the compliance gaps. You do **not** need SharePoint, Power Automate, Camel, Studio, or Marketing Automation for the core requirements.

A key correction from the earlier design: **Odoo Studio and Marketing Automation are Enterprise-only**; Email Marketing is available in Community. ([Odoo](https://www.odoo.com/forum/help-1/can-use-marketing-automation-in-community-edition-if-we-buy-or-how-293785?utm_source=chatgpt.com "can use marketing automation in community edition if we buy or how | Odoo"))

Your original requirements need recipient sourcing, consent validation, suppression filtering, personalized newsletter sending, delivery/bounce/complaint processing, archival, reporting, and recipient-level traceability.

**Recommended Odoo 19 Community stack**

| Module | Technical module | Need | Role |
| --- | --- | --- | --- |
| Contacts | contacts | Must | Recipient/customer master |
| Discuss/Mail | mail | Must | Chatter, activities, notifications, mail infrastructure |
| Email Marketing | mass_mailing | Must | Newsletter composition, lists, campaign sending, unsubscribe, blacklist, statistics |
| Website | website | Recommended | Public subscribe/unsubscribe/consent pages |
| Custom Newsletter Compliance | newsletter_compliance | Must | Consent, approval, eligibility, suppression enhancement, audit archive |
| Custom Delivery Integration | within compliance module initially | Must for full FRs | Delivery/bounce/complaint event handling |

You can therefore start with just:

Contacts

   +

Email Marketing

   +

Newsletter Compliance (custom)

and add Website if you want Odoo itself to collect public consent.

**1\. Configure standard Email Marketing first**

Install **Email Marketing** and **Contacts**.

Odoo's Email Marketing should remain responsible for:

*   newsletter HTML/content;
*   mailing lists;
*   recipients;
*   scheduling;
*   personalization;
*   unsubscribe;
*   basic blacklist;
*   send statistics;
*   open/click tracking.

Odoo 19 includes dedicated Email Marketing functionality and documentation for mailing lists, unsubscriptions, and analytics. ([Odoo](https://www.odoo.com/documentation/19.0/applications/marketing/email_marketing/?utm_source=chatgpt.com "Index of /documentation/19.0/applications/marketing/email_marketing/"))

I would **not rebuild these features** in your custom module.

**2\. Proposed functional architecture**

Your new Odoo-native architecture becomes:

                        ODOO 19 COMMUNITY

┌─────────────────────────────────────────────────────────────┐

│                                                             │

│   Contacts                                                  │

│      │                                                      │

│      ├──── Recipient Profile                                │

│      └──── Consent / Communication History                  │

│                                                             │

│   Email Marketing                                           │

│      │                                                      │

│      ├──── Newsletter                                       │

│      ├──── Mailing Lists                                    │

│      ├──── Recipient Segmentation                           │

│      ├──── Personalization                                  │

│      ├──── Scheduling                                       │

│      └──── Standard Analytics                               │

│                                                             │

│   Newsletter Compliance \[Custom CE Module\]                  │

│      │                                                      │

│      ├──── Consent Register                                 │

│      ├──── Consent Purposes                                 │

│      ├──── Suppression Register                             │

│      ├──── Campaign Governance                              │

│      ├──── Recipient Eligibility Engine                     │

│      ├──── Campaign Run                                     │

│      ├──── Send Event Ledger                                │

│      ├──── Immutable Campaign Archive                       │

│      └──── Compliance Dashboard                             │

│                                                             │

└─────────────────────────────┬───────────────────────────────┘

                              │

                              ▼

                       SMTP / Email Provider

                              │

                 ┌────────────┴────────────┐

                 │                         │

              Delivery                 Events

                                      │

                                      ▼

                           Newsletter Compliance

The SMTP provider does not need to be AWS SES. It can later be:

*   SES;
*   SendGrid;
*   Mailgun;
*   SMTP relay;
*   another transactional mail provider.

That keeps your application provider-neutral.

**3\. Map your original requirements to Community Edition**

**Recipient sourcing**

Your specification requires campaign recipients from a configured source and exclusion of suppressed/unconsented recipients.

Use:

Contacts

     +

Mailing Contacts

     +

Mailing Lists

Add custom fields such as:

Brand

Recipient Type

Segment

Region

Country

Language

Communication Category

You can initially import recipients through CSV if another CRM remains the system of record.

**4\. Consent Purpose master**

Create a new model:

newsletter.consent.purpose

Examples:

| Code | Purpose |
| --- | --- |
| CORPORATE_NEWS | Corporate Newsletter |
| HEALTHCARE_NEWS | Healthcare Updates |
| PRODUCT_NEWS | Product Announcements |
| EVENT_MARKETING | Event Invitations |
| INSURANCE_NEWS | Insurance Newsletter |
| PROMOTIONS | Promotional Communication |

Each mailing must select exactly one consent purpose.

Fields:

Code

Name

Description

Brand

Privacy Notice Version

Requires Explicit Consent

Retention Days

Active

Company

**5\. Consent Register**

Create:

newsletter.consent.record

This is one of the most important custom models because your original requirement explicitly requires evidence of consent including timestamp, channel/source and purpose.

Recommended fields:

| Field | Example |
| --- | --- |
| Consent ID | CONS-000123 |
| Contact | John Smith |
| Email | john@example.com |
| Purpose | Healthcare Newsletter |
| Status | Active |
| Consent Given | 2026-08-18 10:23 |
| Source | Website |
| Channel | Web |
| Privacy Notice Version | PRIV-3.2 |
| Evidence | Form/attachment/reference |
| Expiry Date | optional |
| Withdrawal Date | optional |
| Withdrawal Reason | optional |

States:

Pending

Active

Withdrawn

Expired

Invalidated

Superseded

Never overwrite historical consent.

For example:

CONS-001

Healthcare Newsletter

Active

2025-01-15

↓

user withdraws

CONS-001

Healthcare Newsletter

Withdrawn

2026-08-20

If they later consent again:

CONS-002

Healthcare Newsletter

Active

2026-09-02

Preserve CONS-001.

**6\. Add a Consent smart button to Contact**

On res.partner, add:

Consents        3

Campaigns      14

Suppressions    1

Opening **Consents** should display the recipient's complete consent history.

The Contact screen could ultimately look like:

\-----------------------------------------------------

John Smith

john@example.com

\[Consents: 3\] \[Mailings: 14\] \[Suppressions: 1\]

Communication Eligibility

\-------------------------

Corporate Newsletter        ✓ Allowed

Healthcare Newsletter       ✓ Allowed

Promotional Offers          ✕ Suppressed

Insurance Newsletter        ✕ No Consent

\-----------------------------------------------------

This makes the compliance status understandable to business users.

**7\. Extend Email Marketing**

Extend the standard mailing model rather than create another campaign application.

Conceptually:

class MailingMailing(models.Model):

    \_inherit = "mailing.mailing"

Add:

Campaign Compliance ID

Brand

Consent Purpose

Compliance State

Compliance Owner

Content Approved By

Content Approved At

Compliance Approved By

Compliance Approved At

Preflight Status

Targeted Count

Eligible Count

Excluded Count

Archive Record

**8\. Campaign workflow**

Because Community does not have Studio approval rules, implement the workflow inside your module.

Use:

DRAFT

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

   ├── FAILED ──> Correct Campaign

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

Additional terminal states:

Rejected

Cancelled

Suspended

Failed

**9\. Campaign approval**

Create four roles:

Newsletter Author

Content Approver

Compliance Reviewer

Campaign Operator

Then enforce:

**Author**

Can:

Create

Edit

Submit for Review

Cannot:

Approve own content

Compliance approve

Send

**Content Approver**

Can:

Approve Content

Reject Content

**Compliance Reviewer**

Can:

Approve Compliance

Reject Compliance

Review Recipient Exclusions

**Campaign Operator**

Can:

Run Preflight

Schedule

Send

Monitor

The **Send** action must be disabled server-side unless:

state = ready\_to\_send

AND

preflight\_status = passed

This is much stronger than relying on UI visibility.

**10\. Preflight Eligibility Engine**

This is the central control.

Before sending, evaluate every recipient.

Recipient

   │

   ▼

Valid Email?

   ├── NO → Exclude

   │

   ▼ YES

Correct Segment?

   ├── NO → Exclude

   │

   ▼ YES

Valid Consent for Purpose?

   ├── NO → Exclude

   │

   ▼ YES

Consent Withdrawn/Expired?

   ├── YES → Exclude

   │

   ▼ NO

Global Blacklist?

   ├── YES → Exclude

   │

   ▼ NO

Applicable Suppression?

   ├── YES → Exclude

   │

   ▼ NO

Already Sent?

   ├── YES → Exclude

   │

   ▼ NO

ELIGIBLE

**11\. Preflight result screen**

Create:

newsletter.recipient.eligibility

After preflight, show something like:

| Status | Count |
| --- | --- |
| Target recipients | 10,000 |
| Eligible | 8,925 |
| Missing consent | 620 |
| Withdrawn consent | 105 |
| Global blacklist | 89 |
| Purpose suppression | 64 |
| Invalid email | 91 |
| Duplicate email | 72 |
| Already sent | 34 |

This is much better than silently excluding recipients.

The Compliance Reviewer should be able to click:

Missing Consent: 620

and inspect those 620 records.

**12\. Suppression Register**

Standard Odoo blacklist should remain in place, but supplement it with:

newsletter.suppression.entry

Your specification distinguishes hard bounce, complaint, unsubscribe and repeated soft bounce.

Fields:

Email

Contact

Scope

Brand

Consent Purpose

Reason

Effective From

Effective Until

Source Campaign

Evidence

Active

Reinstatement Status

Scopes:

GLOBAL

BRAND

PURPOSE

MAILING LIST

CAMPAIGN

This matters.

Imagine a recipient says:

"Stop sending me promotional offers, but I still want healthcare updates."

You should not globally blacklist them.

Therefore:

PROMOTIONAL

    → purpose suppression

Healthcare Newsletter

    → still eligible

![](file:////Users/maruti/Library/Group%20Containers/UBF8T346G9.Office/TemporaryItems/msohtmlclip/clip_image005.png)

**13\. Suppression reasons**

Configure:

Unsubscribe

Global Opt-Out

Hard Bounce

Repeated Soft Bounce

Spam Complaint

Invalid Address

Compliance Hold

Legal Restriction

Manual Suppression

Data Quality

Other

Do not allow users to type arbitrary suppression categories.

Use a controlled master.

**14\. Bounce rules**

Implement:

**Hard bounce**

Hard Bounce

     ↓

Immediate Suppression

**Complaint**

Spam Complaint

     ↓

Immediate Global Suppression

**Soft bounce**

Soft Bounce #1

      ↓

Count = 1

Soft Bounce #2

      ↓

Count = 2

Soft Bounce #3

      ↓

Threshold reached

      ↓

Suppress

Make threshold configurable:

Soft Bounce Threshold = 3

This directly implements FR-19 through FR-21.

**15\. Campaign Run**

Do not treat a mailing record itself as the execution record.

Create:

newsletter.campaign.run

Why?

Suppose:

Monthly Healthcare Newsletter

runs every month.

You want:

Campaign

     │

     ├── Run AUG-2026

     ├── Run SEP-2026

     └── Run OCT-2026

Each run gets:

Run ID

Campaign

Started At

Completed At

Recipients Targeted

Recipients Eligible

Excluded

Sent

Delivered

Bounced

Complained

Unsubscribed

Failed

This makes resuming and audit much cleaner.

![](file:////Users/maruti/Library/Group%20Containers/UBF8T346G9.Office/TemporaryItems/msohtmlclip/clip_image005.png)

**16\. Send Event Ledger**

Create:

newsletter.send.event

Events:

Targeted

Eligibility Passed

Eligibility Failed

Queued

Sent

Delivered

Delayed

Soft Bounce

Hard Bounce

Complaint

Unsubscribe

Suppressed

Retry

Failed

Store:

Event ID

Campaign Run

Recipient

Email

Event Type

Timestamp

Message ID

Attempt

Provider Response

Reason

This satisfies the requirement to reconstruct a recipient's consent basis and complete send history.

**17\. Recipient timeline**

On a contact, you should ultimately be able to see:

John Smith

john@example.com

15-Jan-2026

Consent Granted

Healthcare Newsletter

01-Feb-2026

Campaign HN-2026-02

Delivered

01-Mar-2026

Campaign HN-2026-03

Delivered

04-Apr-2026

Campaign HN-2026-04

Soft Bounce

04-May-2026

Campaign HN-2026-05

Delivered

12-Jun-2026

Consent Withdrawn

Promotional Newsletter

12-Jun-2026

Purpose Suppression Created

01-Jul-2026

Campaign PR-2026-07

Excluded: Consent Withdrawn

That becomes a very strong audit artifact.

**18\. Campaign Archive**

Create:

newsletter.campaign.archive

At completion, snapshot:

**Campaign identity**

Campaign ID

Campaign Run ID

Newsletter Name

Brand

Purpose

**Content**

Subject

From

Reply-To

HTML Content

Text Content

Attachments

**Audience**

Recipient Segment

Target Count

Eligible Count

Excluded Count

**Execution**

Approved By

Compliance Approved By

Sent By

Started At

Completed At

**Results**

Sent

Delivered

Bounced

Complained

Unsubscribed

Failed

**Integrity**

Add:

SHA-256 Content Hash

Archive Hash

Locked

Created At

The original specification specifically asks for a read-only, auditable as-sent record.

**19\. Archive locking**

Once:

state = archived

override:

write()

unlink()

and reject changes unless an explicitly controlled administrative operation exists.

For example:

def write(self, vals):

    if self.filtered("locked"):

        raise UserError(

            "Archived campaigns cannot be modified."

        )

    return super().write(vals)

Also disable deletion.

This provides stronger control than simply marking a view read-only.

**20\. Unsubscribe flow**

Use Odoo's existing unsubscribe capability as the front door where possible.

Then extend the outcome:

Recipient clicks unsubscribe

             │

             ▼

        Odoo opt-out

             │

             ▼

 Newsletter Compliance

             │

      ┌──────┴────────┐

      ▼               ▼

Withdraw consent   Suppression entry

      │               │

      └──────┬────────┘

             ▼

       Send-event log

Odoo's Email Marketing includes mailing-list and unsubscribe capabilities in current Odoo 19 documentation. ([Odoo](https://www.odoo.com/documentation/19.0/applications/marketing/email_marketing/?utm_source=chatgpt.com "Index of /documentation/19.0/applications/marketing/email_marketing/"))

**21\. Public consent collection**

If Website is installed:

Newsletter Subscription

Form:

Email\*

First Name

Last Name

☐ Healthcare Updates

☐ Corporate Newsletter

☐ Product Announcements

Privacy Notice v3.2

☐ I consent to receiving the selected communications.

\[Subscribe\]

Do **not** create one generic consent such as:

Marketing = YES

Instead create separate consent records:

john@example.com

Healthcare Updates

Active

john@example.com

Product Announcements

Active

This directly supports purpose limitation.

**22\. Double opt-in**

I strongly recommend:

Form Submitted

      ↓

Consent = Pending

      ↓

Confirmation Email

      ↓

Recipient clicks Confirm

      ↓

Consent = Active

Store:

Request timestamp

Confirmation timestamp

Consent purpose

Privacy notice version

Confirmation token reference

This provides better evidence than a simple list subscription.

**23\. Scheduling without Marketing Automation**

Marketing Automation is not available in Community Edition. ([Odoo](https://www.odoo.com/forum/help-1/can-use-marketing-automation-in-community-edition-if-we-buy-or-how-293785?utm_source=chatgpt.com "can use marketing automation in community edition if we buy or how | Odoo"))

You don't actually need it for your stated requirements.

Use:

Email Marketing scheduling

+

Odoo scheduled actions (ir.cron)

Custom scheduled actions can handle:

Consent expiry

Retention processing

Campaign scheduling checks

Bounce escalation

Statistics reconciliation

Archive generation

So we can recreate precisely the small subset of automation you need without building a general-purpose Marketing Automation product.

![](file:////Users/maruti/Library/Group%20Containers/UBF8T346G9.Office/TemporaryItems/msohtmlclip/clip_image005.png)

**24\. Recommended menu**

Email Marketing

│

├── Mailings

├── Mailing Lists

│

├── Compliance

│   ├── Dashboard

│   │

│   ├── Consent

│   │   ├── Consent Records

│   │   ├── Consent Purposes

│   │   ├── Withdrawals

│   │   └── Expiring Consent

│   │

│   ├── Suppression

│   │   ├── Suppression Register

│   │   ├── Hard Bounces

│   │   ├── Complaints

│   │   └── Reinstatements

│   │

│   ├── Campaign Governance

│   │   ├── Awaiting Content Review

│   │   ├── Awaiting Compliance Review

│   │   ├── Preflight Results

│   │   └── Campaign Runs

│   │

│   ├── Audit

│   │   ├── Campaign Archives

│   │   ├── Recipient History

│   │   └── Send Events

│   │

│   └── Configuration

│       ├── Consent Purposes

│       ├── Suppression Reasons

│       ├── Brands

│       ├── Retention Policies

│       └── Compliance Settings

**25\. What stays standard vs custom**

| Capability | Odoo CE | Custom |
| --- | --- | --- |
| Newsletter editor | ✅ |  |
| Mailing list | ✅ |  |
| Email send | ✅ |  |
| Scheduling | ✅ |  |
| Personalization | ✅ |  |
| Basic unsubscribe | ✅ |  |
| Standard blacklist | ✅ |  |
| Basic statistics | ✅ |  |
| Contacts | ✅ |  |
| Purpose-specific consent |  | ✅ |
| Consent evidence |  | ✅ |
| Compliance approvals |  | ✅ |
| Preflight eligibility |  | ✅ |
| Scoped suppression |  | ✅ |
| Soft-bounce policy |  | ✅ |
| Complaint management | Partial | ✅ |
| Campaign-run model |  | ✅ |
| Recipient event ledger | Partial | ✅ |
| Immutable archive |  | ✅ |
| Compliance dashboard |  | ✅ |
| Retention governance |  | ✅ |
