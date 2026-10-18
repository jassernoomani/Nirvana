import { Component, DestroyRef, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { AuthService, User } from './auth.service';

@Component({selector: 'auth-login', standalone: true, imports: [FormsModule, RouterLink], templateUrl: './login.html', styleUrl: './login.css'})
export class LoginComponent {
  private auth = inject(AuthService);
  private router = inject(Router);
  private destroy = inject(DestroyRef);
  private query = inject(ActivatedRoute).snapshot.queryParamMap;
  mode = signal<'login' | 'register'>('login');
  expired = this.query.get('expired') === '1';
  fullName = ''; email = ''; password = '';
  busy = signal(false);
  error = signal('');

  switchTo(mode: 'login' | 'register') {this.mode.set(mode); this.error.set(''); this.password = '';}
  submit() {
    if (this.busy()) return;
    const email = this.email.trim();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {this.error.set('Enter a valid email address.'); return;}
    if (this.mode() === 'register') {
      if (!this.fullName.trim()) {this.error.set('Enter your name.'); return;}
      if (this.password.length < 8) {this.error.set('Choose a password of at least 8 characters.'); return;}
    } else if (!this.password) {this.error.set('Enter your password.'); return;}
    this.busy.set(true); this.error.set('');
    const request = this.mode() === 'login' ? this.auth.login(email, this.password) : this.auth.register(this.fullName.trim(), email, this.password);
    request.pipe(takeUntilDestroyed(this.destroy)).subscribe({
      next: user => {this.busy.set(false); this.router.navigateByUrl(this.destination(user));},
      error: (err: HttpErrorResponse) => {this.busy.set(false); this.password = ''; this.error.set(this.message(err));}
    });
  }
  /** Only same-site paths are followed, and customers are never sent to staff pages. */
  private destination(user: User) {
    const target = this.query.get('returnUrl') ?? '';
    const safe = target.startsWith('/') && !target.startsWith('//') && !target.startsWith('/login');
    if (!safe || (user.role !== 'staff' && target.startsWith('/admin'))) return this.auth.home(user);
    return target;
  }
  private message(err: HttpErrorResponse) {
    if (err.status === 0 || err.status === 502 || err.status === 504) return 'Cannot reach the restaurant server. Please try again in a moment.';
    const detail = err.error?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) return detail.map((d: {msg: string}) => d.msg).join('. ');
    return 'Something went wrong. Please try again.';
  }
}
