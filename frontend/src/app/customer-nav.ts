import { Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { AuthService } from './auth.service';
import { CartService } from './cart.service';

/** Header shared by the customer pages outside the menu: same links, cart and account controls everywhere. */
@Component({selector: 'customer-nav', standalone: true, imports: [RouterLink, RouterLinkActive], template: `
  <header class="customer-nav">
    <a class="brand" routerLink="/" aria-label="Restauration home"><span>r.</span>restauration<em>●</em></a>
    <nav aria-label="Main">
      <a routerLink="/" routerLinkActive="active" [routerLinkActiveOptions]="{exact: true}">Menu</a>
      @if (auth.user()?.role === 'staff') {
        <a routerLink="/admin">Staff workspace</a>
      } @else {
        <a routerLink="/recommendations" routerLinkActive="active">Picked for you</a>
        <a routerLink="/reservations" routerLinkActive="active">Book a table</a>
        <a routerLink="/orders" routerLinkActive="active">My orders</a>
        <a class="cart" routerLink="/checkout" routerLinkActive="active">Cart <span>{{ cart.count() }}</span></a>
      }
    </nav>
    <div class="account">
      @if (auth.user(); as user) {
        <span class="name">{{ user.full_name.split(' ')[0] }}</span><button type="button" (click)="auth.signOut('/')">Sign out</button>
      } @else {
        <a routerLink="/login">Sign in</a>
      }
    </div>
  </header>`, styles: [`
  :host{display:block;background:#faf9f4;border-bottom:1px solid #e6e6da}
  .customer-nav{max-width:1100px;margin:auto;padding:20px 40px;display:flex;align-items:center;gap:28px}
  .brand{display:flex;align-items:center;gap:9px;font-size:22px;font-weight:800;color:#29462f;text-decoration:none;letter-spacing:-1px;flex-shrink:0}
  .brand>span{background:#2f5136;color:#fff;width:32px;height:32px;display:grid;place-items:center;border-radius:9px;font:26px Georgia}
  .brand em{font-size:8px;font-style:normal;color:#b9cd7f}
  nav{display:flex;gap:20px;margin-left:auto;overflow-x:auto}
  nav a,.account a{color:#5f6f58;font-size:13px;text-decoration:none;white-space:nowrap;padding:6px 0;border-bottom:2px solid transparent}
  nav a.active{color:#2e5137;font-weight:600;border-bottom-color:#2e5137}
  .cart span{display:inline-grid;place-items:center;min-width:20px;height:20px;border-radius:10px;background:#2e5137;color:#fff;font-size:11px;margin-left:4px}
  .account{display:flex;align-items:center;gap:10px;font-size:13px;flex-shrink:0}
  .name{color:#293c2c;font-weight:600}
  .account button{border:1px solid #dfe5d7;background:#fff;border-radius:7px;padding:7px 11px;color:#546348;font-size:12px;cursor:pointer}
  @media(max-width:760px){
    .customer-nav{flex-wrap:wrap;padding:14px 16px;gap:10px 16px}
    nav{order:3;width:100%;margin-left:0;gap:18px;padding-bottom:2px}
    .account{margin-left:auto}
    .name{display:none}
  }`]})
export class CustomerNavComponent {
  auth = inject(AuthService);
  cart = inject(CartService);
  constructor() {this.auth.ready();}
}
