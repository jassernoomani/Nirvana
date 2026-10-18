import { Component, DestroyRef, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { errorMessage, Order, OrderService, STATUS_LABELS } from './order.service';

@Component({selector: 'order-detail', standalone: true, imports: [DatePipe, DecimalPipe, RouterLink], templateUrl: './order.html', styleUrl: './pages.css'})
export class OrderComponent {
  private destroy = inject(DestroyRef);
  readonly labels = STATUS_LABELS;
  readonly justPlaced = inject(Router).getCurrentNavigation()?.extras.state?.['justPlaced'] === true;
  order = signal<Order | null>(null);
  error = signal('');

  constructor() {
    const reference = inject(ActivatedRoute).snapshot.paramMap.get('reference') ?? '';
    inject(OrderService).get(reference).pipe(takeUntilDestroyed(this.destroy)).subscribe({
      next: order => this.order.set(order),
      error: (err: HttpErrorResponse) => this.error.set(err.status === 404 ? 'We could not find this order in your account.' : errorMessage(err))
    });
  }
  /** Stored as local restaurant time without a zone. */
  date(value: string) {return value.replace(' ', 'T');}
}
