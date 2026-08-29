// Copies each demo project's raw video.webm (nested under a hashed
// per-test directory by Playwright) into a clean, discoverable filename
// alongside it - demo-recordings/01-newsletter-author.webm, etc.
const fs = require("fs");
const path = require("path");

const RAW_DIR = path.join(__dirname, "..", "demo-recordings", ".raw");
const OUT_DIR = path.join(__dirname, "..", "demo-recordings");

const PROJECT_NAMES = {
  "00-full-platform-e2e": "00-full-platform-e2e",
  "01-author": "01-newsletter-author",
  "02-content-approver": "02-content-approver",
  "03-compliance-reviewer": "03-compliance-reviewer",
  "04-compliance-administrator": "04-compliance-administrator",
  "05-campaign-operator": "05-campaign-operator",
  "06-operations-administrator": "06-operations-administrator",
  "07-privacy-officer": "07-privacy-officer",
  "08-legal-hold-administrator": "08-legal-hold-administrator",
  "09-compliance-audit-reviewer": "09-compliance-audit-reviewer",
};

if (!fs.existsSync(RAW_DIR)) {
  console.error(`No raw recordings found at ${RAW_DIR} - run "npm run demo" first.`);
  process.exit(1);
}

for (const entry of fs.readdirSync(RAW_DIR)) {
  // Playwright truncates long directory names in the middle and appends
  // the project name at the very end - so match by suffix, not prefix
  // (a prefix match misses e.g. "04-compliance-administrator", whose
  // directory name gets truncated to "...administrato-<hash>-...").
  const projectKey = Object.keys(PROJECT_NAMES).find((key) => entry.endsWith(key));
  if (!projectKey) continue;

  const videoPath = path.join(RAW_DIR, entry, "video.webm");
  if (!fs.existsSync(videoPath)) continue;

  const dest = path.join(OUT_DIR, `${PROJECT_NAMES[projectKey]}.webm`);
  fs.copyFileSync(videoPath, dest);
  console.log(`${PROJECT_NAMES[projectKey]}.webm`);
}
