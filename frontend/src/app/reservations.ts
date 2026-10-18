import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subject, switchMap, catchError, of } from 'rxjs';
import { AuthService } from './auth.service';
import { errorMessage } from './order.service';
import { Availability, Reservation, RESERVATION_LABELS, ReservationService } from './reservation.service';

const MAX_DAYS_AHEAD = 60;

function isoDay(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

@Component({selector: 'reservation-page', standalone: true, imports: [DatePipe, FormsModule, RouterLink], templateUrl: './reservations.html', styleUrls: ['./pages.css', './reservations.css']})
export class ReservationsComponent {
  private api = inject(ReservationService);
  private destroy = inject(DestroyRef);
  auth = inject(AuthService);
  readonly labels = RESERVATION_LABELS;
  readonly today = isoDay(new Date());
  readonly lastDay = isoDay(new Date(Date.now() + MAX_DAYS_AHEAD * 86400000));
  date = this.today; partySize = 2; time = ''; phone = ''; notes = '';
  availability = signal<Availability | null>(null);
  loadingSlots = signal(false);
  booking = signal(false);
  error = signal('');
  confirmation = signal<Reservation | null>(null);
  reservations = signal<Reservation[] | null>(null);
  listError = signal('');
  confirmingCancel = signal<number | null>(null);
  anyFree = computed(() => !!this.availability()?.slots.some(s => s.available));
  partySizes = computed(() => Array.from({length: this.availability()?.max_party_size || 8}, (_, i) => i + 1));
  upcoming = computed(() => (this.reservations() ?? []).filter(r => this.isUpcoming(r)).reverse());
  past = computed(() => (this.reservations() ?? []).filter(r => !this.isUpcoming(r)));
  private slotRequests = new Subject<{date: string; partySize: number}>();

  constructor() {
    this.slotRequests.pipe(switchMap(({date, partySize}) => this.api.availability(date, partySize).pipe(
      catchError((err: HttpErrorResponse) => {this.error.set(errorMessage(err)); return of(null);}))),
      takeUntilDestroyed(this.destroy)).subscribe(result => {
        this.availability.set(result); this.loadingSlots.set(false);
        if (!result?.slots.some(s => s.time === this.time && s.available)) this.time = '';
      });
    this.loadSlots();
    this.loadReservations();
  }
  loadSlots() {
    this.error.set(''); this.time = '';
    if (!this.date || this.date < this.today || this.date > this.lastDay) {this.availability.set(null); return;}
    this.loadingSlots.set(true);
    this.slotRequests.next({date: this.date, partySize: this.partySize});
  }
  loadReservations() {
    this.api.mine().pipe(takeUntilDestroyed(this.destroy)).subscribe({
      next: rows => this.reservations.set(rows), error: (err: HttpErrorResponse) => this.listError.set(errorMessage(err))
    });
  }
  submit() {
    if (this.booking()) return;
    this.confirmation.set(null);
    if (!this.date) {this.error.set('Choose a date.'); return;}
    if (this.date < this.today) {this.error.set('Choose a date that is not in the past.'); return;}
    if (this.date > this.lastDay) {this.error.set(`Reservations open ${MAX_DAYS_AHEAD} days in advance.`); return;}
    if (!(this.partySize >= 1)) {this.error.set('Choose the number of guests.'); return;}
    if (!this.time) {this.error.set('Choose a time.'); return;}
    if (this.phone.trim() && !/^\+?[0-9 ().-]{6,30}$/.test(this.phone.trim())) {this.error.set('Enter a valid phone number, or leave it empty.'); return;}
    this.booking.set(true); this.error.set('');
    this.api.book({date: this.date, time: this.time, party_size: this.partySize, contact_phone: this.phone.trim() || null, notes: this.notes.trim() || null})
      .pipe(takeUntilDestroyed(this.destroy)).subscribe({
        next: reservation => {
          this.booking.set(false); this.confirmation.set(reservation);
          this.notes = ''; this.loadSlots(); this.loadReservations();
        },
        error: (err: HttpErrorResponse) => {this.booking.set(false); this.error.set(errorMessage(err)); this.loadSlots();}
      });
  }
  cancel(reservation: Reservation) {
    this.api.cancel(reservation.id).pipe(takeUntilDestroyed(this.destroy)).subscribe({
      next: () => {this.confirmingCancel.set(null); this.confirmation.set(null); this.loadReservations(); this.loadSlots();},
      error: (err: HttpErrorResponse) => {this.confirmingCancel.set(null); this.listError.set(errorMessage(err));}
    });
  }
  /** Stored as local restaurant time without a zone. */
  when(value: string) {return value.replace(' ', 'T');}
  private isUpcoming(r: Reservation) {return new Date(this.when(r.reserved_for)) > new Date() && r.status !== 'completed';}
}
