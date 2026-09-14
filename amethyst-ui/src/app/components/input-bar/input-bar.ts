import { Component, ViewChild, ElementRef, signal, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { TextFieldModule } from '@angular/cdk/text-field';
import { ChatService } from '../../services/chat';
import { AmethystApiService } from '../../services/amethyst-api';

type ModelMode = 'auto' | 'coder' | 'chat';

@Component({
  selector: 'app-input-bar',
  standalone: true,
  imports: [
    CommonModule, FormsModule, MatIconModule, MatButtonModule,
    MatTooltipModule, MatFormFieldModule, MatInputModule,
    TextFieldModule, MatSnackBarModule,
  ],
  templateUrl: './input-bar.html',
  styleUrl: './input-bar.scss',
})
export class InputBarComponent {
  @ViewChild('textarea') textarea!: ElementRef<HTMLTextAreaElement>;
  @ViewChild('fileInput') fileInput!: ElementRef<HTMLInputElement>;
  @ViewChild('imageInput') imageInput!: ElementRef<HTMLInputElement>;

  text          = '';
  modelMode     = signal<ModelMode>('auto');
  attachedFiles = signal<File[]>([]);
  attachedImageName = signal<string | null>(null);
  attachedImageB64: string | null = null;
  uploading     = signal(false);

  constructor(
    public chat: ChatService,
    private api: AmethystApiService,
    private snackBar: MatSnackBar,
  ) {
    effect(() => {
      // Auto-focus the input when streaming finishes
      if (!this.chat.streaming()) {
        setTimeout(() => {
          this.textarea?.nativeElement?.focus();
        }, 100);
      }
    });
  }

  canSend() { return (this.text.trim().length > 0 || !!this.attachedImageB64) && !this.chat.streaming(); }

  charCount() { return this.text.length; }

  setMode(m: ModelMode) { this.modelMode.set(m); }

  openFileDialog() {
    this.fileInput.nativeElement.click();
  }

  openImageDialog() {
    this.imageInput.nativeElement.click();
  }

  onImageSelected(event: Event) {
    const input = event.target as HTMLInputElement;
    if (!input.files || input.files.length === 0) return;
    const file = input.files[0];

    const reader = new FileReader();
    reader.onload = () => {
      this.attachedImageB64 = (reader.result as string).split(',')[1];
      this.attachedImageName.set(file.name);
    };
    reader.readAsDataURL(file);
    if (this.imageInput) this.imageInput.nativeElement.value = '';
  }

  onFileSelected(event: Event) {
    const input = event.target as HTMLInputElement;
    if (!input.files || input.files.length === 0) return;

    const file = input.files[0];
    const maxSize = 50 * 1024 * 1024; // 50MB

    if (file.size > maxSize) {
      this.snackBar.open('File too large. Max size: 50MB', 'OK', { duration: 3000 });
      return;
    }

    // Check file type
    const validExts = ['.pdf', '.txt', '.md', '.py', '.js', '.ts', '.json', '.csv', '.log', '.html', '.css'];
    const ext = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!validExts.includes(ext)) {
      this.snackBar.open(`Unsupported file type: ${ext}. Use PDF, text, or code files.`, 'OK', { duration: 4000 });
      return;
    }

    this.attachedFiles.set([file]);
    this.uploadToRag(file);
  }

  uploadToRag(file: File) {
    this.uploading.set(true);
    const sessionId = this.chat.activeId() || undefined;
    this.api.uploadDocument(file, sessionId).subscribe({
      next: (res) => {
        this.uploading.set(false);
        this.snackBar.open(`✓ ${file.name} uploaded (${res.chunks_added} chunks)`, 'OK', { duration: 3000 });
        
        // Push visual indicator to the chat
        this.chat.addAttachmentMessage(file.name);

        this.attachedFiles.set([]);
        // Reset file input
        if (this.fileInput) this.fileInput.nativeElement.value = '';
      },
      error: (err) => {
        this.uploading.set(false);
        this.snackBar.open(`✗ Upload failed: ${err.message}`, 'OK', { duration: 4000 });
        this.attachedFiles.set([]);
        if (this.fileInput) this.fileInput.nativeElement.value = '';
      },
    });
  }

  removeAttachment() {
    this.attachedFiles.set([]);
    if (this.fileInput) this.fileInput.nativeElement.value = '';
  }

  removeImage() {
    this.attachedImageName.set(null);
    this.attachedImageB64 = null;
    if (this.imageInput) this.imageInput.nativeElement.value = '';
  }

  send() {
    if (!this.canSend()) return;
    const msg = this.text.trim();
    this.text = '';
    const mode = this.modelMode();
    const imageToSend = this.attachedImageB64;
    
    // Clear image state after sending
    this.removeImage();
    
    this.chat.sendMessage(msg, mode === 'auto' ? undefined : mode, undefined, imageToSend || undefined);
  }

  handleKey(event: KeyboardEvent) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.send();
    }
  }

  stopGeneration() {
    this.chat.stopGeneration();
  }
}
