import { Inbox } from 'lucide-react';

export function EmptyState({ label = '暂无数据' }: { label?: string }) {
  return (
    <div className="empty-state">
      <Inbox size={22} />
      <span>{label}</span>
    </div>
  );
}
