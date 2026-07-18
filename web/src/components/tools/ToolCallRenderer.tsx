import {
  ToolCallCard,
  ArgsSection,
  ResultSection,
  type ToolStatus,
} from "./ToolCallCard";

export type { ToolStatus };

const DATA_URI_IMAGE =
  /data:image\/(?:png|jpe?g|gif|webp|svg\+xml);base64,[A-Za-z0-9+/=]+/g;

/**
 * Pull data-URI images out of a result string so they render as inline
 * previews instead of base64 walls of text.
 */
function extractImages(result: unknown): { display: unknown; images: string[] } {
  if (typeof result !== "string") return { display: result, images: [] };
  const images = result.match(DATA_URI_IMAGE) ?? [];
  if (images.length === 0) return { display: result, images: [] };
  return { display: result.replace(DATA_URI_IMAGE, "[image]"), images };
}

interface ToolCallRendererProps {
  name: string;
  args: Record<string, unknown>;
  result: unknown;
  status: ToolStatus;
}

/**
 * Generic fallback renderer for tools without a dedicated entry in
 * registry.ts: pretty-printed args plus the raw result, with any embedded
 * data-URI images shown as previews.
 */
export function ToolCallRenderer({
  name,
  args,
  result,
  status,
}: ToolCallRendererProps) {
  const { display, images } = extractImages(result);

  return (
    <ToolCallCard name={name} status={status}>
      <ArgsSection args={args} />
      <ResultSection result={display} status={status} />
      {images.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {images.map((src, i) => (
            <img
              key={i}
              src={src}
              alt={`tool result ${i + 1}`}
              loading="lazy"
              className="max-w-full max-h-64 rounded-ctl border border-app-border"
            />
          ))}
        </div>
      )}
    </ToolCallCard>
  );
}
