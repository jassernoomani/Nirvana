import { inject, Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';

export interface Dish {id: number; name: string; description: string | null; price: number; category: string; is_available: boolean; preparation_minutes: number; is_vegetarian: boolean; image_url: string | null;}
export type DishInput = Omit<Dish, 'id'>;

@Injectable({providedIn: 'root'})
export class MenuService {
  private http = inject(HttpClient);
  list(filters: Record<string, string | number | boolean>) {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(filters)) if (value !== '') params = params.set(key, value);
    return this.http.get<Dish[]>('/api/menu', {params});
  }
  categories() { return this.http.get<string[]>('/api/menu/categories'); }
  page(page: number, pageSize: number) {return this.http.get<{items: Dish[]; total: number; page: number; page_size: number}>('/api/menu/page', {params: {page, page_size: pageSize}});}
  create(dish: DishInput) { return this.http.post<Dish>('/api/menu', dish); }
  update(id: number, dish: DishInput) { return this.http.put<Dish>(`/api/menu/${id}`, dish); }
  availability(id: number, available: boolean) { return this.http.patch<Dish>(`/api/menu/${id}`, {is_available: available}); }
  delete(id: number) { return this.http.delete<void>(`/api/menu/${id}`); }
}
