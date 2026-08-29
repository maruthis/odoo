export const BASE_URL = process.env.ODOO_BASE_URL || "http://localhost:8069";
export const DB_NAME = process.env.ODOO_DB || "odoo19";
export const ADMIN_LOGIN = process.env.ODOO_ADMIN_LOGIN || "admin";
export const ADMIN_PASSWORD = process.env.ODOO_ADMIN_PASSWORD || "admin";

// Every demo user shares one password for simplicity - this is a local
// test-automation fixture, not a real credential.
export const DEMO_PASSWORD = "Demo12345!";

export interface RoleDefinition {
  key: string;
  login: string;
  name: string;
  /** External IDs of newsletter_compliance groups this role should hold,
   * beyond the base groups every demo user gets. */
  groupXmlIds: string[];
}

// Mirrors "Appendix A - Setting Up Demo Users" in
// mydocs/Newsletter Compliance Demo Playbook.md exactly - login names,
// and the one role each should hold.
export const ROLES: RoleDefinition[] = [
  {
    key: "author",
    login: "demo.author",
    name: "Demo Author",
    groupXmlIds: ["newsletter_compliance.group_newsletter_author"],
  },
  {
    key: "contentApprover",
    login: "demo.approver",
    name: "Demo Content Approver",
    groupXmlIds: ["newsletter_compliance.group_newsletter_content_approver"],
  },
  {
    key: "complianceReviewer",
    login: "demo.reviewer",
    name: "Demo Compliance Reviewer",
    groupXmlIds: ["newsletter_compliance.group_newsletter_compliance_reviewer"],
  },
  {
    key: "complianceAdmin",
    login: "demo.compliance.admin",
    name: "Demo Compliance Administrator",
    groupXmlIds: ["newsletter_compliance.group_newsletter_compliance_admin"],
  },
  {
    key: "operator",
    login: "demo.operator",
    name: "Demo Campaign Operator",
    groupXmlIds: ["newsletter_compliance.group_newsletter_campaign_operator"],
  },
  {
    key: "opsAdmin",
    login: "demo.ops.admin",
    name: "Demo Operations Administrator",
    groupXmlIds: ["newsletter_compliance.group_newsletter_operations_admin"],
  },
  {
    key: "privacyOfficer",
    login: "demo.privacy",
    name: "Demo Privacy Officer",
    groupXmlIds: ["newsletter_compliance.group_newsletter_privacy_officer"],
  },
  {
    key: "legalHoldAdmin",
    login: "demo.legal.hold",
    name: "Demo Legal Hold Administrator",
    groupXmlIds: ["newsletter_compliance.group_newsletter_legal_hold_admin"],
  },
  {
    key: "auditor",
    login: "demo.auditor",
    name: "Demo Compliance Audit Reviewer",
    groupXmlIds: ["newsletter_compliance.group_newsletter_compliance_auditor"],
  },
];

// Every demo user also needs standard Email Marketing access - the
// Newsletter Compliance groups layer on top of it, they don't replace it
// (see the Demo Playbook's Appendix A note).
export const BASE_GROUP_XML_IDS = ["base.group_user", "mass_mailing.group_mass_mailing_user"];
