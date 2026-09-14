import {
  Component, Input, OnChanges, SimpleChanges,
  ChangeDetectionStrategy, ChangeDetectorRef
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { marked } from 'marked';
import hljs from 'highlight.js';
import { ChatMessage } from '../../services/chat';

// ── Marked setup ──────────────────────────────────────────────────────────────
marked.setOptions({ gfm: true, breaks: true });

const renderer = new marked.Renderer();
renderer.code = ({ text, lang }: { text: string; lang?: string }) => {
  const language = lang && hljs.getLanguage(lang) ? lang : 'plaintext';
  const highlighted = hljs.highlight(text, { language }).value;
  return `<pre><div class="code-header"><span class="lang-label">${language.toUpperCase()}</span>
<button class="copy-btn" data-code="${encodeURIComponent(text)}">
  <span class="copy-icon">content_copy</span> Copy
</button></div><code class="hljs language-${language}">${highlighted}</code></pre>`;
};
marked.use({ renderer });

@Component({
  selector: 'app-message-bubble',
  standalone: true,
  imports: [CommonModule, MatIconModule, MatTooltipModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="bubble-row" [class.user-row]="isUser" [class.assistant-row]="!isUser">

      <!-- Avatar -->
      <div class="avatar" [class.user-avatar]="isUser" [class.ai-avatar]="!isUser">
        @if (isUser) { 👤 } @else { {{ modelIcon() }} }
      </div>

      <div class="bubble-content">
        <!-- Header -->
        <div class="bubble-meta">
          <span class="sender" [style.color]="nameColor()">{{ displayName() }}</span>
          <span class="time">{{ formatTime(msg.timestamp) }}</span>
          @if (!isUser && msg.model) {
            <span class="model-pill">{{ shortModel(msg.model) }}</span>
          }
          <!-- Copy full message -->
          @if (!isUser && msg.content && !msg.streaming) {
            <button class="meta-btn" (click)="copyMessage()" [matTooltip]="copied ? 'Copied!' : 'Copy response'">
              <mat-icon>{{ copied ? 'check' : 'content_copy' }}</mat-icon>
            </button>
          }
        </div>

        <!-- Body -->
        <div class="bubble-body" [class.user-bubble]="isUser" [class.ai-bubble]="!isUser">
          @if (isUser) {
            <span class="user-text">{{ msg.content }}</span>
            @if (msg.image_b64) {
              <img [src]="'data:image/jpeg;base64,' + msg.image_b64" class="msg-image" alt="Attached image" />
            }
          } @else if (msg.streaming && !msg.content) {
            <div class="typing">
              <span></span><span></span><span></span>
            </div>
          } @else {
            <div class="md-content"
                 [innerHTML]="rendered"
                 (click)="onBodyClick($event)"></div>
            @if (msg.streaming) {
              <span class="cursor">▌</span>
            }
          }
        </div>
      </div>
    </div>
  `,
  styleUrl: './message-bubble.scss',
})
export class MessageBubbleComponent implements OnChanges {
  @Input() msg!: ChatMessage;

  rendered: SafeHtml = '';
  copied = false;
  private _lastContent = '';

  get isUser() { return this.msg.role === 'user'; }

  constructor(private sanitizer: DomSanitizer, private cdr: ChangeDetectorRef) {}

  ngOnChanges(c: SimpleChanges) {
    if (c['msg'] && !this.isUser && this.msg.content !== this._lastContent) {
      this._lastContent = this.msg.content;

      let processed = this.msg.content || '';
      processed = this.stripLatex(processed);

      const html = marked.parse(processed) as string;
      this.rendered = this.sanitizer.bypassSecurityTrustHtml(html);
      this.cdr.markForCheck();
    }
  }

  /**
   * Recursively-safe LaTeX stripper.
   * Handles nested braces like \frac{\sqrt{x}}{y+1} correctly.
   */
  private stripLatex(text: string): string {
    // Strip display-mode LaTeX delimiters (only when they appear on their own lines)
    text = text.replace(/^\s*\\\[\s*$/gm, '');
    text = text.replace(/^\s*\\\]\s*$/gm, '');
    // Strip inline LaTeX delimiters
    text = text.replace(/\\\(/g, '').replace(/\\\)/g, '');

    // \frac{A}{B} → (A) / (B) — supports nested braces
    text = text.replace(/\\frac\s*(\{(?:[^{}]|\{[^{}]*\})*\})\s*(\{(?:[^{}]|\{[^{}]*\})*\})/g,
      (_m, num, den) => `(${num.slice(1, -1)}) / (${den.slice(1, -1)})`);

    // \sqrt{X} → sqrt(X)
    text = text.replace(/\\sqrt\s*(\{(?:[^{}]|\{[^{}]*\})*\})/g,
      (_m, inner) => `sqrt(${inner.slice(1, -1)})`);

    // \text{X} → X
    text = text.replace(/\\text\s*(\{(?:[^{}]|\{[^{}]*\})*\})/g,
      (_m, inner) => inner.slice(1, -1));

    // Common LaTeX symbols → plain text equivalents
    const symbols: [RegExp, string][] = [
      [/\\times/g, '×'],
      [/\\cdot/g, '·'],
      [/\\div/g, '÷'],
      [/\\pm/g, '±'],
      [/\\leq/g, '≤'],
      [/\\geq/g, '≥'],
      [/\\neq/g, '≠'],
      [/\\approx/g, '≈'],
      [/\\infty/g, '∞'],
      [/\\pi/g, 'π'],
      [/\\alpha/g, 'α'],
      [/\\beta/g, 'β'],
      [/\\sum/g, 'Σ'],
      [/\\int/g, '∫'],
      [/\\implies/g, '⟹'],
      [/\\rightarrow/g, '→'],
      [/\\leftarrow/g, '←'],
    ];
    for (const [pattern, replacement] of symbols) {
      text = text.replace(pattern, replacement);
    }

    return text;
  }

  modelIcon() {
    const m = this.msg.model ?? '';
    return m.includes('coder') ? '⚡' : '✦';
  }

  displayName() {
    if (this.isUser) return 'You';
    return (this.msg.model ?? '').includes('coder') ? 'Amethyst Coder' : 'Amethyst';
  }

  nameColor() {
    if (this.isUser) return 'var(--pink)';
    return (this.msg.model ?? '').includes('coder') ? 'var(--cyan)' : 'var(--accent-glow)';
  }

  shortModel(model: string) {
    return model.split(':')[0];
  }

  formatTime(ts: number) {
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  copyMessage() {
    navigator.clipboard.writeText(this.msg.content).then(() => {
      this.copied = true;
      this.cdr.markForCheck();
      setTimeout(() => { this.copied = false; this.cdr.markForCheck(); }, 2000);
    });
  }

  onBodyClick(event: MouseEvent) {
    const btn = (event.target as HTMLElement).closest('.copy-btn') as HTMLButtonElement | null;
    if (!btn) return;
    const code = decodeURIComponent(btn.dataset['code'] ?? '');
    navigator.clipboard.writeText(code).then(() => {
      const label = btn.querySelector('.copy-icon');
      const orig = btn.innerHTML;
      btn.innerHTML = '<span class="copy-icon">check</span> Copied';
      btn.classList.add('copied');
      setTimeout(() => { btn.innerHTML = orig; btn.classList.remove('copied'); }, 1800);
    });
  }
}
