R3 should be **Preflight & Recipient Eligibility**. This is the release where the R1 consent/suppression foundation and the R2 campaign-governance workflow are connected to the actual Odoo mailing recipient population.

The key rule is:

> **A campaign may be approved, but it may not be sent until every intended recipient has been evaluated and the approved eligible population has been frozen for that campaign run.**

That directly addresses the original requirements to exclude suppressed recipients, require valid consent, prevent duplicate/resend behavior, and preserve recipient-level traceability.

Odoo 19’s standard mailing form exposes native **Send** and **Schedule** actions, and Odoo’s own modules override `action_put_in_queue()` and `action_send_mail()` to enforce preconditions before dispatch. That gives us a suitable server-side enforcement point. ([GitHub](https://github.com/odoo/odoo/blob/19.0/addons/mass_mailing/views/mailing_mailing_views.xml?utm_source=chatgpt.com "odoo/addons/mass_mailing/views/mailing_mailing_views.xml at 19.0 · odoo/odoo · GitHub"))

# R3 — Preflight & Recipient Eligibility

## 1\. R3 scope

| Capability | R3 |
| --- | --- |
| Resolve campaign recipients | ✅ |
| Normalize recipient emails | ✅ |
| Deduplicate recipients | ✅ |
| Validate email presence/format | ✅ |
| Validate purpose-specific consent | ✅ |
| Evaluate consent expiry/withdrawal | ✅ |
| Check Odoo global blacklist | ✅ |
| Check custom scoped suppression | ✅ |
| Check mailing-list opt-out | ✅ |
| Detect already-sent recipient | ✅ |
| Create recipient eligibility records | ✅ |
| Preflight summary/dashboard | ✅ |
| Freeze eligible recipient population | ✅ |
| Block Send/Schedule unless passed | ✅ |
| Invalidate preflight after governed changes | ✅ |
| Campaign Run foundation | ✅ |
| Actual delivery events | R4/R5 |
| Bounce/complaint feedback | R5 |

* * *

# 2\. R3 architecture

The process becomes:

    R1
    Consent + Suppression
            │
            │
            ▼
    R2
    Approved Campaign
            │
            ▼
    Preflight Required
            │
            ▼
    R3 ELIGIBILITY ENGINE
            │
            ├── Resolve recipients
            ├── Normalize email
            ├── Validate email
            ├── Deduplicate
            ├── Validate consent
            ├── Check consent expiry/withdrawal
            ├── Check Odoo blacklist
            ├── Check custom suppression
            ├── Check list opt-out
            └── Check already sent
            │
            ▼
    Recipient Eligibility Ledger
            │
            ├── Eligible
            └── Excluded + reason
            │
            ▼
    Freeze eligible population
            │
            ▼
    READY TO SEND

* * *

# 3\. Add two core models

Create:

    newsletter.campaign.run
    newsletter.recipient.eligibility

These should be separate from `mailing.mailing`.

Why?

Because:

    mailing.mailing

is the campaign definition.

Whereas:

    newsletter.campaign.run

is one concrete execution attempt.

Example:

    Healthcare Monthly Newsletter
    CMP-2026-000128
    
    Run 1:
    RUN-2026-000414
    28-Aug-2026
    
    Run 2:
    RUN-2026-000589
    28-Sep-2026

That distinction becomes important later for retries, resumability, and audit.

* * *

# 4\. Campaign Run model

## Model

    _name = "newsletter.campaign.run"

## Fields

| Field | Type |
| --- | --- |
| reference | Char |
| mailing_id | Many2one mailing.mailing |
| campaign_compliance_id | Related/Char |
| governance_version | Integer |
| state | Selection |
| preflight_started_at | Datetime |
| preflight_completed_at | Datetime |
| preflight_started_by_id | Many2one |
| targeted_count | Integer |
| eligible_count | Integer |
| excluded_count | Integer |
| duplicate_count | Integer |
| missing_consent_count | Integer |
| withdrawn_consent_count | Integer |
| expired_consent_count | Integer |
| global_blacklist_count | Integer |
| suppression_count | Integer |
| invalid_email_count | Integer |
| already_sent_count | Integer |
| input_hash | Char |
| result_hash | Char |
| frozen | Boolean |
| company_id | Many2one |

State:

    draft
    evaluating
    passed
    failed
    invalidated
    sending
    completed
    cancelled

* * *

# 5\. Campaign Run sequence

Use:

    RUN-2026-000001

Sequence:

    <record id="seq_newsletter_campaign_run" model="ir.sequence">
        <field name="name">Newsletter Campaign Run</field>
        <field name="code">newsletter.campaign.run</field>
        <field name="prefix">RUN-%(year)s-</field>
        <field name="padding">6</field>
    </record>

* * *

# 6\. Recipient Eligibility model

Create:

    newsletter.recipient.eligibility

One record represents:

> “Why was this recipient eligible or excluded from this exact campaign run?”

Fields:

| Field | Purpose |
| --- | --- |
| campaign_run_id | Run |
| mailing_id | Campaign |
| partner_id | Contact if available |
| mailing_contact_id | Mailing contact if applicable |
| recipient_model | Original model |
| recipient_res_id | Original record ID |
| email_original | Original email |
| email_normalized | Normalized email |
| status | Eligible / Excluded |
| reason_code | Primary decision |
| reason_detail | Explanation |
| consent_record_id | Consent used |
| suppression_entry_id | Applicable suppression |
| mailing_list_id | Relevant list |
| evaluated_at | Timestamp |
| ruleset_version | Version |
| evaluation_sequence | Processing order |
| decision_hash | Integrity hash |
| company_id | Company |

* * *

# 7\. Eligibility states

Use:

    status = fields.Selection([
        ("eligible", "Eligible"),
        ("excluded", "Excluded"),
    ])

Keep the high-level status simple.

The real explanation goes into:

    reason_code

* * *

# 8\. Reason codes

I recommend controlled values:

    reason_code = fields.Selection([
        ("eligible", "Eligible"),
        ("missing_email", "Missing Email"),
        ("invalid_email", "Invalid Email"),
        ("duplicate_email", "Duplicate Email"),
        ("missing_consent", "Missing Consent"),
        ("pending_consent", "Pending Consent"),
        ("withdrawn_consent", "Withdrawn Consent"),
        ("expired_consent", "Expired Consent"),
        ("invalidated_consent", "Invalidated Consent"),
        ("wrong_consent_purpose", "Wrong Consent Purpose"),
        ("global_blacklist", "Global Blacklist"),
        ("global_suppression", "Global Suppression"),
        ("purpose_suppression", "Purpose Suppression"),
        ("mailing_list_suppression", "Mailing List Suppression"),
        ("mailing_list_opt_out", "Mailing List Opt-Out"),
        ("already_sent", "Already Sent"),
        ("company_mismatch", "Company Mismatch"),
        ("manual_hold", "Manual Hold"),
        ("other", "Other"),
    ])

Do not use free-text as the primary reason because reporting later depends on deterministic reason codes.

* * *

# 9\. Eligibility decision order

The decision order matters.

I recommend:

    1  Resolve recipient
    2  Obtain email
    3  Normalize email
    4  Validate syntax
    5  Detect duplicate
    6  Validate company
    7  Check global Odoo blacklist
    8  Check global custom suppression
    9  Check purpose suppression
    10 Check mailing-list suppression / opt-out
    11 Find valid consent for campaign purpose
    12 Check consent status
    13 Check expiry
    14 Check already-sent status
    15 ELIGIBLE

Why this order?

Because cheap deterministic checks should run before more expensive consent/history lookups.

* * *

# 10\. Eligibility algorithm

Conceptually:

    def evaluate_recipient(
        campaign,
        campaign_run,
        recipient,
        seen_emails,
    ):
        email = normalize_email(recipient.email)
    
        if not email:
            return EXCLUDE("missing_email")
    
        if not valid_email(email):
            return EXCLUDE("invalid_email")
    
        if email in seen_emails:
            return EXCLUDE("duplicate_email")
    
        seen_emails.add(email)
    
        if is_odoo_blacklisted(email):
            return EXCLUDE("global_blacklist")
    
        suppression = find_global_suppression(email)
    
        if suppression:
            return EXCLUDE(
                "global_suppression",
                suppression=suppression,
            )
    
        suppression = find_purpose_suppression(
            email,
            campaign.consent_purpose_id,
        )
    
        if suppression:
            return EXCLUDE(
                "purpose_suppression",
                suppression=suppression,
            )
    
        if mailing_list_opted_out(recipient, campaign):
            return EXCLUDE("mailing_list_opt_out")
    
        consent = find_effective_consent(
            email=email,
            purpose=campaign.consent_purpose_id,
            company=campaign.company_id,
        )
    
        if not consent:
            return EXCLUDE("missing_consent")
    
        if consent.status == "withdrawn":
            return EXCLUDE(
                "withdrawn_consent",
                consent=consent,
            )
    
        if consent.status == "expired":
            return EXCLUDE(
                "expired_consent",
                consent=consent,
            )
    
        if already_sent(campaign_run, email):
            return EXCLUDE("already_sent")
    
        return ELIGIBLE(consent=consent)

* * *

# 11\. Email validation

Do not invent your own complex RFC parser.

Use Odoo's email utilities where possible, with fallback normalization in your own service layer.

At minimum:

    trim whitespace
    lowercase comparison value
    preserve original email separately

Do not modify the recipient's actual stored email just because the comparison form is normalized.

Store both:

    email_original
    email_normalized

* * *

# 12\. Recipient resolution

This is an important technical area because Odoo can send to more than just mailing contacts.

The standard mailing form supports recipient models and mailing lists. ([GitHub](https://github.com/odoo/odoo/blob/19.0/addons/mass_mailing/views/mailing_mailing_views.xml?utm_source=chatgpt.com "odoo/addons/mass_mailing/views/mailing_mailing_views.xml at 19.0 · odoo/odoo · GitHub"))

Therefore, R3 should not hard-code:

    res.partner only

Implement an adapter-style method:

    def _get_compliance_recipient_candidates(self):
        ...

Each candidate should resolve to a normalized structure:

    {
        "model": "res.partner",
        "res_id": 123,
        "partner_id": 123,
        "mailing_contact_id": False,
        "email": "john@example.com",
        "mailing_list_ids": [...],
    }

or:

    {
        "model": "mailing.contact",
        "res_id": 456,
        "partner_id": False,
        "mailing_contact_id": 456,
        "email": "john@example.com",
        "mailing_list_ids": [12],
    }

This keeps the engine reusable.

* * *

# 13\. Consent lookup

Create a service:

    services/consent_service.py

Method:

    get_effective_consent(
        email,
        purpose_id,
        company_id,
        evaluation_time,
    )

Search for:

    email_normalized = recipient
    purpose_id = campaign purpose
    company_id = campaign company
    status = active
    given_at <= evaluation time
    expires_at is null OR expires_at > evaluation time

If multiple active consents somehow exist:

*   choose the newest valid one;
    
*   flag a data-quality warning;
    
*   do not silently ignore the duplication forever.
    

R1 should ideally prevent overlapping active consents, but R3 should still be defensive.

* * *

# 14\. Suppression lookup

Create:

    services/suppression_service.py

Method:

    get_applicable_suppression(
        email,
        purpose_id,
        mailing_list_ids,
        evaluation_time,
    )

Precedence:

    GLOBAL
        >
    PURPOSE
        >
    MAILING LIST

Return the strongest applicable suppression.

* * *

# 15\. Odoo blacklist check

Standard Odoo Email Marketing already has global blacklist behavior. R3 should therefore check both:

    Odoo standard global blacklist
    +
    newsletter.suppression.entry

This avoids accidentally allowing an email that was blocked through normal Odoo Email Marketing.

Do not duplicate every native blacklist record into your own custom model just for preflight. Treat the native blacklist as one authoritative global exclusion source.

* * *

# 16\. Mailing-list opt-out

For campaigns targeting mailing lists, check Odoo's mailing subscription/opt-out state.

This is distinct from:

    Global blacklist

and from:

    Purpose-level consent

The hierarchy becomes:

    Active consent may exist
            │
            ▼
    Recipient opted out of specific mailing list?
            │
           YES
            ▼
    Exclude

Consent alone should not override a more recent specific opt-out.

* * *

# 17\. Duplicate handling

Duplicates should be handled by:

    normalized email

within the same run.

Example:

    res.partner #123
    john@example.com
    
    mailing.contact #721
    John@Example.com

These are one recipient for dispatch purposes.

The first deterministic candidate can win, but the duplicate record should still create an eligibility entry:

    Excluded
    Reason: duplicate_email
    Duplicate Of: eligibility record #...

Add:

    duplicate_of_id

to the eligibility model.

* * *

# 18\. Already-sent rule

Your original NFR requires resumability without sending again to recipients already successfully dispatched in that campaign run.

R3 should establish the decision interface even though the complete send-event ledger comes later.

For now, add:

    newsletter.campaign.run.recipient_frozen

or simply use eligibility records plus a `dispatch_state`.

Suggested field:

    dispatch_state = fields.Selection([
        ("not_sent", "Not Sent"),
        ("queued", "Queued"),
        ("sent", "Sent"),
    ])

R4 will expand this substantially.

* * *

# 19\. Preflight execution

Button:

    Run Compliance Preflight

Allowed only when:

    compliance_state = preflight_required

and:

    content approval valid
    compliance approval valid

* * *

# 20\. Preflight method

Conceptual implementation:

    def action_run_compliance_preflight(self):
        self.ensure_one()
    
        if self.compliance_state != "preflight_required":
            raise UserError(
                _("Campaign is not ready for preflight.")
            )
    
        self._verify_approval_integrity()
    
        run = self.env[
            "newsletter.campaign.run"
        ].create({
            "mailing_id": self.id,
            "governance_version": self.governance_version,
            "state": "evaluating",
            "preflight_started_at": fields.Datetime.now(),
            "preflight_started_by_id": self.env.user.id,
        })
    
        recipients = self._get_compliance_recipient_candidates()
    
        seen_emails = set()
    
        for sequence, recipient in enumerate(recipients, start=1):
            result = self.env[
                "newsletter.eligibility.service"
            ].evaluate(
                campaign=self,
                campaign_run=run,
                recipient=recipient,
                seen_emails=seen_emails,
            )
    
            self.env[
                "newsletter.recipient.eligibility"
            ].create(
                self._prepare_eligibility_vals(
                    run,
                    recipient,
                    result,
                    sequence,
                )
            )
    
        run._finalize_preflight()
    
        return self._open_preflight_result(run)

In practice the eligibility service will be a normal Python service/helper, not necessarily an Odoo model.

* * *

# 21\. Batch processing

Do not load 100,000 recipient records into Python memory at once.

Use batching.

Example configuration:

    Preflight Batch Size = 2,000

Algorithm:

    Resolve IDs
        ↓
    Batch 1: 1–2000
    Batch 2: 2001–4000
    ...

Use bulk searches for:

    consents
    suppressions
    blacklists

rather than one database query per recipient.

Avoid:

    for recipient:
        search consent
        search suppression
        search blacklist

because that creates an N+1-query problem.

* * *

# 22\. Efficient evaluation design

For each batch:

    Collect normalized emails
            │
            ├── fetch blacklist records in one query
            ├── fetch active suppressions in one query
            ├── fetch relevant consent records in one query
            └── fetch mailing-list opt-outs in one query

Build dictionaries:

    blacklisted_emails = {...}
    
    consents_by_email = {
        "a@example.com": consent_record,
    }
    
    suppressions_by_email = {
        "b@example.com": suppression_record,
    }

Then evaluate in memory.

This will scale much better.

* * *

# 23\. Preflight summary

After processing, show:

    CMP-2026-000128
    RUN-2026-000414
    
    PRE-FLIGHT PASSED
    
    Targeted                        25,000
    
    Eligible                        21,620
    
    Excluded                         3,380
    --------------------------------------
    Missing consent                  1,850
    Withdrawn consent                  245
    Expired consent                    110
    Global blacklist                   420
    Purpose suppression                190
    Mailing-list opt-out               155
    Invalid email                      180
    Duplicate email                    210
    Already sent                        20

* * *

# 24\. Pass/fail semantics

Important: a campaign with excluded recipients is **not automatically a failed preflight**.

For example:

    25,000 targeted
    21,620 eligible
    3,380 legitimately excluded

can still be:

    PASSED

because exclusion is the intended compliance behavior.

Preflight should fail when there is a **system/control problem**, such as:

    Consent Purpose missing
    Approvals invalid
    Recipient resolution failed
    Eligibility evaluation incomplete
    Database/API failure
    Eligibility records don't reconcile
    Eligible population cannot be frozen

This is an important distinction.

* * *

# 25\. Reconciliation rule

Always require:

    Targeted Count
    =
    Eligible Count
    +
    Excluded Count

If not:

    Preflight FAILED

Similarly:

    Excluded Count
    =
    sum(all exclusion reason counts)

unless you explicitly permit multiple exclusion reasons per person.

I recommend one **primary exclusion reason** plus optional secondary flags.

That makes reconciliation easy.

* * *

# 26\. Primary vs secondary reasons

Example:

    john@example.com
    
    No consent
    AND
    Globally blacklisted

Primary reason should follow precedence.

For example:

    PRIMARY:
    global_blacklist
    
    SECONDARY:
    missing_consent

Add optional:

    secondary_reason_codes

as JSON or a related detail model.

For R3 MVP, one primary reason is sufficient.

* * *

# 27\. Freeze eligible population

This is critical.

When preflight passes:

    Eligibility Records = Frozen
    Campaign Run = Frozen

The actual send must use:

    eligible recipients from this campaign run

—not re-resolve the original mailing domain at send time.

Otherwise:

    10:00 preflight
    10:05 contact added to list
    10:10 Send

could send to a person who was never evaluated.

So:

> **Preflight must freeze the recipient population.**

* * *

# 28\. Frozen eligibility fields

Add to eligibility:

    frozen = fields.Boolean(default=False)

and Run:

    frozen = fields.Boolean(default=False)
    frozen_at = fields.Datetime()

When finalized:

    eligible/excluded status cannot be edited

except by invalidating the entire run and executing a new preflight.

* * *

# 29\. Campaign relationship

Extend `mailing.mailing`:

    campaign_run_ids = fields.One2many(
        "newsletter.campaign.run",
        "mailing_id",
    )
    
    current_campaign_run_id = fields.Many2one(
        "newsletter.campaign.run",
        readonly=True,
    )
    
    preflight_targeted_count = fields.Integer(
        related="current_campaign_run_id.targeted_count",
    )
    
    preflight_eligible_count = fields.Integer(
        related="current_campaign_run_id.eligible_count",
    )
    
    preflight_excluded_count = fields.Integer(
        related="current_campaign_run_id.excluded_count",
    )

* * *

# 30\. Successful preflight transition

On successful completion:

    mailing.compliance_state
    preflight_required
            ↓
    ready

and:

    preflight_status = passed

Also:

    current_campaign_run_id = RUN-...

* * *

# 31\. Governed changes invalidate preflight

R2 invalidated approvals after significant changes.

Now add another layer:

    Subject changed
    Body changed
    Consent Purpose changed
    Recipient definition changed
    Brand changed
    Sender changed

causes:

    Current Preflight Run → INVALIDATED

and:

    compliance_state = draft/content review

depending on the change.

Even a recipient-only change should invalidate the frozen population.

* * *

# 32\. Consent changes after preflight

This is trickier.

Suppose:

    10:00 preflight passes
    10:05 John withdraws consent
    10:10 send begins

A frozen preflight must **not** override a newer withdrawal.

Therefore, use two controls:

### Preflight

Full eligibility calculation.

### Dispatch-time safety check

Immediately before queuing an individual recipient:

    Is recipient now globally suppressed?
    Has consent been withdrawn since preflight?

If yes:

    do not send

This is necessary because the original requirement says a suppressed address must not be sent to **at time of dispatch**, not merely at preflight time.

* * *

# 33\. R3 dispatch-time check

For now implement a lightweight method:

    def _check_recipient_dispatch_eligibility(
        self,
        eligibility_record,
    ):
        ...

Check only volatile controls:

    global blacklist
    active suppression
    consent withdrawal
    consent expiry

Do not rerun the entire campaign segmentation.

If status changed:

    eligibility.dispatch_state = blocked

Later R4 records a formal send event.

* * *

# 34\. Server-side send blocking

This is where R3 becomes enforceable.

Override:

    action_put_in_queue()

and:

    action_send_mail()

Odoo itself uses these methods and other native modules already override them for prerequisite checks. ([GitHub](https://github.com/odoo/odoo/blob/19.0/addons/marketing_card/models/mailing_mailing.py?utm_source=chatgpt.com "odoo/addons/marketing_card/models/mailing_mailing.py at 19.0 · odoo/odoo · GitHub"))

Example:

    def _assert_compliance_ready(self):
        for mailing in self:
            if mailing.mailing_type != "mail":
                continue
    
            if mailing.compliance_state != "ready":
                raise UserError(
                    _(
                        "Campaign %(campaign)s cannot be sent. "
                        "Compliance preflight has not passed."
                    ) % {
                        "campaign":
                            mailing.compliance_campaign_id
                            or mailing.display_name
                    }
                )
    
            run = mailing.current_campaign_run_id
    
            if (
                not run
                or run.state != "passed"
                or not run.frozen
            ):
                raise UserError(
                    _("A valid frozen campaign run is required.")
                )

Then:

    def action_put_in_queue(self):
        self._assert_compliance_ready()
        return super().action_put_in_queue()

and:

    def action_send_mail(self, res_ids=None):
        self._assert_compliance_ready()
        return super().action_send_mail(res_ids=res_ids)

Exact method signatures should be checked against your deployed Odoo 19 source.

* * *

# 35\. What about Odoo `action_launch`?

The UI currently exposes `action_launch` for Send and `action_schedule` for scheduling. ([GitHub](https://github.com/odoo/odoo/blob/19.0/addons/mass_mailing/views/mailing_mailing_views.xml?utm_source=chatgpt.com "odoo/addons/mass_mailing/views/mailing_mailing_views.xml at 19.0 · odoo/odoo · GitHub"))

I recommend two layers:

    UI layer:
    hide/disable Send/Schedule until Ready

plus:

    server layer:
    block queue/send methods

If testing shows `action_launch` can bypass the lower-level hooks in your exact deployment, override it too.

Never rely only on button visibility.

* * *

# 36\. Important enforcement question: how do we ensure only frozen recipients are sent?

This is the most technically important part of R3.

Standard Odoo normally resolves recipients from its mailing model/domain.

Our compliance system needs the actual dispatch population to be:

    Eligibility records
    WHERE
    campaign_run_id = current run
    AND status = eligible

There are two possible designs.

## Option A — override recipient domain

Modify the mailing's recipient-resolution logic so it resolves only frozen eligible record IDs.

Best when the campaign recipient model is stable.

## Option B — materialize an approved mailing list

Create a temporary/frozen internal mailing list containing exactly the eligible recipients.

Then send the Odoo mailing to that list.

For Odoo Community and maintainability, I prefer **Option A if recipients are `mailing.contact` or one predictable model**; otherwise a controlled frozen recipient list may be easier operationally.

* * *

# 37\. Recommended R3 approach

Create:

    newsletter.campaign.run.recipient

only if needed, but in most cases:

    newsletter.recipient.eligibility

already contains the frozen population.

Add helper:

    def _get_frozen_eligible_res_ids(self):
        self.ensure_one()
    
        return self.current_campaign_run_id\
            .eligibility_ids\
            .filtered(lambda x: x.status == "eligible")\
            .mapped("recipient_res_id")

Then hook Odoo's recipient-selection method.

The exact method should be verified from your running Odoo 19 code before implementation because recipient-domain internals are more version-sensitive than the high-level send actions.

* * *

# 38\. Preflight screen

Add smart buttons on the mailing:

    [Runs: 2]
    [Eligible: 21,620]
    [Excluded: 3,380]

New tab:

    Preflight

Contents:

    Current Run:
    RUN-2026-000414
    
    Status:
    PASSED
    
    Started:
    28-Aug-2026 15:31
    
    Completed:
    28-Aug-2026 15:33
    
    Run By:
    Campaign Operator
    
    Targeted:
    25,000
    
    Eligible:
    21,620
    
    Excluded:
    3,380
    
    [View Eligible Recipients]
    [View Excluded Recipients]
    [View All Decisions]

* * *

# 39\. Eligibility list view

Columns:

    Email
    Recipient
    Status
    Reason
    Consent Record
    Suppression
    Mailing List
    Evaluated At

Filters:

    Eligible
    Excluded
    
    Missing Consent
    Withdrawn Consent
    Expired Consent
    Global Blacklist
    Global Suppression
    Purpose Suppression
    Mailing List Opt-Out
    Invalid Email
    Duplicate
    Already Sent

* * *

# 40\. Compliance reviewer experience

The reviewer should be able to click:

    Missing Consent: 1,850

and immediately get:

    Name
    Email
    Purpose
    Reason
    Last Consent Record

Similarly:

    Purpose Suppression: 190

opens the corresponding recipient records.

This is essential for explainability.

* * *

# 41\. No manual override of eligibility

Do **not** allow an operator to simply change:

    Excluded → Eligible

That would destroy the compliance model.

If an exclusion is incorrect:

    Fix the source data
        │
        ├── Add valid consent
        ├── Reinstate suppression via authorized workflow
        ├── Correct email
        └── Correct mailing-list status
            │
            ▼
    Run preflight again

This is a critical business rule.

* * *

# 42\. Preflight invalidation

A preflight run should be invalidated when:

    Campaign content changes
    Recipient segment changes
    Consent purpose changes
    Brand changes
    Sender changes
    Approval invalidated

But not necessarily when:

    someone edits an unrelated internal note

Use the governed-field set from R2.

* * *

# 43\. Preflight freshness

I recommend adding:

    max_preflight_age_minutes

to configuration.

Example:

    60 minutes

Before scheduling/sending:

    preflight completed 3 hours ago

can trigger:

    Re-run Preflight Required

This reduces risk from rapidly changing suppression/consent states.

If volumes are high, you may use a longer window plus the dispatch-time safety check.

* * *

# 44\. Configuration model

Create or extend:

    newsletter.compliance.settings

Fields:

| Setting | Example |
| --- | --- |
| Preflight batch size | 2000 |
| Max preflight age | 60 min |
| Duplicate policy | First eligible wins |
| Allow zero-recipient send | No |
| Require explicit consent | Yes |
| Dispatch-time recheck | Yes |
| Fail if consent duplicates found | Warning |
| Fail if reconciliation mismatch | Yes |

* * *

# 45\. Zero eligible recipients

If:

    Targeted = 500
    Eligible = 0
    Excluded = 500

Preflight should:

    FAIL / BLOCK

because there is nothing valid to send.

Add:

    minimum_eligible_recipient_count = 1

* * *

# 46\. Threshold warnings

Although FR-28 is primarily about bounce/complaint rates during sending, R3 can support preflight warnings.

Examples:

    >30% recipients missing consent
    >10% invalid emails
    >20% globally suppressed

These don't necessarily block, but display:

    WARNING

for data-quality attention.

* * *

# 47\. Preflight result states

Use:

    not_run
    running
    passed
    passed_with_warning
    failed
    invalidated

That is richer than simple pass/fail.

* * *

# 48\. Audit fields

Every preflight should retain:

    campaign governance version
    approval version
    consent purpose
    recipient query/domain
    run timestamp
    operator
    rule-set version
    input hash
    result hash
    counts

This supports eventual end-to-end traceability required by NFR-09.

* * *

# 49\. Ruleset version

Add:

    ELIGIBILITY-RULESET-1.0

to each decision.

Why?

A year from now the rule may change.

You then want to know:

> Which logic decided John was eligible on August 28, 2026?

Store:

    ruleset_version = "1.0"

Do not just rely on current source code.

* * *

# 50\. Hashing

For each run calculate:

### Input hash

Over:

    Campaign ID
    Governance Version
    Content hash
    Consent Purpose
    Recipient definition
    Brand
    Preflight timestamp

### Result hash

Over canonical ordered records such as:

    email_normalized
    status
    reason_code
    consent_record_id
    suppression_entry_id

This does not make the database tamper-proof, but it provides useful integrity evidence.

* * *

# 51\. Security groups

R3 actions:

| Action | Author | Reviewer | Operator | Admin | Auditor |
| --- | --- | --- | --- | --- | --- |
| Run Preflight |  | ✅ optional | ✅ | ✅ |  |
| View decisions | ✅ limited | ✅ | ✅ | ✅ | ✅ |
| Modify decisions |  |  |  | No normal UI |  |
| Invalidate run |  | ✅ | ✅ | ✅ |  |
| Send after pass |  |  | ✅ | ✅ |  |
| Change rules |  |  |  | ✅ |  |
| Read audit |  | ✅ | ✅ | ✅ | ✅ |

* * *

# 52\. R3 business rules

| Rule | Requirement |
| --- | --- |
| R3-BR-01 | Every intended recipient must receive a decision |
| R3-BR-02 | Consent must match campaign purpose |
| R3-BR-03 | Withdrawn/expired consent is not valid |
| R3-BR-04 | Global blacklist always excludes |
| R3-BR-05 | Global suppression always excludes |
| R3-BR-06 | Purpose suppression excludes matching purpose |
| R3-BR-07 | Mailing-list opt-out excludes the applicable mailing |
| R3-BR-08 | Duplicate normalized email is sent at most once |
| R3-BR-09 | Exclusion cannot be manually overridden |
| R3-BR-10 | Targeted = Eligible + Excluded |
| R3-BR-11 | Eligible population must be frozen |
| R3-BR-12 | Send requires valid frozen preflight |
| R3-BR-13 | Governed changes invalidate preflight |
| R3-BR-14 | Dispatch rechecks volatile suppression/consent state |
| R3-BR-15 | Zero eligible recipients cannot be sent |
| R3-BR-16 | Every decision retains rule-set version |
| R3-BR-17 | Re-running preflight creates a new run; it does not overwrite history |
| R3-BR-18 | Already successfully sent recipients are not resent within the same run |

* * *

# 53\. Acceptance tests

Before R3 is complete, I would require all of these.

### Basic eligibility

1.  Active matching consent → eligible.
    
2.  No consent → excluded.
    
3.  Consent for different purpose → excluded.
    
4.  Withdrawn consent → excluded.
    
5.  Expired consent → excluded.
    
6.  Pending consent → excluded.
    
7.  Invalidated consent → excluded.
    

### Suppression

8.  Odoo global blacklist → excluded.
    
9.  Custom global suppression → excluded.
    
10.  Purpose suppression matching campaign → excluded.
    
11.  Purpose suppression for another purpose → does not exclude.
    
12.  Mailing-list suppression matching list → excluded.
    
13.  List-level opt-out → excluded.
    

### Email quality

14.  Missing email → excluded.
    
15.  Invalid email → excluded.
    
16.  Case variation duplicates → deduplicated.
    
17.  Duplicate across Partner/Mailing Contact → only one eligible.
    

### Reconciliation

18.  Every target has one decision.
    
19.  Targeted = Eligible + Excluded.
    
20.  Reason counts reconcile with excluded count.
    
21.  Incomplete evaluation → preflight failed.
    

### Workflow

22.  Draft campaign cannot preflight.
    
23.  Content-review campaign cannot preflight.
    
24.  Compliance-approved campaign can preflight.
    
25.  Successful run → Ready to Send.
    
26.  Failed run → remains blocked.
    
27.  Campaign change → run invalidated.
    
28.  Re-run creates new Campaign Run.
    
29.  Old run retained.
    

### Send enforcement

30.  No preflight → Send blocked.
    
31.  Failed preflight → Send blocked.
    
32.  Passed but unfrozen run → Send blocked.
    
33.  Passed frozen run → Send allowed.
    
34.  Direct RPC call → blocked if not compliant.
    
35.  Scheduled send uses same checks.
    

### Frozen population

36.  Contact added after preflight → not included in existing run.
    
37.  Contact removed after preflight → existing run still reflects original decision, but send policy follows frozen set.
    
38.  Consent withdrawn after preflight but before dispatch → recipient blocked.
    
39.  Global suppression added after preflight → recipient blocked.
    
40.  Recipient already successfully dispatched in run → not resent.
    

* * *

# 54\. Requirement traceability

| Original requirement | R3 implementation |
| --- | --- |
| FR-01 recipient source | Recipient resolver |
| FR-02 suppression exclusion | Suppression evaluation |
| FR-03 valid consent | Consent eligibility |
| FR-04 valid email | Email validation |
| FR-13 controlled sending | Governance gate; provider throttling later |
| FR-16 failed-send isolation | Campaign Run foundation |
| FR-17 retry safety | Run/recipient state foundation |
| FR-27 recipient reconstruction | Eligibility ledger |
| NFR-03 partial failure isolation | Recipient-level execution model foundation |
| NFR-04 no resend after interruption | Already-sent control |
| NFR-07 restricted compliance data | R1/R3 RBAC |
| NFR-09 end-to-end traceability | Run + eligibility records |
| RC-07 consent required | Consent decision |
| RC-08 consent evidence | Linked R1 consent record |
| RC-09 withdrawal effective | Preflight + dispatch recheck |

The original requirements explicitly require suppression filtering before send and prohibit dispatch to any address on the suppression list at dispatch time.

# 55\. End state after R3

The operator experience should now be:

    Healthcare Monthly Newsletter
    CMP-2026-000128
    
    Content Approval:
    ✓
    
    Compliance Approval:
    ✓
    
    Preflight:
    ✓ PASSED
    
    Current Run:
    RUN-2026-000414
    
    Targeted:
    25,000
    
    Eligible:
    21,620
    
    Excluded:
    3,380
    
    Population Frozen:
    ✓
    
    Compliance State:
    READY TO SEND
    
    [View Eligible]
    [View Excluded]
    [Schedule]
    [Send]

At this point, the application has a strong **governed pre-send control plane**.

The next increment, **R4 — Campaign Execution, Send Event Ledger & Immutable Archive**, should take that frozen eligible population and implement recipient-level queue/sent/retry states, reliable resumability, campaign completion/reconciliation, complete recipient history, and the exact **as-sent** compliance archive.