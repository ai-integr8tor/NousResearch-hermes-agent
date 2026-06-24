#!/usr/bin/env node
// Patch spectrum-ts' iMessage inbound mapper until upstream preserves mixed
// text + attachment Apple events. The SDK mapper returns only attachment
// content whenever attachments are present, which drops message.content.text
// before Hermes can see it.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const MARKER = "Hermes patch: Preserve mixed text + attachment iMessage payloads";

function scriptDir() {
  return path.dirname(fileURLToPath(import.meta.url));
}

function replaceOnce(source, from, to, label) {
  const count = source.split(from).length - 1;
  if (count !== 1) {
    throw new Error(`expected exactly one ${label} match, found ${count}`);
  }
  return source.replace(from, to);
}

function replaceFirst(source, from, to, label) {
  if (!source.includes(from)) {
    throw new Error(`expected at least one ${label} match, found 0`);
  }
  return source.replace(from, to);
}

function addTextChildSnippetSpaces() {
  return `if (text2) {\n      items.unshift({\n        ...base,\n        id: formatChildId(0, messageGuidStr),\n        content: asText(text2),\n        partIndex: 0,\n        parentId: messageGuidStr\n      });\n    }`;
}

function addTextChildSnippetTabs() {
  return `if (text2) {\n\t\t\titems.unshift({\n\t\t\t\t...base,\n\t\t\t\tid: formatChildId(0, messageGuidStr),\n\t\t\t\tcontent: asText(text2),\n\t\t\t\tpartIndex: 0,\n\t\t\t\tparentId: messageGuidStr\n\t\t\t});\n\t\t}`;
}

function patchRebuildV3(source) {
  source = replaceOnce(
    source,
    `  const attachments = messageAttachments(message);\n  if (attachments.length === 1) {`,
    `  const attachments = messageAttachments(message);\n  const text2 = message.content.text;\n  if (attachments.length === 1) {`,
    "v3 rebuild text capture"
  );
  source = replaceOnce(
    source,
    `    return buildAttachmentMessage(client, base, info, messageGuidStr, 0);`,
    `    const msg2 = await buildAttachmentMessage(\n      client,\n      base,\n      info,\n      text2 ? formatChildId(1, messageGuidStr) : messageGuidStr,\n      text2 ? 1 : 0,\n      text2 ? messageGuidStr : void 0\n    );\n    if (text2) {\n      const textMsg = {\n        ...base,\n        id: formatChildId(0, messageGuidStr),\n        content: asText(text2),\n        partIndex: 0,\n        parentId: messageGuidStr\n      };\n      return {\n        ...base,\n        id: messageGuidStr,\n        content: asProviderGroup([textMsg, msg2])\n      };\n    }\n    return msg2;`,
    "v3 rebuild single attachment"
  );
  source = replaceFirst(
    source,
    `          formatChildId(i, messageGuidStr),\n          i,\n          messageGuidStr`,
    `          formatChildId(text2 ? i + 1 : i, messageGuidStr),\n          text2 ? i + 1 : i,\n          messageGuidStr`,
    "v3 rebuild multi attachment child index"
  );
  source = replaceFirst(
    source,
    `    return {\n      ...base,\n      id: messageGuidStr,\n      content: asProviderGroup(items)\n    };\n  }\n  if (getBalloonBundleId(message) === URL_BALLOON_BUNDLE_ID) {`,
    `    ${addTextChildSnippetSpaces()}\n    return {\n      ...base,\n      id: messageGuidStr,\n      content: asProviderGroup(items)\n    };\n  }\n  if (getBalloonBundleId(message) === URL_BALLOON_BUNDLE_ID) {`,
    "v3 rebuild multi attachment text child"
  );
  source = replaceFirst(
    source,
    `  const text2 = message.content.text;\n  return {\n    ...base,`,
    `  return {\n    ...base,`,
    "v3 rebuild duplicate text declaration"
  );
  return source;
}

function patchInboundV3(source) {
  source = replaceOnce(
    source,
    `  const attachments = messageAttachments(event.message);\n  if (attachments.length === 1) {`,
    `  const attachments = messageAttachments(event.message);\n  const text2 = event.message.content.text;\n  if (attachments.length === 1) {`,
    "v3 inbound text capture"
  );
  source = replaceOnce(
    source,
    `      messageGuidStr,\n      0\n    );\n    cacheMessage(cache, msg2);\n    return [msg2];`,
    `      text2 ? formatChildId(1, messageGuidStr) : messageGuidStr,\n      text2 ? 1 : 0,\n      text2 ? messageGuidStr : void 0\n    );\n    if (text2) {\n      const textMsg = {\n        ...base,\n        id: formatChildId(0, messageGuidStr),\n        content: asText(text2),\n        partIndex: 0,\n        parentId: messageGuidStr\n      };\n      const parent = {\n        ...base,\n        id: messageGuidStr,\n        content: asProviderGroup([textMsg, msg2])\n      };\n      cacheMessage(cache, parent);\n      return [parent];\n    }\n    cacheMessage(cache, msg2);\n    return [msg2];`,
    "v3 inbound single attachment"
  );
  source = replaceOnce(
    source,
    `          formatChildId(i, messageGuidStr),\n          i,\n          messageGuidStr`,
    `          formatChildId(text2 ? i + 1 : i, messageGuidStr),\n          text2 ? i + 1 : i,\n          messageGuidStr`,
    "v3 inbound multi attachment child index"
  );
  source = replaceOnce(
    source,
    `    const parent = {\n      ...base,\n      id: messageGuidStr,\n      content: asProviderGroup(items)\n    };`,
    `    ${addTextChildSnippetSpaces()}\n    const parent = {\n      ...base,\n      id: messageGuidStr,\n      content: asProviderGroup(items)\n    };`,
    "v3 inbound multi attachment text child"
  );
  source = replaceOnce(
    source,
    `  const text2 = event.message.content.text;\n  const msg = {`,
    `  const msg = {`,
    "v3 inbound duplicate text declaration"
  );
  return source;
}

function patchV3(source) {
  let patched = patchRebuildV3(source);
  patched = patchInboundV3(patched);
  return patched;
}

function patchRebuildV5(source) {
  source = replaceOnce(
    source,
    `\tconst attachments = messageAttachments(message);\n\tif (attachments.length === 1) {`,
    `\tconst attachments = messageAttachments(message);\n\tconst text2 = message.content.text;\n\tif (attachments.length === 1) {`,
    "v5 rebuild text capture"
  );
  source = replaceOnce(
    source,
    `\t\treturn buildAttachmentMessage(client, base, info, messageGuidStr, 0);`,
    `\t\tconst msg2 = await buildAttachmentMessage(\n\t\t\tclient,\n\t\t\tbase,\n\t\t\tinfo,\n\t\t\ttext2 ? formatChildId(1, messageGuidStr) : messageGuidStr,\n\t\t\ttext2 ? 1 : 0,\n\t\t\ttext2 ? messageGuidStr : void 0\n\t\t);\n\t\tif (text2) {\n\t\t\tconst textMsg = {\n\t\t\t\t...base,\n\t\t\t\tid: formatChildId(0, messageGuidStr),\n\t\t\t\tcontent: asText(text2),\n\t\t\t\tpartIndex: 0,\n\t\t\t\tparentId: messageGuidStr\n\t\t\t};\n\t\t\treturn {\n\t\t\t\t...base,\n\t\t\t\tid: messageGuidStr,\n\t\t\t\tcontent: asProviderGroup([textMsg, msg2])\n\t\t\t};\n\t\t}\n\t\treturn msg2;`,
    "v5 rebuild single attachment"
  );
  source = replaceFirst(
    source,
    `\t\t\titems.push(await buildAttachmentMessage(client, base, info, formatChildId(i, messageGuidStr), i, messageGuidStr));`,
    `\t\t\titems.push(await buildAttachmentMessage(client, base, info, formatChildId(text2 ? i + 1 : i, messageGuidStr), text2 ? i + 1 : i, messageGuidStr));`,
    "v5 rebuild multi attachment child index"
  );
  source = replaceFirst(
    source,
    `\t\treturn {\n\t\t\t...base,\n\t\t\tid: messageGuidStr,\n\t\t\tcontent: asProviderGroup(items)\n\t\t};\n\t}\n\tif (getBalloonBundleId(message) === URL_BALLOON_BUNDLE_ID)`,
    `\t\t${addTextChildSnippetTabs()}\n\t\treturn {\n\t\t\t...base,\n\t\t\tid: messageGuidStr,\n\t\t\tcontent: asProviderGroup(items)\n\t\t};\n\t}\n\tif (getBalloonBundleId(message) === URL_BALLOON_BUNDLE_ID)`,
    "v5 rebuild multi attachment text child"
  );
  source = replaceOnce(
    source,
    `\tconst text = message.content.text;\n\treturn {`,
    `\treturn {`,
    "v5 rebuild duplicate text declaration"
  );
  source = replaceOnce(
    source,
    `\t\tcontent: text ? asText(text) : asCustom(message)`,
    `\t\tcontent: text2 ? asText(text2) : asCustom(message)`,
    "v5 rebuild final text reference"
  );
  return source;
}

function patchInboundV5(source) {
  source = replaceOnce(
    source,
    `\tconst attachments = messageAttachments(event.message);\n\tif (attachments.length === 1) {`,
    `\tconst attachments = messageAttachments(event.message);\n\tconst text2 = event.message.content.text;\n\tif (attachments.length === 1) {`,
    "v5 inbound text capture"
  );
  source = replaceOnce(
    source,
    `\t\tconst msg = await buildAttachmentMessage(client, base, info, messageGuidStr, 0);\n\t\tcacheMessage(cache, msg);\n\t\treturn [msg];`,
    `\t\tconst msg = await buildAttachmentMessage(\n\t\t\tclient,\n\t\t\tbase,\n\t\t\tinfo,\n\t\t\ttext2 ? formatChildId(1, messageGuidStr) : messageGuidStr,\n\t\t\ttext2 ? 1 : 0,\n\t\t\ttext2 ? messageGuidStr : void 0\n\t\t);\n\t\tif (text2) {\n\t\t\tconst textMsg = {\n\t\t\t\t...base,\n\t\t\t\tid: formatChildId(0, messageGuidStr),\n\t\t\t\tcontent: asText(text2),\n\t\t\t\tpartIndex: 0,\n\t\t\t\tparentId: messageGuidStr\n\t\t\t};\n\t\t\tconst parent = {\n\t\t\t\t...base,\n\t\t\t\tid: messageGuidStr,\n\t\t\t\tcontent: asProviderGroup([textMsg, msg])\n\t\t\t};\n\t\t\tcacheMessage(cache, parent);\n\t\t\treturn [parent];\n\t\t}\n\t\tcacheMessage(cache, msg);\n\t\treturn [msg];`,
    "v5 inbound single attachment"
  );
  source = replaceOnce(
    source,
    `\t\t\titems.push(await buildAttachmentMessage(client, base, info, formatChildId(i, messageGuidStr), i, messageGuidStr));`,
    `\t\t\titems.push(await buildAttachmentMessage(client, base, info, formatChildId(text2 ? i + 1 : i, messageGuidStr), text2 ? i + 1 : i, messageGuidStr));`,
    "v5 inbound multi attachment child index"
  );
  source = replaceOnce(
    source,
    `\t\tconst parent = {\n\t\t\t...base,\n\t\t\tid: messageGuidStr,\n\t\t\tcontent: asProviderGroup(items)\n\t\t};`,
    `\t\t${addTextChildSnippetTabs()}\n\t\tconst parent = {\n\t\t\t...base,\n\t\t\tid: messageGuidStr,\n\t\t\tcontent: asProviderGroup(items)\n\t\t};`,
    "v5 inbound multi attachment text child"
  );
  source = replaceOnce(
    source,
    `\tconst text = event.message.content.text;\n\tconst msg = {`,
    `\tconst msg = {`,
    "v5 inbound duplicate text declaration"
  );
  source = replaceOnce(
    source,
    `\t\tcontent: text ? asText(text) : asCustom(event.message)`,
    `\t\tcontent: text2 ? asText(text2) : asCustom(event.message)`,
    "v5 inbound final text reference"
  );
  return source;
}

function patchV5(source) {
  let patched = patchRebuildV5(source);
  patched = patchInboundV5(patched);
  return patched;
}

function candidateDistDirs(root) {
  return [
    path.join(root, "node_modules", "@spectrum-ts", "imessage", "dist"),
    path.join(root, "node_modules", "spectrum-ts", "dist"),
  ];
}

export function patchSpectrumTs(root = scriptDir()) {
  for (const dist of candidateDistDirs(root)) {
    if (!fs.existsSync(dist)) continue;
    const files = fs.readdirSync(dist)
      .filter((name) => name.endsWith(".js"))
      .map((name) => path.join(dist, name));

    for (const file of files) {
      const raw = fs.readFileSync(file, "utf8");
      if (raw.includes(MARKER)) {
        return { patched: false, file, reason: "already patched" };
      }
      // Normalize to LF for matching so the patch works regardless of the
      // checkout's line-ending style (Windows git autocrlf produces CRLF,
      // which would otherwise defeat the \n-based search strings). The
      // original EOL style is restored on write.
      const CR = String.fromCharCode(13);
      const CRLF = CR + "\n";
      const usedCRLF = raw.includes(CRLF);
      const original = usedCRLF ? raw.split(CRLF).join("\n") : raw;
      let patched = null;
      try {
        if (original.includes("const toInboundMessages = async") &&
            original.includes("const rebuildFromAppleMessage = async")) {
          patched = patchV5(original);
        } else if (original.includes("var toInboundMessages = async") &&
                   original.includes("var rebuildFromAppleMessage = async")) {
          patched = patchV3(original);
        }
      } catch (err) {
        throw new Error(`${path.basename(file)} matched iMessage inbound chunk but patch failed: ${err?.message || err}`);
      }
      if (!patched) continue;
      patched = `// ${MARKER}\n${patched}`;
      if (usedCRLF) {
        patched = patched.split("\n").join(CRLF);
      }
      fs.writeFileSync(file, patched, "utf8");
      return { patched: true, file };
    }
  }
  throw new Error("could not find spectrum-ts iMessage inbound chunk to patch");
}

const _invokedDirectly =
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href;
if (_invokedDirectly) {
  try {
    const root = process.argv[2] ? path.resolve(process.argv[2]) : scriptDir();
    const result = patchSpectrumTs(root);
    const action = result.patched ? "patched" : "ok";
    console.error(`photon-sidecar: spectrum mixed attachment patch ${action}: ${result.file}`);
  } catch (err) {
    console.error(`photon-sidecar: spectrum mixed attachment patch failed: ${err?.stack || err}`);
    process.exit(1);
  }
}
