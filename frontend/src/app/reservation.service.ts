import { inject, Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';

export interface Reservation {id: number; reserved_for: string; party_size: number; status: string; table_label: string | null; contact_phone: string | null; notes: string | null; created_at: string;}
export interface Availability {date: string; party_size: number; duration_minutes: number; max_party_size: number; slots: {time: string; available: boolean}[];}
export interface ReservationRequest {date: string; time: string; party_size: number; contact_phone: string | null; notes: string | null;}

// "booked" is the confirmed state: the server only accepts a booking once it has a free table.
export const RESERVATION_LABELS: Partial<Record<string, string>> = {
  booked: 'Confirmed', seated: 'Seated', completed: 'Completed', cancelled: 'Cancelled', no_show: 'Missed'
};

@Injectable({providedIn: 'root'})
export class ReservationService {
  private http = inject(HttpClient);
  availability(date: string, partySize: number) {
    return this.http.get<Availability>('/api/reservations/availability', {params: {date, party_size: partySize}});
  }
  book(request: ReservationRequest) {return this.http.post<Reservation>('/api/reservations', request);}
  mine() {return this.http.get<Reservation[]>('/api/reservations');}
  cancel(id: number) {return this.http.post<Reservation>(`/api/reservations/${id}/cancel`, {});}
}
