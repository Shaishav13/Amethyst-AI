import {
  Component, ElementRef, ViewChild,
  AfterViewChecked, signal, HostListener
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MessageBubbleComponent } from '../message-bubble/message-bubble';
import { InputBarComponent } from '../input-bar/input-bar';
import { ChatService } from '../../services/chat';

@Component({
  selector: 'app-chat-window',
  standalone: true,
  imports: [CommonModule, MatIconModule, MatTooltipModule, MessageBubbleComponent, InputBarComponent],
  template: `
    <div class="chat-window">
      <div class="messages" #messagesContainer (scroll)="onScroll()">

        @if (chat.activeSession(); as session) {
          @if (session.messages.length === 0) {
            <div class="empty-state">
              <div class="empty-glyph">✦</div>
              <h2>Amethyst</h2>
              <p>Fully local AI — no internet required</p>
              <div class="hints">
                <span class="hint"><mat-icon>keyboard</mat-icon> Enter to send</span>
                <span class="hint"><mat-icon>code</mat-icon> Ctrl+Shift+A from editor</span>
                <span class="hint"><mat-icon>auto_awesome</mat-icon> Auto-routes to best model</span>
              </div>
            </div>
          } @else {
            @for (msg of session.messages; track msg.id) {
              <app-message-bubble [msg]="msg" />
            }
            <!-- Bottom anchor -->
            <div #bottomAnchor style="height:1px"></div>
          }
        }
      </div>

      <!-- Scroll to bottom FAB -->
      @if (showScrollBtn()) {
        <button class="scroll-fab" (click)="scrollToBottom()" matTooltip="Scroll to bottom">
          <mat-icon>keyboard_arrow_down</mat-icon>
        </button>
      }

      <app-input-bar />
    </div>
  `,
  styleUrl: './chat-window.scss',
})
export class ChatWindowComponent implements AfterViewChecked {
  @ViewChild('messagesContainer') messagesContainer!: ElementRef<HTMLDivElement>;
  @ViewChild('bottomAnchor')      bottomAnchor!: ElementRef<HTMLDivElement>;

  showScrollBtn = signal(false);
  private _lastScrollKey = '';
  private _userScrolledUp = false;

  constructor(public chat: ChatService) {}

  onScroll() {
    const el = this.messagesContainer?.nativeElement;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    this._userScrolledUp = !atBottom;
    this.showScrollBtn.set(!atBottom);
  }

  ngAfterViewChecked() {
    const session = this.chat.activeSession();
    if (!session || session.messages.length === 0) return;

    const msgs  = session.messages;
    const last  = msgs[msgs.length - 1];
    const key   = `${session.id}-${msgs.length}-${last.content.length}`;

    if (key !== this._lastScrollKey) {
      this._lastScrollKey = key;
      // Auto-scroll only if user hasn't scrolled up manually
      if (!this._userScrolledUp) {
        this.scrollToBottom();
      }
    }
  }

  scrollToBottom() {
    try {
      const el = this.messagesContainer?.nativeElement;
      if (el) {
        el.scrollTop = el.scrollHeight;
        this._userScrolledUp = false;
        this.showScrollBtn.set(false);
      }
    } catch {}
  }
}
