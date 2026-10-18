import { Component, DestroyRef, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subject, catchError, of, switchMap } from 'rxjs';
import { HttpErrorResponse } from '@angular/common/http';
import { Dish, DishInput, MenuService } from './menu.service';
import { DialogFocusDirective } from './dialog-focus';

@Component({selector: 'app-root', standalone: true, imports: [CommonModule, FormsModule, DialogFocusDirective], templateUrl: './app.html'})
export class AppComponent {
  private api = inject(MenuService);
  private destroy = inject(DestroyRef);
  private requests = new Subject<Record<string, string | number | boolean>>();
  dishes = signal<Dish[]>([]);
  categories = signal<string[]>([]);
  loading = signal(true);
  error = signal('');
  notice = signal('');
  editor = signal(false);
  saving = signal(false);
  pending = signal<number | null>(null);
  deleting = signal<Dish | null>(null);
  editId: number | null = null;
  search = ''; category = ''; available = ''; vegetarian = ''; sort = 'category'; direction = 'asc';
  minPrice: number | null = null; maxPrice: number | null = null;
  page = 1; readonly pageSize = 12;
  form: DishInput = this.emptyForm();
  formError = signal('');

  constructor() {
    this.requests.pipe(switchMap(filters => this.api.list(filters).pipe(catchError((err: HttpErrorResponse) => {
      this.error.set(this.message(err)); return of([] as Dish[]);
    }))), takeUntilDestroyed(this.destroy)).subscribe(items => { this.dishes.set(items); this.loading.set(false); });
    this.loadCategories(); this.load();
  }
  emptyForm(): DishInput {return {name: '', description: '', price: 0, category: '', is_available: true, preparation_minutes: 15, is_vegetarian: false, image_url: null};}
  get visible() {return this.dishes().slice(0, this.pageSize);}
  get hasNext() {return this.dishes().length > this.pageSize;}
  get availableCount() {return this.visible.filter(d => d.is_available).length;}
  load(reset = false) {
    if (reset) this.page = 1;
    this.error.set(''); this.loading.set(true);
    const filters: Record<string, string | number | boolean> = {search: this.search.trim(), category: this.category, available: this.available, vegetarian: this.vegetarian, sort: this.sort, direction: this.direction, limit: this.pageSize + 1, offset: (this.page - 1) * this.pageSize};
    if (this.minPrice !== null) filters['min_price'] = this.minPrice;
    if (this.maxPrice !== null) filters['max_price'] = this.maxPrice;
    this.requests.next(filters);
  }
  loadCategories() {this.api.categories().pipe(takeUntilDestroyed(this.destroy)).subscribe({next: rows => this.categories.set(rows), error: () => {}});}
  reset() {this.search = this.category = this.available = this.vegetarian = ''; this.minPrice = this.maxPrice = null; this.sort = 'category'; this.direction = 'asc'; this.load(true);}
  move(delta: number) {this.page += delta; this.load();}
  open(dish?: Dish) {this.editId = dish?.id ?? null; this.form = dish ? {name: dish.name, description: dish.description, price: dish.price, category: dish.category, is_available: dish.is_available, preparation_minutes: dish.preparation_minutes, is_vegetarian: dish.is_vegetarian, image_url: dish.image_url} : this.emptyForm(); this.formError.set(''); this.editor.set(true);}
  close() {if (!this.saving()) this.editor.set(false);}
  save() {
    if (this.saving()) return;
    const body = {...this.form, name: this.form.name.trim(), category: this.form.category.trim(), description: this.form.description?.trim() || null};
    if (!body.name || !body.category || !(body.price > 0) || !Number.isInteger(body.preparation_minutes) || body.preparation_minutes < 1 || body.preparation_minutes > 240) {this.formError.set('Enter a name, category, positive price, and preparation time from 1 to 240 minutes.'); return;}
    this.saving.set(true); this.formError.set('');
    (this.editId === null ? this.api.create(body) : this.api.update(this.editId, body)).pipe(takeUntilDestroyed(this.destroy)).subscribe({next: () => {this.saving.set(false); this.editor.set(false); this.notice.set('Dish saved successfully.'); this.loadCategories(); this.load(true);}, error: err => {this.saving.set(false); this.formError.set(this.message(err));}});
  }
  toggle(dish: Dish) {
    if (this.pending() !== null) return;
    this.pending.set(dish.id); this.error.set('');
    this.api.availability(dish.id, !dish.is_available).pipe(takeUntilDestroyed(this.destroy)).subscribe({next: () => {this.pending.set(null); this.notice.set('Availability updated.'); this.load();}, error: err => {this.pending.set(null); this.error.set(this.message(err));}});
  }
  confirmDelete() {
    const dish = this.deleting(); if (!dish || this.pending() !== null) return;
    this.pending.set(dish.id);
    this.api.delete(dish.id).pipe(takeUntilDestroyed(this.destroy)).subscribe({next: () => {this.pending.set(null); this.deleting.set(null); this.notice.set('Dish deleted.'); this.loadCategories(); this.load(true);}, error: err => {this.pending.set(null); this.deleting.set(null); this.error.set(this.message(err));}});
  }
  private message(err: HttpErrorResponse): string {
    if (err.status === 0 || err.status === 502 || err.status === 504) return 'Cannot connect to the restaurant API. Start the backend on port 8000, then retry.';
    const detail = err.error?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) return detail.map((d: {msg: string}) => d.msg).join('. ');
    return 'The request failed. Please try again.';
  }
}
