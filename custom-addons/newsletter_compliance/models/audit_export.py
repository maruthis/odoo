import base64
import datetime
import json

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..services import config_service


class NewsletterAuditExport(models.Model):
    _name = "newsletter.audit.export"
    _description = "Newsletter Audit Export"
    _order = "generated_at desc, id desc"

    reference = fields.Char(readonly=True, copy=False, default="New")

    export_type = fields.Selection(
        [
            ("campaign", "Campaign Package"),
            ("recipient", "Recipient Package"),
        ],
        required=True,
    )

    campaign_run_id = fields.Many2one(
        "newsletter.campaign.run", index=True, ondelete="set null"
    )
    privacy_request_id = fields.Many2one(
        "newsletter.privacy.request", index=True, ondelete="set null"
    )

    generated_by_id = fields.Many2one(
        "res.users", default=lambda self: self.env.user, required=True
    )
    generated_at = fields.Datetime(default=fields.Datetime.now, required=True)

    masked = fields.Boolean(default=True)
    record_count = fields.Integer(default=0)
    file_hash = fields.Char(readonly=True)
    purpose = fields.Text()

    attachment_id = fields.Many2one("ir.attachment", readonly=True, ondelete="set null")
    download_count = fields.Integer(default=0)

    expires_at = fields.Datetime()

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
                    self.env["ir.sequence"].next_by_code("newsletter.audit.export") or "New"
                )
            vals.setdefault(
                "expires_at",
                fields.Datetime.now()
                + datetime.timedelta(days=config_service.get_audit_export_expiry_days(self.env)),
            )
        return super().create(vals_list)

    def action_generate_campaign_package(self):
        from ..services import audit_export_service

        self.ensure_one()
        if self.export_type != "campaign" or not self.campaign_run_id:
            raise UserError(_("A campaign run is required for a campaign package export."))

        package, file_hash = audit_export_service.build_campaign_package(
            self.env, self.campaign_run_id, masked=self.masked
        )
        self._attach_package(package, file_hash, record_count=1)

    def action_generate_recipient_package(self, discovery_manifest):
        from ..services import audit_export_service

        self.ensure_one()
        package, file_hash = audit_export_service.build_recipient_package(
            self.env, discovery_manifest, masked=self.masked
        )
        record_count = sum(len(v) for v in discovery_manifest.values())
        self._attach_package(package, file_hash, record_count=record_count)

    def _attach_package(self, package, file_hash, record_count):
        self.ensure_one()
        content = json.dumps(package, indent=2, sort_keys=True, default=str).encode("utf-8")
        attachment = self.env["ir.attachment"].sudo().create(
            {
                "name": f"{self.reference}.json",
                "datas": base64.b64encode(content),
                "res_model": self._name,
                "res_id": self.id,
                "mimetype": "application/json",
            }
        )
        self.write(
            {
                "attachment_id": attachment.id,
                "file_hash": file_hash,
                "record_count": record_count,
            }
        )

    def action_download(self):
        self.ensure_one()
        if not self.attachment_id:
            raise UserError(_("This export has no generated file (it may have expired)."))
        self.write({"download_count": self.download_count + 1})
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{self.attachment_id.id}?download=true",
            "target": "self",
        }

    @api.model
    def _cron_expire_audit_exports(self):
        expired = self.search(
            [("expires_at", "<=", fields.Datetime.now()), ("attachment_id", "!=", False)]
        )
        for export in expired:
            export.attachment_id.sudo().unlink()
            export.write({"attachment_id": False})
