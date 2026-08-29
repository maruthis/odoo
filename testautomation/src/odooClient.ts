/**
 * Minimal Odoo JSON-RPC client used for test data setup (creating demo
 * users, seeding purposes/brands/partners/consent/draft campaigns).
 *
 * Deliberately not used to *assert* application behavior - assertions
 * belong in the Playwright UI tests, driven through the browser exactly
 * as a real user would. This client only exists to get the database into
 * a known starting state quickly and reliably, the same way the Odoo
 * module's own Python tests seed fixtures instead of clicking through
 * the UI to create every prerequisite record.
 */
import { BASE_URL, DB_NAME } from "./env";

export class OdooClient {
  private cookie: string | null = null;
  private uid: number | null = null;

  constructor(private baseUrl: string = BASE_URL, private db: string = DB_NAME) {}

  async authenticate(login: string, password: string): Promise<number> {
    const res = await fetch(`${this.baseUrl}/web/session/authenticate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        jsonrpc: "2.0",
        method: "call",
        params: { db: this.db, login, password },
      }),
    });
    const json = await res.json();
    if (json.error) {
      throw new Error(`Odoo authentication failed: ${JSON.stringify(json.error)}`);
    }
    const setCookie = res.headers.get("set-cookie");
    if (!setCookie) {
      throw new Error("Odoo authentication did not return a session cookie");
    }
    this.cookie = setCookie.split(";")[0];
    this.uid = json.result.uid;
    return this.uid as number;
  }

  private assertAuthenticated() {
    if (!this.cookie) {
      throw new Error("OdooClient is not authenticated - call authenticate() first");
    }
  }

  async callKw<T = any>(
    model: string,
    method: string,
    args: any[] = [],
    kwargs: Record<string, any> = {}
  ): Promise<T> {
    this.assertAuthenticated();
    const res = await fetch(`${this.baseUrl}/web/dataset/call_kw`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Cookie: this.cookie as string },
      body: JSON.stringify({
        jsonrpc: "2.0",
        method: "call",
        params: { model, method, args, kwargs },
      }),
    });
    const json = await res.json();
    if (json.error) {
      throw new Error(
        `Odoo call ${model}.${method} failed: ${JSON.stringify(json.error.data?.message || json.error)}`
      );
    }
    return json.result as T;
  }

  search(model: string, domain: any[], opts: Record<string, any> = {}) {
    return this.callKw<number[]>(model, "search", [domain], opts);
  }

  create(model: string, vals: Record<string, any>) {
    return this.callKw<number>(model, "create", [vals]);
  }

  write(model: string, ids: number[], vals: Record<string, any>) {
    return this.callKw<boolean>(model, "write", [ids, vals]);
  }

  async findOrCreate(model: string, domain: any[], vals: Record<string, any>): Promise<number> {
    const found = await this.search(model, domain, { limit: 1 });
    if (found.length) return found[0];
    return this.create(model, vals);
  }

  /** Resolves a list of "module.xmlid" strings to their res_id via ir.model.data. */
  async resolveXmlIds(xmlIds: string[]): Promise<number[]> {
    const ids: number[] = [];
    for (const xmlId of xmlIds) {
      const [module, name] = xmlId.split(".");
      const rows = await this.callKw<{ res_id: number }[]>(
        "ir.model.data",
        "search_read",
        [[["module", "=", module], ["name", "=", name]]],
        { fields: ["res_id"] }
      );
      if (!rows.length) {
        throw new Error(`Could not resolve external id ${xmlId}`);
      }
      ids.push(rows[0].res_id);
    }
    return ids;
  }
}
