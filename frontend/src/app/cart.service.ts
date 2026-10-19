import { computed, effect, Injectable, signal } from '@angular/core';
import { Dish } from './menu.service';

export interface CartLine {dish: Dish; quantity: number;}
const STORAGE_KEY = 'nirvana-cart';
export const MAX_PER_DISH = 99;

// The cart is kept in this browser so it survives signing in and page reloads.
// Prices here are for display only: the server recalculates every total.
@Injectable({providedIn: 'root'})
export class CartService {
  readonly lines = signal<CartLine[]>(this.restore());
  readonly count = computed(() => this.lines().reduce((n, line) => n + line.quantity, 0));
  readonly total = computed(() => this.lines().reduce((n, line) => n + Math.round(line.dish.price * 100) * line.quantity, 0) / 100);

  constructor() {
    effect(() => {
      const lines = this.lines();
      try {localStorage.setItem(STORAGE_KEY, JSON.stringify(lines));} catch {}
    });
  }
  quantity(id: number) {return this.lines().find(line => line.dish.id === id)?.quantity ?? 0;}
  add(dish: Dish) {
    if (!dish.is_available || this.quantity(dish.id) >= MAX_PER_DISH) return false;
    this.lines.update(lines => lines.some(line => line.dish.id === dish.id) ? lines.map(line => line.dish.id === dish.id ? {...line, quantity: line.quantity + 1} : line) : [...lines, {dish, quantity: 1}]);
    return true;
  }
  decrease(id: number) {this.lines.update(lines => lines.flatMap(line => line.dish.id !== id ? [line] : line.quantity > 1 ? [{...line, quantity: line.quantity - 1}] : []));}
  remove(id: number) {this.lines.update(lines => lines.filter(line => line.dish.id !== id));}
  clear() {this.lines.set([]);}
  /** Refresh names, prices and availability from the latest menu; drop dishes that are gone or unavailable. */
  sync(menu: Dish[]) {
    this.lines.update(lines => lines.flatMap(line => {const dish = menu.find(d => d.id === line.dish.id && d.is_available); return dish ? [{dish, quantity: line.quantity}] : [];}));
  }
  private restore(): CartLine[] {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]');
      return Array.isArray(saved) ? saved.filter(line => line?.dish?.id && Number.isInteger(line.quantity) && line.quantity >= 1 && line.quantity <= MAX_PER_DISH) : [];
    } catch {return [];}
  }
}
