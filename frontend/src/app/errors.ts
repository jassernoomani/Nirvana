import { HttpErrorResponse } from '@angular/common/http';

/** A readable message for a failed API call: the server's own explanation when it gives one, otherwise the fallback. */
export function errorMessage(err: HttpErrorResponse, fallback = 'Something went wrong. Please try again.'): string {
  // No response at all, a gateway error, or the development proxy's empty 500 when the API is not running.
  // (A real server error carries a body, so it is not mistaken for this.)
  const unreachable = err.status === 0 || [502, 503, 504].includes(err.status) || (err.status === 500 && (err.error === null || err.error === ''));
  if (unreachable) return 'Cannot reach the restaurant server. Check that it is running and try again.';
  const detail = err.error?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d: {msg: string}) => d.msg).join('. ');
  return fallback;
}
