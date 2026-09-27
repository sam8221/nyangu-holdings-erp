import { colors } from '../theme'
import { formatMoney } from '../utils/format'

/** A small, dependency-free bar chart. `data` is [{ label, value }]. */
export default function MiniBarChart({ data, height = 160, currency = 'ZMW' }) {
  const max = Math.max(1, ...data.map((d) => Number(d.value) || 0))
  const barWidth = 100 / Math.max(data.length, 1)
  return (
    <div>
      <svg
        viewBox={`0 0 100 ${height}`}
        preserveAspectRatio="none"
        width="100%"
        height={height}
        role="img"
        aria-label="Monthly net sales"
      >
        {data.map((d, i) => {
          const value = Number(d.value) || 0
          const barHeight = (value / max) * (height - 8)
          return (
            <rect
              key={d.label}
              x={i * barWidth + barWidth * 0.18}
              y={height - barHeight}
              width={barWidth * 0.64}
              height={Math.max(barHeight, value > 0 ? 2 : 0)}
              rx={1.5}
              fill={i === data.length - 1 ? colors.primary : '#90caf9'}
            >
              <title>{`${d.label}: ${formatMoney(d.value, currency)}`}</title>
            </rect>
          )
        })}
      </svg>
      <div style={{ display: 'flex' }}>
        {data.map((d) => (
          <div
            key={d.label}
            style={{ flex: 1, textAlign: 'center', fontSize: 12, color: colors.muted }}
          >
            {d.label}
          </div>
        ))}
      </div>
    </div>
  )
}
