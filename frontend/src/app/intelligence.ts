import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from './auth.service';
import { StaffNavComponent } from './staff-nav';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { AiService, Forecast, ModelStatus, ReviewReport } from './ai.service';

@Component({standalone: true, imports: [CommonModule, FormsModule, RouterLink, StaffNavComponent], templateUrl: './intelligence.html', styleUrl: './intelligence.css'})
export class IntelligenceComponent {
  private ai = inject(AiService); private destroy = inject(DestroyRef);
  auth = inject(AuthService); private router = inject(Router);
  tab = signal('forecast'); model = signal<ModelStatus | null>(null); forecast = signal<Forecast | null>(null);
  reviews = signal<ReviewReport | null>(null); prompts = signal<Record<string, string> | null>(null);
  forecastBusy = signal(false); reviewBusy = signal(false); error = signal('');
  days = 7; reviewDays = 30; sample = 8; selectedDay = signal('');
  hourly = computed(() => this.forecast()?.hourly.filter(row => row.at.startsWith(this.selectedDay())) ?? []);
  peak = computed(() => Math.max(1, ...this.hourly().map(row => row.orders)));
  purchases = computed(() => this.forecast()?.ingredients.filter(item => item.suggested_purchase > 0).length ?? 0);
  constructor() {this.checkModel(); this.runForecast();}
  signOut() {this.auth.logout().subscribe({complete: () => this.router.navigate(['/login']), error: () => this.router.navigate(['/login'])});}
  label(value: string) {return value.replaceAll('_', ' ');}
  checkModel() {this.ai.status().pipe(takeUntilDestroyed(this.destroy)).subscribe({next: s => this.model.set(s), error: () => this.error.set('Could not check the local model connection.')});}
  runForecast() {
    if (this.forecastBusy()) return;
    this.forecastBusy.set(true); this.error.set('');
    this.ai.forecast(this.days).pipe(takeUntilDestroyed(this.destroy)).subscribe({next: data => {this.forecast.set(data); this.selectedDay.set(data.daily[0]?.date ?? ''); this.forecastBusy.set(false);}, error: e => {this.forecastBusy.set(false); this.error.set(e.error?.detail || 'Forecast unavailable. Check the order history and backend requirements.');}});
  }
  runReviews() {
    if (this.reviewBusy()) return;
    this.reviewBusy.set(true); this.error.set('');
    this.ai.reviews(this.reviewDays, this.sample).pipe(takeUntilDestroyed(this.destroy)).subscribe({next: report => {this.reviews.set(report); this.reviewBusy.set(false);}, error: e => {this.reviewBusy.set(false); this.error.set(e.error?.detail || 'Review analysis failed. Please retry.');}});
  }
  showPrompts() {this.tab.set('prompts'); if (!this.prompts()) this.ai.prompts().pipe(takeUntilDestroyed(this.destroy)).subscribe({next: p => this.prompts.set(p), error: () => this.error.set('Could not load prompts.')});}
}
