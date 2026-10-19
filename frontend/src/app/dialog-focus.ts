import { AfterViewInit, Directive, ElementRef, HostListener, OnDestroy, inject } from '@angular/core';

@Directive({selector: '[dialogFocus]', standalone: true})
export class DialogFocusDirective implements AfterViewInit, OnDestroy {
  private host = inject<ElementRef<HTMLElement>>(ElementRef);
  private previous = document.activeElement as HTMLElement | null;
  private controls() {return Array.from(this.host.nativeElement.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]'));}
  ngAfterViewInit() {this.controls()[0]?.focus();}
  ngOnDestroy() {this.previous?.focus();}
  @HostListener('keydown', ['$event'])
  trap(event: KeyboardEvent) {
    if (event.key !== 'Tab') return;
    const controls = this.controls();
    const first = controls[0]; const last = controls[controls.length - 1];
    if (!first) {event.preventDefault(); return;}
    if (event.shiftKey && document.activeElement === first) {event.preventDefault(); last.focus();}
    else if (!event.shiftKey && document.activeElement === last) {event.preventDefault(); first.focus();}
  }
}
