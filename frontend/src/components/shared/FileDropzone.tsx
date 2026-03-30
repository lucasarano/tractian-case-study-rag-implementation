import { useCallback, useState } from "react";
import { Upload, FileCheck } from "lucide-react";

interface Props {
  accept?: string;
  onFile: (file: File) => void;
}

export function FileDropzone({ accept = ".pdf", onFile }: Props) {
  const [dragging, setDragging] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) {
        setFileName(file.name);
        onFile(file);
      }
    },
    [onFile],
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        setFileName(file.name);
        onFile(file);
      }
    },
    [onFile],
  );

  return (
    <label
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      className={`flex cursor-pointer flex-col items-center gap-3 rounded-2xl border-2 border-dashed p-10 transition-all duration-200 ${
        dragging
          ? "border-accent-blue bg-accent-blue/5 scale-[1.01]"
          : fileName
            ? "border-accent-green/40 bg-accent-green/5"
            : "border-border hover:border-border-bright hover:bg-bg-secondary"
      }`}
    >
      {fileName ? (
        <>
          <FileCheck className="h-8 w-8 text-accent-green" />
          <p className="font-mono text-sm font-medium text-accent-green">{fileName}</p>
        </>
      ) : (
        <>
          <Upload className="h-8 w-8 text-text-muted" />
          <p className="text-sm text-text-secondary">
            Drop a <span className="font-semibold text-text-primary">{accept}</span> file or click
            to browse
          </p>
        </>
      )}
      <input type="file" accept={accept} onChange={handleChange} className="hidden" />
    </label>
  );
}
