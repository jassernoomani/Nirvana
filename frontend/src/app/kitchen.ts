import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { serverTime } from './server-time';
import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { RouterLink } from '@angular/router';
import { AuthService } from './auth.service';
import { KitchenOrder, KitchenService, KitchenStatus } from './kitchen.service';
import { errorMessage } from './errors';
import { StaffNavComponent } from './staff-nav';

// No real-time channel exists in the project, so the board polls. Orders change
// on a scale of minutes, so a short interval is enough and cheap for SQLite.
const REFRESH_MS = 15000;

interface Column {status: KitchenStatus; title: string; empty: string; action: string; next: string;}

@Component({
  selector: 'staff-kitchen', 
  standalone: true, 
  imports: [DatePipe, RouterLink, StaffNavComponent], 
  templateUrl: './kitchen.html', 
  styleUrl: './kitchen.css'
})
export class KitchenComponent {
  private api = inject(KitchenService);
  auth = inject(AuthService);
  
  readonly columns: Column[] = [
    {status: 'pending', title: 'New', empty: 'No new orders. New orders appear here automatically.', action: 'Start preparing', next: 'preparing'},
    {status: 'preparing', title: 'Preparing', empty: 'Nothing on the stove right now.', action: 'Mark ready', next: 'ready'},
    {status: 'ready', title: 'Ready', empty: 'No orders waiting to be served.', action: 'Served', next: 'served'},
  ];
  
  orders = signal<KitchenOrder[]>([]);
  loading = signal(true);
  error = signal('');
  updatedAt = signal<Date | null>(null);
  busy = signal<number | null>(null);
  now = signal(Date.now());

  // --- NEW AI STATE VARIABLES ---
  aiEstimates = signal<Record<number, {minutes: number, reason: string, source: string}>>({});
  aiLoading = signal<number | null>(null);
  // ------------------------------

  // Set when loading the board failed, so the next successful refresh clears that message
  // (messages from a refused status change stay until dismissed).
  private refreshFailed = false;
  
  byStatus = computed(() => {
    const groups: Record<string, KitchenOrder[]> = {pending: [], preparing: [], ready: []};
    // The server sends oldest first; keep that order inside each column.
    for (const order of this.orders()) groups[order.status]?.push(order);
    return groups;
  });

  constructor() {
    this.load();
    const timer = setInterval(() => {
      this.now.set(Date.now());
      if (!document.hidden && this.busy() === null) this.load(true);
    }, REFRESH_MS);
    inject(DestroyRef).onDestroy(() => clearInterval(timer));
  }

  load(background = false) {
    if (!background) this.loading.set(true);
    this.api.orders().subscribe({
      next: orders => {
        this.orders.set(orders); 
        this.loading.set(false); 
        this.updatedAt.set(new Date()); 
        this.now.set(Date.now()); 
        if (!background || this.refreshFailed) this.error.set(''); 
        this.refreshFailed = false;
      },
      error: (err: HttpErrorResponse) => {
        this.loading.set(false); 
        this.error.set(errorMessage(err)); 
        this.refreshFailed = true;
      }
    });
  }

  advance(order: KitchenOrder, column: Column) {
    if (this.busy() !== null) return;
    this.busy.set(order.id); this.error.set('');
    this.api.move(order.id, order.status, column.next).subscribe({
      next: updated => {
        this.busy.set(null);
        // Served orders leave the board; others move to their new column.
        this.orders.update(list => updated.status === 'served' ? list.filter(o => o.id !== updated.id) : list.map(o => o.id === updated.id ? updated : o));
      },
      error: (err: HttpErrorResponse) => {this.busy.set(null); this.error.set(errorMessage(err)); this.load(true);}
    });
  }

  /** Minutes since the order was placed. */
  age(order: KitchenOrder) {return Math.max(0, Math.floor((this.now() - this.time(order.created_at)) / 60000));}
  
  /** An order is late once it has waited longer than its slowest dish takes to prepare, plus a margin. */
  late(order: KitchenOrder) {return order.status !== 'ready' && this.age(order) > order.longest_preparation_minutes + 10;}
  
  time(value: string) {return new Date(serverTime(value)).getTime();}
  
  at(value: string) {return serverTime(value);}

  // --- NEW AI METHOD ---
  getAiEstimate(orderId: number) {
    if (this.aiLoading() !== null) return; // Prevent multiple clicks at once
    this.aiLoading.set(orderId);
    
    // We assume you will add this method to your KitchenService next!
    this.api.getPrepTimeEstimate(orderId).subscribe({
      next: (data) => {
        this.aiEstimates.update(prev => ({...prev, [orderId]: data}));
        this.aiLoading.set(null);
      },
      error: (err) => {
        console.error("AI Error:", err);
        this.aiLoading.set(null);
        // Optional: show an alert or a toast notification here if it fails
      }
    });
  }
}