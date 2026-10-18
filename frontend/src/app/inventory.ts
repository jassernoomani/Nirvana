import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { Router, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Observable } from 'rxjs';
import { AuthService } from './auth.service';
import { DialogFocusDirective } from './dialog-focus';
import { errorMessage } from './order.service';
import { AdjustReason, InventoryItem, InventoryService, MOVEMENT_LABELS, StockMovement } from './inventory.service';

type Mode = 'delivery' | 'adjust' | 'edit' | 'history';
type Direction = 'waste' | 'remove' | 'add';

@Component({selector: 'staff-inventory', standalone: true, imports: [DatePipe, DecimalPipe, FormsModule, RouterLink, DialogFocusDirective], templateUrl: './inventory.html', styleUrl: './inventory.css'})
export class InventoryComponent {
  private api = inject(InventoryService);
  private destroy = inject(DestroyRef);
  private router = inject(Router);
  auth = inject(AuthService);
  readonly movementLabels = MOVEMENT_LABELS;
  readonly statusLabels = {ok: 'In stock', low: 'Low stock', out: 'Out of stock'};
  items = signal<InventoryItem[]>([]);
  loading = signal(true);
  error = signal('');
  notice = signal('');
  search = signal(''); status = signal('');
  // Dialog state
  selected = signal<InventoryItem | null>(null);
  mode = signal<Mode>('delivery');
  saving = signal(false);
  formError = signal('');
  history = signal<StockMovement[] | null>(null);
  quantity: number | null = null; minimum: number | null = null; direction: Direction = 'waste'; note = '';

  filtered = computed(() => {
    const query = this.search().trim().toLowerCase();
    const wanted = this.status();
    return this.items().filter(i => (!query || i.name.toLowerCase().includes(query) || i.used_in.some(d => d.toLowerCase().includes(query)) || String(i.id) === query)
      && (!wanted || (wanted === 'attention' ? i.status !== 'ok' : i.status === wanted)));
  });
  lowCount = computed(() => this.items().filter(i => i.status === 'low').length);
  outCount = computed(() => this.items().filter(i => i.status === 'out').length);

  constructor() {this.load();}
  load() {
    this.loading.set(true); this.error.set('');
    this.api.list().pipe(takeUntilDestroyed(this.destroy)).subscribe({
      next: items => {this.items.set(items); this.loading.set(false);},
      error: (err: HttpErrorResponse) => {this.loading.set(false); this.error.set(errorMessage(err));}
    });
  }
  showAttention() {this.status.set('attention'); this.search.set('');}
  open(item: InventoryItem, mode: Mode) {
    this.selected.set(item); this.mode.set(mode); this.formError.set(''); this.note = '';
    this.quantity = mode === 'edit' ? item.stock_quantity : null;
    this.minimum = mode === 'edit' ? item.reorder_level : null;
    this.direction = 'waste';
    if (mode === 'history') {
      this.history.set(null);
      this.api.history(item.id).pipe(takeUntilDestroyed(this.destroy)).subscribe({
        next: rows => this.history.set(rows), error: (err: HttpErrorResponse) => {this.history.set([]); this.formError.set(errorMessage(err));}
      });
    }
  }
  close() {if (!this.saving()) this.selected.set(null);}
  save() {
    const item = this.selected(); if (!item || this.saving()) return;
    const note = this.note.trim() || null;
    let request: Observable<InventoryItem>;
    let message: string;
    if (this.mode() === 'edit') {
      if (this.quantity === null || !(this.quantity >= 0)) {this.formError.set('Enter the counted quantity (0 or more).'); return;}
      if (this.minimum === null || !(this.minimum >= 0)) {this.formError.set('Enter a minimum level (0 or more).'); return;}
      request = this.api.update(item.id, {stock_quantity: this.quantity, reorder_level: this.minimum, note});
      message = `${item.name} updated.`;
    } else {
      if (this.quantity === null || !(this.quantity > 0)) {this.formError.set('Enter a quantity greater than zero.'); return;}
      const removing = this.mode() === 'adjust' && this.direction !== 'add';
      if (removing && this.quantity > item.stock_quantity) {this.formError.set(`Only ${item.stock_quantity} ${item.unit} in stock: you cannot remove more than that.`); return;}
      const reason: AdjustReason = this.mode() === 'delivery' ? 'delivery' : this.direction === 'waste' ? 'waste' : 'correction';
      request = this.api.adjust(item.id, removing ? -this.quantity : this.quantity, reason, note);
      message = this.mode() === 'delivery' ? `Delivery recorded: ${this.quantity} ${item.unit} of ${item.name} added.`
        : `${item.name} ${removing ? 'reduced' : 'increased'} by ${this.quantity} ${item.unit}.`;
    }
    this.saving.set(true); this.formError.set('');
    request.pipe(takeUntilDestroyed(this.destroy)).subscribe({
      next: updated => {
        this.items.update(items => items.map(i => i.id === updated.id ? updated : i));
        this.saving.set(false); this.selected.set(null);
        this.notice.set(`${message} Now ${updated.stock_quantity} ${updated.unit}.`);
      },
      error: (err: HttpErrorResponse) => {this.saving.set(false); this.formError.set(errorMessage(err));}
    });
  }
  signOut() {this.auth.logout().subscribe({complete: () => this.router.navigate(['/login']), error: () => this.router.navigate(['/login'])});}
  when(value: string) {return value.replace(' ', 'T');}
}
