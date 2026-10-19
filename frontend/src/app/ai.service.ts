import { inject, Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Dish } from './menu.service';

export interface ModelStatus {available: boolean; model: string; installed_models: string[]; message: string;}
export interface Preferences {is_vegetarian: boolean; allergen_ids: number[]; favorite_categories: string[]; allergens: {id: number; name: string}[]; categories: string[];}
export interface Picks {items: {dish: Dish; score: number; reasons: string[]; allergens: string[]}[]; mode: string; model: string | null; warning: string | null; excluded_count: number; notice: string; profile: {is_vegetarian: boolean; allergies: string[]; favorite_categories: string[]; history_items: number};}
export interface Forecast {model: string; candidate_model: string; history_days: number; history_from: string; history_to: string; holdout_hours: number; model_mae: number; baseline_mae: number; total_orders: number; notice: string; daily: {date: string; orders: number; peak_hour: string}[]; hourly: {at: string; orders: number}[]; ingredients: {id: number; name: string; unit: string; forecast_usage: number; stock: number; reserve: number; suggested_purchase: number}[];}
export interface ReviewReport {days: number; total_reviews: number; average_rating: number | null; sample_size: number; analyzed_count: number; pending_count: number; flagged_count: number; sentiments: Record<string, number>; topics: {topic: string; count: number; review_ids: number[]}[]; examples: {id: number; date: string; rating: number; text: string; sentiment: string; complaints: {topic: string; quote: string}[]}[]; insights: {summary: string; actions: {topic: string; action: string}[]} | null; model: string; warnings: string[]; notice: string;}

@Injectable({providedIn: 'root'})
export class AiService {
  private http = inject(HttpClient);
  status() {return this.http.get<ModelStatus>('/api/ai/status');}
  profile() {return this.http.get<Preferences>('/api/ai/profile');}
  saveProfile(profile: Preferences) {return this.http.put('/api/ai/profile', {is_vegetarian: profile.is_vegetarian, allergen_ids: profile.allergen_ids, favorite_categories: profile.favorite_categories});}
  recommendations(useLlm: boolean) {return this.http.get<Picks>('/api/ai/recommendations', {params: {use_llm: useLlm}});}
  forecast(days: number) {return this.http.get<Forecast>('/api/ai/forecast', {params: {days}});}
  reviews(days: number, limit: number) {return this.http.post<ReviewReport>('/api/ai/reviews', {}, {params: {days, limit}});}
  prompts() {return this.http.get<Record<string, string>>('/api/ai/prompts');}
}
