import { postureTheme, type Posture } from '../theme'

type PostureChipProps = {
  posture: Posture
}

export function PostureChip({ posture }: PostureChipProps) {
  const theme = postureTheme[posture]

  return (
    <span
      className="inline-flex items-center rounded-full px-2.5 py-1 text-sm font-semibold"
      style={{ backgroundColor: `${theme.color}1f`, color: theme.color }}
    >
      {theme.label}
    </span>
  )
}
