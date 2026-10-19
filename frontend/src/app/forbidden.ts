import { Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { AuthService } from './auth.service';

@Component({selector: 'auth-forbidden', standalone: true, imports: [RouterLink], styleUrl: './login.css', template: `
  <div class="auth-page">
    <a class="auth-brand" routerLink="/" aria-label="Restauration home"><span>r.</span>restauration<em>●</em></a>
    <main class="auth-card" role="alert">
      <div class="eyebrow">STAFF ONLY</div>
      <h1>This page is for restaurant staff.</h1>
      <p class="auth-lead">You are signed in as {{ auth.user()?.email }}, which is a customer account.</p>
      <a class="auth-submit auth-link" routerLink="/">Back to the menu</a>
      <button class="auth-back auth-plain" type="button" (click)="switchAccount()">Sign in with a staff account</button>
    </main>
  </div>`, styles: ['.auth-link{display:block;text-align:center;text-decoration:none}.auth-plain{border:0;background:none;width:100%;cursor:pointer}']})
export class ForbiddenComponent {
  auth = inject(AuthService);
  switchAccount() {this.auth.signOut('/login', {queryParams: {returnUrl: '/admin'}});}
}
