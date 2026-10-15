import hljs from "highlight.js/lib/core";
import bash from "highlight.js/lib/languages/bash";
import json from "highlight.js/lib/languages/json";
import python from "highlight.js/lib/languages/python";

// Only the languages Monty's scripts, tool arguments, and replies use, to keep the bundle small.
hljs.registerLanguage("python", python);
hljs.registerLanguage("json", json);
hljs.registerLanguage("bash", bash);

const ALIASES: Record<string, string> = { py: "python", sh: "bash", shell: "bash" };

/** Highlighted HTML for `code`. highlight.js escapes the source, so the result is safe to
 *  insert; a language it doesn't know comes back escaped and uncolored. */
export function highlight(code: string, language = "python"): string {
  const lang = ALIASES[language] ?? language;
  if (hljs.getLanguage(lang)) return hljs.highlight(code, { language: lang, ignoreIllegals: true }).value;
  return hljs.highlight(code, { language: "plaintext", ignoreIllegals: true }).value;
}
