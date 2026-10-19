import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from './auth.service';
import { StaffNavComponent } from './staff-nav';
import { NoShowOverview, NoShowRisk, NoShowService, StoredReminder } from './noshow.service';

const RISK_LABELS: Record<NoShowRisk, string> = {low: 'Low', medium: 'Medium', high: 'High', average: 'Average'};
const KIND_LABELS: Record<string, string> = {day_before: '24 h before', same_day: '3 h before'};

@Component({selector: 'staff-noshow', standalone: true, imports: [CommonModule, FormsModule, RouterLink, StaffNavComponent], templateUrl: './noshow.html', styleUrl: './noshow.css'})
export class NoShowComponent {
  private api = inject(NoShowService);
  private destroy = inject(DestroyRef);
  private router = inject(Router);
  auth = inject(AuthService);
  data = signal<NoShowOverview | null>(null);
  stored = signal<StoredReminder[]>([]);
  loading = signal(false);
  working = signal(false);
  error = signal('');
  notice = signal('');
  showAll = signal(false);
  days = 7;

  rows = computed(() => {
    const all = [...(this.data()?.predictions ?? [])].sort((a, b) => b.probability - a.probability);
    return this.showAll() ? all : all.filter(item => item.risk === 'high' || item.risk === 'medium');
  });
  atRisk = computed(() => this.data()?.predictions.filter(item => item.risk === 'high' || item.risk === 'medium').length ?? 0);
  newReminders = computed(() => this.data()?.reminder_plan.filter(step => !step.already_scheduled).length ?? 0);
  extraTotal = computed(() => this.data()?.services.reduce((sum, service) => sum + service.suggested_extra_bookings, 0) ?? 0);
  pending = computed(() => this.stored().filter(item => item.status === 'pending').length);
  usesModel = computed(() => this.data()?.model === this.data()?.candidate_model);

  constructor() {this.load();}

  signOut() {this.auth.logout().subscribe({complete: () => this.router.navigate(['/login']), error: () => this.router.navigate(['/login'])});}
  risk(value: NoShowRisk) {return RISK_LABELS[value];}
  kind(value: string) {return KIND_LABELS[value] ?? value;}
  percent(value: number | null | undefined) {return value === null || value === undefined ? '—' : `${(value * 100).toFixed(value < 0.1 ? 1 : 0)}%`;}
  serviceLabel(value: string) {return value === 'lunch' ? 'Lunch' : 'Dinner';}

  load() {
    if (this.loading()) return;
    this.loading.set(true); this.error.set('');
    this.api.overview(this.days).pipe(takeUntilDestroyed(this.destroy)).subscribe({
      next: data => {this.data.set(data); this.loading.set(false); this.loadStored();},
      error: err => {this.data.set(null); this.loading.set(false); this.error.set(this.message(err, 'No-show prediction is unavailable. Check the reservation history and backend requirements.'));}
    });
  }
  loadStored() {
    this.api.reminders().pipe(takeUntilDestroyed(this.destroy)).subscribe({next: rows => this.stored.set(rows), error: () => this.stored.set([])});
  }
  schedule() {
    if (this.working()) return;
    this.working.set(true); this.error.set(''); this.notice.set('');
    this.api.schedule(this.days).pipe(takeUntilDestroyed(this.destroy)).subscribe({
      next: result => {this.working.set(false); this.notice.set(`${result.created} reminder${result.created === 1 ? '' : 's'} scheduled, ${result.already_scheduled} already in place.`); this.refresh();},
      error: err => {this.working.set(false); this.error.set(this.message(err, 'Could not schedule the reminders.'));}
    });
  }
  dispatch() {
    if (this.working()) return;
    this.working.set(true); this.error.set(''); this.notice.set('');
    this.api.dispatch().pipe(takeUntilDestroyed(this.destroy)).subscribe({
      next: result => {this.working.set(false); this.notice.set(`${result.dispatched} sent to the outbox, ${result.skipped} skipped, ${result.failed} failed. ${result.notice}`); this.refresh();},
      error: err => {this.working.set(false); this.error.set(this.message(err, 'Could not send the reminders.'));}
    });
  }
  private refresh() {
    this.api.overview(this.days).pipe(takeUntilDestroyed(this.destroy)).subscribe({next: data => this.data.set(data), error: () => {}});
    this.loadStored();
  }
  private message(err: HttpErrorResponse, fallback: string): string {
    if (err.status === 0 || err.status === 502 || err.status === 504) return 'Cannot connect to the restaurant API. Start the backend on port 8000, then retry.';
    const detail = err.error?.detail;
    return typeof detail === 'string' ? detail : fallback;
  }
}
