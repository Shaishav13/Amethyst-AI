import { Component, OnInit, signal } from '@angular/core';
import { SidebarComponent } from './components/sidebar/sidebar';
import { ChatWindowComponent } from './components/chat-window/chat-window';
import { TopbarComponent } from './components/topbar/topbar';
import { ChatService } from './services/chat';
import { AmethystApiService } from './services/amethyst-api';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [SidebarComponent, ChatWindowComponent, TopbarComponent],
  template: `
    <div class="app-shell" [class.sidebar-collapsed]="sidebarCollapsed()">
      <app-sidebar [collapsed]="sidebarCollapsed()" />
      <div class="main-area">
        <app-topbar (toggleSidebar)="sidebarCollapsed.set(!sidebarCollapsed())" />
        <app-chat-window />
      </div>
    </div>
  `,
  styles: [`
    .app-shell {
      display: flex;
      height: 100vh;
      overflow: hidden;
      background: var(--bg-deep);
    }
    .main-area {
      flex: 1;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      min-width: 0;
    }
  `],
})
export class App implements OnInit {
  sidebarCollapsed = signal(false);

  constructor(private chat: ChatService, private api: AmethystApiService) {}

  ngOnInit() {
    this.chat.newSession();
    this.api.getStatus().subscribe(s => {
      this.chat.coderModel.set(s.coder_model ?? '');
      this.chat.chatModel.set(s.chat_model ?? '');
    });
  }
}
