import hashlib
import json

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain

from ..services import consent_service, eligibility_service, suppression_service

GOVERNED_FIELDS = {
    "subject",
    "body_html",
    "body_arch",
    "email_from",
    "reply_to",
    "brand_id",
    "consent_purpose_id",
    "mailing_domain",
    "contact_list_ids",
}

APPROVAL_HELD_STATES = {"compliance_review", "approved", "preflight_required", "ready"}


class MailingMailing(models.Model):
    _inherit = "mailing.mailing"

    # -- Campaign identity -------------------------------------------------
    compliance_campaign_id = fields.Char(
        string="Campaign Compliance ID",
        readonly=True,
        copy=False,
        index=True,
        tracking=True,
    )

    brand_id = fields.Many2one(
        "newsletter.campaign.brand",
        string="Brand / Business Domain",
        ondelete="restrict",
        tracking=True,
    )

    consent_purpose_id = fields.Many2one(
        "newsletter.consent.purpose",
        string="Consent Purpose",
        ondelete="restrict",
        tracking=True,
    )

    business_owner_id = fields.Many2one(
        "res.users",
        string="Campaign Owner",
        default=lambda self: self.env.user,
        tracking=True,
    )

    compliance_owner_id = fields.Many2one(
        "res.users",
        string="Compliance Owner",
        tracking=True,
    )

    compliance_state = fields.Selection(
        [
            ("draft", "Draft"),
            ("content_review", "Content Review"),
            ("compliance_review", "Compliance Review"),
            ("approved", "Approved"),
            ("preflight_required", "Preflight Required"),
            ("ready", "Ready to Send"),
            ("sending", "Sending"),
            ("completed", "Completed"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
        tracking=True,
        copy=False,
    )

    requires_compliance_review = fields.Boolean(
        string="Requires Compliance Review",
        default=True,
        help="If disabled, an approved content review moves the campaign "
        "directly to Preflight Required without a separate compliance "
        "review step.",
    )

    # -- Approval information ------------------------------------------
    content_review_requested_at = fields.Datetime(readonly=True, copy=False)
    content_review_requested_by_id = fields.Many2one(
        "res.users", readonly=True, copy=False
    )

    content_approved_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    content_approved_at = fields.Datetime(readonly=True, copy=False)

    compliance_approved_by_id = fields.Many2one(
        "res.users", readonly=True, copy=False
    )
    compliance_approved_at = fields.Datetime(readonly=True, copy=False)

    rejected_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    rejected_at = fields.Datetime(readonly=True, copy=False)
    rejection_reason = fields.Text(readonly=True, copy=False)

    cancelled_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    cancelled_at = fields.Datetime(readonly=True, copy=False)
    cancellation_reason = fields.Text(readonly=True, copy=False)

    approval_version = fields.Integer(default=0, readonly=True, copy=False)

    # -- Governance / approval snapshot ---------------------------------
    approval_content_hash = fields.Char(readonly=True, copy=False)
    approval_subject = fields.Char(readonly=True, copy=False)
    approval_email_from = fields.Char(readonly=True, copy=False)
    approval_reply_to = fields.Char(readonly=True, copy=False)
    approval_recipient_domain = fields.Text(readonly=True, copy=False)
    approval_consent_purpose_id = fields.Many2one(
        "newsletter.consent.purpose", readonly=True, copy=False
    )

    approvals_valid = fields.Boolean(compute="_compute_approvals_valid")
    metadata_valid = fields.Boolean(compute="_compute_metadata_valid")
    compliance_warning = fields.Text(compute="_compute_metadata_valid")

    preflight_status = fields.Selection(
        [
            ("not_run", "Not Run"),
            ("required", "Required"),
            ("passed", "Passed"),
            ("passed_with_warning", "Passed with Warning"),
            ("failed", "Failed"),
            ("invalidated", "Invalidated"),
        ],
        default="not_run",
        copy=False,
    )

    approval_history_ids = fields.One2many(
        "newsletter.campaign.approval", "mailing_id", string="Approval History"
    )

    # -- R3: Preflight & recipient eligibility -----------------------------
    campaign_run_ids = fields.One2many(
        "newsletter.campaign.run", "mailing_id", string="Campaign Runs", copy=False
    )

    current_campaign_run_id = fields.Many2one(
        "newsletter.campaign.run",
        string="Current Campaign Run",
        readonly=True,
        copy=False,
    )

    preflight_targeted_count = fields.Integer(
        related="current_campaign_run_id.targeted_count", readonly=True
    )
    preflight_eligible_count = fields.Integer(
        related="current_campaign_run_id.eligible_count", readonly=True
    )
    preflight_excluded_count = fields.Integer(
        related="current_campaign_run_id.excluded_count", readonly=True
    )

    # -- Create / copy ----------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)

        for record in records:
            if record.mailing_type == "mail" and not record.compliance_campaign_id:
                record.compliance_campaign_id = self.env[
                    "ir.sequence"
                ].next_by_code("newsletter.compliance.campaign")

        return records

    def copy_data(self, default=None):
        default = dict(default or {})
        default.setdefault("compliance_campaign_id", False)
        default.setdefault("compliance_state", "draft")
        default.setdefault("content_review_requested_at", False)
        default.setdefault("content_review_requested_by_id", False)
        default.setdefault("content_approved_by_id", False)
        default.setdefault("content_approved_at", False)
        default.setdefault("compliance_approved_by_id", False)
        default.setdefault("compliance_approved_at", False)
        default.setdefault("rejected_by_id", False)
        default.setdefault("rejected_at", False)
        default.setdefault("rejection_reason", False)
        default.setdefault("cancelled_by_id", False)
        default.setdefault("cancelled_at", False)
        default.setdefault("cancellation_reason", False)
        default.setdefault("approval_version", 0)
        default.setdefault("approval_content_hash", False)
        default.setdefault("approval_subject", False)
        default.setdefault("approval_email_from", False)
        default.setdefault("approval_reply_to", False)
        default.setdefault("approval_recipient_domain", False)
        default.setdefault("approval_consent_purpose_id", False)
        default.setdefault("preflight_status", "not_run")
        return super().copy_data(default=default)

    # -- Metadata validation ----------------------------------------------
    def _validate_compliance_metadata(self):
        self.ensure_one()

        missing = []

        checks = {
            "name": _("Campaign Name"),
            "subject": _("Subject"),
            "brand_id": _("Brand"),
            "consent_purpose_id": _("Consent Purpose"),
            "email_from": _("From Address"),
            "body_html": _("Newsletter Content"),
            "business_owner_id": _("Campaign Owner"),
        }

        for field_name, label in checks.items():
            if not self[field_name]:
                missing.append(label)

        if not self.mailing_domain and not self.contact_list_ids:
            missing.append(_("Recipient Segment / Mailing List"))

        if self.brand_id and not self.brand_id.physical_address:
            missing.append(_("Physical Mailing Address (on Brand)"))

        if missing:
            raise ValidationError(
                _("The following campaign information is required:\n%s")
                % "\n".join("- %s" % item for item in missing)
            )

        return True

    @api.depends(
        "name",
        "subject",
        "brand_id",
        "consent_purpose_id",
        "email_from",
        "body_html",
        "business_owner_id",
        "mailing_domain",
        "contact_list_ids",
    )
    def _compute_metadata_valid(self):
        for mailing in self:
            try:
                mailing._validate_compliance_metadata()
                mailing.metadata_valid = True
                mailing.compliance_warning = False
            except ValidationError as exc:
                mailing.metadata_valid = False
                mailing.compliance_warning = str(exc)

    @api.depends(
        "compliance_state", "content_approved_by_id", "compliance_approved_by_id"
    )
    def _compute_approvals_valid(self):
        for mailing in self:
            if mailing.compliance_state not in APPROVAL_HELD_STATES:
                mailing.approvals_valid = False
                continue
            mailing.approvals_valid = bool(mailing.content_approved_by_id) and (
                bool(mailing.compliance_approved_by_id)
                or not mailing.requires_compliance_review
            )

    # -- Brand defaults -----------------------------------------------------
    @api.onchange("brand_id")
    def _onchange_brand_id(self):
        for mailing in self:
            if not mailing.brand_id:
                continue
            if not mailing.email_from:
                mailing.email_from = mailing.brand_id.email_from
            if not mailing.reply_to:
                mailing.reply_to = mailing.brand_id.reply_to
            if not mailing.consent_purpose_id and mailing.brand_id.default_consent_purpose_id:
                mailing.consent_purpose_id = mailing.brand_id.default_consent_purpose_id

    # -- Approval hash / snapshot ------------------------------------------
    def _build_approval_hash(self):
        self.ensure_one()

        payload = {
            "subject": self.subject or "",
            "email_from": self.email_from or "",
            "reply_to": self.reply_to or "",
            "body_html": self.body_html or "",
            "brand_id": self.brand_id.id or False,
            "consent_purpose_id": self.consent_purpose_id.id or False,
            "mailing_domain": self.mailing_domain or "",
            "contact_list_ids": sorted(self.contact_list_ids.ids),
        }

        encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _capture_content_approval_snapshot(self):
        self.ensure_one()
        self.with_context(skip_compliance_invalidation=True).write(
            {
                "approval_content_hash": self._build_approval_hash(),
                "approval_subject": self.subject,
                "approval_email_from": self.email_from,
                "approval_reply_to": self.reply_to,
                "approval_recipient_domain": json.dumps(
                    {
                        "mailing_domain": self.mailing_domain or "",
                        "contact_list_ids": sorted(self.contact_list_ids.ids),
                    }
                ),
                "approval_consent_purpose_id": self.consent_purpose_id.id,
            }
        )

    def _verify_content_approval_integrity(self):
        self.ensure_one()
        if self._build_approval_hash() != self.approval_content_hash:
            raise UserError(
                _(
                    "Campaign content has changed since content approval. "
                    "Approval integrity check failed."
                )
            )

    def _log_campaign_approval(self, approval_type, decision, comments=False):
        self.ensure_one()
        self.env["newsletter.campaign.approval"].sudo().create(
            {
                "mailing_id": self.id,
                "approval_version": self.approval_version,
                "approval_type": approval_type,
                "decision": decision,
                "reviewer_id": self.env.user.id,
                "comments": comments,
                "content_hash": self.approval_content_hash,
                "subject_snapshot": self.subject,
                "recipient_snapshot": self.approval_recipient_domain,
                "consent_purpose_id": self.consent_purpose_id.id,
                "brand_id": self.brand_id.id,
                "company_id": self.env.company.id,
            }
        )

    # -- Governance actions -------------------------------------------------
    def action_submit_content_review(self):
        for mailing in self:
            if mailing.compliance_state not in ("draft", "rejected"):
                raise UserError(_("This campaign cannot be submitted for review."))

            mailing._validate_compliance_metadata()

            mailing.write(
                {
                    "compliance_state": "content_review",
                    "content_review_requested_at": fields.Datetime.now(),
                    "content_review_requested_by_id": self.env.user.id,
                }
            )

            mailing.message_post(
                body=_(
                    "Campaign submitted for content review by %(user)s.",
                    user=self.env.user.display_name,
                )
            )

        return True

    def action_approve_content(self):
        self.ensure_one()

        if self.compliance_state != "content_review":
            raise UserError(_("Campaign is not awaiting content review."))

        if not self.env.user.has_group(
            "newsletter_compliance.group_newsletter_content_approver"
        ) and not self.env.user.has_group(
            "newsletter_compliance.group_newsletter_compliance_admin"
        ):
            raise UserError(_("You are not authorized to approve content."))

        if self.business_owner_id == self.env.user:
            raise UserError(_("Campaign owners cannot approve their own content."))

        self._validate_compliance_metadata()

        next_state = (
            "compliance_review" if self.requires_compliance_review else "preflight_required"
        )

        self.write(
            {
                "content_approved_by_id": self.env.user.id,
                "content_approved_at": fields.Datetime.now(),
                "approval_version": self.approval_version + 1,
                "compliance_state": next_state,
            }
        )

        self._capture_content_approval_snapshot()
        self._log_campaign_approval(approval_type="content", decision="approved")

        self.message_post(
            body=_(
                "Content approved by %(user)s.", user=self.env.user.display_name
            )
        )

        if not self.requires_compliance_review:
            self.write({"preflight_status": "required"})
            self.message_post(
                body=_(
                    "Compliance review not required for this campaign; "
                    "moved directly to Preflight Required."
                )
            )

        return True

    def action_approve_compliance(self):
        self.ensure_one()

        if self.compliance_state != "compliance_review":
            raise UserError(_("Campaign is not awaiting compliance review."))

        if not self.env.user.has_group(
            "newsletter_compliance.group_newsletter_compliance_reviewer"
        ) and not self.env.user.has_group(
            "newsletter_compliance.group_newsletter_compliance_admin"
        ):
            raise UserError(_("You are not authorized to approve compliance."))

        if not self.content_approved_by_id:
            raise UserError(_("Content approval is required first."))

        if self.business_owner_id == self.env.user:
            raise UserError(
                _("Campaign owner cannot compliance-approve this campaign.")
            )

        self._validate_compliance_metadata()
        self._verify_content_approval_integrity()

        self.write(
            {
                "compliance_approved_by_id": self.env.user.id,
                "compliance_approved_at": fields.Datetime.now(),
                "compliance_state": "preflight_required",
                "preflight_status": "required",
            }
        )

        self._log_campaign_approval(approval_type="compliance", decision="approved")

        self.message_post(
            body=_(
                "Compliance approved by %(user)s.", user=self.env.user.display_name
            )
        )

        return True

    def action_reject(self, reason, comments=False, return_to="draft"):
        self.ensure_one()

        if self.compliance_state not in ("content_review", "compliance_review"):
            raise UserError(_("Campaign is not awaiting review and cannot be rejected."))

        if not reason:
            raise UserError(_("A rejection reason is required."))

        approval_type = "content" if self.compliance_state == "content_review" else "compliance"

        self.with_context(skip_compliance_invalidation=True).write(
            {
                "compliance_state": return_to,
                "rejected_by_id": self.env.user.id,
                "rejected_at": fields.Datetime.now(),
                "rejection_reason": reason,
            }
        )

        self._log_campaign_approval(
            approval_type=approval_type, decision="rejected", comments=comments or reason
        )

        self.message_post(
            body=_(
                "Campaign rejected by %(user)s. Reason: %(reason)s",
                user=self.env.user.display_name,
                reason=reason,
            )
        )

        return True

    def action_cancel_campaign(self, reason):
        self.ensure_one()

        if self.compliance_state not in (
            "draft",
            "content_review",
            "compliance_review",
            "approved",
            "preflight_required",
        ):
            raise UserError(_("Campaign cannot be cancelled from its current state."))

        if not reason:
            raise UserError(_("A cancellation reason is required."))

        if (
            self.business_owner_id != self.env.user
            and not self.env.user.has_group(
                "newsletter_compliance.group_newsletter_compliance_admin"
            )
        ):
            raise UserError(_("Only the campaign owner or an administrator can cancel this campaign."))

        self.write(
            {
                "compliance_state": "cancelled",
                "cancelled_by_id": self.env.user.id,
                "cancelled_at": fields.Datetime.now(),
                "cancellation_reason": reason,
            }
        )

        self.message_post(
            body=_(
                "Campaign cancelled by %(user)s. Reason: %(reason)s",
                user=self.env.user.display_name,
                reason=reason,
            )
        )

        return True

    # -- R3: Recipient resolution --------------------------------------------
    def _get_compliance_recipient_candidates(self):
        """Resolve every recipient the mailing currently targets into the
        normalized candidate structure the eligibility engine expects.
        Uses the mailing's own recipient model/domain (never hard-codes
        res.partner), matching whatever model the mailing form's Recipients
        field points to.
        """
        self.ensure_one()

        model_name = self.mailing_model_real
        res_ids = self.env[model_name].search(Domain(self._parse_mailing_domain())).ids
        records = self.env[model_name].browse(res_ids)

        candidates = []
        if model_name == "mailing.contact":
            for contact in records:
                candidates.append(
                    {
                        "model": "mailing.contact",
                        "res_id": contact.id,
                        "partner_id": False,
                        "mailing_contact_id": contact.id,
                        "email": contact.email or "",
                        "mailing_list_ids": contact.list_ids.ids,
                    }
                )
        elif model_name == "res.partner":
            for partner in records:
                candidates.append(
                    {
                        "model": "res.partner",
                        "res_id": partner.id,
                        "partner_id": partner.id,
                        "mailing_contact_id": False,
                        "email": partner.email or "",
                        "mailing_list_ids": [],
                    }
                )
        else:
            field_names = records._fields
            email_field = "email_normalized" if "email_normalized" in field_names else (
                "email" if "email" in field_names else None
            )
            for record in records:
                candidates.append(
                    {
                        "model": model_name,
                        "res_id": record.id,
                        "partner_id": record.partner_id.id
                        if "partner_id" in field_names and record.partner_id
                        else False,
                        "mailing_contact_id": False,
                        "email": (record[email_field] or "") if email_field else "",
                        "mailing_list_ids": [],
                    }
                )

        return candidates

    def _build_result_hash(self, eligibility_records):
        payload = "|".join(
            sorted(
                "%s:%s:%s:%s:%s"
                % (
                    r.email_normalized,
                    r.status,
                    r.reason_code,
                    r.consent_record_id.id or "",
                    r.suppression_entry_id.id or "",
                )
                for r in eligibility_records
            )
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _link_duplicate_eligibility(self, eligibility_records):
        by_email = {}
        for record in eligibility_records.sorted("evaluation_sequence"):
            by_email.setdefault(record.email_normalized, []).append(record)

        for records in by_email.values():
            if len(records) <= 1:
                continue
            first = records[0]
            for duplicate in records[1:]:
                if duplicate.reason_code == "duplicate_email":
                    duplicate.with_context(skip_eligibility_freeze_guard=True).write(
                        {"duplicate_of_id": first.id}
                    )

    def _open_preflight_result(self, run):
        return {
            "type": "ir.actions.act_window",
            "name": _("Preflight Result"),
            "res_model": "newsletter.campaign.run",
            "view_mode": "form",
            "res_id": run.id,
            "target": "current",
        }

    def action_view_current_run_eligible(self):
        self.ensure_one()
        return self.current_campaign_run_id.action_view_eligible()

    def action_view_current_run_excluded(self):
        self.ensure_one()
        return self.current_campaign_run_id.action_view_excluded()

    def action_run_compliance_preflight(self):
        self.ensure_one()

        if self.compliance_state != "preflight_required":
            raise UserError(_("Campaign is not ready for preflight."))

        if (
            not self.env.user.has_group(
                "newsletter_compliance.group_newsletter_campaign_operator"
            )
            and not self.env.user.has_group(
                "newsletter_compliance.group_newsletter_compliance_reviewer"
            )
            and not self.env.user.has_group(
                "newsletter_compliance.group_newsletter_compliance_admin"
            )
        ):
            raise UserError(_("You are not authorized to run compliance preflight."))

        self._verify_content_approval_integrity()

        evaluation_time = fields.Datetime.now()

        run = self.env["newsletter.campaign.run"].create(
            {
                "mailing_id": self.id,
                "governance_version": self.approval_version,
                "state": "evaluating",
                "preflight_started_at": evaluation_time,
                "preflight_started_by_id": self.env.user.id,
                "input_hash": self._build_approval_hash(),
            }
        )

        candidates = self._get_compliance_recipient_candidates()

        eligibility_vals_list, counts = eligibility_service.evaluate_candidates(
            self.env, self, run, candidates, evaluation_time
        )

        created = self.env["newsletter.recipient.eligibility"].create(eligibility_vals_list)
        self._link_duplicate_eligibility(created)
        run.write({"result_hash": self._build_result_hash(created)})

        run._finalize_preflight(counts, targeted_count=len(candidates))

        # Always link the run so operators can inspect it (including a
        # failed one) from the mailing's Preflight tab.
        self.write({"current_campaign_run_id": run.id})

        if run.state == "passed":
            self.write(
                {
                    "compliance_state": "ready",
                    "preflight_status": "passed",
                }
            )
            self.message_post(
                body=_(
                    "Preflight passed: %(eligible)s eligible, %(excluded)s "
                    "excluded out of %(targeted)s targeted.",
                    eligible=run.eligible_count,
                    excluded=run.excluded_count,
                    targeted=run.targeted_count,
                )
            )
        else:
            self.write({"preflight_status": "failed"})
            self.message_post(
                body=_(
                    "Preflight failed: %(reason)s",
                    reason=run.failure_reason or _("see run for details"),
                )
            )

        return self._open_preflight_result(run)

    # -- R3: Frozen recipient population & dispatch-time recheck -----------
    def _get_recipients_domain(self):
        self.ensure_one()
        run = self.current_campaign_run_id
        if run and run.frozen and run.state == "passed":
            eligible = run.eligibility_ids.filtered(lambda e: e.status == "eligible")
            self._dispatch_time_recheck(eligible)
            res_ids = eligible.filtered(
                lambda e: e.dispatch_state not in ("blocked", "sent")
            ).mapped("recipient_res_id")
            return Domain("id", "in", res_ids)
        return super()._get_recipients_domain()

    def _dispatch_time_recheck(self, eligibility_records):
        """Immediately before recipients are resolved for dispatch, recheck
        only volatile controls (blacklist, suppression, consent withdrawal/
        expiry) - a frozen preflight must never override a newer withdrawal
        or suppression. Does not rerun the full segmentation.
        """
        self.ensure_one()

        to_check = eligibility_records.filtered(lambda e: e.dispatch_state != "sent")
        if not to_check:
            return

        emails = list({e.email_normalized for e in to_check if e.email_normalized})
        if not emails:
            return

        now = fields.Datetime.now()
        company_id = self.env.company.id
        purpose_id = self.consent_purpose_id.id

        blacklisted = set(
            self.env["mail.blacklist"].sudo().search([("email", "in", emails)]).mapped("email")
        )
        suppressions = suppression_service.get_applicable_suppressions_by_email(
            self.env, emails, purpose_id, self.contact_list_ids.ids, now,
            brand_id=self.brand_id.id, campaign_mailing_id=self.id,
        )
        active_consents = consent_service.get_effective_consents_by_email(
            self.env, emails, purpose_id, company_id, now
        )

        to_block = to_check.filtered(
            lambda e: e.email_normalized in blacklisted
            or e.email_normalized in suppressions
            or e.email_normalized not in active_consents
        )
        if to_block:
            to_block.sudo().write({"dispatch_state": "blocked"})
            self.message_post(
                body=_(
                    "%(count)s recipient(s) blocked at dispatch time due to "
                    "a suppression or consent change since preflight.",
                    count=len(to_block),
                )
            )

    # -- R3: Server-side send blocking --------------------------------------
    def _assert_compliance_ready(self):
        for mailing in self:
            if mailing.mailing_type != "mail":
                continue

            if mailing.compliance_state != "ready":
                raise UserError(
                    _(
                        "Campaign %(campaign)s cannot be sent. Compliance "
                        "preflight has not passed.",
                        campaign=mailing.compliance_campaign_id or mailing.display_name,
                    )
                )

            run = mailing.current_campaign_run_id
            if not run or run.state != "passed" or not run.frozen:
                raise UserError(
                    _("A valid frozen campaign run is required before this campaign can be sent.")
                )

    def action_put_in_queue(self):
        self._assert_compliance_ready()
        return super().action_put_in_queue()

    def action_send_mail(self, res_ids=None):
        self._assert_compliance_ready()
        return super().action_send_mail(res_ids=res_ids)

    def action_reset_to_draft(self, reason):
        self.ensure_one()

        if not reason:
            raise UserError(_("A reason is required to return this campaign to Draft."))

        self.with_context(skip_compliance_invalidation=True).write(
            {
                "compliance_state": "draft",
                "content_approved_by_id": False,
                "content_approved_at": False,
                "compliance_approved_by_id": False,
                "compliance_approved_at": False,
                "preflight_status": "not_run",
            }
        )

        self.message_post(
            body=_(
                "Campaign returned to Draft by %(user)s. Reason: %(reason)s",
                user=self.env.user.display_name,
                reason=reason,
            )
        )

        return True

    # -- Change-invalidates-approval ----------------------------------------
    def write(self, vals):
        if self.env.context.get("skip_compliance_invalidation"):
            return super().write(vals)

        governed_change = bool(GOVERNED_FIELDS.intersection(vals))

        approved_records = (
            self.filtered(lambda r: r.compliance_state in APPROVAL_HELD_STATES)
            if governed_change
            else self.browse()
        )

        result = super().write(vals)

        if approved_records:
            approved_records._invalidate_compliance_approval()

        return result

    def _invalidate_compliance_approval(self):
        for mailing in self:
            mailing._log_campaign_approval(
                approval_type="compliance"
                if mailing.compliance_approved_by_id
                else "content",
                decision="invalidated",
                comments=_("Controlled campaign content or metadata changed."),
            )

            run_to_invalidate = mailing.current_campaign_run_id

            mailing.with_context(skip_compliance_invalidation=True).write(
                {
                    "compliance_state": "draft",
                    "content_approved_by_id": False,
                    "content_approved_at": False,
                    "compliance_approved_by_id": False,
                    "compliance_approved_at": False,
                    "preflight_status": "not_run",
                    "current_campaign_run_id": False,
                }
            )

            if run_to_invalidate and run_to_invalidate.state in (
                "draft",
                "evaluating",
                "passed",
                "passed_with_warning",
            ):
                run_to_invalidate.sudo()._invalidate(
                    reason=_("Controlled campaign content or metadata changed.")
                )

            mailing.message_post(
                body=_(
                    "Campaign approval was invalidated because controlled "
                    "campaign content or metadata changed."
                )
            )
