import { inject, Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';

export type NoShowRisk = 'low' | 'medium' | 'high' | 'average';

export interface NoShowFactor {factor: string; effect: 'raises' | 'lowers';}
export interface NoShowReminderState {kind: string; status: string; scheduled_for: string;}
export interface NoShowPrediction {
  id: number; reserved_for: string; guest: string; party_size: number; table_label: string | null;
  probability: number; risk: NoShowRisk; channel: 'sms' | 'email'; factors: NoShowFactor[]; reminders: NoShowReminderState[];
}
export interface ServicePlan {
  date: string; service: 'lunch' | 'dinner'; bookings: number; covers: number; covers_at_risk: number;
  expected_no_shows: number; chance_of_any_no_show: number; suggested_extra_bookings: number; clash_risk: number;
}
export interface ReminderPlanItem {
  reservation_id: number; guest: string; reserved_for: string; kind: string; channel: string;
  scheduled_for: string; risk: number; message: string; already_scheduled: boolean;
}
export interface NoShowOverview {
  model: string; candidate_model: string; horizon_days: number;
  thresholds: {medium: number; high: number}; overbooking: {tolerance: number; max_extra: number};
  trained_on: number; training_from: string; training_to: string; holdout_size: number; holdout_no_shows: number;
  base_rate: number; model_brier: number; baseline_brier: number; model_auc: number | null;
  top_quartile_rate: number | null; other_rate: number | null;
  predictions: NoShowPrediction[]; services: ServicePlan[]; reminder_plan: ReminderPlanItem[]; notice: string;
}
export interface ScheduleResult {model: string; planned: number; created: number; already_scheduled: number;}
export interface DispatchResult {dispatched: number; skipped: number; failed: number; delivery: string; notice: string;}
export interface StoredReminder {
  id: number; reservation_id: number; kind: string; channel: string; scheduled_for: string; risk: number;
  status: 'pending' | 'dispatched' | 'skipped'; detail: string | null; dispatched_at: string | null;
  reserved_for: string; guest: string;
}

@Injectable({providedIn: 'root'})
export class NoShowService {
  private http = inject(HttpClient);
  overview(days: number) {return this.http.get<NoShowOverview>('/api/ai/noshow/overview', {params: {days}});}
  schedule(days: number) {return this.http.post<ScheduleResult>('/api/ai/noshow/reminders/schedule', {}, {params: {days}});}
  dispatch() {return this.http.post<DispatchResult>('/api/ai/noshow/reminders/dispatch', {});}
  reminders() {return this.http.get<StoredReminder[]>('/api/ai/noshow/reminders', {params: {limit: 50}});}
}
