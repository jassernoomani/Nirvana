import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { serverTime } from './server-time';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { forkJoin } from 'rxjs';
import { Router, RouterLink } from '@angular/router';
import { Dish, MenuService } from './menu.service';
import { AuthService } from './auth.service';
import { CartService, removedNotice } from './cart.service';
import { OrderService, ReviewSummary } from './order.service';
import { DialogFocusDirective } from './dialog-focus';


@Component({selector: 'customer-menu', standalone: true, imports: [CommonModule, FormsModule, RouterLink, DialogFocusDirective], templateUrl: './customer.html', styleUrl: './customer.css'})
export class CustomerComponent {
  private api = inject(MenuService);
  private destroy = inject(DestroyRef);
  auth = inject(AuthService);
  dishes = signal<Dish[]>([]);
  loading = signal(true);
  error = signal('');
  search = signal(''); category = signal(''); vegetarian = signal(false); sort = signal('name');
  page = signal(1); readonly pageSize = 9;
  private cartService = inject(CartService);
  private router = inject(Router);
  cart = this.cartService.lines;
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
  cartCount = this.cartService.count;
  total = this.cartService.total;

  guestReviews = signal<ReviewSummary | null>(null);
  readonly stars = [1, 2, 3, 4, 5];

  constructor() {
    this.load(); this.auth.ready();
    inject(OrderService).publicReviews().pipe(takeUntilDestroyed(this.destroy)).subscribe({next: summary => this.guestReviews.set(summary), error: () => {}});
  }
  reviewDate(value: string) {return serverTime(value);}
  firstName(fullName: string) {return fullName.split(' ')[0];}
  signOut() {this.auth.signOut().then(() => this.notice.set('You have been signed out.'));}
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
    const removed = removedNotice(this.cartService.sync(items));
    if (removed) this.notice.set(removed);
  }
  private failed() {this.loading.set(false); this.error.set('Our menu is temporarily unavailable. Please try again in a moment.');}
  filter() {this.page.set(1);}
  reset() {this.search.set(''); this.category.set(''); this.vegetarian.set(false); this.sort.set('name'); this.filter();}
  quantity(id: number) {return this.cartService.quantity(id);}
  add(dish: Dish) {if (this.cartService.add(dish)) this.notice.set(`${dish.name} added to your cart.`);}
  decrease(id: number) {this.cartService.decrease(id);}
  remove(id: number) {this.cartService.remove(id);}
  /** Signed-out visitors sign in first; their cart is kept in the browser meanwhile. */
  checkout() {
    this.cartOpen.set(false);
    this.router.navigate(this.auth.user() ? ['/checkout'] : ['/login'], this.auth.user() ? {} : {queryParams: {returnUrl: '/checkout'}});
  }
}
