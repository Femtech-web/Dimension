export function Code({ title, lang, children, terminal }: { title?: string; lang?: string; children: string; terminal?: boolean }) {
  return (
    <div className={`code${terminal ? " terminal" : ""}`}>
      {(title || lang) && (
        <div className="code-head">
          <span>{title}</span>
          <span>{lang}</span>
        </div>
      )}
      <pre>
        <code>{children}</code>
      </pre>
    </div>
  );
}
