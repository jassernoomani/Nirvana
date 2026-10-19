import { inject, Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';

export interface InventoryItem {id: number; name: string; unit: string; stock_quantity: number; reorder_level: number; status: 'ok' | 'low' | 'out'; used_in: string[];}
export interface StockMovement {id: number; change: number; quantity_after: number; reason: string; note: string | null; staff_name: string | null; order_reference: string | null; created_at: string;}
export type AdjustReason = 'delivery' | 'correction' | 'waste';

export const MOVEMENT_LABELS: Partial<Record<string, string>> = {
  delivery: 'Delivery', correction: 'Correction', waste: 'Waste', count: 'Stock count', order: 'Customer order'
};

@Injectable({providedIn: 'root'})
export class InventoryService {
  private http = inject(HttpClient);
  list() {return this.http.get<InventoryItem[]>('/api/inventory');}
  adjust(id: number, change: number, reason: AdjustReason, note: string | null) {
    return this.http.post<InventoryItem>(`/api/inventory/${id}/adjust`, {change, reason, note});
  }
  update(id: number, body: {stock_quantity?: number; reorder_level?: number; note?: string | null}) {
    return this.http.put<InventoryItem>(`/api/inventory/${id}`, body);
  }
  history(id: number) {return this.http.get<StockMovement[]>(`/api/inventory/${id}/movements`);}
}
