import datetime
import json

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class NewsletterPrivacyRequest(models.Model):
    _name = "newsletter.privacy.request"
    _description = "Newsletter Privacy Request"
    _order = "received_at desc, id desc"
    _inherit = ["mail.thread"]

    reference = fields.Char(readonly=True, copy=False, default="New")

    request_type = fields.Selection(
        [
            ("access", "Access"),
            ("export", "Export"),
            ("correction", "Correction"),
            ("erasure", "Erasure"),
            ("restriction", "Restriction"),
            ("objection", "Objection"),
            ("consent_history", "Consent History"),
            ("marketing_opt_out", "Marketing Opt-Out"),
        ],
        required=True,
        tracking=True,
    )

    requester = fields.Char(help="Name/contact of whoever submitted the request.")
    partner_id = fields.Many2one("res.partner", ondelete="set null")
    email_normalized = fields.Char()

    received_at = fields.Datetime(default=fields.Datetime.now, required=True)
    due_at = fields.Datetime(compute="_compute_due_at", store=True)

    status = fields.Selection(
        [
            ("received", "Received"),
            ("identity_verification", "Identity Verification"),
            ("discovery", "Discovery"),
            ("legal_review", "Legal / Retention Check"),
            ("decision", "Decision"),
            ("execution", "Execution"),
            ("completed", "Completed"),
        ],
        default="received",
        required=True,
        tracking=True,
    )

    identity_verified = fields.Boolean(default=False, tracking=True)
    verification_method = fields.Char()

    assigned_to = fields.Many2one("res.users")

    decision = fields.Selection(
        [
            ("fulfil", "Fulfil"),
            ("partial", "Partially Fulfil"),
            ("reject", "Reject"),
        ],
    )
    decision_reason = fields.Text()
    completed_at = fields.Datetime(readonly=True)

    discovery_manifest = fields.Text(readonly=True, help="JSON summary of records found.")
    discovery_counts = fields.Text(readonly=True)

    retention_action_ids = fields.One2many(
        "newsletter.retention.action", "privacy_request_id", string="Actions Taken"
    )

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    @api.depends("received_at")
    def _compute_due_at(self):
        for request in self:
            request.due_at = (
                request.received_at + datetime.timedelta(days=30) if request.received_at else False
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("reference", "New") == "New":
                vals["reference"] = (
                    self.env["ir.sequence"].next_by_code("newsletter.privacy.request") or "New"
                )
        return super().create(vals_list)

    def action_verify_identity(self, method):
        self.ensure_one()
        if not method:
            raise UserError(_("A verification method is required."))
        self.write(
            {
                "identity_verified": True,
                "verification_method": method,
                "status": "discovery",
            }
        )
        self.message_post(body=_("Identity verified via %(method)s.", method=method))

    def action_verify_identity_button(self):
        """No-argument wrapper so this can be wired to a form button -
        uses whatever verification_method is already filled in on the
        record."""
        self.ensure_one()
        self.action_verify_identity(self.verification_method)

    def action_run_discovery(self):
        from ..services import privacy_discovery_service

        self.ensure_one()
        discovery = privacy_discovery_service.discover(
            self.env, partner=self.partner_id, email_normalized=self.email_normalized
        )
        self.write(
            {
                "discovery_counts": json.dumps(discovery["counts"]),
                "status": "legal_review" if self.status == "discovery" else self.status,
            }
        )
        return discovery

    def action_decide(self, decision, reason):
        self.ensure_one()
        if not reason:
            raise UserError(_("A decision reason is required."))
        self.write({"decision": decision, "decision_reason": reason, "status": "decision"})

    def action_execute(self):
        from ..services import erasure_service, privacy_discovery_service

        self.ensure_one()

        if self.request_type in ("erasure", "restriction") and not self.identity_verified:
            raise UserError(
                _("Identity must be verified before an erasure/restriction request can be executed.")
            )

        if self.request_type not in ("erasure", "restriction"):
            # access/export/consent_history etc. don't mutate data - just
            # confirm discovery has been run so there's something to export.
            self.write({"status": "execution"})
            return []

        discovery = privacy_discovery_service.discover(
            self.env, partner=self.partner_id, email_normalized=self.email_normalized
        )
        results = erasure_service.execute(self.env, discovery["manifest"], privacy_request=self)
        self.write({"status": "execution"})
        return results

    def action_complete(self):
        self.ensure_one()
        if self.request_type in ("erasure", "restriction") and not self.retention_action_ids:
            raise UserError(
                _("This request has no recorded actions yet - run execution before completing it.")
            )
        self.write({"status": "completed", "completed_at": fields.Datetime.now()})

    @api.model
    def _cron_monitor_overdue_requests(self):
        """Raises/refreshes a single operational alert for privacy
        requests past their due_at while still open (R6 blueprint §26/§37)."""
        overdue_count = self.sudo().search_count(
            [("status", "!=", "completed"), ("due_at", "<", fields.Datetime.now())]
        )
        if not overdue_count:
            return
        self.env["newsletter.compliance.alert"]._create_or_update_alert(
            "privacy_request_overdue",
            "critical" if overdue_count >= 3 else "warning",
            "overdue_privacy_requests",
            float(overdue_count),
            0.0,
        )
