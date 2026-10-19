import { Component, DestroyRef, effect, inject, signal } from '@angular/core';
import { CustomerNavComponent } from './customer-nav';
import { DecimalPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Router, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CartService, MAX_PER_DISH } from './cart.service';
import { MenuService } from './menu.service';
import { errorMessage, newIdempotencyKey, OrderService } from './order.service';

@Component({selector: 'order-checkout', standalone: true, imports: [DecimalPipe, RouterLink, CustomerNavComponent], templateUrl: './checkout.html', styleUrl: './pages.css'})
export class CheckoutComponent {
  cart = inject(CartService);
  private orders = inject(OrderService);
  private router = inject(Router);
  private destroy = inject(DestroyRef);
  readonly max = MAX_PER_DISH;
  placing = signal(false);
  error = signal('');
  // One key per version of the cart: resubmitting the same cart (double click,
  // retry after a network error) returns the same order instead of a new one.
  private key = newIdempotencyKey();

  constructor() {
    effect(() => {this.cart.lines(); this.key = newIdempotencyKey();});
    // Refresh prices and availability so the review matches the current menu.
    inject(MenuService).page(1, 100).pipe(takeUntilDestroyed(this.destroy)).subscribe({next: page => this.cart.sync(page.items), error: () => {}});
  }
  confirm() {
    if (this.placing()) return;
    if (!this.cart.lines().length) {this.error.set('Your cart is empty. Add a dish before checking out.'); return;}
    this.placing.set(true); this.error.set('');
    this.orders.place(this.cart.lines(), this.key).pipe(takeUntilDestroyed(this.destroy)).subscribe({
      next: order => {
        // Only now that the order exists is the cart emptied.
        this.cart.clear();
        this.router.navigate(['/orders', order.reference], {state: {justPlaced: true}});
      },
      error: (err: HttpErrorResponse) => {this.placing.set(false); this.error.set(errorMessage(err));}
    });
  }
}
