import { api } from "@/lib/api";

// Clipboard image MIME → file extension. Mirrors the set the TUI's /image
// attach path and the gateway's image sniffer accept.
const IMAGE_MIME_EXT: Record<string, string> = {
  "image/png": "png",
  "image/jpeg": "jpg",
  "image/gif": "gif",
  "image/webp": "webp",
  "image/bmp": "bmp",
};

// Upload subdirectory under the dashboard managed-files root (the gateway's
// HERMES_HOME, e.g. /opt/data). Kept shallow + predictable so users can find
// and prune pasted images.
const PASTE_UPLOAD_DIR = "uploads/paste";

// Anthropic caps a single vision image at ~25 MB; reject earlier client-side
// with a clear message rather than round-tripping a doomed upload.
const MAX_IMAGE_BYTES = 25 * 1024 * 1024;

export interface ImagePasteResult {
  /** Absolute container path the gateway wrote the image to. */
  path: string;
  /** Byte size of the uploaded image. */
  bytes: number;
  /** File extension chosen for the upload (no dot). */
  ext: string;
}

/** Pull the first image blob out of a DataTransfer, or null if none present. */
export function firstImageFromClipboard(
  data: DataTransfer | null,
): File | null {
  if (!data) return null;
  const items = data.items;
  if (items) {
    for (let i = 0; i < items.length; i++) {
      const it = items[i];
      if (it.kind === "file" && it.type.startsWith("image/")) {
        const f = it.getAsFile();
        if (f) return f;
      }
    }
  }
  // Safari/Firefox sometimes expose files but not items for pasted images.
  const files = data.files;
  if (files) {
    for (let i = 0; i < files.length; i++) {
      if (files[i].type.startsWith("image/")) return files[i];
    }
  }
  return null;
}

function extForBlob(blob: Blob): string {
  return IMAGE_MIME_EXT[blob.type] || "png";
}

function timestampName(ext: string): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  const stamp =
    `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}` +
    `_${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}` +
    `_${p(d.getMilliseconds() % 1000)}`;
  return `paste_${stamp}.${ext}`;
}

/**
 * Upload a pasted image blob to the gateway's managed-files root and return
 * the absolute container path.
 *
 * The dashboard Chat tab is an xterm mirror of a TUI running INSIDE the
 * gateway (often a remote Docker container). The container has no access to
 * the browser's clipboard, so the server-side `clipboard.paste` path can
 * never see a pasted image. Instead we upload the bytes the browser already
 * holds, then hand the resulting container path to the TUI's `/image`
 * command (see attachPastedImage in ChatPage).
 */
export async function uploadPastedImage(blob: Blob): Promise<ImagePasteResult> {
  if (blob.size === 0) throw new Error("clipboard image is empty");
  if (blob.size > MAX_IMAGE_BYTES) {
    const mb = Math.round(MAX_IMAGE_BYTES / (1024 * 1024));
    throw new Error(`image too large (max ${mb} MB)`);
  }
  const ext = extForBlob(blob);
  const name = timestampName(ext);
  const relPath = `${PASTE_UPLOAD_DIR}/${name}`;
  const file =
    blob instanceof File
      ? new File([blob], name, { type: blob.type })
      : new File([blob], name, { type: blob.type });
  const res = await api.uploadFile(relPath, file, true);
  // The server resolves + returns the absolute container path; prefer the
  // entry path, fall back to the top-level path field.
  const absPath = res.entry?.path || res.path;
  if (!absPath) throw new Error("upload succeeded but no path was returned");
  return { path: absPath, bytes: blob.size, ext };
}
