import { inject, Injectable, signal } from '@angular/core';
import { NavigationExtras, Router } from '@angular/router';
import { HttpClient } from '@angular/common/http';
import { catchError, finalize, firstValueFrom, of, tap } from 'rxjs';

export interface User {id: number; email: string; full_name: string; role: 'customer' | 'staff'; is_vegetarian: boolean;}

// The session lives in an HttpOnly cookie the browser sends automatically; this
// service only mirrors who is signed in. The backend enforces every permission.
@Injectable({providedIn: 'root'})
export class AuthService {
  private http = inject(HttpClient);
  private router = inject(Router);
  readonly user = signal<User | null>(null);
  private session: Promise<User | null> | null = null;

  /** Resolves once the current session is known; the lookup runs once per page load. */
  ready(): Promise<User | null> {
    this.session ??= firstValueFrom(this.http.get<User>('/api/auth/me').pipe(catchError(() => of(null))))
      .then(user => {this.user.set(user); return user;});
    return this.session;
  }
  login(email: string, password: string) {
    return this.http.post<User>('/api/auth/login', {email, password}).pipe(tap(user => this.signedIn(user)));
  }
  register(full_name: string, email: string, password: string) {
    return this.http.post<User>('/api/auth/register', {full_name, email, password}).pipe(tap(user => this.signedIn(user)));
  }
  logout() {
    return this.http.post<void>('/api/auth/logout', {}).pipe(finalize(() => this.signedIn(null)));
  }
  /** Ends the session, even if the server cannot be reached, then optionally opens another page. */
  signOut(redirectTo?: string, extras?: NavigationExtras): Promise<void> {
    return new Promise(resolve => {
      const done = () => {if (redirectTo) this.router.navigate([redirectTo], extras); resolve();};
      this.logout().subscribe({complete: done, error: done});
    });
  }
  /** Called when the server rejects the session (expired or revoked). */
  expire() {this.signedIn(null);}
  home(user: User) {return user.role === 'staff' ? '/admin' : '/';}
  private signedIn(user: User | null) {
    this.user.set(user);
    this.session = Promise.resolve(user);
  }
}
