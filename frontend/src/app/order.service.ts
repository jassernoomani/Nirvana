import { inject, Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { CartLine } from './cart.service';

export interface OrderLine {menu_item_id: number; name: string; quantity: number; unit_price: number; line_total: number;}
export interface Order {id: number; reference: string; status: string; total: number; created_at: string; items: OrderLine[];}

export const STATUS_LABELS: Partial<Record<string, string>> = {
  pending: 'Received', preparing: 'Being prepared', ready: 'Ready', served: 'Served', cancelled: 'Cancelled'
};

@Injectable({providedIn: 'root'})
export class OrderService {
  private http = inject(HttpClient);
  /** Only ids and quantities are sent; the server prices the order. */
  place(lines: CartLine[], idempotencyKey: string) {
    return this.http.post<Order>('/api/orders', {
      items: lines.map(line => ({menu_item_id: line.dish.id, quantity: line.quantity})), idempotency_key: idempotencyKey
    });
  }
  mine() {return this.http.get<Order[]>('/api/orders');}
  get(reference: string) {return this.http.get<Order>(`/api/orders/${encodeURIComponent(reference)}`);}
}

export function newIdempotencyKey(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join('');
}

export function errorMessage(err: HttpErrorResponse): string {
  if (err.status === 0 || err.status === 502 || err.status === 504) return 'Cannot reach the restaurant server. Check your connection and try again.';
  const detail = err.error?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d: {msg: string}) => d.msg).join('. ');
  return 'Something went wrong. Please try again.';
}
