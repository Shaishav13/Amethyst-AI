import { Component, OnInit, Input, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatDividerModule } from '@angular/material/divider';
import { ChatService, ChatSession } from '../../services/chat';
import { AmethystApiService, Session } from '../../services/amethyst-api';
import { SystemStatsComponent } from '../system-stats/system-stats';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [
    CommonModule, MatIconModule, MatButtonModule,
    MatTooltipModule, MatDividerModule, SystemStatsComponent,
  ],
  templateUrl: './sidebar.html',
  styleUrl: './sidebar.scss',
})
export class SidebarComponent implements OnInit {
  @Input() collapsed = false;

  storedSessions  = signal<Session[]>([]);
  profile         = signal<any>(null);
  memoryExpanded  = signal(false);
  historyExpanded = signal(true);

  constructor(public chat: ChatService, private api: AmethystApiService) {}

  ngOnInit() {
    this.loadSessions();
    this.loadProfile();
  }

  loadSessions() {
    this.api.getSessions().subscribe({ next: r => this.storedSessions.set(r.sessions), error: () => {} });
  }

  loadProfile() {
    this.api.getProfile().subscribe({ next: p => this.profile.set(p), error: () => {} });
  }

  newChat() { this.chat.newSession(); }

  openSession(s: Session) {
    this.api.getSession(s.id).subscribe(detail => {
      const session: ChatSession = {
        id: detail.id,
        title: detail.title,
        messages: detail.messages.map(m => ({
          id: crypto.randomUUID(),
          role: m.role as 'user' | 'assistant',
          content: m.content,
          model: m.model,
          timestamp: m.timestamp * 1000,
        })),
      };
      this.chat.loadSession(session);
    });
  }

  deleteSession(s: Session, event: MouseEvent) {
    event.stopPropagation();
    this.api.deleteSession(s.id).subscribe(() => {
      this.storedSessions.update(l => l.filter(x => x.id !== s.id));
      this.chat.deleteSession(s.id);
    });
  }

  clearAll() {
    this.api.clearSessions().subscribe(() => {
      this.chat.clearAll();
      this.storedSessions.set([]);
      this.chat.newSession();
    });
  }

  isActive(id: string) { return this.chat.activeId() === id; }

  formatDate(ts: number) {
    const d = new Date(ts * 1000);
    const now = new Date();
    return d.toDateString() === now.toDateString()
      ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      : d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  }

  hasMemory() {
    const p = this.profile();
    return p && (p.facts?.length || p.preferences?.length || p.projects?.length);
  }
}
