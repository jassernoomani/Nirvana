import { inject } from '@angular/core';
import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';
import { AuthService } from './auth.service';

/** Staff-only pages. This only keeps the UI tidy; the API rejects non-staff requests itself. */
export const staffGuard: CanActivateFn = async (_route, state) => {
  const auth = inject(AuthService); const router = inject(Router);
  const user = await auth.ready();
  if (!user) return router.createUrlTree(['/login'], {queryParams: {returnUrl: state.url}});
  return user.role === 'staff' ? true : router.createUrlTree(['/forbidden']);
};

/** Customer-only pages such as checkout; staff go back to their workspace. */
export const customerGuard: CanActivateFn = async (_route, state) => {
  const auth = inject(AuthService); const router = inject(Router);
  const user = await auth.ready();
  if (!user) return router.createUrlTree(['/login'], {queryParams: {returnUrl: state.url}});
  return user.role === 'customer' ? true : router.createUrlTree([auth.home(user)]);
};

/** Pages for any signed-in user. */
export const signedInGuard: CanActivateFn = async (_route, state) => {
  const auth = inject(AuthService); const router = inject(Router);
  return (await auth.ready()) ? true : router.createUrlTree(['/login'], {queryParams: {returnUrl: state.url}});
};

/** The sign-in page sends people who are already signed in to their home page. */
export const guestGuard: CanActivateFn = async () => {
  const auth = inject(AuthService); const router = inject(Router);
  const user = await auth.ready();
  return user ? router.createUrlTree([auth.home(user)]) : true;
};

/** When a signed-in user's session stops being accepted, send them to sign in again. */
export const sessionInterceptor: HttpInterceptorFn = (request, next) => {
  const auth = inject(AuthService); const router = inject(Router);
  return next(request).pipe(catchError((error: HttpErrorResponse) => {
    if (error.status === 401 && auth.user() && !request.url.startsWith('/api/auth/')) {
      auth.expire();
      router.navigate(['/login'], {queryParams: {expired: 1, returnUrl: router.url}});
    }
    return throwError(() => error);
  }));
};
