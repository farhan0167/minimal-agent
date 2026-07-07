import { type FC, useEffect, useState } from "react";
import { type Highlighter, createHighlighter } from "shiki";

interface ShikiHighlighterProps {
  language: string;
  code: string;
  components: {
    Pre: FC<React.ComponentPropsWithoutRef<"pre">>;
    Code: FC<React.ComponentPropsWithoutRef<"code">>;
  };
}

let highlighterPromise: Promise<Highlighter> | null = null;

function getHighlighter() {
  if (!highlighterPromise) {
    highlighterPromise = createHighlighter({
      themes: ["github-light", "github-dark"],
      langs: [
        "javascript",
        "typescript",
        "python",
        "bash",
        "json",
        "html",
        "css",
        "markdown",
        "yaml",
        "sql",
        "go",
        "rust",
        "java",
        "c",
        "cpp",
        "shell",
        "jsx",
        "tsx",
      ],
    });
  }
  return highlighterPromise;
}

export const ShikiSyntaxHighlighter: FC<ShikiHighlighterProps> = ({
  language,
  code,
  components: { Code },
}) => {
  const [html, setHtml] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    getHighlighter().then(async (hl) => {
      if (cancelled) return;

      const loadedLangs = hl.getLoadedLanguages();
      let lang = language.toLowerCase();
      if (!loadedLangs.includes(lang)) {
        try {
          await hl.loadLanguage(lang as Parameters<typeof hl.loadLanguage>[0]);
        } catch {
          lang = "text";
        }
      }

      if (cancelled) return;

      const result = hl.codeToHtml(code, {
        lang,
        themes: { light: "github-light", dark: "github-dark" },
        defaultColor: false,
      });
      setHtml(result);
    });

    return () => {
      cancelled = true;
    };
  }, [language, code]);

  if (html) {
    return <div className="shiki-wrapper" dangerouslySetInnerHTML={{ __html: html }} />;
  }

  return <Code>{code}</Code>;
};
