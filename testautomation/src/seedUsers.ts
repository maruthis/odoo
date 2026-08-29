import { OdooClient } from "./odooClient";
import { ADMIN_LOGIN, ADMIN_PASSWORD, BASE_GROUP_XML_IDS, DEMO_PASSWORD, ROLES } from "./env";

/**
 * Idempotently ensures all 9 demo users from the Demo Playbook's
 * Appendix A exist with the right single role each. Safe to run
 * repeatedly against the same database - existing users are left alone
 * apart from having their password/groups reset to the expected state,
 * so a stale demo user from a previous run never silently drifts.
 */
export async function ensureDemoUsers(): Promise<void> {
  const admin = new OdooClient();
  await admin.authenticate(ADMIN_LOGIN, ADMIN_PASSWORD);

  // The admin account is also used (via RPC, never via the UI tests
  // themselves) to advance seeded campaigns through approval/preflight
  // as a fixture shortcut - it needs Compliance Administrator to be
  // authorized for those calls the same way a real admin would be.
  const [adminComplianceGroupId] = await admin.resolveXmlIds([
    "newsletter_compliance.group_newsletter_compliance_admin",
  ]);
  const [adminUserId] = await admin.search("res.users", [["login", "=", ADMIN_LOGIN]]);
  if (adminUserId) {
    await admin.write("res.users", [adminUserId], {
      group_ids: [[4, adminComplianceGroupId]],
    });
  }

  const baseGroupIds = await admin.resolveXmlIds(BASE_GROUP_XML_IDS);

  for (const role of ROLES) {
    const roleGroupIds = await admin.resolveXmlIds(role.groupXmlIds);
    const groupIds = [...new Set([...baseGroupIds, ...roleGroupIds])];

    const existingIds = await admin.search("res.users", [["login", "=", role.login]]);

    if (existingIds.length) {
      await admin.write("res.users", existingIds, {
        name: role.name,
        password: DEMO_PASSWORD,
        group_ids: [[6, 0, groupIds]],
        active: true,
      });
    } else {
      await admin.create("res.users", {
        name: role.name,
        login: role.login,
        password: DEMO_PASSWORD,
        group_ids: [[6, 0, groupIds]],
      });
    }
  }
}

if (require.main === module) {
  ensureDemoUsers()
    .then(() => {
      // eslint-disable-next-line no-console
      console.log(`Provisioned ${ROLES.length} demo users.`);
    })
    .catch((err) => {
      // eslint-disable-next-line no-console
      console.error(err);
      process.exit(1);
    });
}
