/**
 * The API sends timestamps as "YYYY-MM-DD HH:MM:SS" in the restaurant's local time.
 * This turns them into a form Date and the date pipe parse the same way in every browser.
 */
export function serverTime(value: string): string {
  return value.replace(' ', 'T');
}
