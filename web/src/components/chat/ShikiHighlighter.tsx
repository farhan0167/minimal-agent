import { type FC, useEffect, useState } from "react";
import { type Highlighter, createHighlighter } from "shiki";
import type { SyntaxHighlighterProps } from "@assistant-ui/react-markdown";
import { THEMES } from "../../themes";
import { useThemeTokens } from "../../hooks/use-theme-tokens";

let highlighterPromise: Promise<Highlighter> | null = null;

// Every registered theme's Shiki companions, loaded up front.
//
// The highlighter is a singleton created once with a fixed theme list, so it
// cannot be handed a new theme later without rebuilding it — and rebuilding on
// every switch would re-download the grammars. Registering the union instead
// keeps switching instant, and costs only the themes a theme actually names.
const SHIKI_THEMES = [
  ...new Set(
    Object.values(THEMES).flatMap((t) => [t.shiki.light, t.shiki.dark]),
  ),
];

function getHighlighter() {
  if (!highlighterPromise) {
    highlighterPromise = createHighlighter({
      themes: SHIKI_THEMES,
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

export const ShikiSyntaxHighlighter: FC<SyntaxHighlighterProps> = ({
  language,
  code,
  components: { Code },
}) => {
  const [html, setHtml] = useState<string | null>(null);
  const { theme } = useThemeTokens();

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

      // Both modes are compiled into CSS variables (defaultColor: false), and
      // the .dark .shiki rules in index.css pick between them — so this does
      // not re-run on mode change, only when the theme names different
      // companions.
      const result = hl.codeToHtml(code, {
        lang,
        themes: { light: theme.shiki.light, dark: theme.shiki.dark },
        defaultColor: false,
      });
      setHtml(result);
    });

    return () => {
      cancelled = true;
    };
  }, [language, code, theme]);

  if (html) {
    return <div className="shiki-wrapper" dangerouslySetInnerHTML={{ __html: html }} />;
  }

  return <Code>{code}</Code>;
};
