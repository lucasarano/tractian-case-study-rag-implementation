interface Props {
  data: unknown;
  maxHeight?: string;
}

export function JsonViewer({ data, maxHeight = "24rem" }: Props) {
  return (
    <pre
      className="overflow-auto rounded-xl border border-border bg-bg-secondary p-4 font-mono text-xs leading-relaxed text-text-secondary"
      style={{ maxHeight }}
    >
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}
