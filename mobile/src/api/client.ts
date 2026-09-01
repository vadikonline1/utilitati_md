import Constants from 'expo-constants';
import * as SecureStore from 'expo-secure-store';

const DEFAULT_API_URL = 'https://utilitati.nistorlazar.md/api';
const TOKEN_KEY = 'utilitati.token';

function apiUrl(): string {
  const extra = Constants.expoConfig?.extra as { apiUrl?: string } | undefined;
  return extra?.apiUrl || DEFAULT_API_URL;
}

export function getApiUrl(): string {
  return apiUrl();
}

export async function saveToken(token: string): Promise<void> {
  await SecureStore.setItemAsync(TOKEN_KEY, token);
}

export async function getToken(): Promise<string | null> {
  return SecureStore.getItemAsync(TOKEN_KEY);
}

export async function clearToken(): Promise<void> {
  await SecureStore.deleteItemAsync(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: { method?: string; body?: unknown; token?: string | null } = {},
): Promise<T> {
  const { method = 'GET', body, token } = options;
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  // Prefer an explicitly passed token, else the stored one.
  const authToken = token ?? (await getToken());
  if (authToken) headers.Authorization = `Bearer ${authToken}`;

  let res: Response;
  try {
    res = await fetch(`${apiUrl()}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, 'Eroare de rețea. Verifică conexiunea.');
  }

  if (!res.ok) {
    let detail = 'Eroare de server';
    try {
      const data = await res.json();
      if (data && data.detail) detail = data.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

// --------------------------------------------------------------------------- //
// Auth
// --------------------------------------------------------------------------- //
export interface PublicUser {
  id: number;
  username: string;
  full_name: string;
  email: string;
}

export function login(username: string, password: string): Promise<{ token: string; user: PublicUser }> {
  return request('/auth/login', { method: 'POST', body: { username, password }, token: null });
}

export function register(
  username: string,
  password: string,
  email: string,
  full_name: string,
): Promise<{ token: string; user: PublicUser }> {
  return request('/auth/register', {
    method: 'POST',
    body: { username, password, email, full_name },
    token: null,
  });
}

export function me(): Promise<PublicUser> {
  return request('/auth/me');
}

export function forgotPassword(email: string): Promise<{ ok: boolean }> {
  return request('/auth/forgot-password', { method: 'POST', body: { email }, token: null });
}

export function resetPassword(token: string, newPassword: string): Promise<{ ok: boolean }> {
  return request('/auth/reset-password', {
    method: 'POST',
    body: { token, new_password: newPassword },
    token: null,
  });
}

// --------------------------------------------------------------------------- //
// Homes
// --------------------------------------------------------------------------- //
export interface Home {
  id: number;
  name: string;
  address: string;
  floor: string;
  metro_area: string;
  status: string;
  utilities_count?: number;
  unpaid_invoices?: number;
  created_at?: string;
}

export interface Account {
  id: number;
  home_id: number | null;
  provider: string;
  label: string;
  contract_number: string;
  place_of_consumption: string;
  username: string;
  password?: string;
  icon?: string;
  status: string;
  created_at?: string;
}

export interface Provider {
  id: string;
  name?: string;
  label?: string;
}

export interface Invoice {
  id: number;
  account_id: number;
  invoice_number: string;
  external_invoice_id?: string | null;
  amount_mdl: number;
  currency: string;
  period?: string | null;
  issue_date?: string | null;
  due_date?: string | null;
  is_paid: number;
  pay_status: string;
  status: string;
  pdf_url?: string | null;
  checked_at?: string | null;
  created_at?: string;
}

export function listHomes(): Promise<Home[]> {
  return request('/homes');
}

export function listProviders(): Promise<Provider[]> {
  return request('/providers');
}

export function createHome(payload: Partial<Home>): Promise<Home> {
  return request('/homes', { method: 'POST', body: payload });
}

export function getHome(id: number): Promise<{ home: Home; accounts: Account[] }> {
  return request(`/homes/${id}`);
}

export function updateHome(id: number, payload: Partial<Home>): Promise<Home> {
  return request(`/homes/${id}`, { method: 'PUT', body: payload });
}

export function setHomeStatus(id: number, status: string): Promise<Home> {
  return request(`/homes/${id}/status?status=${encodeURIComponent(status)}`, {
    method: 'POST',
  });
}

export function deleteHome(id: number): Promise<{ deleted: boolean }> {
  return request(`/homes/${id}`, { method: 'DELETE' });
}

// --------------------------------------------------------------------------- //
// Accounts
// --------------------------------------------------------------------------- //
export function listAccounts(homeId?: number): Promise<Account[]> {
  const qs = homeId ? `?home_id=${homeId}` : '';
  return request(`/accounts${qs}`);
}

export function createAccount(payload: Partial<Account>): Promise<Account> {
  return request('/accounts', { method: 'POST', body: payload });
}

export function updateAccount(id: number, payload: Partial<Account>): Promise<Account> {
  return request(`/accounts/${id}`, { method: 'PUT', body: payload });
}

export function setAccountStatus(id: number, status: string): Promise<Account> {
  return request(`/accounts/${id}/status?status=${encodeURIComponent(status)}`, {
    method: 'POST',
  });
}

export function deleteAccount(id: number): Promise<{ deleted: boolean }> {
  return request(`/accounts/${id}`, { method: 'DELETE' });
}

export function accountInvoices(id: number): Promise<{ invoices: Invoice[] }> {
  return request(`/accounts/${id}/invoices`);
}

export function refreshAccount(
  id: number,
): Promise<{
  is_connected: boolean;
  error_message?: string;
  unpaid_balance_mdl: number;
  invoices: Invoice[];
}> {
  return request(`/accounts/${id}/refresh`, { method: 'POST' });
}

export function submitMeterReading(id: number, value: number): Promise<{ submitted: boolean }> {
  return request(`/accounts/${id}/meter-reading?reading_value=${encodeURIComponent(value)}`, {
    method: 'POST',
  });
}

// --------------------------------------------------------------------------- //
// Invoices
// --------------------------------------------------------------------------- //
export function listInvoices(accountId?: number): Promise<{ invoices: Invoice[] }> {
  const qs = accountId ? `?account_id=${accountId}` : '';
  return request(`/invoices${qs}`);
}

export function invoiceHistory(id: number): Promise<{ history: unknown[] }> {
  return request(`/invoices/${id}/history`);
}

export function setInvoiceStatus(id: number, status: string): Promise<Invoice> {
  return request(`/invoices/${id}/status?status=${encodeURIComponent(status)}`, {
    method: 'POST',
  });
}

export function deleteInvoice(id: number): Promise<{ deleted: boolean }> {
  return request(`/invoices/${id}`, { method: 'DELETE' });
}
