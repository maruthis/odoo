/** data-menu-xmlid values from custom-addons/newsletter_compliance/views/menu_views.xml,
 * kept in one place so a future menu rename only needs updating here. */
export const MENU = {
  dashboard: "newsletter_compliance.menu_newsletter_dashboard",

  myCampaigns: "newsletter_compliance.menu_newsletter_campaign_my",
  contentReviewQueue: "newsletter_compliance.menu_newsletter_campaign_content_review_queue",
  complianceReviewQueue: "newsletter_compliance.menu_newsletter_campaign_compliance_review_queue",
  preflightRequired: "newsletter_compliance.menu_newsletter_campaign_preflight_required",
  readyToSend: "newsletter_compliance.menu_newsletter_campaign_ready",
  rejected: "newsletter_compliance.menu_newsletter_campaign_rejected",
  approvalHistory: "newsletter_compliance.menu_newsletter_campaign_approval_history",

  activeRuns: "newsletter_compliance.menu_newsletter_execution_active_runs",
  retryPending: "newsletter_compliance.menu_newsletter_execution_retry_pending",
  failedRecipients: "newsletter_compliance.menu_newsletter_execution_failed",
  dispatchBlocked: "newsletter_compliance.menu_newsletter_execution_blocked",
  completedRuns: "newsletter_compliance.menu_newsletter_execution_completed_runs",

  deliverabilityOutcomes: "newsletter_compliance.menu_newsletter_deliverability_outcomes",
  deliveryEvents: "newsletter_compliance.menu_newsletter_deliverability_events",

  activeAlerts: "newsletter_compliance.menu_newsletter_monitoring_alerts",

  auditCampaignRuns: "newsletter_compliance.menu_newsletter_audit_campaign_run",
  auditRecipientDecisions: "newsletter_compliance.menu_newsletter_audit_recipient_eligibility",
  auditSendEvents: "newsletter_compliance.menu_newsletter_audit_send_events",
  auditCampaignArchives: "newsletter_compliance.menu_newsletter_audit_campaign_archives",
  auditExports: "newsletter_compliance.menu_newsletter_audit_exports",
  auditIntegrityVerification: "newsletter_compliance.menu_newsletter_audit_integrity_verification",

  privacyRequests: "newsletter_compliance.menu_newsletter_privacy_requests",
  retentionPolicies: "newsletter_compliance.menu_newsletter_retention_policies",
  retentionActionLedger: "newsletter_compliance.menu_newsletter_retention_action_ledger",
  retentionExceptions: "newsletter_compliance.menu_newsletter_retention_exceptions",
  legalHolds: "newsletter_compliance.menu_newsletter_legal_holds",

  consentRecords: "newsletter_compliance.menu_newsletter_consent_record",
  activeConsents: "newsletter_compliance.menu_newsletter_consent_record_active",

  activeSuppressions: "newsletter_compliance.menu_newsletter_suppression_entry_active",
  allSuppressions: "newsletter_compliance.menu_newsletter_suppression_entry",

  configuration: "newsletter_compliance.menu_newsletter_compliance_configuration",
  configConsentPurposes: "newsletter_compliance.menu_newsletter_compliance_configuration_purpose",
  configBrands: "newsletter_compliance.menu_newsletter_compliance_configuration_brand",
  configDelivery: "newsletter_compliance.menu_newsletter_compliance_configuration_delivery",
} as const;
