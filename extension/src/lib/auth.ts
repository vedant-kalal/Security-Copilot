/**
 * Authentication + device-registration flows for the extension.
 * Mirrors the architecture doc's "First Use" journey (section 3):
 * sign in -> JWT -> backend registers a Device -> monitoring starts.
 */
import { api, type TokenResponse } from "@/lib/api";
import { clearAuth, getStorage, setStorage } from "@/lib/storage";

interface Device {
  device_id: string;
  browser: string;
  os: string;
}

function detectBrowserAndOs(): { browser: string; os: string } {
  const ua = navigator.userAgent;
  const browser = ua.includes("Edg/") ? "Edge" : ua.includes("Chrome/") ? "Chrome" : "Unknown Browser";
  const platform = navigator.platform || "Unknown OS";
  return { browser, os: platform };
}

async function ensureDeviceRegistered(): Promise<string> {
  const { deviceId } = await getStorage();
  if (deviceId) return deviceId;

  const { browser, os } = detectBrowserAndOs();
  const device = await api.post<Device>("/devices", { browser, os });
  await setStorage({ deviceId: device.device_id });
  return device.device_id;
}

export async function login(email: string, password: string): Promise<void> {
  const tokens = await api.post<TokenResponse>("/auth/login", { email, password }, true);
  await setStorage({ accessToken: tokens.access_token, refreshToken: tokens.refresh_token, userEmail: email });
  await ensureDeviceRegistered();
}

export async function register(email: string, password: string): Promise<void> {
  const tokens = await api.post<TokenResponse>("/auth/register", { email, password }, true);
  await setStorage({ accessToken: tokens.access_token, refreshToken: tokens.refresh_token, userEmail: email });
  await ensureDeviceRegistered();
}

export async function logout(): Promise<void> {
  await clearAuth();
}

export async function isAuthenticated(): Promise<boolean> {
  const { accessToken } = await getStorage();
  return accessToken !== null;
}

export { ensureDeviceRegistered };
