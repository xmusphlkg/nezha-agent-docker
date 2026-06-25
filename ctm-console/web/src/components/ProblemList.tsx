import type { Problem } from '../types';
import { age } from '../lib/format';

export function ProblemList({ problems, limit }: { problems: Problem[]; limit?: number }) {
  const visible = typeof limit === 'number' ? problems.slice(0, limit) : problems;
  return (
    <div className="problem-list">
      {visible.map((problem) => (
        <article key={`${problem.source}-${problem.eventId}-${problem.name}`} className={`problem ${problem.severity}`}>
          <div className="problem-main">
            <strong>{problem.name}</strong>
            <span>{problem.host || problem.source}</span>
          </div>
          <div className="problem-meta">
            <span>{problem.source}</span>
            <span>{problem.severity}</span>
            <span>{age(problem.ageSec)}</span>
            <span>{problem.acknowledged ? 'ack' : 'open'}</span>
          </div>
        </article>
      ))}
    </div>
  );
}
