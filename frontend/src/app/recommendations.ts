import { Component, DestroyRef, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { switchMap } from 'rxjs';
import { AiService, Picks, Preferences } from './ai.service';
import { CartService } from './cart.service';
import { Dish } from './menu.service';

@Component({standalone: true, imports: [CommonModule, FormsModule, RouterLink], templateUrl: './recommendations.html', styleUrl: './intelligence.css'})
export class RecommendationsComponent {
  private ai = inject(AiService); private destroy = inject(DestroyRef); cart = inject(CartService);
  profile = signal<Preferences | null>(null); picks = signal<Picks | null>(null);
  busy = signal(false); error = signal(''); notice = signal(''); useLlm = false;
  constructor() {
    this.ai.profile().pipe(takeUntilDestroyed(this.destroy)).subscribe({next: p => {this.profile.set(p); this.refresh();}, error: e => this.error.set(e.error?.detail || 'Could not load your dietary profile.')});
  }
  refresh() {
    if (this.busy()) return;
    this.busy.set(true); this.error.set('');
    this.ai.recommendations(this.useLlm).pipe(takeUntilDestroyed(this.destroy)).subscribe({next: data => {this.picks.set(data); this.busy.set(false);}, error: e => {this.error.set(e.error?.detail || 'Recommendations could not be loaded.'); this.busy.set(false);}});
  }
  save() {
    const p = this.profile(); if (!p || this.busy()) return;
    this.busy.set(true); this.error.set(''); this.picks.set(null);
    this.ai.saveProfile(p).pipe(switchMap(() => this.ai.recommendations(this.useLlm)), takeUntilDestroyed(this.destroy)).subscribe({next: data => {this.picks.set(data); this.busy.set(false); this.notice.set('Dietary preferences saved.');}, error: e => {this.busy.set(false); this.error.set(e.error?.detail || 'Could not save preferences.');}});
  }
  toggleAllergen(id: number, checked: boolean) {const p = this.profile(); if (p) p.allergen_ids = checked ? [...p.allergen_ids, id] : p.allergen_ids.filter(x => x !== id);}
  toggleCategory(category: string, checked: boolean) {const p = this.profile(); if (p) p.favorite_categories = checked ? [...p.favorite_categories, category] : p.favorite_categories.filter(x => x !== category);}
  add(dish: Dish) {if (this.cart.add(dish)) this.notice.set(`${dish.name} added to your cart.`);}
}
