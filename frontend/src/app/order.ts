import { Component, DestroyRef, inject, signal } from '@angular/core';
import { serverTime } from './server-time';
import { errorMessage } from './errors';
import { CustomerNavComponent } from './customer-nav';
import { DatePipe, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Order, OrderService, STATUS_LABELS } from './order.service';

@Component({selector: 'order-detail', standalone: true, imports: [DatePipe, DecimalPipe, FormsModule, RouterLink, CustomerNavComponent], templateUrl: './order.html', styleUrl: './pages.css'})
export class OrderComponent {
  private destroy = inject(DestroyRef);
  private orders = inject(OrderService);
  readonly labels = STATUS_LABELS;
  readonly justPlaced = inject(Router).getCurrentNavigation()?.extras.state?.['justPlaced'] === true;
  order = signal<Order | null>(null);
  error = signal('');
  readonly stars = [1, 2, 3, 4, 5];
  rating = 0; comment = '';
  sending = signal(false);
  reviewError = signal('');
  reviewSent = signal(false);

  constructor() {
    const reference = inject(ActivatedRoute).snapshot.paramMap.get('reference') ?? '';
    this.orders.get(reference).pipe(takeUntilDestroyed(this.destroy)).subscribe({
      next: order => this.order.set(order),
      error: (err: HttpErrorResponse) => this.error.set(err.status === 404 ? 'We could not find this order in your account.' : errorMessage(err))
    });
  }
  submitReview() {
    const order = this.order(); if (!order || this.sending()) return;
    if (!this.rating) {this.reviewError.set('Choose a rating from 1 to 5 stars.'); return;}
    if (this.comment.trim().length < 3) {this.reviewError.set('Please write a short comment (at least 3 characters).'); return;}
    this.sending.set(true); this.reviewError.set('');
    this.orders.review(order.reference, this.rating, this.comment.trim()).pipe(takeUntilDestroyed(this.destroy)).subscribe({
      next: updated => {this.sending.set(false); this.order.set(updated); this.reviewSent.set(true);},
      error: (err: HttpErrorResponse) => {this.sending.set(false); this.reviewError.set(errorMessage(err));}
    });
  }
  /** Stored as local restaurant time without a zone. */
  date(value: string) {return serverTime(value);}
}
