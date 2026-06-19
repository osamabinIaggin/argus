import { CopyButton } from '../ui/CopyButton'

interface JsonViewerProps {
  data: unknown
}

function highlight(json: string): string {
  return json
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(
      /("[\w_]+")\s*:/g,
      '<span style="color:#3B7DD8">$1</span>:'
    )
    .replace(
      /: ("(?:[^"\\]|\\.)*")/g,
      ': <span style="color:#2D9E6B">$1</span>'
    )
    .replace(
      /: (true|false|null)/g,
      ': <span style="color:#DA7756">$1</span>'
    )
    .replace(
      /: (-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g,
      ': <span style="color:#D4901F">$1</span>'
    )
}

export function JsonViewer({ data }: JsonViewerProps) {
  const jsonStr = JSON.stringify(data, null, 2)
  const lines = jsonStr.split('\n')

  return (
    <div className="relative bg-surface-2 rounded-xl border border-divider overflow-hidden">
      <div className="absolute top-3 right-3 z-10">
        <CopyButton text={jsonStr} />
      </div>
      <pre className="overflow-auto max-h-[70vh] p-5 pr-10 text-xs font-mono leading-relaxed">
        {lines.map((line, i) => (
          <div key={i} className="flex">
            <span className="text-text-3 select-none w-10 shrink-0 text-right mr-4 border-r border-divider pr-3">
              {i + 1}
            </span>
            <span
              className="whitespace-pre"
              dangerouslySetInnerHTML={{ __html: highlight(line) }}
            />
          </div>
        ))}
      </pre>
    </div>
  )
}
