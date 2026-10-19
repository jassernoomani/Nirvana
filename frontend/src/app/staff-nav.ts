import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

/** Sidebar links shared by every staff page. */
@Component({selector: 'staff-nav', standalone: true, imports: [RouterLink, RouterLinkActive], template: `
  <nav class="side-nav" aria-label="Staff workspace">
    @for (link of links; track link.path) {
      <a [routerLink]="link.path" routerLinkActive #active="routerLinkActive" [routerLinkActiveOptions]="{exact: true}"
         [class.nav-active]="active.isActive" [class.nav-link]="!active.isActive" [attr.aria-current]="active.isActive ? 'page' : null">
        <span>{{ link.icon }}</span> {{ link.label }} @if (active.isActive) {<span class="nav-dot"></span>}
      </a>
    }
  </nav>`})
export class StaffNavComponent {
  readonly links = [
    {path: '/admin', label: 'Menu studio', icon: '▦'},
    {path: '/admin/kitchen', label: 'Kitchen', icon: '◷'},
    {path: '/admin/inventory', label: 'Inventory', icon: '▤'},
    {path: '/admin/intelligence', label: 'Intelligence', icon: '✦'},
    {path: '/admin/noshow', label: 'No-shows', icon: '◐'},
  ];
}
