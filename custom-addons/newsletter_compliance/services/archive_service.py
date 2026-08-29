"""Builds the immutable archive snapshot from a completed campaign run."""
import hashlib
import json


def build_archive_vals(mailing, run):
    return {
        "mailing_id": mailing.id,
        "campaign_run_id": run.id,
        "campaign_compliance_id": mailing.compliance_campaign_id,
        "governance_version": run.governance_version,
        "approval_version": mailing.approval_version,
        "brand_id": mailing.brand_id.id,
        "consent_purpose_id": mailing.consent_purpose_id.id,
        # content snapshot
        "subject_snapshot": mailing.subject,
        "preview_snapshot": mailing.preview,
        "email_from_snapshot": mailing.email_from,
        "reply_to_snapshot": mailing.reply_to,
        "body_html_snapshot": mailing.body_html,
        "physical_address_snapshot": mailing.brand_id.physical_address,
        # recipient-definition snapshot
        "mailing_model_snapshot": mailing.mailing_model_real,
        "mailing_domain_snapshot": mailing.mailing_domain,
        "mailing_list_snapshot": json.dumps(mailing.contact_list_ids.mapped("name")),
        "targeted_count": run.targeted_count,
        "eligible_count": run.eligible_count,
        "excluded_count": run.excluded_count,
        # approval snapshot
        "business_owner_id": mailing.business_owner_id.id,
        "content_approved_by_id": mailing.content_approved_by_id.id,
        "content_approved_at": mailing.content_approved_at,
        "compliance_approved_by_id": mailing.compliance_approved_by_id.id,
        "compliance_approved_at": mailing.compliance_approved_at,
        "approval_content_hash": mailing.approval_content_hash,
        "preflight_result_hash": run.result_hash,
        "ruleset_version": run.eligibility_ids[:1].ruleset_version if run.eligibility_ids else False,
        # execution snapshot
        "execution_started_at": run.execution_started_at,
        "execution_completed_at": run.execution_completed_at,
        "execution_started_by_id": run.execution_started_by_id.id,
        "sent_count": run.sent_count,
        "blocked_at_dispatch_count": run.blocked_at_dispatch_count,
        "failed_count": run.failed_count,
        "cancelled_count": run.cancelled_count,
        "retry_count": run.retry_pending_count,
    }


def build_attachment_vals(env, mailing):
    """Copies each mailing attachment's actual bytes into a new,
    independent ir.attachment so the archive holds real evidence rather
    than only a hash of content that could later be edited or deleted on
    the mailing itself (R6 §7.12 / §20 "Attachments + hashes").
    """
    vals_list = []
    for attachment in mailing.attachment_ids:
        data = attachment.raw or b""
        copy = env["ir.attachment"].sudo().create(
            {
                "name": attachment.name,
                "datas": attachment.datas,
                "mimetype": attachment.mimetype,
            }
        )
        vals_list.append(
            {
                "filename": attachment.name,
                "mimetype": attachment.mimetype,
                "size": attachment.file_size,
                "checksum": hashlib.sha256(data).hexdigest(),
                "attachment_copy_id": copy.id,
            }
        )
    return vals_list
