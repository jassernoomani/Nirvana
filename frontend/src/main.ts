import { bootstrapApplication } from '@angular/platform-browser';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideZonelessChangeDetection } from '@angular/core';
import { AppComponent } from './app/app';
import { Component } from '@angular/core';
import { provideRouter, RouterOutlet } from '@angular/router';
import { CustomerComponent } from './app/customer';
import { LoginComponent } from './app/login';
import { ForbiddenComponent } from './app/forbidden';
import { CheckoutComponent } from './app/checkout';
import { OrderComponent } from './app/order';
import { OrdersComponent } from './app/orders';
import { IntelligenceComponent } from './app/intelligence';
import { RecommendationsComponent } from './app/recommendations';
import { ReservationsComponent } from './app/reservations';
import { InventoryComponent } from './app/inventory';
import { KitchenComponent } from './app/kitchen';
import { customerGuard, guestGuard, sessionInterceptor, signedInGuard, staffGuard } from './app/auth.guards';

@Component({selector: 'app-root', standalone: true, imports: [RouterOutlet], template: '<router-outlet />'})
class RootComponent {}

bootstrapApplication(RootComponent, {providers: [provideHttpClient(withInterceptors([sessionInterceptor])), provideZonelessChangeDetection(), provideRouter([
  {path: '', component: CustomerComponent, title: 'Restauration · Fresh from our kitchen'},
  {path: 'login', component: LoginComponent, canActivate: [guestGuard], title: 'Restauration · Sign in'},
  {path: 'admin', component: AppComponent, canActivate: [staffGuard], title: 'Restauration · Menu studio'},
  {path: 'admin/intelligence', component: IntelligenceComponent, canActivate: [staffGuard], title: 'Restauration · Restaurant intelligence'},
  {path: 'recommendations', component: RecommendationsComponent, canActivate: [customerGuard], title: 'Restauration · Picked for you'},
  {path: 'admin/kitchen', component: KitchenComponent, canActivate: [staffGuard], title: 'Restauration · Kitchen'},
  {path: 'admin/inventory', component: InventoryComponent, canActivate: [staffGuard], title: 'Restauration · Inventory'},
  {path: 'checkout', component: CheckoutComponent, canActivate: [customerGuard], title: 'Restauration · Checkout'},
  {path: 'orders', component: OrdersComponent, canActivate: [customerGuard], title: 'Restauration · My orders'},
  {path: 'orders/:reference', component: OrderComponent, canActivate: [signedInGuard], title: 'Restauration · Order'},
  {path: 'reservations', component: ReservationsComponent, canActivate: [customerGuard], title: 'Restauration · Book a table'},
  {path: 'forbidden', component: ForbiddenComponent, canActivate: [signedInGuard], title: 'Restauration · Staff only'},
  {path: '**', redirectTo: ''}
])]}).catch(console.error);
