import { Emotions as E, NowPlaying } from '../lib/api'

const ICON: Record<string, string> = { happy: '😄', welcome: '👋', curious: '🤔', 'yes/no': '🙆', dance: '💃', sad: '😢', angry: '😠', sleep: '😴', other: '✨' }

export function EmotionGrid({ emotions, playing, can, onPlay }: { emotions: E | null; playing: NowPlaying; can: boolean; onPlay: (n: string) => void }) {
  if (!emotions) return <div className="muted">loading moves…</div>
  return (
    <div className="emotions">
      {emotions.groups.map((g) => (
        <div key={g.family} className="fam">
          <div className="fam-title">{ICON[g.family] ?? '✨'} {g.family} <span className="muted">{g.moves.length}</span></div>
          <div className="chips">
            {g.moves.map((m) => (
              <button key={m} className={`chip ${playing?.name === m ? 'playing' : ''}`} disabled={!can} onClick={() => onPlay(m)} title={m}>
                {m.replace(/(\d+)$/, ' $1')}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
