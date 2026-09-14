import { Component, OnInit, signal, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ChatService } from '../../services/chat';
import { AmethystApiService, ModelStatus } from '../../services/amethyst-api';

@Component({
  selector: 'app-topbar',
  standalone: true,
  imports: [CommonModule, MatIconModule, MatButtonModule, MatTooltipModule],
  template: `
    <div class="topbar">
      <!-- Sidebar toggle -->
      <button class="icon-btn" matTooltip="Toggle sidebar" (click)="toggleSidebar.emit()">
        <mat-icon>menu</mat-icon>
      </button>

      <div class="divider-v"></div>

      <!-- Session title -->
      <span class="session-title">{{ activeTitle() }}</span>

      <div class="spacer"></div>

      <!-- Model badges -->
      <div class="model-badges">
        @if (status()) {
          <span class="badge coder" [matTooltip]="status()!.coder_model">
            <span class="dot" [class.online]="status()!.online"></span>
            {{ shortName(status()!.coder_model) }}
          </span>
          <span class="badge chat" [matTooltip]="status()!.chat_model">
            <span class="dot" [class.online]="status()!.online"></span>
            {{ shortName(status()!.chat_model) }}
          </span>
        } @else {
          <span class="badge offline">
            <mat-icon style="font-size:14px;height:14px;width:14px">warning</mat-icon>
            Offline
          </span>
        }
      </div>

      <div class="divider-v"></div>

      <!-- Actions -->
      <button class="icon-btn" matTooltip="New chat" (click)="newChat()">
        <mat-icon>add</mat-icon>
      </button>
      <button class="icon-btn" matTooltip="Clear conversation" (click)="clearHistory()">
        <mat-icon>delete_sweep</mat-icon>
      </button>
      <button class="icon-btn" matTooltip="Refresh status" (click)="refreshStatus()">
        <mat-icon>refresh</mat-icon>
      </button>
    </div>
  `,
  styleUrl: './topbar.scss',
})
export class TopbarComponent implements OnInit {
  @Output() toggleSidebar = new EventEmitter<void>();

  status = signal<ModelStatus | null>(null);

  constructor(private chat: ChatService, private api: AmethystApiService) {}

  ngOnInit() { this.refreshStatus(); }

  activeTitle() {
    return this.chat.activeSession()?.title ?? 'Amethyst';
  }

  refreshStatus() {
    this.api.getStatus().subscribe({
      next: s => this.status.set(s),
      error: () => this.status.set(null),
    });
  }

  shortName(model: string) {
    return model?.split(':')[0] ?? '';
  }

  newChat() {
    this.chat.newSession();
  }

  clearHistory() {
    const id = this.chat.activeId();
    if (id) { this.chat.deleteSession(id); this.chat.newSession(); }
  }
}
