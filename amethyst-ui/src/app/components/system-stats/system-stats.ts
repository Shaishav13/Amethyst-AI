import { Component, OnInit, OnDestroy, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AmethystApiService, SystemSnapshot } from '../../services/amethyst-api';

@Component({
  selector: 'app-system-stats',
  standalone: true,
  imports: [CommonModule],
  template: `
    @if (snap() && snap()!.available) {
      <div class="stats">
        <div class="stat-row">
          <span class="stat-label">CPU</span>
          <div class="bar-track">
            <div class="bar-fill" [style.width.%]="snap()!.cpu_percent"
                 [class.warn]="snap()!.cpu_percent > 80"
                 [class.danger]="snap()!.cpu_percent > 95"></div>
          </div>
          <span class="stat-val">{{ snap()!.cpu_percent | number:'1.0-0' }}%</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">RAM</span>
          <div class="bar-track">
            <div class="bar-fill" [style.width.%]="snap()!.ram_percent"
                 [class.warn]="snap()!.ram_percent > 80"
                 [class.danger]="snap()!.ram_percent > 92"></div>
          </div>
          <span class="stat-val">{{ snap()!.ram_used_gb | number:'1.1-1' }}/{{ snap()!.ram_total_gb | number:'1.0-0' }}G</span>
        </div>
        @if (snap()!.battery_percent !== null) {
          <div class="stat-row">
            <span class="stat-label">BAT</span>
            <div class="bar-track">
              <div class="bar-fill battery"
                   [style.width.%]="snap()!.battery_percent"
                   [class.warn]="(snap()!.battery_percent ?? 100) < 25"
                   [class.danger]="(snap()!.battery_percent ?? 100) < 10"></div>
            </div>
            <span class="stat-val">
              {{ snap()!.battery_percent | number:'1.0-0' }}%
              {{ snap()!.battery_plugged ? '⚡' : '' }}
            </span>
          </div>
        }
      </div>
    }
  `,
  styleUrl: './system-stats.scss',
})
export class SystemStatsComponent implements OnInit, OnDestroy {
  snap = signal<SystemSnapshot | null>(null);
  private _interval: any;

  constructor(private api: AmethystApiService) {}

  ngOnInit() {
    this.refresh();
    this._interval = setInterval(() => this.refresh(), 10000);
  }

  ngOnDestroy() {
    clearInterval(this._interval);
  }

  refresh() {
    this.api.getSystem().subscribe({
      next: s => this.snap.set(s),
      error: () => {},
    });
  }
}
