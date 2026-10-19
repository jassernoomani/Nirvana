import { Component, DestroyRef, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { errorMessage, Order, OrderService, STATUS_LABELS } from './order.service';

@Component({selector: 'order-list', standalone: true, imports: [DatePipe, DecimalPipe, RouterLink], styleUrl: './pages.css', template: `
<div class="page">
  <header class="page-header"><a class="page-brand" routerLink="/" aria-label="Restauration home"><span>r.</span>restauration<em>●</em></a><a class="page-link" routerLink="/">← Back to the menu</a></header>
  <main class="page-main">
    <div class="eyebrow">YOUR ACCOUNT</div>
    <h1>My orders.</h1>
    @if (orders(); as orders) {
      @if (!orders.length) {
        <section class="page-card page-empty"><h2>No orders yet.</h2><p>Your orders will appear here once you place one.</p><a class="page-primary" routerLink="/">Explore the menu</a></section>
      } @else {
        <section class="page-card">
          <table class="order-table">
            <thead><tr><th>Reference</th><th>Placed</th><th>Status</th><th class="num">Items</th><th class="num">Total</th><th>Review</th></tr></thead>
            <tbody>
              @for (order of orders; track order.id) {
                <tr><td data-label="Reference"><a [routerLink]="['/orders', order.reference]">{{ order.reference }}</a></td><td data-label="Placed">{{ date(order.created_at) | date:'d MMM y, HH:mm' }}</td><td data-label="Status"><span class="status" [attr.data-status]="order.status">{{ labels[order.status] ?? order.status }}</span></td><td class="num" data-label="Items">{{ count(order) }}</td><td class="num" data-label="Total">{{ order.total | number:'1.2-2' }}</td><td data-label="Review">@if (order.review; as review) {<span class="stars-inline" [attr.aria-label]="review.rating + ' out of 5 stars'">{{ starText(review.rating) }}</span>} @else if (order.status === 'served') {<a [routerLink]="['/orders', order.reference]">Rate it</a>} @else {<span class="muted">—</span>}</td></tr>
              }
            </tbody>
          </table>
        </section>
      }
    } @else if (error()) {
      <section class="page-card page-empty" role="alert"><h2>We couldn't load your orders.</h2><p>{{ error() }}</p></section>
    } @else {
      <p class="page-loading" role="status">Loading your orders…</p>
    }
  </main>
</div>`})
export class OrdersComponent {
  private destroy = inject(DestroyRef);
  readonly labels = STATUS_LABELS;
  orders = signal<Order[] | null>(null);
  error = signal('');
  constructor() {
    inject(OrderService).mine().pipe(takeUntilDestroyed(this.destroy)).subscribe({
      next: orders => this.orders.set(orders), error: (err: HttpErrorResponse) => this.error.set(errorMessage(err))
    });
  }
  starText(rating: number) {return '★'.repeat(rating);}
  count(order: Order) {return order.items.reduce((n, item) => n + item.quantity, 0);}
  date(value: string) {return value.replace(' ', 'T');}
}
