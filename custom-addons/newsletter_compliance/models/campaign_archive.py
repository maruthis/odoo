import hashlib
import json

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class NewsletterCampaignArchiveAttachment(models.Model):
    _name = "newsletter.campaign.archive.attachment"
    _description = "Newsletter Campaign Archive Attachment Snapshot"

    archive_id = fields.Many2one(
        "newsletter.campaign.archive", required=True, index=True, ondelete="cascade"
    )
    filename = fields.Char(required=True)
    mimetype = fields.Char()
    size = fields.Integer()
    checksum = fields.Char(string="SHA-256")
    attachment_copy_id = fields.Many2one(
        "ir.attachment",
        ondelete="restrict",
        readonly=True,
        help="A protected copy of the file content as it existed at "
        "archive time - distinct from the mailing's original attachment, "
        "which remains editable/deletable on the mailing itself.",
    )

    def write(self, vals):
        raise UserError(_("Archive attachment snapshots are immutable."))

    def unlink(self):
        raise UserError(_("Archive attachment snapshots cannot be deleted."))


class NewsletterCampaignArchive(models.Model):
    _name = "newsletter.campaign.archive"
    _description = "Newsletter Campaign Archive"
    _inherit = ["newsletter.retention.mixin"]
    _order = "create_date desc, id desc"
    _rec_name = "reference"

    reference = fields.Char(readonly=True, copy=False, default="New")

    mailing_id = fields.Many2one(
        "mailing.mailing", required=True, index=True, ondelete="restrict"
    )
    campaign_run_id = fields.Many2one(
        "newsletter.campaign.run", required=True, index=True, ondelete="restrict"
    )
    campaign_compliance_id = fields.Char(readonly=True)
    governance_version = fields.Integer(readonly=True)
    approval_version = fields.Integer(readonly=True)
    archive_version = fields.Integer(default=1, readonly=True)

    brand_id = fields.Many2one("newsletter.campaign.brand", readonly=True, ondelete="restrict")
    consent_purpose_id = fields.Many2one(
        "newsletter.consent.purpose", readonly=True, ondelete="restrict"
    )

    created_at = fields.Datetime(readonly=True, default=fields.Datetime.now)
    created_by_id = fields.Many2one(
        "res.users", readonly=True, default=lambda self: self.env.user
    )

    # -- Content snapshot ---------------------------------------------------
    subject_snapshot = fields.Char(readonly=True)
    preview_snapshot = fields.Char(readonly=True)
    email_from_snapshot = fields.Char(readonly=True)
    reply_to_snapshot = fields.Char(readonly=True)
    body_html_snapshot = fields.Html(readonly=True, sanitize=False)
    physical_address_snapshot = fields.Text(readonly=True)

    attachment_ids = fields.One2many(
        "newsletter.campaign.archive.attachment", "archive_id", readonly=True
    )

    # -- Recipient-definition snapshot --------------------------------------
    mailing_model_snapshot = fields.Char(readonly=True)
    mailing_domain_snapshot = fields.Text(readonly=True)
    mailing_list_snapshot = fields.Text(readonly=True)

    targeted_count = fields.Integer(readonly=True)
    eligible_count = fields.Integer(readonly=True)
    excluded_count = fields.Integer(readonly=True)

    # -- Approval snapshot ----------------------------------------------------
    business_owner_id = fields.Many2one("res.users", readonly=True)
    content_approved_by_id = fields.Many2one("res.users", readonly=True)
    content_approved_at = fields.Datetime(readonly=True)
    compliance_approved_by_id = fields.Many2one("res.users", readonly=True)
    compliance_approved_at = fields.Datetime(readonly=True)
    approval_content_hash = fields.Char(readonly=True)
    preflight_result_hash = fields.Char(readonly=True)
    ruleset_version = fields.Char(readonly=True)

    # -- Execution snapshot ---------------------------------------------------
    execution_started_at = fields.Datetime(readonly=True)
    execution_completed_at = fields.Datetime(readonly=True)
    execution_started_by_id = fields.Many2one("res.users", readonly=True)

    sent_count = fields.Integer(readonly=True)
    blocked_at_dispatch_count = fields.Integer(readonly=True)
    failed_count = fields.Integer(readonly=True)
    cancelled_count = fields.Integer(readonly=True)
    retry_count = fields.Integer(readonly=True)

    # -- Integrity / lock -------------------------------------------------------
    locked = fields.Boolean(default=False, readonly=True)
    locked_at = fields.Datetime(readonly=True)
    archive_hash = fields.Char(readonly=True)

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("reference", "New") == "New":
                vals["reference"] = (
                    self.env["ir.sequence"].next_by_code("newsletter.campaign.archive") or "New"
                )
        return super().create(vals_list)

    def _build_archive_hash(self):
        self.ensure_one()
        payload = {
            "campaign_compliance_id": self.campaign_compliance_id or "",
            "campaign_run": self.campaign_run_id.reference or "",
            "subject": self.subject_snapshot or "",
            "email_from": self.email_from_snapshot or "",
            "reply_to": self.reply_to_snapshot or "",
            "body_html_hash": hashlib.sha256(
                (self.body_html_snapshot or "").encode("utf-8")
            ).hexdigest(),
            "attachment_hashes": sorted(self.attachment_ids.mapped("checksum")),
            "consent_purpose_id": self.consent_purpose_id.id or False,
            "governance_version": self.governance_version,
            "approval_content_hash": self.approval_content_hash or "",
            "preflight_result_hash": self.preflight_result_hash or "",
            "targeted_count": self.targeted_count,
            "eligible_count": self.eligible_count,
            "sent_count": self.sent_count,
            "execution_completed_at": self.execution_completed_at.isoformat()
            if self.execution_completed_at
            else "",
        }
        encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _calculate_and_lock(self):
        for archive in self:
            archive_hash = archive._build_archive_hash()
            super(NewsletterCampaignArchive, archive).write(
                {
                    "archive_hash": archive_hash,
                    "locked": True,
                    "locked_at": fields.Datetime.now(),
                }
            )

    def verify_integrity(self):
        """Recompute the archive hash from stored snapshot fields and
        compare against the locked hash. Returns True only if unchanged.
        """
        for archive in self:
            if archive._build_archive_hash() != archive.archive_hash:
                return False
        return True

    def action_verify_integrity(self):
        self.ensure_one()
        ok = self.verify_integrity()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Archive Integrity"),
                "message": _("Archive hash verified: matches stored content.")
                if ok
                else _("Archive hash mismatch - stored content may have been altered."),
                "type": "success" if ok else "danger",
                "sticky": not ok,
            },
        }

    # Fields the retention engine (or a legal hold) may still update after
    # the archive is locked - none of them touch the evidentiary content,
    # so allowing them doesn't weaken immutability.
    _RETENTION_MIXIN_FIELDS = {
        "retention_policy_id",
        "retention_start_at",
        "retain_until",
        "retention_state",
        "legal_hold",
        "retention_basis",
    }

    def write(self, vals):
        if self.env.context.get("skip_archive_lock_guard"):
            return super().write(vals)
        if self.filtered("locked") and set(vals) - self._RETENTION_MIXIN_FIELDS:
            raise UserError(_("Archived campaign evidence cannot be modified."))
        return super().write(vals)

    def unlink(self):
        raise UserError(_("Campaign archives cannot be deleted."))
