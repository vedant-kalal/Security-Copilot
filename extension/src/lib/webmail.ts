/**
 * Recognized webmail hosts — used by the popup to decide whether to
 * automatically run a quick phishing check on the page's visible text
 * the moment it opens (see Popup.tsx), the same way it already shows an
 * automatic quick verdict for the current tab's URL. Deliberately a short,
 * explicit hostname list rather than a heuristic ("contains 'mail'") —
 * false positives here mean silently sending page text from an unrelated
 * site to the backend, which is worse than just missing a webmail
 * provider we haven't added yet.
 */
const WEBMAIL_HOSTS = [
  "mail.google.com",
  "outlook.live.com",
  "outlook.office.com",
  "outlook.office365.com",
  "mail.yahoo.com",
  "mail.proton.me",
];

export function isWebmailHost(hostname: string): boolean {
  return WEBMAIL_HOSTS.includes(hostname.toLowerCase());
}
