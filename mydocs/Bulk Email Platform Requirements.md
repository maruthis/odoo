# 2\. Overall Description

## 2.1 Product Perspective

The platform is a new integration capability spanning Microsoft 365 and AWS. Microsoft SharePoint is the system of record for newsletter (HTML) content, both pre-send (draft/approved) and post-send (archived for audit). Microsoft Power Automate owns campaign initiation — it detects an approved newsletter in SharePoint and triggers the send process — and owns post-send archival back into SharePoint. Apache Camel ESB, orchestrating AWS managed services (SES, SNS, SQS), owns the actual mediation, throttling, personalization, and dispatch of email once triggered. It is not a replacement for a Customer Data Platform or CRM; it consumes recipient and consent data from those systems of record and does not itself become the system of record for consent.

## 2.2 Product Functions (Summary)

•    Author and store newsletter content as an HTML file in a designated SharePoint document library, with an approval status column

•    Trigger the campaign send process via Power Automate when a newsletter is marked approved (or on a configured schedule)

•    Ingest a recipient list for a given campaign from an internal source (database or SharePoint list)

•    Filter recipients against a suppression list prior to send

•    Retrieve the approved newsletter HTML content from SharePoint (via Microsoft Graph API) and merge recipient-specific data

•    Throttle and queue outbound sends to respect SES sending limits

•    Dispatch email via SES under a designated configuration set

•    Consume SES delivery/bounce/complaint events via SNS/SQS and update the suppression list

•    On campaign completion, archive the sent newsletter and campaign statistics to a SharePoint audit library via Power Automate

•    Provide operational visibility (counts sent, failed, bounced, complained) per campaign

## 2.3 User Classes and Characteristics

| User Class | Description | Technical Proficiency |
| --- | --- | --- |
| Newsletter Author/Approver | Authors newsletter HTML content and saves it to the SharePoint document library; sets the approval status that allows a campaign to be triggered | Low — uses SharePoint only, no direct access to Camel or AWS |
| Campaign Operator | Initiates a newsletter send by approving the SharePoint item / running the Power Automate flow; selects recipient segment | Low — uses SharePoint/Power Automate, not the underlying Camel route |
| Integration Engineer | Builds/maintains Camel routes, AWS configuration, and the Power Automate flow / Graph API integration | High |
| Compliance Reviewer | Audits consent trail, suppression list accuracy, regulatory posture, and the SharePoint archive | Medium |
| Recipient (Data Principal) | Receives the newsletter; may unsubscribe or complain | N/A — external party |

## 2.4 Operating Environment

AWS Cloud (region to be confirmed based on data-residency requirements — see Section 7), Apache Camel running on an existing enterprise integration runtime, standard enterprise network and IAM controls.

## 2.5 Design and Implementation Constraints

•    Must operate within AWS SES sending quota and rate limits applicable to the account's current sending status (sandbox vs. production)

•    Must use IAM roles with least-privilege access to SES, SNS and SQS — no long-lived static credentials embedded in Camel routes

•    Must access SharePoint via an Azure AD (Entra ID) app registration with least-privilege Microsoft Graph API permissions (application permissions scoped to the specific site/library) — no interactive user credentials embedded in the integration

•    Must not send to any address present on the suppression list at time of dispatch

# 3\. Business / Stakeholder Requirements

These are the high-level needs the platform must satisfy, from which the detailed requirements in Sections 4–8 are derived.

| ID | Requirement Description | Priority | Verification Method |
| --- | --- | --- | --- |
| BR-01 | The organization shall be able to send newsletter/marketing email to a defined recipient segment without manual, per-recipient effort. | High | Demo |
| BR-02 | The organization shall be able to demonstrate, on request, that a given recipient consented to receive the email sent to them. | High | Audit |
| BR-03 | The organization shall avoid sending to recipients who have bounced, complained, or unsubscribed. | High | Test |
| BR-04 | The organization shall be able to reuse the same platform for multiple business domains/brands under MedhAnkura and Techsophy. | Medium | Demo |
| BR-05 | The organization shall retain sender reputation (bounce/complaint rate) within thresholds required to keep SES sending privileges active. | High | Monitoring |
| BR-06 | The organization shall retain an auditable, unalterable record of every newsletter as actually sent, including when it was sent and to how many recipients, without operating a separate archival system. | High | Audit |

# 4\. Functional Requirements

### 4.1 Recipient Sourcing and Filtering

| ID | Requirement Description | Priority | Verification Method |
| --- | --- | --- | --- |
| FR-01 | The system shall retrieve the recipient list for a campaign from a configured source (database query or SharePoint list) at route execution time. | High | Test |
| FR-02 | The system shall exclude, prior to send, any recipient address present on the current suppression list. | High | Test |
| FR-03 | The system shall exclude any recipient address lacking a valid, recorded consent entry for the campaign category being sent. | High | Test |
| FR-04 | The system shall validate recipient email address syntax prior to submission to SES and reject/log malformed addresses without halting the batch. | Medium | Test |

### 4.2 Newsletter Storage and Campaign Triggering (SharePoint / Power Automate)

| ID | Requirement Description | Priority | Verification Method |
| --- | --- | --- | --- |
| FR-05 | The newsletter HTML file shall be authored and saved by the content team into a designated SharePoint document library (e.g., "Newsletters – Draft"), with metadata columns for Campaign ID, Subject Line, Segment, and Approval Status. | High | Test |
| FR-06 | A Power Automate flow shall monitor the designated SharePoint library and trigger campaign initiation automatically when a newsletter item's Approval Status is set to "Approved for Send" (alternatively, on a configured schedule for recurring newsletters). | High | Test |
| FR-07 | The Power Automate flow shall validate that required metadata (Campaign ID, Subject Line, Segment) is present before triggering the send; incomplete items shall not trigger a campaign and shall be flagged back to the author. | High | Test |
| FR-08 | The Power Automate flow shall invoke the Camel ESB campaign-initiation endpoint (HTTP/REST), passing the SharePoint file reference and campaign metadata as parameters. | High | Test |

### 4.3 Newsletter Retrieval and Personalization

| ID | Requirement Description | Priority | Verification Method |
| --- | --- | --- | --- |
| FR-09 | The system shall retrieve the approved newsletter HTML content from the specified SharePoint document library location via Microsoft Graph API at route execution time. | High | Test |
| FR-10 | The system shall use the SharePoint file version indicated by the campaign metadata (or the latest published version if unspecified). | Medium | Test |
| FR-11 | The system shall merge recipient-specific fields into the retrieved HTML content prior to send (e.g., name, personalized links) without executing arbitrary code embedded in the content. | High | Test |
| FR-12 | The system shall insert a functioning one-click unsubscribe link and a List-Unsubscribe header value unique to each recipient. | High | Test |

### 4.4 Throttling, Queuing and Dispatch

| ID | Requirement Description | Priority | Verification Method |
| --- | --- | --- | --- |
| FR-13 | The system shall throttle outbound send rate to remain within the SES account's current maximum send rate. | High | Test |
| FR-14 | The system shall buffer prepared messages in a queue (SQS) between the preparation stage and the SES dispatch stage to allow independent retry of each stage. | Medium | Test |
| FR-15 | The system shall tag every send with a campaign identifier via an SES configuration set. | High | Test |
| FR-16 | The system shall route send failures (SES throttling/errors) to a Dead Letter Channel with the original message and failure reason preserved for retry or manual review. | High | Test |
| FR-17 | The system shall apply exponential backoff before retrying a failed send, up to a configurable maximum retry count. | Medium | Test |

### 4.5 Event Feedback and Suppression Management

| ID | Requirement Description | Priority | Verification Method |
| --- | --- | --- | --- |
| FR-18 | The system shall consume SES delivery, bounce, and complaint notifications published via SNS/SQS. | High | Test |
| FR-19 | The system shall automatically add an address to the suppression list on receipt of a hard bounce or complaint event. | High | Test |
| FR-20 | The system shall process an unsubscribe request (via the one-click link) and add the address to the suppression list within a defined SLA (see NFR section). | High | Test |
| FR-21 | The system shall NOT automatically suppress an address on a soft bounce alone; soft bounces shall be counted and escalated to suppression after a configurable repeated-failure threshold. | Medium | Test |

### 4.6 Post-Send Archival (SharePoint Audit Trail)

| ID | Requirement Description | Priority | Verification Method |
| --- | --- | --- | --- |
| FR-22 | Upon completion of a campaign (all recipients processed, whether delivered, bounced, or failed), Camel shall notify Power Automate of completion via an HTTP callback/webhook, including summary statistics. | High | Test |
| FR-23 | On receipt of the completion notification, the Power Automate flow shall copy or move the sent newsletter HTML file from the draft/approved library into a designated SharePoint archive library (e.g., "Newsletters – Archive"). | High | Test |
| FR-24 | The archived newsletter item shall be tagged with audit metadata: Campaign ID, Send Date/Time, Recipient Count, Delivered Count, Bounced Count, Complained Count, and Unsubscribed Count. | High | Test |
| FR-25 | The archived newsletter item shall be set to read-only (e.g., via SharePoint content approval, versioning, or permission restriction) so that its content as sent cannot be altered retroactively. | High | Test |

### 4.7 Reporting and Operability

| ID | Requirement Description | Priority | Verification Method |
| --- | --- | --- | --- |
| FR-26 | The system shall record, per campaign, counts of: recipients targeted, sent, suppressed pre-send, delivered, bounced, complained, and unsubscribed. | High | Test |
| FR-27 | The system shall expose or log sufficient detail to reconstruct, for any single recipient, the consent basis and send history on request. | High | Audit |
| FR-28 | The system shall alert an operator when bounce rate or complaint rate for an in-progress campaign exceeds a configurable warning threshold. | High | Test |

# 5\. Interface Requirements

| Interface | Direction | Description |
| --- | --- | --- |
| SharePoint document library (Newsletters – Draft) | Inbound (read) | Source of the approved newsletter HTML content, accessed via Microsoft Graph API (FR-05, FR-09). |
| Power Automate flow (SharePoint trigger) | Inbound (trigger) | Detects newsletter approval in SharePoint and invokes the Camel campaign-initiation endpoint (FR-06–FR-08). |
| Camel campaign-initiation endpoint (HTTP/REST) | Inbound | Exposed by Camel (e.g., camel-servlet/camel-rest) for Power Automate to call when starting a campaign. |
| camel-aws2-ses | Outbound | Submits prepared email messages for delivery. |
| camel-aws2-sqs | Bidirectional | Buffers prepared sends; receives SES event notifications relayed via SNS. |
| SNS Topic (SES events) | Inbound | Publishes delivery, bounce, and complaint notifications from SES. |
| Recipient source (DB / SharePoint list) | Inbound (read) | Supplies the campaign recipient list. |
| Suppression list store | Bidirectional | Read prior to send; written on bounce/complaint/unsubscribe. |
| Consent/CRM system | Inbound (read) | Source of truth for recipient consent status, referenced by FR-03. |
| Camel completion webhook → Power Automate | Outbound | Notifies Power Automate of campaign completion and statistics to trigger archival (FR-22). |
| SharePoint document library (Newsletters – Archive) | Outbound (write) | Receives the archived, read-only newsletter with audit metadata, written by Power Automate (FR-23–FR-25). |
| Operational monitoring / alerting | Outbound | Receives campaign metrics and threshold-breach alerts (FR-26–FR-28). |

# 6\. Non-Functional Requirements

### 6.1 Performance

| ID | Requirement Description | Priority | Verification Method |
| --- | --- | --- | --- |
| NFR-01 | The system shall sustain a send throughput consistent with the SES account's approved maximum send rate without triggering throttling errors. | High | Test |
| NFR-02 | The system shall process an unsubscribe request and reflect it in the suppression list within 24 hours (target: near real-time). | High | Test |

### 6.2 Reliability and Availability

| ID | Requirement Description | Priority | Verification Method |
| --- | --- | --- | --- |
| NFR-03 | A partial failure of a batch send (e.g., transient SES error for a subset of recipients) shall not prevent successful delivery to the remaining recipients. | High | Test |
| NFR-04 | The system shall be resumable after an interruption without re-sending to recipients already successfully dispatched in that campaign run. | High | Test |

### 6.3 Security

| ID | Requirement Description | Priority | Verification Method |
| --- | --- | --- | --- |
| NFR-05 | All AWS service access shall use IAM roles scoped to least privilege; no static access keys shall be stored in Camel route configuration. | High | Review |
| NFR-06 | Recipient personal data (email address, name, merge fields) shall be encrypted in transit (TLS) and at rest (SQS default/KMS encryption; SharePoint Online default encryption for archived content). | High | Review |
| NFR-07 | Access to the suppression list and consent data shall be restricted to authorized roles and logged. | High | Review |
| NFR-08 | All Camel-to-SharePoint access shall use an Azure AD app registration with Microsoft Graph API application permissions scoped to the specific site/library; the same principle of least privilege applies to the Power Automate flow's SharePoint connection. | High | Review |

### 6.4 Maintainability and Auditability

| ID | Requirement Description | Priority | Verification Method |
| --- | --- | --- | --- |
| NFR-09 | Every campaign send shall be traceable end-to-end (recipient, newsletter version, consent basis, timestamp, outcome) for a minimum retention period aligned to the organization's data retention policy, with the SharePoint archive (FR-23–FR-25) serving as the durable audit record. | High | Audit |
| NFR-10 | Camel routes shall be independently deployable/configurable per business domain (e.g., Hospital, Insurance Brokerage) without code duplication of the core sending logic. | Medium | Review |

### 6.5 Usability

| ID | Requirement Description | Priority | Verification Method |
| --- | --- | --- | --- |
| NFR-11 | Triggering a campaign shall require only setting the SharePoint newsletter's Approval Status (plus Campaign ID, Subject Line, Segment already on the item) — no direct interaction with Camel or AWS by the Campaign Operator. | Medium | Demo |

# 7\. Regulatory and Compliance Requirements

The following requirements are prerequisites for lawful and sustainable bulk email operation. These should be read alongside, and are expected to be reflected in, the organization's existing DPDPA Compliance Roadmap (TSIS-DPO-ROADMAP-2026-001).

### 7.1 AWS SES Account Prerequisites

| ID | Requirement Description | Priority | Verification Method |
| --- | --- | --- | --- |
| RC-01 | The AWS SES account shall be moved out of the sandbox environment (production access approved) before any bulk send to unverified recipients. | High | Config Review |
| RC-02 | The sending domain shall have DKIM signing enabled and verified in SES. | High | Config Review |
| RC-03 | An SPF record authorizing SES shall be published on the sending domain. | High | Config Review |
| RC-04 | A DMARC policy shall be published for the sending domain, with alignment validated before moving to an enforcing (quarantine/reject) policy. | High | Config Review |
| RC-05 | The system shall maintain bounce rate and complaint rate below the thresholds required to retain SES sending privileges (industry guidance: bounce <5%, complaint <0.1%). | High | Monitoring |
| RC-06 | For sustained high-volume sending, a dedicated IP with a documented warm-up plan shall be used rather than shared IP cold-start. | Medium | Config Review |

### 7.2 Consent and Data Protection (DPDPA 2023 / GDPR where applicable)

| ID | Requirement Description | Priority | Verification Method |
| --- | --- | --- | --- |
| RC-07 | The system shall only send marketing/newsletter email to recipients with a recorded, valid consent (opt-in) for that category of communication. | High | Audit |
| RC-08 | The consent record referenced by RC-07 shall capture, at minimum, timestamp, source/channel of consent, and consent scope/purpose. | High | Audit |
| RC-09 | The system shall provide a mechanism for withdrawal of consent that results in actual removal from future sends (via the suppression list), not merely a flag on the recipient record. | High | Test |
| RC-10 | Personal data used for email sending shall not be repurposed beyond the stated newsletter/campaign purpose (purpose limitation). | High | Review |
| RC-11 | Recipient personal data shall be retained only for the period defined in the organization's data retention schedule and shall be erasable on a valid erasure request. | High | Review |

### 7.3 Commercial Email Law (CAN-SPAM, and equivalent where applicable)

| ID | Requirement Description | Priority | Verification Method |
| --- | --- | --- | --- |
| RC-12 | Every marketing email shall include a valid physical mailing address for the sending organization. | High | Test |
| RC-13 | Every marketing email shall include a clear and conspicuous unsubscribe mechanism, and unsubscribe requests shall be honored within the legally required window (10 business days under CAN-SPAM, faster where RC-09/FR-20 apply). | High | Test |
| RC-14 | Subject lines and header (From/Reply-To) information shall accurately reflect the sender and content; deceptive headers are prohibited. | High | Review |

### 7.4 Audit Evidence (SharePoint Archive)

| ID | Requirement Description | Priority | Verification Method |
| --- | --- | --- | --- |
| RC-15 | The as-sent newsletter content, together with send date, campaign statistics, and recipient-segment reference, shall be retained in the SharePoint archive library in a read-only state as the auditable record of what was communicated, to whom, and when. | High | Audit |
| RC-16 | Access to the SharePoint archive library shall be restricted to authorized Compliance Reviewer and Integration Engineer roles, consistent with least-privilege access principles. | Medium | Review |

# 8\. Data Requirements

### 8.1 Key Data Entities

| Entity | Key Attributes | System of Record |
| --- | --- | --- |
| Recipient | Email address, name, segment/tags, consent reference | CRM / Consent system (external to this platform) |
| Consent Record | Recipient ID, purpose/category, timestamp, source, status | CRM / Consent system |
| Suppression Entry | Email address, reason (bounce/complaint/unsubscribe), timestamp | This platform |
| Campaign | Campaign ID, newsletter reference, configuration set, schedule | This platform |
| Newsletter (Draft/Approved) | File ID, version, SharePoint library location, Approval Status, content type (HTML) | SharePoint (Newsletters – Draft library) |
| Newsletter (Archived) | File ID, Campaign ID, Send Date/Time, recipient/delivery/bounce/complaint counts, read-only flag | SharePoint (Newsletters – Archive library) |
| Send Event | Recipient, campaign, timestamp, outcome (sent/bounced/complained/delivered) | This platform (event log) |

### 8.2 Data Retention

Send-event and suppression data shall be retained per the organization's data retention schedule, sufficient to satisfy the audit trail required by NFR-09 and RC-08, and no longer than necessary per RC-11.

# 9\. Assumptions, Dependencies and Constraints

## 9.1 Assumptions

•    Newsletter HTML content is authored and quality-reviewed by the content team directly in SharePoint (or uploaded there after external authoring); the platform only reads and merges the approved file.

•    A consent/CRM system of record already exists or will be established prior to production go-live; this platform is a consumer, not the source, of consent data.

•    AWS account-level SES production access approval is a business/administrative process pursued in parallel with development.

•    The organization's Microsoft 365 tenant and SharePoint Online site for newsletters already exist or will be provisioned ahead of development.

•    Power Automate premium connector licensing (required for HTTP/custom-connector actions) is available or will be procured.

## 9.2 Dependencies

•    AWS account with SES, SNS, SQS enabled in the target region

•    DNS access for the sending domain to publish SPF/DKIM/DMARC records (RC-02–RC-04)

•    Availability of a suppression-list data store (new or existing)

•    SharePoint Online site with "Newsletters – Draft" and "Newsletters – Archive" document libraries provisioned, including the required metadata columns (Campaign ID, Subject Line, Segment, Approval Status)

•    Azure AD (Entra ID) app registration with Microsoft Graph API permissions for Camel's SharePoint access, and a Power Automate connection with equivalent SharePoint permissions

•    Network/firewall path for Power Automate to reach the Camel ESB HTTP endpoint, and for Camel to reach the Microsoft Graph API

## 9.3 Constraints

•    Send throughput is bounded by the AWS account's SES sending quota at any point in time

•    Solution must run within the existing Camel ESB runtime/deployment model already used by the organization

•    Campaign triggering is bounded by Power Automate flow run limits and licensing tier of the Microsoft 365 tenant

# 10\. Acceptance Criteria and Verification

Each requirement in Sections 3–8 carries a Verification Method (Test, Demo, Audit, Review, Monitoring, or Config Review). The platform shall be considered ready for production go-live when:

1.   All High-priority requirements have passed their designated verification method.

2.   SES account is confirmed out of sandbox with domain authentication (SPF/DKIM/DMARC) verified (RC-01–RC-04).

3.   A test campaign run to a representative recipient set demonstrates: correct suppression-list exclusion, correct unsubscribe processing within SLA, and correct event feedback loop updating the suppression list.

4.   Compliance Reviewer sign-off confirming alignment with DPDPA/consent requirements (Section 7.2) is obtained (see Approval table, Section 1).

5.   Bounce and complaint rates during test campaigns remain within thresholds defined in RC-05.

6.   A test campaign demonstrates the full SharePoint/Power Automate loop end-to-end: approval status change triggers the send (FR-06), and campaign completion results in a correctly tagged, read-only archive entry (FR-22–FR-25).