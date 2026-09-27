/* Minimal YAML colouring: keys indigo, list dashes coral, values white. `stagger` lands the
   lines one after another, the way the compiler emits them. */
export default function YamlBlock({ code, stagger = false, className = '' }) {
  return (
    <pre className={`w-full overflow-x-auto font-mono text-[11.5px] leading-[1.7] text-white/85 ${className}`}>
      {code.split('\n').map((line, i) => {
        const [, indent = '', dash = '', key = '', rest = ''] =
          /^(\s*)(- )?((?:"[^"]*"|[^:\s]+)\s*:)?\s*(.*)$/.exec(line) ?? []
        return (
          <div key={i} className={stagger ? 'animate-rise' : ''} style={stagger ? { animationDelay: `${i * 45}ms` } : undefined}>
            {indent}
            {dash && <span className="text-coral-300">{dash}</span>}
            {key && <span className="text-arc-300">{key}</span>}
            {rest && <span className="text-white"> {rest}</span>}
          </div>
        )
      })}
    </pre>
  )
}
