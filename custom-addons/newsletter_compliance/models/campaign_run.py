import datetime
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..services import (
    archive_service,
    config_service,
    consent_service,
    dispatch_service,
    integrity_service,
    reconciliation_service,
    retry_service,
    suppression_service,
)

_logger = logging.getLogger(__name__)

REASON_TO_COUNT_FIELD = {
    "duplicate_email": "duplicate_count",
    "missing_consent": "missing_consent_count",
    "pending_consent": "missing_consent_count",
    "withdrawn_consent": "withdrawn_consent_count",
    "expired_consent": "expired_consent_count",
    "invalidated_consent": "missing_consent_count",
    "global_blacklist": "global_blacklist_count",
    "global_suppression": "suppression_count",
    "brand_suppression": "suppression_count",
    "purpose_suppression": "suppression_count",
    "mailing_list_suppression": "suppression_count",
    "campaign_suppression": "suppression_count",
    "mailing_list_opt_out": "suppression_count",
    "missing_email": "invalid_email_count",
    "invalid_email": "invalid_email_count",
    "already_sent": "already_sent_count",
}



class NewsletterCampaignRun(models.Model):
    _name = "newsletter.campaign.run"
    _description = "Newsletter Campaign Run"
    _inherit = ["newsletter.retention.mixin"]
    _order = "create_date desc, id desc"
    _rec_name = "reference"

    reference = fields.Char(readonly=True, copy=False, default="New")

    mailing_id = fields.Many2one(
        "mailing.mailing",
        required=True,
        index=True,
        ondelete="cascade",
    )

    campaign_compliance_id = fields.Char(
        related="mailing_id.compliance_campaign_id", store=True, readonly=True
    )

    governance_version = fields.Integer(
        readonly=True,
        help="Snapshot of the campaign's approval_version at the time this "
        "run was started.",
    )

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("evaluating", "Evaluating"),
            ("passed", "Preflight Passed"),
            ("passed_with_warning", "Passed with Warning"),
            ("failed", "Preflight Failed"),
            ("invalidated", "Invalidated"),
            ("queued", "Queued"),
            ("sending", "Sending"),
            ("partially_completed", "Partially Completed"),
            ("suspended", "Suspended"),
            ("completed", "Completed"),
            ("completed_with_errors", "Completed With Errors"),
            ("cancelled", "Cancelled"),
            ("archived", "Archived"),
        ],
        default="draft",
        required=True,
        index=True,
    )

    failure_reason = fields.Text(readonly=True)

    preflight_started_at = fields.Datetime(readonly=True)
    preflight_completed_at = fields.Datetime(readonly=True)
    preflight_started_by_id = fields.Many2one("res.users", readonly=True)

    targeted_count = fields.Integer(readonly=True, default=0)
    eligible_count = fields.Integer(readonly=True, default=0)
    excluded_count = fields.Integer(readonly=True, default=0)
    duplicate_count = fields.Integer(readonly=True, default=0)
    missing_consent_count = fields.Integer(readonly=True, default=0)
    withdrawn_consent_count = fields.Integer(readonly=True, default=0)
    expired_consent_count = fields.Integer(readonly=True, default=0)
    global_blacklist_count = fields.Integer(readonly=True, default=0)
    suppression_count = fields.Integer(readonly=True, default=0)
    invalid_email_count = fields.Integer(readonly=True, default=0)
    already_sent_count = fields.Integer(readonly=True, default=0)

    input_hash = fields.Char(readonly=True)
    result_hash = fields.Char(readonly=True)

    frozen = fields.Boolean(default=False, readonly=True)
    frozen_at = fields.Datetime(readonly=True)

    # -- R4: Execution ----------------------------------------------------
    execution_started_at = fields.Datetime(readonly=True)
    execution_completed_at = fields.Datetime(readonly=True)
    execution_started_by_id = fields.Many2one("res.users", readonly=True)

    queued_count = fields.Integer(readonly=True, default=0)
    processing_count = fields.Integer(readonly=True, default=0)
    sent_count = fields.Integer(readonly=True, default=0)
    failed_count = fields.Integer(readonly=True, default=0)
    blocked_at_dispatch_count = fields.Integer(readonly=True, default=0)
    retry_pending_count = fields.Integer(readonly=True, default=0)
    cancelled_count = fields.Integer(readonly=True, default=0)

    delivered_count = fields.Integer(readonly=True, default=0)
    bounced_count = fields.Integer(readonly=True, default=0)
    complained_count = fields.Integer(readonly=True, default=0)
    unsubscribed_count = fields.Integer(readonly=True, default=0)

    next_retry_at = fields.Datetime(readonly=True)

    execution_batch_size = fields.Integer(
        default=lambda self: config_service.get_dispatch_batch_size(self.env)
    )
    maximum_retry_count = fields.Integer(
        default=lambda self: config_service.get_maximum_retry_count(self.env)
    )

    archive_id = fields.Many2one("newsletter.campaign.archive", readonly=True, copy=False)
    current_outcome_id = fields.Many2one(
        "newsletter.campaign.outcome", readonly=True, copy=False
    )

    last_reconciled_at = fields.Datetime(readonly=True)

    cancelled_by_id = fields.Many2one("res.users", readonly=True)
    cancelled_at = fields.Datetime(readonly=True)
    cancellation_reason = fields.Text(readonly=True)

    suspended_by_id = fields.Many2one("res.users", readonly=True)
    suspended_at = fields.Datetime(readonly=True)
    suspension_reason = fields.Text(readonly=True)

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    eligibility_ids = fields.One2many(
        "newsletter.recipient.eligibility", "campaign_run_id", string="Eligibility Decisions"
    )

    event_ids = fields.One2many(
        "newsletter.send.event", "campaign_run_id", string="Send Events"
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("reference", "New") == "New":
                vals["reference"] = (
                    self.env["ir.sequence"].next_by_code("newsletter.campaign.run") or "New"
                )
        return super().create(vals_list)

    def _reason_count_field(self, reason_code):
        return REASON_TO_COUNT_FIELD.get(reason_code)

    def _apply_counts(self, counts, targeted_count):
        """``counts`` is a Counter keyed by reason_code (including
        "eligible"), as returned by the eligibility service. ``targeted_count``
        is the actual number of resolved recipient candidates - kept
        independent of the counts total so reconciliation is a real check,
        not a tautology.
        """
        self.ensure_one()

        eligible = counts.get("eligible", 0)
        excluded = sum(v for k, v in counts.items() if k != "eligible")

        vals = {
            "targeted_count": targeted_count,
            "eligible_count": eligible,
            "excluded_count": excluded,
        }
        for reason_code, field_name in REASON_TO_COUNT_FIELD.items():
            vals[field_name] = vals.get(field_name, 0) + counts.get(reason_code, 0)

        self.write(vals)

    def _finalize_preflight(self, counts, targeted_count):
        """Reconcile counts, decide pass/fail, and freeze the run and its
        eligibility records if it passes. Returns nothing - callers read
        ``self.state`` afterwards.
        """
        self.ensure_one()

        self._apply_counts(counts, targeted_count)

        actual_decisions = sum(counts.values())
        reconciled = (
            actual_decisions == targeted_count
            and self.eligible_count + self.excluded_count == targeted_count
        )

        if not reconciled:
            self.write(
                {
                    "state": "failed",
                    "failure_reason": _(
                        "Eligibility decisions do not reconcile with the "
                        "targeted recipient count."
                    ),
                    "preflight_completed_at": fields.Datetime.now(),
                }
            )
            return

        minimum_eligible = config_service.get_minimum_eligible_recipient_count(self.env)
        if self.eligible_count < minimum_eligible:
            self.write(
                {
                    "state": "failed",
                    "failure_reason": _(
                        "Preflight found only %(eligible)s eligible recipient(s), below "
                        "the configured minimum of %(minimum)s; a campaign cannot be sent "
                        "to zero people.",
                        eligible=self.eligible_count,
                        minimum=minimum_eligible,
                    ),
                    "preflight_completed_at": fields.Datetime.now(),
                }
            )
            return

        self.write(
            {
                "state": "passed",
                "preflight_completed_at": fields.Datetime.now(),
            }
        )
        self._freeze()

    def _freeze(self):
        self.ensure_one()
        now = fields.Datetime.now()
        self.eligibility_ids.with_context(skip_eligibility_freeze_guard=True).write(
            {"frozen": True}
        )
        self.write({"frozen": True, "frozen_at": now})

    def _invalidate(self, reason=False):
        for run in self:
            run.write({"state": "invalidated", "failure_reason": reason})

    def action_view_eligible(self):
        self.ensure_one()
        return self._open_eligibility_list(_("Eligible Recipients"), [("status", "=", "eligible")])

    def action_view_excluded(self):
        self.ensure_one()
        return self._open_eligibility_list(_("Excluded Recipients"), [("status", "=", "excluded")])

    def action_view_all_decisions(self):
        self.ensure_one()
        return self._open_eligibility_list(_("All Decisions"), [])

    def _open_eligibility_list(self, name, extra_domain):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": "newsletter.recipient.eligibility",
            "view_mode": "list,form",
            "domain": [("campaign_run_id", "=", self.id)] + extra_domain,
            "context": {"search_default_group_by_reason": 1},
        }

    def action_view_events(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Send Events"),
            "res_model": "newsletter.send.event",
            "view_mode": "list,form",
            "domain": [("campaign_run_id", "=", self.id)],
        }

    def action_view_archive(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Campaign Archive"),
            "res_model": "newsletter.campaign.archive",
            "view_mode": "form",
            "res_id": self.archive_id.id,
        }

    def action_view_outcome(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Campaign Outcome"),
            "res_model": "newsletter.campaign.outcome",
            "view_mode": "form",
            "res_id": self.current_outcome_id.id,
        }

    # -- R4: Execution ------------------------------------------------------
    def action_start_execution(self):
        self.ensure_one()

        if (
            not self.env.user.has_group(
                "newsletter_compliance.group_newsletter_campaign_operator"
            )
            and not self.env.user.has_group(
                "newsletter_compliance.group_newsletter_compliance_admin"
            )
        ):
            raise UserError(_("You are not authorized to start campaign execution."))

        if self.mailing_id.compliance_state != "ready":
            raise UserError(_("Campaign is not Ready to Send."))

        if self.state != "passed" or not self.frozen:
            raise UserError(_("A passed, frozen campaign run is required before sending."))

        max_age_minutes = config_service.get_max_preflight_age_minutes(self.env)
        if self.preflight_completed_at and max_age_minutes:
            age = fields.Datetime.now() - self.preflight_completed_at
            if age > datetime.timedelta(minutes=max_age_minutes):
                raise UserError(
                    _(
                        "This preflight is more than %(max_age)s minutes old and may no "
                        "longer reflect current consent/suppression state. Re-run "
                        "preflight before sending.",
                        max_age=max_age_minutes,
                    )
                )

        self.write(
            {
                "state": "queued",
                "execution_started_at": fields.Datetime.now(),
                "execution_started_by_id": self.env.user.id,
            }
        )
        self.mailing_id.write({"compliance_state": "sending"})

        # Created now (not at completion) so bounce/complaint rates can be
        # monitored and alerted on while the campaign is still sending
        # (R5 section 45), not only after the fact.
        if not self.current_outcome_id:
            outcome = self.env["newsletter.campaign.outcome"].sudo().create(
                {
                    "campaign_run_id": self.id,
                    "mailing_id": self.mailing_id.id,
                    "sent_count": 0,
                }
            )
            self.write({"current_outcome_id": outcome.id})

        eligible = self.eligibility_ids.filtered(lambda e: e.status == "eligible")
        for eligibility in eligible:
            self._create_event(eligibility, "queued")
        eligible.with_context(skip_eligibility_freeze_guard=True).write(
            {
                "dispatch_state": "queued",
                "first_queued_at": fields.Datetime.now(),
                "last_queued_at": fields.Datetime.now(),
            }
        )

        cron = self.env.ref(
            "newsletter_compliance.ir_cron_newsletter_dispatch_worker", raise_if_not_found=False
        )
        if cron:
            cron._trigger()

        return True

    def action_suspend(self, reason):
        self.ensure_one()

        if not reason:
            raise UserError(_("A suspension reason is required."))

        if self.state not in ("queued", "sending", "partially_completed"):
            raise UserError(_("This run is not currently executing."))

        self.write(
            {
                "state": "suspended",
                "suspended_by_id": self.env.user.id,
                "suspended_at": fields.Datetime.now(),
                "suspension_reason": reason,
            }
        )
        self.mailing_id.message_post(
            body=_(
                "Campaign execution suspended. Reason: %(reason)s. "
                "Recipients already sent are unaffected; the worker will "
                "not acquire new recipients until resumed.",
                reason=reason,
            )
        )

    def action_resume(self, reason):
        self.ensure_one()

        if not reason:
            raise UserError(_("A reason is required to resume a suspended campaign."))

        if (
            not self.env.user.has_group(
                "newsletter_compliance.group_newsletter_campaign_operator"
            )
            and not self.env.user.has_group(
                "newsletter_compliance.group_newsletter_compliance_admin"
            )
        ):
            raise UserError(_("You are not authorized to resume campaign execution."))

        if self.state != "suspended":
            raise UserError(_("This run is not suspended."))

        self.write({"state": "partially_completed"})
        self.mailing_id.message_post(
            body=_(
                "Campaign execution resumed by %(user)s. Reason: %(reason)s",
                user=self.env.user.display_name,
                reason=reason,
            )
        )

        cron = self.env.ref(
            "newsletter_compliance.ir_cron_newsletter_dispatch_worker", raise_if_not_found=False
        )
        if cron:
            cron._trigger()

    def action_cancel_execution(self, reason):
        self.ensure_one()

        if not reason:
            raise UserError(_("A cancellation reason is required."))

        if (
            not self.env.user.has_group(
                "newsletter_compliance.group_newsletter_campaign_operator"
            )
            and not self.env.user.has_group(
                "newsletter_compliance.group_newsletter_compliance_admin"
            )
        ):
            raise UserError(_("You are not authorized to cancel campaign execution."))

        if self.state not in ("queued", "sending", "partially_completed", "suspended"):
            raise UserError(_("This run is not currently executing."))

        pending = self.eligibility_ids.filtered(
            lambda e: e.status == "eligible"
            and e.dispatch_state in ("not_queued", "queued", "retry_pending")
        )
        for eligibility in pending:
            self._create_event(
                eligibility, "campaign_cancelled", error_message=reason, source="user"
            )
        pending.with_context(skip_eligibility_freeze_guard=True).write(
            {"dispatch_state": "cancelled"}
        )

        self._recompute_execution_counts()
        self.write(
            {
                "state": "cancelled",
                "cancelled_by_id": self.env.user.id,
                "cancelled_at": fields.Datetime.now(),
                "cancellation_reason": reason,
            }
        )
        self.mailing_id.message_post(
            body=_(
                "Campaign execution cancelled by %(user)s. Reason: %(reason)s. "
                "%(sent)s already sent, %(pending)s cancelled before dispatch.",
                user=self.env.user.display_name,
                reason=reason,
                sent=self.sent_count,
                pending=len(pending),
            )
        )
        return True

    def action_retry_failed(self):
        self.ensure_one()

        if (
            not self.env.user.has_group(
                "newsletter_compliance.group_newsletter_campaign_operator"
            )
            and not self.env.user.has_group(
                "newsletter_compliance.group_newsletter_compliance_admin"
            )
        ):
            raise UserError(_("You are not authorized to retry failed recipients."))

        retryable = self.eligibility_ids.filtered(
            lambda e: e.dispatch_state == "failed"
            and e.last_error_retryable
            and e.dispatch_attempt_count < self.maximum_retry_count
        )
        if not retryable:
            raise UserError(_("No retryable failed recipients found."))

        retryable.with_context(skip_eligibility_freeze_guard=True).write(
            {"dispatch_state": "retry_pending", "next_retry_at": fields.Datetime.now()}
        )
        for eligibility in retryable:
            self._create_event(eligibility, "retry_scheduled", source="user")

        if self.state in ("completed", "completed_with_errors"):
            self.write({"state": "partially_completed"})

        self._recompute_execution_counts()

        cron = self.env.ref(
            "newsletter_compliance.ir_cron_newsletter_dispatch_worker", raise_if_not_found=False
        )
        if cron:
            cron._trigger()

        return True

    def _correlation_id(self, eligibility):
        return "%s:%s:%s" % (
            self.mailing_id.compliance_campaign_id or self.mailing_id.id,
            self.reference,
            eligibility.id,
        )

    def _create_event(self, eligibility, event_type, error_code=False, error_message=False, provider_message_id=False, source="odoo"):
        self.ensure_one()
        self.env["newsletter.send.event"].sudo().create(
            {
                "campaign_run_id": self.id,
                "mailing_id": self.mailing_id.id,
                "eligibility_id": eligibility.id,
                "partner_id": eligibility.partner_id.id,
                "mailing_contact_id": eligibility.mailing_contact_id.id,
                "email_normalized": eligibility.email_normalized,
                "event_type": event_type,
                "attempt_number": eligibility.dispatch_attempt_count,
                "provider_message_id": provider_message_id or eligibility.provider_message_id,
                "correlation_id": self._correlation_id(eligibility),
                "error_code": error_code,
                "error_message": error_message,
                "source": source,
                "company_id": self.company_id.id,
            }
        )

    def _dispatch_time_compliance_check(self, eligibility):
        """Volatile-only recheck immediately before submitting to the
        provider: consent withdrawal, blacklist, and suppression added
        since preflight. Never reruns full segmentation.
        """
        self.ensure_one()

        email = eligibility.email_normalized
        if not email:
            return {"allowed": False, "reason": _("Missing normalized email.")}

        now = fields.Datetime.now()
        company_id = self.company_id.id
        purpose_id = self.mailing_id.consent_purpose_id.id

        if self.env["mail.blacklist"].sudo().search_count([("email", "=", email)]):
            return {"allowed": False, "reason": _("Recipient is on the global blacklist.")}

        suppressions = suppression_service.get_applicable_suppressions_by_email(
            self.env, [email], purpose_id, self.mailing_id.contact_list_ids.ids, now,
            brand_id=self.mailing_id.brand_id.id, campaign_mailing_id=self.mailing_id.id,
        )
        if email in suppressions:
            return {
                "allowed": False,
                "reason": _("An active suppression now applies to this recipient."),
            }

        active_consents = consent_service.get_effective_consents_by_email(
            self.env, [email], purpose_id, company_id, now
        )
        if email not in active_consents:
            return {
                "allowed": False,
                "reason": _("Consent is no longer active for this campaign's purpose."),
            }

        return {"allowed": True, "reason": False}

    def _calculate_next_retry(self, eligibility):
        delay = retry_service.calculate_next_retry_delay(
            eligibility.dispatch_attempt_count,
            base_delay=config_service.get_base_retry_delay_seconds(self.env),
            max_delay=config_service.get_maximum_retry_delay_seconds(self.env),
        )
        return fields.Datetime.now() + datetime.timedelta(seconds=delay)

    def _dispatch_recipient(self, eligibility):
        self.ensure_one()

        if eligibility.dispatch_state == "sent":
            return

        eligibility.with_context(skip_eligibility_freeze_guard=True).write(
            {
                "dispatch_state": "processing",
                "last_attempt_at": fields.Datetime.now(),
                "dispatch_attempt_count": eligibility.dispatch_attempt_count + 1,
            }
        )
        self._create_event(eligibility, "dispatch_started")

        compliance_result = self._dispatch_time_compliance_check(eligibility)

        if not compliance_result["allowed"]:
            eligibility.with_context(skip_eligibility_freeze_guard=True).write(
                {"dispatch_state": "blocked"}
            )
            self._create_event(
                eligibility, "dispatch_recheck_blocked", error_message=compliance_result["reason"]
            )
            return

        self._create_event(eligibility, "dispatch_recheck_passed")
        self._create_event(eligibility, "send_attempted")

        result = dispatch_service.send_recipient(self.env, self.mailing_id, eligibility)

        if result["accepted"]:
            eligibility.with_context(skip_eligibility_freeze_guard=True).write(
                {
                    "dispatch_state": "sent",
                    "first_sent_at": eligibility.first_sent_at or fields.Datetime.now(),
                    "provider_message_id": result["provider_message_id"],
                }
            )
            self._create_event(
                eligibility, "send_accepted", provider_message_id=result["provider_message_id"]
            )
        elif result["retryable"] and eligibility.dispatch_attempt_count < self.maximum_retry_count:
            eligibility.with_context(skip_eligibility_freeze_guard=True).write(
                {
                    "dispatch_state": "retry_pending",
                    "next_retry_at": self._calculate_next_retry(eligibility),
                    "last_error_code": result["error_code"],
                    "last_error_message": result["error_message"],
                    "last_error_retryable": True,
                }
            )
            self._create_event(
                eligibility,
                "retry_scheduled",
                error_code=result["error_code"],
                error_message=result["error_message"],
            )
        else:
            eligibility.with_context(skip_eligibility_freeze_guard=True).write(
                {
                    "dispatch_state": "failed",
                    "last_error_code": result["error_code"],
                    "last_error_message": result["error_message"],
                    "last_error_retryable": bool(result["retryable"]),
                }
            )
            self._create_event(
                eligibility,
                "send_failed_final",
                error_code=result["error_code"],
                error_message=result["error_message"],
            )

    def _lock_next_dispatch_batch(self):
        self.ensure_one()
        # Raw SQL bypasses the ORM cache entirely, so any pending writes
        # (e.g. dispatch_state='sent' from the previous batch) must be
        # flushed to the actual table first, or this query will still see
        # stale rows and could re-select an already-dispatched recipient.
        self.env["newsletter.recipient.eligibility"].flush_model()
        self.env.cr.execute(
            """
            SELECT id FROM newsletter_recipient_eligibility
            WHERE campaign_run_id = %s
              AND status = 'eligible'
              AND dispatch_state IN ('not_queued', 'queued', 'retry_pending')
              AND (next_retry_at IS NULL OR next_retry_at <= %s)
            ORDER BY evaluation_sequence
            LIMIT %s
            FOR UPDATE SKIP LOCKED
            """,
            (self.id, fields.Datetime.now(), self.execution_batch_size),
        )
        ids = [row[0] for row in self.env.cr.fetchall()]
        return self.env["newsletter.recipient.eligibility"].browse(ids)

    def _process_next_dispatch_batch(self):
        self.ensure_one()

        if self.state == "queued":
            self.write({"state": "sending"})

        recipients = self._lock_next_dispatch_batch()

        if not recipients:
            self._recompute_execution_counts()
            self._reconcile_and_finalize_if_complete()
            return

        for eligibility in recipients:
            self._dispatch_recipient(eligibility)

        self._recompute_execution_counts()
        self._reconcile_and_finalize_if_complete()

    def _recompute_execution_counts(self):
        self.ensure_one()
        eligible = self.eligibility_ids.filtered(lambda e: e.status == "eligible")

        counts = {}
        for eligibility in eligible:
            counts[eligibility.dispatch_state] = counts.get(eligibility.dispatch_state, 0) + 1

        self.write(
            {
                "queued_count": counts.get("queued", 0) + counts.get("not_queued", 0),
                "processing_count": counts.get("processing", 0),
                "sent_count": counts.get("sent", 0),
                "failed_count": counts.get("failed", 0),
                "blocked_at_dispatch_count": counts.get("blocked", 0),
                "retry_pending_count": counts.get("retry_pending", 0),
                "cancelled_count": counts.get("cancelled", 0),
                "last_reconciled_at": fields.Datetime.now(),
            }
        )

        if self.current_outcome_id and not self.current_outcome_id.finalized:
            # sudo(): this is a system bookkeeping side-effect of an
            # already-authorized action (cancel/suspend/dispatch), not a
            # user-directed edit of the outcome record - a Campaign
            # Operator legitimately triggers this without needing direct
            # write access to newsletter.campaign.outcome itself.
            self.current_outcome_id.sudo().write({"sent_count": counts.get("sent", 0)})

        return counts

    def _reconcile_and_finalize_if_complete(self):
        self.ensure_one()

        eligible_count = len(self.eligibility_ids.filtered(lambda e: e.status == "eligible"))
        counts = {
            "not_queued": 0,
            "queued": self.queued_count,
            "processing": self.processing_count,
            "sent": self.sent_count,
            "retry_pending": self.retry_pending_count,
            "failed": self.failed_count,
            "blocked": self.blocked_at_dispatch_count,
            "cancelled": self.cancelled_count,
        }

        if not reconciliation_service.is_complete(eligible_count, counts):
            if self.state not in ("cancelled",):
                self.write({"state": "partially_completed"})
            return

        if not reconciliation_service.reconciles(eligible_count, counts):
            # Should not happen if counts are computed correctly, but never
            # silently mark a mismatched run complete.
            return

        completion_state = reconciliation_service.classify_completion(counts)
        self.write(
            {
                "state": completion_state,
                "execution_completed_at": fields.Datetime.now(),
            }
        )
        self.mailing_id.write({"compliance_state": "completed"})

        total_retries = sum(e.dispatch_attempt_count - 1 for e in self.eligibility_ids if e.dispatch_attempt_count > 1)
        self.mailing_id.message_post(
            body=_(
                "Campaign execution completed (%(status)s). Sent %(sent)s, "
                "blocked %(blocked)s, failed %(failed)s, cancelled %(cancelled)s, "
                "retries %(retries)s.",
                status=completion_state,
                sent=self.sent_count,
                blocked=self.blocked_at_dispatch_count,
                failed=self.failed_count,
                cancelled=self.cancelled_count,
                retries=total_retries,
            )
        )

        self._create_campaign_archive()

    # -- R4: Archive ----------------------------------------------------------
    def _create_campaign_archive(self):
        self.ensure_one()

        if self.archive_id:
            return self.archive_id

        if self.state not in ("completed", "completed_with_errors"):
            raise UserError(_("Only completed runs can be archived."))

        archive_vals = archive_service.build_archive_vals(self.mailing_id, self)
        archive = self.env["newsletter.campaign.archive"].sudo().create(archive_vals)

        attachment_vals_list = archive_service.build_attachment_vals(self.env, self.mailing_id)
        for vals in attachment_vals_list:
            vals["archive_id"] = archive.id
        if attachment_vals_list:
            archive_attachments = self.env["newsletter.campaign.archive.attachment"].sudo().create(
                attachment_vals_list
            )
            for archive_attachment in archive_attachments:
                archive_attachment.attachment_copy_id.sudo().write(
                    {
                        "res_model": archive_attachment._name,
                        "res_id": archive_attachment.id,
                    }
                )

        archive._calculate_and_lock()

        # The outcome was already created at execution start (so bounce/
        # complaint rates could be monitored live) - link it to the now-
        # locked archive rather than creating a second one.
        outcome = self.current_outcome_id
        if not outcome:
            outcome = self.env["newsletter.campaign.outcome"].sudo().create(
                {
                    "campaign_run_id": self.id,
                    "mailing_id": self.mailing_id.id,
                }
            )
            self.write({"current_outcome_id": outcome.id})
        outcome.sudo().write({"archive_id": archive.id})

        self.write({"archive_id": archive.id, "state": "archived"})

        eligible = self.eligibility_ids.filtered(lambda e: e.status == "eligible")
        for eligibility in eligible[:1]:
            self._create_event(eligibility, "campaign_completed")

        return archive

    def action_verify_integrity(self):
        self.ensure_one()
        result = integrity_service.verify_run_integrity(self)
        if result["all_ok"]:
            message = _("Integrity verification passed: event chain and archive both match their stored hashes.")
        else:
            message = _(
                "Integrity verification FAILED: events_ok=%(events_ok)s archive_ok=%(archive_ok)s",
                events_ok=result["events_ok"],
                archive_ok=result["archive_ok"],
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Integrity Verification"),
                "message": message,
                "type": "success" if result["all_ok"] else "danger",
                "sticky": not result["all_ok"],
            },
        }

    @api.model
    def _cron_verify_integrity(self):
        """Periodic sweep re-verifying event-chain/archive/outcome hashes
        for archived runs (R6 blueprint §26 "newsletter_integrity_verifier").
        integrity_service already raises an archive_integrity_failure alert
        on mismatch, so this cron's only job is to call it regularly rather
        than only on-demand via the button.
        """
        runs = self.search([("state", "=", "archived"), ("archive_id", "!=", False)])
        for run in runs:
            try:
                integrity_service.verify_run_integrity(run)
                self.env.cr.commit()
            except Exception:
                self.env.cr.rollback()
                _logger.exception("Integrity verification failed for run %s", run.reference)

    @api.model
    def _cron_process_campaign_dispatch(self):
        runs = self.search(
            [("state", "in", ["queued", "sending", "partially_completed"])], limit=10
        )
        for run in runs:
            try:
                run._process_next_dispatch_batch()
                self.env.cr.commit()
            except Exception:
                self.env.cr.rollback()
                _logger.exception(
                    "Campaign dispatch failed for run %s", run.reference
                )
