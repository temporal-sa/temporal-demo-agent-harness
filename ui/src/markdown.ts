/**
 * Just enough Markdown for Ziggy's replies: headings, lists, rules, and bold, italic, and
 * code spans. It returns plain data for the template to render, never HTML, so nothing a
 * model writes can become markup on the page.
 */

export type Inline = { text: string; style: "plain" | "bold" | "italic" | "code" };
export type Block =
  | { kind: "heading"; level: number; text: Inline[] }
  | { kind: "list"; ordered: boolean; items: Inline[][] }
  | { kind: "rule" }
  | { kind: "code"; language: string; text: string }
  | { kind: "paragraph"; lines: Inline[][] };

// Underscores only emphasize at word edges, so snake_case names like trip_id stay as written.
const INLINE = /(\*\*[^*]+\*\*|(?<!\w)__[^_]+__(?!\w)|`[^`]+`|\*[^*\s][^*]*\*|(?<!\w)_[^_\s][^_]*_(?!\w))/g;

export function inline(text: string): Inline[] {
  return text
    .split(INLINE)
    .filter((piece) => piece !== "")
    .map((piece): Inline => {
      if (/^(\*\*|__).+\1$/.test(piece)) return { text: piece.slice(2, -2), style: "bold" };
      if (/^`.+`$/.test(piece)) return { text: piece.slice(1, -1), style: "code" };
      if (/^([*_]).+\1$/.test(piece)) return { text: piece.slice(1, -1), style: "italic" };
      return { text: piece, style: "plain" };
    });
}

export function markdown(source: string): Block[] {
  const blocks: Block[] = [];
  let fence: { language: string; lines: string[] } | null = null;
  for (const line of source.split("\n")) {
    // A fenced block keeps its lines verbatim until the closing fence. One that never closes
    // (a reply still streaming) shows what has arrived so far.
    const fenceMark = /^\s*```\s*([\w+-]*)\s*$/.exec(line);
    if (fence) {
      if (fenceMark && !fenceMark[1]) {
        blocks.push({ kind: "code", language: fence.language, text: fence.lines.join("\n") });
        fence = null;
      } else {
        fence.lines.push(line);
      }
      continue;
    }
    if (fenceMark) {
      fence = { language: fenceMark[1] || "python", lines: [] };
      continue;
    }
    const last = blocks.at(-1);
    const heading = /^\s*(#{1,6})\s+(.*)$/.exec(line);
    const item = /^\s*([-*•+]|\d+[.)])\s+(.*)$/.exec(line);
    if (!line.trim()) {
      blocks.push({ kind: "paragraph", lines: [] });
    } else if (/^\s*(-{2,}|\*{3,}|_{3,})\s*$/.test(line)) {
      blocks.push({ kind: "rule" });
    } else if (heading) {
      blocks.push({ kind: "heading", level: heading[1].length, text: inline(heading[2]) });
    } else if (item) {
      const ordered = /\d/.test(item[1]);
      if (last?.kind === "list" && last.ordered === ordered) last.items.push(inline(item[2]));
      else blocks.push({ kind: "list", ordered, items: [inline(item[2])] });
    } else if (last?.kind === "paragraph") {
      last.lines.push(inline(line.trim()));
    } else {
      blocks.push({ kind: "paragraph", lines: [inline(line.trim())] });
    }
  }
  if (fence) blocks.push({ kind: "code", language: fence.language, text: fence.lines.join("\n") });
  return blocks.filter((block) => block.kind !== "paragraph" || block.lines.length > 0);
}
