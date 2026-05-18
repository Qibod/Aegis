/**
 * Provisions and tears down ephemeral test tenants via a backend test-only endpoint.
 * The endpoint POST /api/v1/test/provision-tenant must be enabled when
 * AEGIS_ENABLE_TEST_ENDPOINTS=1 (added in PR 4).
 */
import type { TestUser } from './auth';

const API = process.env.API_URL ?? 'http://localhost:8000/api/v1';

export async function provisionTenant(
  fixtureCompany: string,
  role: TestUser['role'] = 'admin',
): Promise<TestUser> {
  const r = await fetch(`${API}/test/provision-tenant`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ fixture_company: fixtureCompany, role }),
  });
  if (!r.ok) throw new Error(`provision failed: ${r.status} ${await r.text()}`);
  return (await r.json()) as TestUser;
}

export async function teardownTenant(orgId: string): Promise<void> {
  await fetch(`${API}/test/teardown-tenant/${orgId}`, { method: 'DELETE' });
}
