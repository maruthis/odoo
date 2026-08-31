"""Tests for dispatch_service.send_recipient()'s open/click tracking wiring.

services/dispatch_service.py bypasses mass_mailing's own send queue (see
its module docstring - the frozen-population/retry/audit requirements in
R3/R4 need more control than that queue offers), which meant Odoo's
native "Opened"/"Clicked" statistics on mailing.mailing could never move
off zero: those are computed from mailing.trace + link_tracker_click rows
that only mass_mailing's own pipeline used to create. send_recipient() now
creates a mailing.trace inline with the mail.mail it sends, and converts
the body's links through mailing.convert_links() first, so a real click
can be measured through the same public /r/<code>/m/<trace_id> redirect
mass_mailing itself uses.

No mocking of mail.mail.send() is needed here: ir.mail_server._disable_send()
is True for the whole duration of any Odoo test run (see
odoo/addons/base/models/ir_mail_server.py), so send() always no-ops
harmlessly regardless of what outgoing mail server is configured on the
database - the mail.mail and mailing.trace rows this suite asserts on are
already created before send() is even called.
"""
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.newsletter_compliance.services import dispatch_service


@tagged("post_install", "-at_install")
class TestNewsletterClickTracking(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Click Tracking Purpose",
                "code": "CLICK_TRACKING_PURPOSE",
                "privacy_notice_version": "v1",
            }
        )
        cls.brand = cls.env["newsletter.campaign.brand"].create(
            {
                "name": "Click Tracking Brand",
                "code": "CLICK_TRACKING_BRAND",
                "email_from": "clicktracking@example.com",
                "physical_address": "1 Click Tracking St",
                "default_consent_purpose_id": cls.purpose.id,
            }
        )
        cls.partner_model = cls.env["ir.model"]._get("res.partner")
        cls.mailing_contact_model = cls.env["ir.model"]._get("mailing.contact")

        cls.approver = cls.env["res.users"].create(
            {
                "name": "Approver Click Test",
                "login": "approver_click_test",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref("mass_mailing.group_mass_mailing_user").id,
                            cls.env.ref(
                                "newsletter_compliance.group_newsletter_content_approver"
                            ).id,
                        ],
                    )
                ],
            }
        )
        cls.reviewer = cls.env["res.users"].create(
            {
                "name": "Reviewer Click Test",
                "login": "reviewer_click_test",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref("mass_mailing.group_mass_mailing_user").id,
                            cls.env.ref(
                                "newsletter_compliance.group_newsletter_compliance_reviewer"
                            ).id,
                        ],
                    )
                ],
            }
        )

    def _make_partner_with_consent(self, name, email):
        partner = self.env["res.partner"].create({"name": name, "email": email})
        self.env["newsletter.consent.record"].create(
            {
                "partner_id": partner.id,
                "purpose_id": self.purpose.id,
                "status": "active",
                "given_at": "2026-01-01 10:00:00",
                "source": "website",
                "channel": "web",
                "privacy_notice_version": "v1",
            }
        )
        return partner

    def _create_ready_campaign(self, partner_ids, body_html="<p>Content</p>"):
        campaign = self.env["mailing.mailing"].create(
            {
                "name": "Click Tracking Campaign",
                "subject": "Click Tracking Subject",
                "mailing_type": "mail",
                "mailing_model_id": self.partner_model.id,
                "mailing_domain": repr([("id", "in", partner_ids)]),
                "brand_id": self.brand.id,
                "consent_purpose_id": self.purpose.id,
                "email_from": "clicktracking@example.com",
                "body_html": body_html,
            }
        )
        campaign.action_submit_content_review()
        campaign.with_user(self.approver).action_approve_content()
        campaign.with_user(self.reviewer).action_approve_compliance()
        campaign.with_user(self.reviewer).action_run_compliance_preflight()
        self.assertEqual(campaign.compliance_state, "ready")
        return campaign

    def _dispatch_one(self, campaign, body_html="<p>Content</p>"):
        """Runs the real send_recipient() (not mocked) for the run's one
        eligible recipient, and returns (result, eligibility)."""
        run = campaign.current_campaign_run_id
        eligibility = run.eligibility_ids.filtered(lambda e: e.status == "eligible")
        self.assertEqual(len(eligibility), 1)
        result = dispatch_service.send_recipient(self.env, campaign, eligibility)
        return result, eligibility

    def test_send_recipient_creates_mailing_trace(self):
        partner = self._make_partner_with_consent("Trace One", "trace.one@example.com")
        campaign = self._create_ready_campaign(partner.ids)
        result, eligibility = self._dispatch_one(campaign)

        self.assertTrue(result["accepted"])

        trace = self.env["mailing.trace"].search([("mass_mailing_id", "=", campaign.id)])
        self.assertEqual(len(trace), 1)
        self.assertEqual(trace.model, "res.partner")
        self.assertEqual(trace.res_id, partner.id)
        self.assertEqual(trace.email, eligibility.email_normalized)

    def test_send_recipient_converts_links_for_click_tracking(self):
        partner = self._make_partner_with_consent("Convert One", "convert.one@example.com")
        campaign = self._create_ready_campaign(
            partner.ids,
            body_html='<p>Visit <a href="https://example.com/landing-page">our page</a></p>',
        )
        self._dispatch_one(campaign)

        link_tracker = self.env["link.tracker"].search([("mass_mailing_id", "=", campaign.id)])
        self.assertEqual(len(link_tracker), 1)
        self.assertEqual(link_tracker.url, "https://example.com/landing-page")

    def test_click_increments_clicked_and_opened_counts(self):
        partner = self._make_partner_with_consent("Click One", "click.one@example.com")
        campaign = self._create_ready_campaign(
            partner.ids,
            body_html='<p>Visit <a href="https://example.com/landing-page">our page</a></p>',
        )
        self._dispatch_one(campaign)

        trace = self.env["mailing.trace"].search([("mass_mailing_id", "=", campaign.id)])
        link_tracker = self.env["link.tracker"].search([("mass_mailing_id", "=", campaign.id)])

        self.assertEqual(campaign.clicked, 0)
        self.assertEqual(campaign.opened, 0)

        # Exercises the same public entry point the /r/<code>/m/<trace_id>
        # redirect controller calls - a click always implies an open too
        # (mass_mailing's own link_tracker.py override).
        click = self.env["link.tracker.click"].add_click(
            link_tracker.code, mailing_trace_id=trace.id
        )
        self.assertTrue(click)

        campaign.invalidate_recordset(["clicked", "opened"])
        self.assertEqual(campaign.clicked, 1)
        self.assertEqual(campaign.opened, 1)
        self.assertEqual(trace.trace_status, "open")

    def test_send_recipient_survives_mail_mail_auto_delete(self):
        """provider_message_id / open-pixel lookups key off mail_mail_id_int
        (a plain integer, not the mail_mail_id relation) specifically so
        tracking keeps working after auto_delete purges the mail.mail row -
        see mailing_trace.py's own comment on that field."""
        partner = self._make_partner_with_consent("Autodel One", "autodel.one@example.com")
        campaign = self._create_ready_campaign(partner.ids)
        result, _eligibility = self._dispatch_one(campaign)

        trace = self.env["mailing.trace"].search([("mass_mailing_id", "=", campaign.id)])
        self.assertEqual(trace.mail_mail_id_int, int(result["provider_message_id"]))

    def test_trace_document_prefers_partner_over_mailing_contact(self):
        contact = self.env["mailing.contact"].create(
            {"name": "Contact Fallback", "email": "contact.fallback@example.com"}
        )
        partner = self.env["res.partner"].create(
            {"name": "Partner Preferred", "email": "partner.preferred@example.com"}
        )
        eligibility = self.env["newsletter.recipient.eligibility"].new(
            {"partner_id": partner.id, "mailing_contact_id": contact.id}
        )
        model, res_id = dispatch_service._mailing_trace_document(eligibility)
        self.assertEqual(model, "res.partner")
        self.assertEqual(res_id, partner.id)

    def test_trace_document_falls_back_to_mailing_contact(self):
        contact = self.env["mailing.contact"].create(
            {"name": "Contact Only", "email": "contact.only@example.com"}
        )
        eligibility = self.env["newsletter.recipient.eligibility"].new(
            {"partner_id": False, "mailing_contact_id": contact.id}
        )
        model, res_id = dispatch_service._mailing_trace_document(eligibility)
        self.assertEqual(model, "mailing.contact")
        self.assertEqual(res_id, contact.id)

    def test_trace_document_none_when_no_recipient_document(self):
        eligibility = self.env["newsletter.recipient.eligibility"].new(
            {"partner_id": False, "mailing_contact_id": False}
        )
        model, res_id = dispatch_service._mailing_trace_document(eligibility)
        self.assertFalse(model)
        self.assertFalse(res_id)

    def test_send_recipient_without_recipient_document_skips_trace_gracefully(self):
        """A frozen eligibility row always has one or the other in
        practice, but tracking must never be able to break a send even if
        that assumption is ever wrong somewhere upstream."""
        partner = self._make_partner_with_consent("No Doc One", "no.doc.one@example.com")
        campaign = self._create_ready_campaign(partner.ids)
        run = campaign.current_campaign_run_id
        eligibility = run.eligibility_ids.filtered(lambda e: e.status == "eligible")
        # frozen eligibility rows reject writes outside execution-mutable
        # fields - mirrors the same escape hatch pseudonymize() uses.
        eligibility.with_context(skip_eligibility_freeze_guard=True).write(
            {"partner_id": False, "mailing_contact_id": False}
        )

        result = dispatch_service.send_recipient(self.env, campaign, eligibility)

        self.assertTrue(result["accepted"])
        trace = self.env["mailing.trace"].search([("mass_mailing_id", "=", campaign.id)])
        self.assertFalse(trace)
