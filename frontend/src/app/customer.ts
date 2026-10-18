import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { forkJoin } from 'rxjs';
import { Dish, MenuService } from './menu.service';
import { DialogFocusDirective } from './dialog-focus';

interface CartLine {dish: Dish; quantity: number;}

@Component({selector: 'customer-menu', standalone: true, imports: [CommonModule, FormsModule, DialogFocusDirective], templateUrl: './customer.html', styleUrl: './customer.css'})
export class CustomerComponent {
  private api = inject(MenuService);
  private destroy = inject(DestroyRef);
  dishes = signal<Dish[]>([]);
  loading = signal(true);
  error = signal('');
  search = signal(''); category = signal(''); vegetarian = signal(false); sort = signal('name');
  page = signal(1); readonly pageSize = 9;
  cart = signal<CartLine[]>([]);
  cartOpen = signal(false);
  detail = signal<Dish | null>(null);
  notice = signal('');
  categories = computed(() => [...new Set(this.dishes().map(d => d.category))].sort());
  filtered = computed(() => {
    const query = this.search().toLowerCase().trim();
    return this.dishes().filter(d => (!this.category() || d.category === this.category()) && (!this.vegetarian() || d.is_vegetarian) && (!query || `${d.name} ${d.description ?? ''}`.toLowerCase().includes(query))).sort((a,b) => this.sort() === 'price-asc' ? a.price - b.price || a.id - b.id : this.sort() === 'price-desc' ? b.price - a.price || a.id - b.id : a.name.localeCompare(b.name) || a.id - b.id);
  });
  visible = computed(() => this.filtered().slice((this.page() - 1) * this.pageSize, this.page() * this.pageSize));
  pageCount = computed(() => Math.max(1, Math.ceil(this.filtered().length / this.pageSize)));
  cartCount = computed(() => this.cart().reduce((n,line) => n + line.quantity, 0));
  total = computed(() => this.cart().reduce((n,line) => n + Math.round(line.dish.price * 100) * line.quantity, 0) / 100);

  constructor() {this.load();}
  load() {
    this.loading.set(true); this.error.set('');
    // The API list is capped at 100; use the count endpoint to retrieve every page.
    this.api.page(1, 100).pipe(takeUntilDestroyed(this.destroy)).subscribe({next: first => {
      const requests = Array.from({length: Math.max(0, Math.ceil(first.total / 100) - 1)}, (_, i) => this.api.page(i + 2, 100));
      if (!requests.length) {this.loaded(first.items); return;}
      forkJoin(requests).pipe(takeUntilDestroyed(this.destroy)).subscribe({next: pages => this.loaded([...first.items, ...pages.flatMap(p => p.items)]), error: () => this.failed()});
    }, error: () => this.failed()});
  }
  private loaded(items: Dish[]) {
    this.dishes.set(items); this.loading.set(false); this.page.set(1);
    this.cart.update(lines => lines.flatMap(line => {const dish = items.find(d => d.id === line.dish.id && d.is_available); return dish ? [{dish, quantity: line.quantity}] : [];}));
  }
  private failed() {this.loading.set(false); this.error.set('Our menu is temporarily unavailable. Please try again in a moment.');}
  filter() {this.page.set(1);}
  reset() {this.search.set(''); this.category.set(''); this.vegetarian.set(false); this.sort.set('name'); this.filter();}
  quantity(id: number) {return this.cart().find(line => line.dish.id === id)?.quantity ?? 0;}
  add(dish: Dish) {
    if (!dish.is_available || this.quantity(dish.id) >= 99) return;
    this.cart.update(lines => lines.some(line => line.dish.id === dish.id) ? lines.map(line => line.dish.id === dish.id ? {...line, quantity: line.quantity + 1} : line) : [...lines, {dish, quantity: 1}]);
    this.notice.set(`${dish.name} added to your cart.`);
  }
  decrease(id: number) {this.cart.update(lines => lines.flatMap(line => line.dish.id !== id ? [line] : line.quantity > 1 ? [{...line, quantity: line.quantity - 1}] : []));}
  remove(id: number) {this.cart.update(lines => lines.filter(line => line.dish.id !== id));}
}
