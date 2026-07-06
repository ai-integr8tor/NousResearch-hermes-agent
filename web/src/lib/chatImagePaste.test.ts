import { describe, expect, it } from "vitest";

import { firstImageFromClipboard } from "./chatImagePaste";

// Minimal DataTransfer stand-ins. jsdom's DataTransfer doesn't let us seed
// items/files, so we hand-roll the shape firstImageFromClipboard reads.
function makeItem(kind: string, type: string, file: File | null) {
  return { kind, type, getAsFile: () => file } as unknown as DataTransferItem;
}

function makeData(opts: {
  items?: DataTransferItem[];
  files?: File[];
}): DataTransfer {
  const items = opts.items ?? [];
  const files = opts.files ?? [];
  const itemList: Record<string | number, unknown> = { length: items.length };
  items.forEach((it, i) => {
    itemList[i] = it;
  });
  const fileList: Record<string | number, unknown> = { length: files.length };
  files.forEach((f, i) => {
    fileList[i] = f;
  });
  return {
    items: itemList,
    files: fileList,
  } as unknown as DataTransfer;
}

const png = new File([new Uint8Array([1, 2, 3])], "x.png", {
  type: "image/png",
});

describe("firstImageFromClipboard", () => {
  it("returns null for null clipboard data", () => {
    expect(firstImageFromClipboard(null)).toBeNull();
  });

  it("finds an image via items[].getAsFile()", () => {
    const data = makeData({ items: [makeItem("file", "image/png", png)] });
    expect(firstImageFromClipboard(data)).toBe(png);
  });

  it("ignores non-file and non-image items", () => {
    const data = makeData({
      items: [
        makeItem("string", "text/plain", null),
        makeItem("file", "application/pdf", new File([], "a.pdf")),
      ],
    });
    expect(firstImageFromClipboard(data)).toBeNull();
  });

  it("falls back to files[] when items are absent (Safari/Firefox)", () => {
    const data = makeData({ files: [png] });
    expect(firstImageFromClipboard(data)).toBe(png);
  });

  it("returns null when nothing image-like is present", () => {
    const data = makeData({
      files: [new File([], "notes.txt", { type: "text/plain" })],
    });
    expect(firstImageFromClipboard(data)).toBeNull();
  });
});
