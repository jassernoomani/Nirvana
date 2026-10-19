import { inject, Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { CartLine } from './cart.service';

export interface OrderLine {menu_item_id: number; name: string; quantity: number; unit_price: number; line_total: number;}
export interface OrderReview {rating: number; comment: string | null; created_at: string;}
export interface Order {id: number; reference: string; status: string; total: number; created_at: string; items: OrderLine[]; review: OrderReview | null;}
export interface PublicReview {rating: number; comment: string; author: string; created_at: string;}
export interface ReviewSummary {average_rating: number | null; review_count: number; reviews: PublicReview[];}

export const ORDERS_PAGE_SIZE = 20;

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
  mine(offset = 0, limit = ORDERS_PAGE_SIZE) {return this.http.get<Order[]>('/api/orders', {params: {offset, limit}});}
  get(reference: string) {return this.http.get<Order>(`/api/orders/${encodeURIComponent(reference)}`);}
  /** The author is taken from the session on the server; only the rating and comment are sent. */
  review(reference: string, rating: number, comment: string) {
    return this.http.post<Order>(`/api/orders/${encodeURIComponent(reference)}/review`, {rating, comment});
  }
  publicReviews(limit = 6) {return this.http.get<ReviewSummary>('/api/reviews', {params: {limit}});}
}

export function newIdempotencyKey(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join('');
}
