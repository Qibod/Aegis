import type { Page } from '@playwright/test';

export interface TestUser {
  email: string;
  password: string;
  role: 'admin' | 'auditor' | 'head_of_audit';
  orgId: string;
  accessToken: string;
}

/**
 * Seeds auth state into localStorage before page navigation.
 *
 * The auth store uses Zustand persist with name 'aegis-auth', which serialises
 * the full state object under the key "aegis-auth".
 * setTokens() also writes raw 'access_token' / 'refresh_token' keys used by
 * Axios interceptors.  We populate both so every read path is satisfied.
 */
export async function loginWithToken(page: Page, user: TestUser) {
  await page.addInitScript((token) => {
    // Zustand persist key — restores full auth state on store hydration
    const persistState = {
      state: {
        accessToken: token,
        refreshToken: null,
        isAuthenticated: true,
        user: null,
        org: null,
      },
      version: 0,
    };
    localStorage.setItem('aegis-auth', JSON.stringify(persistState));

    // Raw keys read directly by Axios interceptors / setTokens callers
    localStorage.setItem('access_token', token);
  }, user.accessToken);

  await page.goto('/company-profile');
  await page.waitForLoadState('networkidle');
}
