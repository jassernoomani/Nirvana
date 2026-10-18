import { bootstrapApplication } from '@angular/platform-browser';
import { provideHttpClient } from '@angular/common/http';
import { provideZonelessChangeDetection } from '@angular/core';
import { AppComponent } from './app/app';
import { Component } from '@angular/core';
import { provideRouter, RouterOutlet } from '@angular/router';
import { CustomerComponent } from './app/customer';

@Component({selector: 'app-root', standalone: true, imports: [RouterOutlet], template: '<router-outlet />'})
class RootComponent {}

bootstrapApplication(RootComponent, {providers: [provideHttpClient(), provideZonelessChangeDetection(), provideRouter([
  {path: '', component: CustomerComponent, title: 'Restauration · Fresh from our kitchen'},
  {path: 'admin', component: AppComponent, title: 'Restauration · Menu studio'},
  {path: '**', redirectTo: ''}
])]}).catch(console.error);
