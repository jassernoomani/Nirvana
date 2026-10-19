import { inject, Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { OrderLine } from './order.service';

export type KitchenStatus = 'pending' | 'preparing' | 'ready';
export interface KitchenOrder {id: number; reference: string; status: KitchenStatus | 'served'; created_at: string; status_since: string; customer_name: string | null; item_count: number; longest_preparation_minutes: number; items: OrderLine[];}

@Injectable({providedIn: 'root'})
export class KitchenService {
  private http = inject(HttpClient);
  orders() {return this.http.get<KitchenOrder[]>('/api/kitchen/orders');}
  /** from_status lets the server refuse the change if another screen already moved the order. */
  move(id: number, fromStatus: string, toStatus: string) {
    return this.http.post<KitchenOrder>(`/api/kitchen/orders/${id}/status`, {from_status: fromStatus, to_status: toStatus});
  }
}
